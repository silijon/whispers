#!/bin/bash

# Low-latency version using pacat directly
# Configuration (copied from capture.sh)
WHISPER_SERVER="http://localhost:8080"
SAMPLE_RATE="16000"
SILENCE_THRESHOLD="0.05"
SILENCE_DURATION="0.80"
GAIN="26"
LANGUAGE="en"
TEMPERATURE="0.0"
INITIAL_PROMPT=""

# Parse device argument
AUDIO_SOURCE="47"  # Default
if [[ "$1" == "-d" && -n "$2" ]]; then
    AUDIO_SOURCE="$2"
fi

echo "🎤 Low-Latency Audio Capture Test"
echo "Using audio source: $AUDIO_SOURCE"
echo "This bypasses sox/rec and uses pacat directly"
echo "Press Ctrl+C to stop"
echo ""

# Build Python command
PYTHON_CMD="python3 streaming_transcriber.py"
PYTHON_CMD="$PYTHON_CMD --server '$WHISPER_SERVER'"
PYTHON_CMD="$PYTHON_CMD --silence-threshold '$SILENCE_THRESHOLD'"
PYTHON_CMD="$PYTHON_CMD --silence-duration '$SILENCE_DURATION'"
PYTHON_CMD="$PYTHON_CMD --sample-rate '$SAMPLE_RATE'"
PYTHON_CMD="$PYTHON_CMD --language '$LANGUAGE'"
PYTHON_CMD="$PYTHON_CMD --temperature '$TEMPERATURE'"
PYTHON_CMD="$PYTHON_CMD --chunk-duration 0.03 --show-levels --raw-pcm"

if [ -n "$INITIAL_PROMPT" ]; then
    PYTHON_CMD="$PYTHON_CMD --initial-prompt $(printf '%q' "$INITIAL_PROMPT")"
fi

# Use pw-record (PipeWire) for ultra-low latency
PIPEWIRE_LATENCY="80/16000" stdbuf -o0 -e0 pw-record --format=s16 --channels=1 --rate="$SAMPLE_RATE" --target="$AUDIO_SOURCE" - | \
    stdbuf -i0 -o0 -e0 sox -t raw -r "$SAMPLE_RATE" -e signed -b 16 -c 1 - -t wav - vol "$GAIN" dB | \
    stdbuf -i0 -o0 -e0 bash -c "$PYTHON_CMD"
