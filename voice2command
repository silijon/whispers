#!/bin/bash
# Voice to Command Pipeline
# Transcribes voice and converts it to bash commands using AI

# Configuration
WHISPER_SERVER="${WHISPER_SERVER:-http://localhost:8080}"
AI_PROVIDER="${AI_PROVIDER:-anthropic}"
EXECUTE_COMMANDS="${EXECUTE_COMMANDS:-false}"
AUDIO_DEVICE="${AUDIO_DEVICE:-0}"
SAMPLE_RATE="${SAMPLE_RATE:-44100}"
GAIN="${GAIN:-26}"
SILENCE_THRESHOLD="${SILENCE_THRESHOLD:-0.05}"
SILENCE_DURATION="${SILENCE_DURATION:-0.80}"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --execute|-e)
            EXECUTE_COMMANDS="true"
            shift
            ;;
        --provider|-p)
            AI_PROVIDER="$2"
            shift 2
            ;;
        --device|-d)
            AUDIO_DEVICE="$2"
            shift 2
            ;;
        --list|-l)
            python3 audio_capture.py --list
            exit 0
            ;;
        --help|-h)
            echo "Voice to Command Pipeline"
            echo ""
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  -e, --execute      Execute the generated commands (BE CAREFUL!)"
            echo "  -p, --provider     AI provider (anthropic, openai, ollama)"
            echo "  -d, --device ID    Audio device index (interactive if not specified)"
            echo "  -l, --list         List available audio devices and exit"
            echo "  -h, --help        Show this help"
            echo ""
            echo "Examples:"
            echo "  $0                 # Generate commands only"
            echo "  $0 --execute       # Generate and execute commands"
            echo "  $0 -p ollama       # Use local Ollama model"
            echo "  $0 -d 0            # Use audio device 0"
            echo "  $0 --list          # List audio devices"
            echo ""
            echo "Say something like:"
            echo "  'List all Python files in this directory'"
            echo "  'Show me the disk usage'"
            echo "  'Create a new directory called test'"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

echo "🎤 Voice to Bash Command"
echo "Provider: $AI_PROVIDER"
if [ "$EXECUTE_COMMANDS" = "true" ]; then
    echo "⚠️  WARNING: Commands will be EXECUTED automatically!"
else
    echo "📋 Commands will be displayed only (use --execute to run them)"
fi
echo "Speak your command, then wait for silence..."
echo ""

# Build audio capture command
AUDIO_CMD="python3 audio_capture.py --sample-rate $SAMPLE_RATE --gain $GAIN"
if [ -n "$AUDIO_DEVICE" ]; then
    AUDIO_CMD="$AUDIO_CMD --device $AUDIO_DEVICE"
fi


# Check for clipboard tools and set up command
if command -v wl-copy >/dev/null 2>&1; then
    CLIPBOARD_CMD="wl-copy"
    echo "Using wl-copy for clipboard (Wayland)"
elif command -v xclip >/dev/null 2>&1; then
    CLIPBOARD_CMD="xclip -selection clipboard"
    echo "Using xclip for clipboard (X11)"
elif command -v pbcopy >/dev/null 2>&1; then
    CLIPBOARD_CMD="pbcopy"
    echo "Using pbcopy for clipboard (macOS)"
else
    echo "Warning: No clipboard tool found (wl-copy, xclip, or pbcopy). Commands will only be displayed."
    CLIPBOARD_CMD="cat > /dev/null"  # Discard clipboard attempts
fi

# Test audio capture first
echo "Testing audio capture..."
timeout 2s $AUDIO_CMD > /dev/null
if [ $? -ne 124 ]; then  # 124 is timeout's exit code for successful timeout
    echo "❌ Audio capture failed. Testing manually:"
    $AUDIO_CMD --help 2>&1 | head -5
    exit 1
fi

echo "✓ Audio capture working"

# Build transcriber command  
TRANSCRIBER_CMD="python3 streaming_transcriber.py --server $WHISPER_SERVER"
TRANSCRIBER_CMD="$TRANSCRIBER_CMD --silence-threshold $SILENCE_THRESHOLD"
TRANSCRIBER_CMD="$TRANSCRIBER_CMD --silence-duration $SILENCE_DURATION"
TRANSCRIBER_CMD="$TRANSCRIBER_CMD --sample-rate $SAMPLE_RATE --raw-pcm"

# Run the full pipeline
$AUDIO_CMD | \
    $TRANSCRIBER_CMD | \
    python3 ai_inference.py --provider "$AI_PROVIDER" --prompt-file prompts/bash_command.txt | \
    while IFS= read -r command; do
        echo "📦 Generated command: $command"
        
        # Copy to clipboard using discovered command
        if [ "$CLIPBOARD_CMD" != "cat > /dev/null" ]; then
            echo "$command" | $CLIPBOARD_CMD
            CLIPBOARD_SUCCESS=true
        else
            CLIPBOARD_SUCCESS=false
        fi
        
        # Also write to temp file for zsh injection
        echo "$command" > /tmp/voice_command
        
        if [ "$EXECUTE_COMMANDS" = "true" ]; then
            echo "⚡ Executing..."
            eval "$command"
            echo "✅ Done"
        else
            if [ "$CLIPBOARD_SUCCESS" = "true" ]; then
                echo "📋 Command copied to clipboard!"
            fi
            echo "💡 To execute, paste and run: $command"
        fi
        echo ""
    done
