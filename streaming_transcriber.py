#!/usr/bin/env python3

import sys
import requests
import struct
import math
import os
import time
from datetime import datetime
from typing import Iterator, Optional
from collections import deque

class StreamingTranscriber:
    def __init__(self, server_url: str, silence_threshold: float = 0.05, 
                 silence_duration: float = 1.0, sample_rate: int = 16000,
                 has_wav_header: bool = True, debug_audio: bool = False,
                 pre_buffer_duration: float = 0.3, language: str = 'en',
                 initial_prompt: Optional[str] = None, temperature: float = 0.0,
                 chunk_duration: float = 0.03, show_levels: bool = False):
        self.server_url = server_url
        self.silence_threshold = silence_threshold
        self.silence_duration = silence_duration
        self.sample_rate = sample_rate
        self.has_wav_header = has_wav_header
        self.debug_audio = debug_audio
        self.pre_buffer_duration = pre_buffer_duration
        self.language = language
        self.initial_prompt = initial_prompt
        self.temperature = temperature
        self.chunk_duration = chunk_duration
        self.show_levels = show_levels
        self.chunk_size = int(sample_rate * chunk_duration)  # Configurable chunk size
        self.chunks_per_second = int(1.0 / chunk_duration)
        self.debug_counter = 0
        self.level_counter = 0  # For level display throttling
        self.last_chunk_time = None  # For latency debugging
        self.start_time = time.time()
        # Pre-buffer to capture audio before voice detection
        self.pre_buffer_size = int(pre_buffer_duration / chunk_duration)  # Number of chunks to keep
        self.pre_buffer = deque(maxlen=self.pre_buffer_size)
        
    def calculate_rms(self, audio_chunk: bytes) -> float:
        """Calculate RMS (root mean square) of audio chunk for silence detection"""
        if len(audio_chunk) < 2:
            return 0.0
            
        # Convert bytes to 16-bit integers
        samples = struct.unpack(f'<{len(audio_chunk)//2}h', audio_chunk)
        
        # Calculate RMS
        if not samples:
            return 0.0
            
        mean_square = sum(sample * sample for sample in samples) / len(samples)
        return math.sqrt(mean_square) / 32768.0  # Normalize to 0-1 range
    
    def detect_silence(self, audio_chunks: list) -> bool:
        """Check if recent audio chunks indicate silence"""
        required_chunks = int(self.silence_duration * self.chunks_per_second)
        if len(audio_chunks) < required_chunks:
            return False
            
        # Check last N chunks for silence
        recent_chunks = audio_chunks[-required_chunks:]
        
        # Count how many chunks are below threshold
        silent_chunks = 0
        for chunk in recent_chunks:
            rms = self.calculate_rms(chunk)
            if rms <= self.silence_threshold:
                silent_chunks += 1
        
        # Require 85% of chunks to be silent (allows for brief noise)
        silence_ratio = silent_chunks / len(recent_chunks)
        return silence_ratio >= 0.85
    
    def read_wav_header(self, stream) -> dict:
        """Read WAV header from stream"""
        header = stream.read(44)  # Standard WAV header is 44 bytes
        if len(header) < 44:
            raise ValueError("Invalid WAV header")
            
        # Parse basic WAV info (simplified)
        return {
            'sample_rate': struct.unpack('<I', header[24:28])[0],
            'channels': struct.unpack('<H', header[22:24])[0],
            'bits_per_sample': struct.unpack('<H', header[34:36])[0]
        }
    
    def stream_audio_chunks(self, stream) -> Iterator[bytes]:
        """Stream audio in chunks, yielding when we have enough data"""
        buffer = b''
        
        # Handle WAV header if present
        if self.has_wav_header:
            try:
                wav_info = self.read_wav_header(stream)
                print(f"📊 Audio format: {wav_info['sample_rate']}Hz, {wav_info['channels']} channels, {wav_info['bits_per_sample']} bits", file=sys.stderr)
            except ValueError:
                print("⚠ Warning: Could not parse WAV header, proceeding anyway", file=sys.stderr)
        else:
            print(f"📊 Expecting raw PCM audio: {self.sample_rate}Hz, mono, 16-bit", file=sys.stderr)
        
        # Read smaller amounts for lower latency
        read_size = max(1024, self.chunk_size * 2)  # At least 1KB but preferably one chunk
        
        while True:
            chunk = stream.read(read_size)
            if not chunk:
                break
                
            buffer += chunk
            
            # Yield complete audio chunks more frequently
            while len(buffer) >= self.chunk_size * 2:  # 2 bytes per sample (16-bit)
                yield buffer[:self.chunk_size * 2]
                buffer = buffer[self.chunk_size * 2:]
        
        # Yield any remaining buffer
        if buffer:
            yield buffer
    
    def create_multipart_stream(self, audio_chunks: list) -> tuple[bytes, str]:
        """Create multipart form data from audio chunks with parameters"""
        boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
        
        # Combine all audio chunks first
        raw_audio = b''.join(audio_chunks)
        
        # Create WAV file with proper header
        total_samples = len(raw_audio) // 2  # 16-bit samples
        wav_header = self.create_wav_header(total_samples)
        audio_data = wav_header + raw_audio
        
        # Build multipart form with parameters
        form_parts = []
        
        # Add audio file
        form_parts.append(
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="audio.wav"\r\n'
            f"Content-Type: audio/wav\r\n\r\n"
        )
        
        form_data = form_parts[0].encode() + audio_data
        
        # Add language parameter
        form_data += f"\r\n--{boundary}\r\n".encode()
        form_data += f'Content-Disposition: form-data; name="language"\r\n\r\n{self.language}'.encode()
        
        # Add temperature parameter
        form_data += f"\r\n--{boundary}\r\n".encode()
        form_data += f'Content-Disposition: form-data; name="temperature"\r\n\r\n{self.temperature}'.encode()
        
        # Add initial prompt if provided
        if self.initial_prompt:
            form_data += f"\r\n--{boundary}\r\n".encode()
            form_data += f'Content-Disposition: form-data; name="initial_prompt"\r\n\r\n{self.initial_prompt}'.encode()
        
        # Close boundary
        form_data += f"\r\n--{boundary}--\r\n".encode()
        
        return form_data, boundary
    
    def create_wav_header(self, num_samples: int) -> bytes:
        """Create a WAV header for the given number of samples"""
        data_size = num_samples * 2  # 2 bytes per sample
        file_size = data_size + 36
        
        header = struct.pack('<4sI4s4sIHHIIHH4sI',
            b'RIFF', file_size, b'WAVE', b'fmt ', 16,
            1, 1, self.sample_rate, self.sample_rate * 2, 2, 16,
            b'data', data_size
        )
        return header
    
    def save_debug_audio(self, audio_data: bytes, chunk_count: int) -> str:
        """Save audio to a debug file and return the filename"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        debug_dir = "audio_debug"
        
        # Create debug directory if it doesn't exist
        if not os.path.exists(debug_dir):
            os.makedirs(debug_dir)
        
        # Save the audio file
        filename = f"{debug_dir}/audio_{timestamp}_{self.debug_counter:03d}_{chunk_count}chunks.wav"
        with open(filename, 'wb') as f:
            f.write(audio_data)
        
        self.debug_counter += 1
        return filename
    
    def clean_transcription(self, text: str) -> str:
        """Clean up common Whisper transcription artifacts"""
        import re
        
        # Remove leading punctuation patterns like ">> " or "- "
        text = re.sub(r'^[>\-•·※◆◇■□▪▫★☆♦♣♠♥]+\s*', '', text)
        
        # Remove bracketed annotations like [BLANK_AUDIO] or (inaudible)
        text = re.sub(r'\[.*?\]|\(.*?\)', '', text)
        
        # Remove multiple spaces
        text = re.sub(r'\s+', ' ', text)
        
        # Strip again after cleaning
        text = text.strip()
        
        # Don't return very short fragments that are likely errors
        if len(text) < 2 and text not in ['I', 'a', 'A']:
            return ''
        
        return text
    
    def transcribe_audio(self, audio_chunks: list) -> Optional[str]:
        """Send audio chunks to whisper server for transcription"""
        if not audio_chunks:
            return None
            
        try:
            form_data, boundary = self.create_multipart_stream(audio_chunks)
            
            # Debug: Save the exact audio being sent
            if self.debug_audio:
                # Extract just the audio data from the multipart form
                # Find the audio data portion (after headers, before boundary)
                form_str = form_data.decode('latin-1', errors='ignore')
                audio_start = form_str.find('\r\n\r\n') + 4
                audio_end = form_data.rfind(b'\r\n--')
                audio_data = form_data[audio_start:audio_end]
                
                debug_file = self.save_debug_audio(audio_data, len(audio_chunks))
                print(f"🔍 Debug: Saved audio to {debug_file}", file=sys.stderr)
                print(f"   - Chunks: {len(audio_chunks)}", file=sys.stderr)
                print(f"   - Raw audio size: {sum(len(c) for c in audio_chunks)} bytes", file=sys.stderr)
                print(f"   - WAV file size: {len(audio_data)} bytes", file=sys.stderr)
                print(f"   - Duration: ~{len(audio_chunks) * 0.1:.1f}s", file=sys.stderr)
            
            headers = {
                'Content-Type': f'multipart/form-data; boundary={boundary}'
            }
            
            print(f"🚀 Sending {len(audio_chunks)} chunks ({len(form_data)} bytes) to server...", file=sys.stderr)
            
            response = requests.post(
                f"{self.server_url}/inference",
                data=form_data,
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                text = result.get('text', '').strip()
                
                # Clean up common Whisper artifacts
                if text:
                    # Remove leading >> or similar markers
                    text = self.clean_transcription(text)
                
                return text if text else None
            else:
                print(f"❌ Server error: {response.status_code} - {response.text}", file=sys.stderr)
                return None
                
        except Exception as e:
            print(f"❌ Transcription error: {e}", file=sys.stderr)
            return None
    
    def run(self):
        """Main processing loop"""
        print("🎤 Streaming transcriber started. Reading audio from stdin...", file=sys.stderr)
        print(f"📡 Server: {self.server_url}", file=sys.stderr)
        print(f"🔇 Silence threshold: {self.silence_threshold:.3f}, duration: {self.silence_duration}s", file=sys.stderr)
        print(f"⏰ Pre-buffer: {self.pre_buffer_duration}s ({self.pre_buffer_size} chunks @ {self.chunk_duration*1000:.0f}ms each)", file=sys.stderr)
        print(f"🌍 Language: {self.language}, Temperature: {self.temperature}", file=sys.stderr)
        if self.initial_prompt:
            print(f"📝 Prompt: {self.initial_prompt[:50]}...", file=sys.stderr)
        
        audio_chunks = []
        recording = False
        
        try:
            for chunk in self.stream_audio_chunks(sys.stdin.buffer):
                current_time = time.time()
                rms = self.calculate_rms(chunk)
                
                # Calculate chunk timing for display and warnings (debug mode only)
                chunk_interval = 0
                if self.last_chunk_time is not None:
                    chunk_interval = current_time - self.last_chunk_time
                    # Only warn every 100 chunks to avoid spam, and only in debug mode
                    if self.debug_audio and chunk_interval > self.chunk_duration * 10 and self.level_counter % 100 == 0:
                        delay_ms = chunk_interval * 1000
                        expected_ms = self.chunk_duration * 1000
                        print(f"\n⚠ Persistent chunk delays averaging {delay_ms:.0f}ms (expected {expected_ms:.0f}ms)\n", file=sys.stderr)
                
                self.last_chunk_time = current_time
                
                # Show real-time levels for debugging (in-place)
                if self.show_levels:
                    self.level_counter += 1
                    if self.level_counter % 10 == 0:  # Show every 10th chunk to reduce spam
                        elapsed = current_time - self.start_time
                        level_bar = '█' * int(rms * 30) + '░' * (30 - int(rms * 30))
                        threshold_pos = int(self.silence_threshold * 30)
                        level_indicator = level_bar[:threshold_pos] + '|' + level_bar[threshold_pos+1:] if threshold_pos < 30 else level_bar + '|'
                        # Show delay in status if significant and in debug mode
                        if self.debug_audio:
                            delay_ms = chunk_interval * 1000
                            expected_ms = self.chunk_duration * 1000
                            if delay_ms > expected_ms * 2 and self.level_counter > 10:
                                delay_indicator = f" delay:{delay_ms:.0f}ms"
                            else:
                                delay_indicator = ""
                        else:
                            delay_indicator = ""
                        # Clear previous line and print new status
                        print(f"\033[2K\r🎚️  {level_indicator} {rms:.4f} [{elapsed:6.1f}s]{delay_indicator}", end='', file=sys.stderr, flush=True)
                
                # Start recording on voice activity
                if not recording and rms > self.silence_threshold:
                    detection_time = time.time() - self.start_time
                    # Clear the level display line and print voice detection
                    print(f"\r🔊 Voice detected at {detection_time:.2f}s (RMS: {rms:.4f})" + " " * 20, file=sys.stderr)
                    recording = True
                    # Start with pre-buffer contents to capture speech onset
                    # Note: current chunk is NOT in pre-buffer yet
                    audio_chunks = list(self.pre_buffer)
                    audio_chunks.append(chunk)  # Add the triggering chunk
                    if self.debug_audio:
                        print(f"   Including {len(self.pre_buffer)} pre-buffer chunks + current chunk", file=sys.stderr)
                elif not recording:
                    # Only add to pre-buffer if we're not starting to record
                    self.pre_buffer.append(chunk)
                elif recording:
                    audio_chunks.append(chunk)
                    
                    # Check for silence (with minimum recording time)
                    min_recording_chunks = int(0.3 / self.chunk_duration)  # At least 0.3 seconds
                    if len(audio_chunks) > min_recording_chunks and self.detect_silence(audio_chunks):
                        duration = len(audio_chunks) * self.chunk_duration
                        # Clear level display and show processing message
                        print(f"\r🔇 Silence detected, processing {len(audio_chunks)} chunks (~{duration:.1f}s)..." + " " * 10, file=sys.stderr)
                        
                        # Remove trailing silence chunks before transcription (but keep some for natural endings)
                        silence_chunks_to_remove = max(1, int(self.silence_duration * 10) // 3)
                        original_chunk_count = len(audio_chunks)
                        if len(audio_chunks) > silence_chunks_to_remove + self.pre_buffer_size:
                            audio_chunks = audio_chunks[:-silence_chunks_to_remove]
                        
                        if self.debug_audio and original_chunk_count != len(audio_chunks):
                            print(f"   Trimmed {original_chunk_count - len(audio_chunks)} silence chunks ({original_chunk_count} -> {len(audio_chunks)})", file=sys.stderr)
                        
                        # Transcribe the recorded audio
                        text = self.transcribe_audio(audio_chunks)
                        
                        if text:
                            # Output transcription to stdout (for piping)
                            print(text, flush=True)
                            # Show confirmation on stderr
                            print(f"✓ Transcribed: '{text}'", file=sys.stderr)
                        else:
                            print("⚠ No text transcribed", file=sys.stderr)
                        
                        # Reset for next recording
                        recording = False
                        audio_chunks = []
                        # Clear pre-buffer to avoid duplicate audio
                        self.pre_buffer.clear()
                        
        except KeyboardInterrupt:
            print("\n👋 Stopping transcriber...", file=sys.stderr)
        except Exception as e:
            print(f"❌ Error: {e}", file=sys.stderr)

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Stream audio transcription')
    parser.add_argument('--server', default='http://localhost:8080', 
                       help='Whisper server URL')
    parser.add_argument('--silence-threshold', type=float, default=0.02,
                       help='Silence threshold (0.0-1.0, default: 0.02)')
    parser.add_argument('--silence-duration', type=float, default=1.5,
                       help='Silence duration in seconds (default: 1.5)')
    parser.add_argument('--sample-rate', type=int, default=16000,
                       help='Audio sample rate')
    parser.add_argument('--raw-pcm', action='store_true',
                       help='Input is raw PCM without WAV header')
    parser.add_argument('--debug-audio', action='store_true',
                       help='Save audio files for debugging (creates audio_debug/ directory)')
    parser.add_argument('--pre-buffer', type=float, default=0.3,
                       help='Pre-buffer duration in seconds to capture before voice detection (default: 0.3)')
    parser.add_argument('--chunk-duration', type=float, default=0.03,
                       help='Audio chunk duration in seconds (default: 0.03 = 30ms, lower = faster response)')
    parser.add_argument('--show-levels', action='store_true',
                       help='Show real-time audio levels for debugging voice detection')
    parser.add_argument('--language', default='en',
                       help='Language code for transcription (default: en)')
    parser.add_argument('--initial-prompt', default=None,
                       help='Initial prompt to help Whisper understand context')
    parser.add_argument('--temperature', type=float, default=0.0,
                       help='Temperature for transcription (0.0 = deterministic, default: 0.0)')
    
    args = parser.parse_args()
    
    transcriber = StreamingTranscriber(
        server_url=args.server,
        silence_threshold=args.silence_threshold,
        silence_duration=args.silence_duration,
        sample_rate=args.sample_rate,
        has_wav_header=not args.raw_pcm,
        debug_audio=args.debug_audio,
        pre_buffer_duration=args.pre_buffer,
        language=args.language,
        initial_prompt=args.initial_prompt,
        temperature=args.temperature,
        chunk_duration=args.chunk_duration,
        show_levels=args.show_levels
    )
    
    if args.debug_audio:
        print("🔍 Debug mode enabled - audio will be saved to audio_debug/", file=sys.stderr)
    
    transcriber.run()

if __name__ == '__main__':
    main()
