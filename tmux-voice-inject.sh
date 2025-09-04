#!/bin/bash
# Inject voice commands into tmux sessions

inject_to_tmux() {
    local command="$1"
    local session="${2:-$(tmux display-message -p '#S')}"
    
    if tmux has-session -t "$session" 2>/dev/null; then
        # Send the command to the tmux session
        tmux send-keys -t "$session" "$command" 
        echo "📤 Injected into tmux session: $session"
    else
        echo "❌ No tmux session found: $session"
    fi
}

# Monitor for voice commands and inject into tmux
monitor_voice_commands() {
    echo "👀 Monitoring for voice commands to inject into tmux..."
    while true; do
        if [[ -f "/tmp/voice_command" ]]; then
            cmd=$(cat "/tmp/voice_command" 2>/dev/null)
            if [[ -n "$cmd" ]]; then
                inject_to_tmux "$cmd"
                rm "/tmp/voice_command"
            fi
        fi
        sleep 0.1
    done
}

# Usage examples:
# ./tmux-voice-inject.sh monitor     # Start monitoring
# ./tmux-voice-inject.sh "ls -la"    # Direct injection

case "${1:-monitor}" in
    monitor)
        monitor_voice_commands
        ;;
    *)
        inject_to_tmux "$1" "$2"
        ;;
esac