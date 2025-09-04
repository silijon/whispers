# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Common Development Commands

### Setup and Installation
```bash
# Install the package in development mode
pip install -e .

# Configure AI provider (required)
cp ai_inference_config.json.example ai_inference.json
# Edit ai_inference.json with your API key
```

### Running the Voice-to-Command System
```bash
# List available audio devices
./audio_capture.py --list

# Test audio capture with a specific device
./audio_capture.py -d 0

# Run voice-to-command pipeline (safe mode - generates commands only)
./voice-to-command.sh

# Execute commands automatically (use with caution!)
./voice-to-command.sh --execute

# Low-latency capture with custom settings
./capture-lowlat.sh --device 0
```

### Debugging and Testing
```bash
# Test AI inference directly
echo "list files" | python3 ai_inference.py --verbose

# Test streaming transcriber with visual audio levels
python3 streaming_transcriber.py --show-levels

# Validate AI configuration
python3 ai_inference.py --save-config test-config.json
```

## Architecture Overview

The system follows a pipeline architecture for converting voice to executable commands:

1. **Audio Capture Layer** (`audio_capture.py`, `capture-lowlat.sh`)
   - Uses sounddevice library for low-latency audio capture
   - Configurable gain, sample rates, and device selection
   - Streams raw audio to stdout for pipeline processing

2. **Voice Activity Detection & Transcription** (`streaming_transcriber.py`)
   - Implements intelligent silence detection with configurable thresholds
   - Pre-buffering captures speech from the beginning (avoiding cut-offs)
   - Sends audio chunks to Whisper server (expected on port 8080)
   - Returns transcribed text when speech ends

3. **AI Command Generation** (`ai_inference.py`)
   - Multi-provider support (Anthropic Claude, OpenAI, Ollama, custom)
   - Task-specific model selection (optimized for speed/cost)
   - Configurable via `ai_inference.json` or command-line arguments
   - Converts natural language to executable bash commands

4. **Shell Integration** (`voice-inject.plugin.zsh`, `tmux-voice-inject.sh`)
   - Intelligent path/filename autocorrection
   - Optional confirmation prompts (VOICE_CONFIRM=1)
   - Automatic zsh history integration
   - Tmux pane injection support

## Key Implementation Details

### Audio Processing Pipeline
- Audio flows through pipes: `audio_capture.py | streaming_transcriber.py | ai_inference.py`
- Each component reads from stdin and writes to stdout
- 16-bit PCM audio at configurable sample rates (default 16kHz for Whisper)

### Voice Activity Detection
- Uses RMS (Root Mean Square) calculation for silence detection
- Pre-buffer maintains last ~300ms of audio before voice detection triggers
- Configurable silence threshold and duration for end-of-speech detection

### AI Provider Configuration
Configuration stored in `ai_inference.json` with provider-specific settings:
- Anthropic: Uses Haiku model for speed (bash commands), Sonnet for complexity
- OpenAI: Supports GPT-3.5/4 models
- Ollama: Local inference without API keys
- Custom: Any OpenAI-compatible endpoint

### Shell Integration Safety
- Commands are NOT executed by default - require explicit `--execute` flag
- Autocorrect feature handles case-insensitive file matching
- Confirmation prompts available via environment variables
- All commands added to shell history for audit trail

## Dependencies

- Python 3.13+ required
- Core Python packages: `sounddevice`, `numpy`, `requests`
- External services: Whisper server (port 8080), AI API provider
- System requirements: PulseAudio/PipeWire for audio capture