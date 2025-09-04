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
DEFAULT_AUDIO_SOURCE="47"  # Default device in config

# Function to list audio devices
list_audio_devices() {
    echo "Available audio input devices:"
    echo "------------------------------"
    pactl list short sources 2>/dev/null | grep -v monitor | nl -v 0 | while read num line; do
        device_id=$(echo "$line" | awk '{print $2}')
        device_name=$(echo "$line" | awk '{print $3}')
        description=$(pactl list sources 2>/dev/null | grep -A 20 "Name: $device_id" | grep "Description:" | sed 's/.*Description: //')
        echo "  [$num] $device_id"
        if [ -n "$description" ]; then
            echo "       $description"
        fi
    done
    echo ""
}

# Function to get audio device
get_audio_device() {
    # Check if device was passed as argument
    if [ -n "$1" ]; then
        # If numeric, treat as selection index
        if [[ "$1" =~ ^[0-9]+$ ]]; then
            # Get device at index
            AUDIO_SOURCE=$(pactl list short sources 2>/dev/null | grep -v monitor | sed -n "$((1 + $1))p" | awk '{print $2}')
            if [ -z "$AUDIO_SOURCE" ]; then
                echo "Error: Invalid device index: $1"
                exit 1
            fi
        else
            # Use as device ID directly
            AUDIO_SOURCE="$1"
        fi
    else
        # Interactive selection
        list_audio_devices
        
        # Get default device (prefer configured default over system default)
        SYSTEM_DEFAULT=$(pactl info 2>/dev/null | grep "Default Source:" | cut -d' ' -f3)
        if [ -n "$DEFAULT_AUDIO_SOURCE" ]; then
            DEFAULT_DISPLAY="$DEFAULT_AUDIO_SOURCE (configured)"
        elif [ -n "$SYSTEM_DEFAULT" ]; then
            DEFAULT_DISPLAY="$SYSTEM_DEFAULT (system)"
        else
            DEFAULT_DISPLAY="none"
        fi
        
        echo "Enter device number (or press Enter for default: $DEFAULT_DISPLAY):"
        read -r device_choice
        
        if [ -z "$device_choice" ]; then
            # Use default (prefer configured over system)
            if [ -n "$DEFAULT_AUDIO_SOURCE" ]; then
                AUDIO_SOURCE="$DEFAULT_AUDIO_SOURCE"
            elif [ -n "$SYSTEM_DEFAULT" ]; then
                AUDIO_SOURCE="$SYSTEM_DEFAULT"
            else
                echo "No default audio source found. Please select a device."
                exit 1
            fi
        elif [[ "$device_choice" =~ ^[0-9]+$ ]]; then
            # Get device at index
            AUDIO_SOURCE=$(pactl list short sources 2>/dev/null | grep -v monitor | sed -n "$((1 + $device_choice))p" | awk '{print $2}')
            if [ -z "$AUDIO_SOURCE" ]; then
                echo "Error: Invalid device selection"
                exit 1
            fi
        else
            echo "Error: Invalid input. Please enter a number."
            exit 1
        fi
    fi
}

# Parse command line arguments
DEVICE_ARG=""
while [[ $# -gt 0 ]]; do
    case $1 in
        --device|-d)
            DEVICE_ARG="$2"
            shift 2
            ;;
        --list|-l)
            list_audio_devices
            exit 0
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  -d, --device ID/INDEX   Audio device ID or index (interactive if not specified)"
            echo "  -l, --list             List available audio devices and exit"
            echo "  -h, --help            Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0                    # Interactive device selection"
            echo "  $0 -d 0               # Use first audio device"
            echo "  $0 -d 47              # Use device ID 47"
            echo "  $0 --list            # List all audio devices"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Get audio device
get_audio_device "$DEVICE_ARG"

echo "🎤 Low-Latency Audio Capture"
echo "Using audio source: $AUDIO_SOURCE"
echo "Settings: ${GAIN}dB gain, ${SILENCE_THRESHOLD} threshold, ${SILENCE_DURATION}s silence"
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

# Check if wl-copy is available (Wayland clipboard)
if command -v wl-copy >/dev/null 2>&1; then
    CLIPBOARD_CMD="wl-copy"
    echo "Using wl-copy for clipboard (Wayland)"
elif command -v xclip >/dev/null 2>&1; then
    CLIPBOARD_CMD="xclip -selection clipboard"
    echo "Using xclip for clipboard (X11)"
else
    echo "Warning: No clipboard tool found (wl-copy or xclip). Transcriptions will only be printed."
    CLIPBOARD_CMD="cat"  # Just pass through if no clipboard available
fi

# Use pw-record (PipeWire) for ultra-low latency
# Pipe transcriber output to clipboard tool
PIPEWIRE_LATENCY="80/16000" stdbuf -o0 -e0 pw-record --format=s16 --channels=1 --rate="$SAMPLE_RATE" --target="$AUDIO_SOURCE" - | \
    stdbuf -i0 -o0 -e0 sox -t raw -r "$SAMPLE_RATE" -e signed -b 16 -c 1 - -t wav - vol "$GAIN" dB | \
    stdbuf -i0 -o0 -e0 bash -c "$PYTHON_CMD" | \
    while IFS= read -r line; do
        echo "$line"  # Show on terminal
        echo -n "$line" | $CLIPBOARD_CMD  # Copy to clipboard
    done
