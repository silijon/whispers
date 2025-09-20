#!/usr/bin/env python3
"""
Low-latency audio capture script using sounddevice
Equivalent to pw-record but in Python for better integration
"""

import sys
import argparse
import sounddevice as sd
import numpy as np
import time
from typing import Optional, List, Dict, Any

class AudioCapture:
    def __init__(self, sample_rate: int = 16000, channels: int = 1, 
                 device: Optional[int] = None, gain_db: float = 26.0,
                 block_size: Optional[int] = None):
        self.sample_rate = sample_rate
        self.channels = channels  
        self.device = device
        self.gain_linear = 10 ** (gain_db / 20.0)  # Convert dB to linear
        self.block_size = block_size or int(sample_rate * 0.03)  # 30ms blocks for low latency
        self.running = False

    def list_audio_devices(self) -> List[Dict[str, Any]]:
        """List available audio input devices"""
        devices = []
        device_list = sd.query_devices()
        
        print("Available audio input devices:")
        print("-" * 30)
        
        for i, device_info in enumerate(device_list):
            # Type cast to access as dictionary
            device_dict = dict(device_info)  # type: ignore
            if device_dict['max_input_channels'] > 0:  # Only input devices
                hostapi_dict = dict(sd.query_hostapis(device_dict['hostapi']))  # type: ignore
                devices.append({
                    'index': i,
                    'name': str(device_dict['name']),
                    'channels': int(device_dict['max_input_channels']),
                    'default_samplerate': float(device_dict['default_samplerate']),
                    'hostapi': str(hostapi_dict['name'])
                })
                
                # Mark default device
                default_marker = " (default)" if i == sd.default.device[0] else ""
                print(f"  [{i}] {device_dict['name']}{default_marker}")
                print(f"       {device_dict['max_input_channels']} channels, "
                      f"{device_dict['default_samplerate']:.0f}Hz, "
                      f"{hostapi_dict['name']}")
        

        print()
        return devices
    
    def get_audio_device(self, device_arg: Optional[str] = None) -> int:
        """Get audio device index, with interactive selection if needed"""
        if device_arg is not None:
            # If numeric, use directly
            if device_arg.isdigit():
                device_index = int(device_arg)
                # Validate device exists and has input
                try:
                    device_info = sd.query_devices(device_index)
                    device_dict = dict(device_info)  # type: ignore
                    if device_dict['max_input_channels'] == 0:
                        raise ValueError(f"Device {device_index} has no input channels")
                    return device_index
                except (ValueError, sd.PortAudioError):
                    print(f"Error: Invalid device index: {device_index}")
                    sys.exit(1)
            else:
                print("Error: Device must be a numeric index")
                sys.exit(1)
        
        # Interactive selection
        devices = self.list_audio_devices()
        
        if not devices:
            print("No input devices found!")
            sys.exit(1)
        
        # Try to find active monitor source
        default_device = sd.default.device[0] if sd.default.device[0] is not None else devices[0]['index']
        
        # Fall back to system default if no monitor found
        if default_device is None:
            default_device = sd.default.device[0] if sd.default.device[0] is not None else devices[0]['index']
        
        print(f"Enter device number (or press Enter for default [{default_device}]):")
        try:
            choice = input().strip()
            
            if not choice:
                return default_device
            elif choice.isdigit():
                device_index = int(choice)
                # Validate selection
                if any(d['index'] == device_index for d in devices):
                    return device_index
                else:
                    print(f"Error: Invalid device selection: {device_index}")
                    sys.exit(1)
            else:
                print("Error: Invalid input. Please enter a number.")
                sys.exit(1)
        except (EOFError, KeyboardInterrupt):
            print("\nCancelled")
            sys.exit(1)
    
    def audio_callback(self, indata: np.ndarray, frames: int, time_info, status):  # type: ignore
        """Callback function for audio stream"""
        if status:
            print(f"Audio status: {status}", file=sys.stderr)
        
        # Apply gain
        audio_data = indata * self.gain_linear
        
        # Clip to prevent overflow
        audio_data = np.clip(audio_data, -1.0, 1.0)
        
        # Convert to 16-bit integers
        audio_int16 = (audio_data * 32767).astype(np.int16)
        
        # Convert to bytes and write to stdout
        audio_bytes = audio_int16.tobytes()
        sys.stdout.buffer.write(audio_bytes)
        sys.stdout.buffer.flush()
    
    def run(self):
        """Start audio capture and stream to stdout"""
        print(f"🎤 Starting audio capture", file=sys.stderr)
        device_dict = dict(sd.query_devices(self.device))  # type: ignore
        print(f"Device: {self.device} ({device_dict['name']})", file=sys.stderr)
        print(f"Format: {self.sample_rate}Hz, {self.channels} channel(s), 16-bit", file=sys.stderr)  
        print(f"Gain: {20 * np.log10(self.gain_linear):.1f}dB", file=sys.stderr)
        print(f"Block size: {self.block_size} samples ({self.block_size/self.sample_rate*1000:.1f}ms)", file=sys.stderr)
        print("Press Ctrl+C to stop", file=sys.stderr)
        print("", file=sys.stderr)
        
        self.running = True
        
        try:
            # Set low latency parameters  
            sd.default.latency = ('low', 'low')  # type: ignore
            
            with sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                device=self.device,
                callback=self.audio_callback,
                blocksize=self.block_size,
                dtype=np.float32
            ) as stream:  # type: ignore
                print(f"✓ Audio stream active", file=sys.stderr)
                
                # Keep the stream open
                while self.running:
                    time.sleep(0.1)
                    
        except KeyboardInterrupt:
            print("\n🛑 Stopping audio capture...", file=sys.stderr)
            self.running = False
        except Exception as e:
            print(f"❌ Audio capture error: {e}", file=sys.stderr)
            sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description='Low-latency audio capture to stdout')
    
    # Device selection
    parser.add_argument('--device', '-d', type=str,
                       help='Audio device index (interactive if not specified)')
    parser.add_argument('--list', '-l', action='store_true',
                       help='List available audio devices and exit')
    
    # Audio parameters
    parser.add_argument('--sample-rate', '-r', type=int, default=44100,
                       help='Sample rate in Hz (default: 44100)')
    parser.add_argument('--channels', '-c', type=int, default=1,
                       help='Number of channels (default: 1)')
    parser.add_argument('--gain', '-g', type=float, default=26.0,
                       help='Gain in dB (default: 26.0)')
    parser.add_argument('--block-size', '-b', type=int, default=None,
                       help='Audio block size in samples (default: 30ms worth)')
    
    args = parser.parse_args()
    
    # Check for sounddevice dependency
    try:
        import sounddevice as sd  # type: ignore  # noqa: F401
        import numpy as np  # type: ignore  # noqa: F401
    except ImportError:
        print("❌ Missing dependency. Please install:", file=sys.stderr)
        print("  pip install sounddevice numpy", file=sys.stderr)
        sys.exit(1)
    
    # Create audio capture instance
    capture = AudioCapture(
        sample_rate=args.sample_rate,
        channels=args.channels,
        gain_db=args.gain,
        block_size=args.block_size
    )
    
    if args.list:
        capture.list_audio_devices()
        return

    # Get device
    device_index = capture.get_audio_device(args.device)
    capture.device = device_index
    
    # Start capture
    capture.run()

if __name__ == '__main__':
    main()
