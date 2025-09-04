#!/bin/bash
# WAV to API Pipeline
# Plays a WAV file through the transcriber and sends each transcription to an API endpoint

# Configuration
WHISPER_SERVER="${WHISPER_SERVER:-http://localhost:8080}"
API_ENDPOINT="${API_ENDPOINT:-http://localhost:8000/plan}"
SILENCE_THRESHOLD="${SILENCE_THRESHOLD:-0.05}"
SILENCE_DURATION="${SILENCE_DURATION:-2}"

# Parse arguments
WAV_FILE=""
while [[ $# -gt 0 ]]; do
    case $1 in
        --file|-f)
            WAV_FILE="$2"
            shift 2
            ;;
        --endpoint|-e)
            API_ENDPOINT="$2"
            shift 2
            ;;
        --help|-h)
            echo "WAV to API Pipeline"
            echo ""
            echo "Usage: $0 --file <wav_file> [OPTIONS]"
            echo ""
            echo "Required:"
            echo "  -f, --file FILE      WAV file to transcribe"
            echo ""
            echo "Options:"
            echo "  -e, --endpoint URL   API endpoint (default: http://localhost:8000/plan)"
            echo "  -h, --help           Show this help"
            echo ""
            echo "Examples:"
            echo "  $0 -f recording.wav"
            echo "  $0 -f audio.wav -e http://localhost:3000/api/speech"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Check if WAV file was specified
if [ -z "$WAV_FILE" ]; then
    echo "❌ Error: WAV file is required"
    echo "Usage: $0 --file <wav_file> [OPTIONS]"
    echo "Use --help for more information"
    exit 1
fi

# Check if file exists
if [ ! -f "$WAV_FILE" ]; then
    echo "❌ Error: File not found: $WAV_FILE"
    exit 1
fi

# Check if file is a WAV
if ! file "$WAV_FILE" | grep -q "WAVE audio\|WAV\|RIFF"; then
    echo "⚠️  Warning: File may not be a valid WAV file"
fi

echo "🎵 WAV to API Pipeline"
echo "📁 Input file: $WAV_FILE"
echo "📡 Whisper Server: $WHISPER_SERVER"
echo "🌐 API Endpoint: $API_ENDPOINT"
echo ""

# Get WAV file info for transcriber configuration
# Try to extract sample rate using sox or ffprobe if available
SAMPLE_RATE=44100  # Default
if command -v sox >/dev/null 2>&1; then
    DETECTED_RATE=$(sox --i -r "$WAV_FILE" 2>/dev/null)
    if [ -n "$DETECTED_RATE" ]; then
        SAMPLE_RATE=$DETECTED_RATE
        echo "Detected sample rate: ${SAMPLE_RATE}Hz (using sox)"
    fi
elif command -v ffprobe >/dev/null 2>&1; then
    DETECTED_RATE=$(ffprobe -v error -select_streams a:0 -show_entries stream=sample_rate -of default=noprint_wrappers=1:nokey=1 "$WAV_FILE" 2>/dev/null)
    if [ -n "$DETECTED_RATE" ]; then
        SAMPLE_RATE=$DETECTED_RATE
        echo "Detected sample rate: ${SAMPLE_RATE}Hz (using ffprobe)"
    fi
else
    echo "Using default sample rate: ${SAMPLE_RATE}Hz"
fi

# Build transcriber command
# Note: WAV files include headers, so we don't use --raw-pcm
TRANSCRIBER_CMD="python3 streaming_transcriber.py --server $WHISPER_SERVER"
TRANSCRIBER_CMD="$TRANSCRIBER_CMD --silence-threshold $SILENCE_THRESHOLD"
TRANSCRIBER_CMD="$TRANSCRIBER_CMD --silence-duration $SILENCE_DURATION"
TRANSCRIBER_CMD="$TRANSCRIBER_CMD --sample-rate $SAMPLE_RATE"
TRANSCRIBER_CMD="$TRANSCRIBER_CMD --show-levels"

echo "Processing WAV file..."
echo ""

# Stream the WAV file through the pipeline
cat "$WAV_FILE" | \
    $TRANSCRIBER_CMD | \
    while IFS= read -r text; do
        if [ -n "$text" ]; then
            echo "📝 Transcribed: $text"
            
            # Create JSON payload
            JSON_PAYLOAD=$(jq -n --arg txt "$text" '{"text_snippet": $txt}')
            
            # Send to API
            echo "📤 Sending to $API_ENDPOINT..."
            
            RESPONSE=$(curl -s -X POST "$API_ENDPOINT" \
                -H "Content-Type: application/json" \
                -d "$JSON_PAYLOAD" \
                -w "\n%{http_code}")
            
            HTTP_CODE=$(echo "$RESPONSE" | tail -n 1)
            BODY=$(echo "$RESPONSE" | head -n -1)
            
            if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "201" ] || [ "$HTTP_CODE" = "204" ]; then
                echo "✅ Sent successfully (HTTP $HTTP_CODE)"
                if [ -n "$BODY" ]; then
                    echo "Response: $BODY"
                fi
            else
                echo "❌ Failed to send (HTTP $HTTP_CODE)"
                if [ -n "$BODY" ]; then
                    echo "Error: $BODY"
                fi
            fi
            echo ""
        fi
    done

echo "✓ Finished processing $WAV_FILE"
