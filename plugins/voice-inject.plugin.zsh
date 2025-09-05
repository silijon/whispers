#!/bin/zsh
# Voice Command Auto-Execute Plugin for zsh
# Add this to your oh-my-zsh plugins or source it in ~/.zshrc
#
# Configuration:
# export VOICE_CONFIRM=1     # Enable confirmation prompts (default: off)
# export VOICE_TIMEOUT=5     # Confirmation timeout in seconds (default: 5)
# export VOICE_AUTOCORRECT=1 # Enable intelligent autocorrect (default: on)

# Ensure history settings are optimal for voice commands
setopt HIST_FIND_NO_DUPS        # Don't show duplicates in history search
setopt HIST_IGNORE_ALL_DUPS     # Remove old duplicates when adding new ones
setopt SHARE_HISTORY            # Share history between sessions
setopt APPEND_HISTORY           # Append to history file
setopt INC_APPEND_HISTORY       # Write to history file immediately

# Intelligent autocorrect function using zsh completion
voice_autocorrect_command() {
    local cmd="$1"
    
    # Skip autocorrect if disabled
    if [[ "${VOICE_AUTOCORRECT:-1}" == "0" ]]; then
        echo "$cmd"
        return
    fi
    
    # Parse the command into words
    local words=("${(@s/ /)cmd}")
    local corrected_words=()
    local command_name="${words[1]}"
    local original_cmd="$cmd"
    
    # Add the command itself (don't autocorrect command names)
    corrected_words+=("$command_name")
    
    # Process each argument
    for ((i=2; i<=${#words}; i++)); do
        local word="${words[i]}"
        local corrected_word="$word"
        
        # Skip flags and options (starting with -)
        if [[ "$word" =~ ^- ]]; then
            corrected_words+=("$word")
            continue
        fi
        
        # Handle different types of arguments
        if [[ "$word" == *\** || "$word" == *\?* ]]; then
            # Handle glob patterns
            corrected_word=$(voice_autocorrect_glob "$word")
        else
            # Handle paths (including ~ expansion and nested paths)
            local expanded_word="${word/#\~/$HOME}"
            corrected_word=$(voice_autocorrect_path "$expanded_word")
            
            # If we expanded ~, convert back if needed
            if [[ "$word" == ~* && "$corrected_word" == "$HOME"* ]]; then
                corrected_word="${corrected_word/#$HOME/~}"
            fi
        fi
        
        corrected_words+=("$corrected_word")
    done
    
    # Rebuild the command
    local corrected_cmd="${(j/ /)corrected_words}"
    
    # Show correction if changes were made
    if [[ "$corrected_cmd" != "$original_cmd" ]]; then
        echo "🔧 Autocorrected: $original_cmd → $corrected_cmd" >&2
    fi
    
    echo "$corrected_cmd"
}

# Helper function to autocorrect file paths
voice_autocorrect_path() {
    local path="$1"
    
    # If path exists as-is, return it
    if [[ -e "$path" ]]; then
        echo "$path"
        return
    fi
    
    # Split path into components
    local components=("${(@s|/|)path}")
    local corrected_components=()
    local current_path=""
    
    # Handle absolute vs relative paths
    if [[ "$path" =~ ^/ ]]; then
        current_path="/"
    else
        current_path="."
    fi
    
    # Process each path component
    for component in "${components[@]}"; do
        # Skip empty components (from leading/trailing slashes)
        [[ -z "$component" ]] && continue
        
        local test_path="$current_path/$component"
        
        # If this component exists exactly, use it
        if [[ -e "$test_path" ]]; then
            corrected_components+=("$component")
            current_path="$test_path"
            continue
        fi
        
        # Try case-insensitive matching
        local found_match=""
        local pattern="${component:l}"
        
        if [[ -d "$current_path" ]]; then
            local candidates=("$current_path"/*)
            local matches=()
            
            # Look for exact case-insensitive matches first
            for candidate in "${candidates[@]}"; do
                local basename="${candidate:t}"
                if [[ "${basename:l}" == "$pattern" ]]; then
                    matches+=("$basename")
                fi
            done
            
            # If exactly one match, use it
            if [[ ${#matches} -eq 1 ]]; then
                found_match="${matches[1]}"
            elif [[ ${#matches} -eq 0 ]]; then
                # Try prefix matching
                for candidate in "${candidates[@]}"; do
                    local basename="${candidate:t}"
                    if [[ "${basename:l}" == ${pattern}* ]]; then
                        matches+=("$basename")
                    fi
                done
                
                # Use prefix match if exactly one found
                if [[ ${#matches} -eq 1 ]]; then
                    found_match="${matches[1]}"
                fi
            fi
        fi
        
        # Use the corrected component or original if no match
        if [[ -n "$found_match" ]]; then
            corrected_components+=("$found_match")
            current_path="$current_path/$found_match"
        else
            corrected_components+=("$component")
            current_path="$current_path/$component"
        fi
    done
    
    # Rebuild the path
    local corrected_path
    if [[ "$path" =~ ^/ ]]; then
        corrected_path="/${(j|/|)corrected_components}"
    else
        corrected_path="${(j|/|)corrected_components}"
    fi
    
    echo "$corrected_path"
}

# Helper function to autocorrect glob patterns
voice_autocorrect_glob() {
    local pattern="$1"
    
    # Try to expand the glob and see what matches
    setopt NULL_GLOB
    local matches=(${~pattern})
    unsetopt NULL_GLOB
    
    # If pattern matches files, return the first match for single file operations (properly quoted)
    if [[ ${#matches} -gt 0 ]]; then
        # Quote the filename if it contains spaces
        local match="${matches[1]}"
        if [[ "$match" == *\ * ]]; then
            echo "'$match'"
        else
            echo "$match"
        fi
        return
    fi
    
    # If no matches, try case-insensitive matching using simpler approach
    setopt NULL_GLOB
    local candidates=(*)
    local case_matches=()
    
    # Use zsh's built-in pattern matching instead of regex
    for candidate in "${candidates[@]}"; do
        local candidate_lower="${candidate:l}"
        local pattern_lower="${pattern:l}"
        
        # Use zsh's pattern matching
        if [[ "$candidate_lower" = ${~pattern_lower} ]]; then
            case_matches+=("$candidate")
        fi
    done
    unsetopt NULL_GLOB
    
    # If exactly one case-insensitive match, use it
    if [[ ${#case_matches} -eq 1 ]]; then
        local match="${case_matches[1]}"
        if [[ "$match" == *\ * ]]; then
            echo "'$match'"
        else
            echo "$match"
        fi
        return
    fi
    
    # If still no matches, try substring matching for patterns with wildcards
    if [[ ${#case_matches} -eq 0 && "$pattern" == *\** ]]; then
        # Extract the non-wildcard part before the first *
        local prefix="${pattern%%\**}"
        local suffix="${pattern##*\*}"
        
        for candidate in "${candidates[@]}"; do
            local candidate_lower="${candidate:l}"
            local prefix_lower="${prefix:l}"
            local suffix_lower="${suffix:l}"
            
            # Check if candidate starts with prefix and ends with suffix
            local match=false
            if [[ -n "$prefix" && -n "$suffix" ]]; then
                if [[ "$candidate_lower" == ${prefix_lower}* && "$candidate_lower" == *${suffix_lower} ]]; then
                    match=true
                fi
            elif [[ -n "$prefix" ]]; then
                if [[ "$candidate_lower" == ${prefix_lower}* ]]; then
                    match=true
                fi
            elif [[ -n "$suffix" ]]; then
                if [[ "$candidate_lower" == *${suffix_lower} ]]; then
                    match=true
                fi
            fi
            
            if [[ "$match" == "true" ]]; then
                case_matches+=("$candidate")
            fi
        done
        
        # Use first substring match if only one found
        if [[ ${#case_matches} -eq 1 ]]; then
            local match="${case_matches[1]}"
            if [[ "$match" == *\ * ]]; then
                echo "'$match'"
            else
                echo "$match"
            fi
            return
        fi
    fi
    
    # Return original pattern if no good matches
    echo "$pattern"
}

# Simple approach: just check for voice commands and execute them immediately
voice_auto_execute() {
    local command_file="/tmp/voice_command"
    if [[ -f "$command_file" ]]; then
        local cmd=$(cat "$command_file" 2>/dev/null)
        if [[ -n "$cmd" ]]; then
            # Remove the file immediately to prevent re-execution
            rm "$command_file" 2>/dev/null
            
            # Apply intelligent autocomplete corrections
            cmd=$(voice_autocorrect_command "$cmd")
            
            if [[ "${VOICE_CONFIRM:-0}" == "1" ]]; then
                # Show confirmation prompt
                echo "🎤 Voice command: $cmd"
                echo -n "Execute? (Y/n) "
                
                # Read response with timeout
                local timeout="${VOICE_TIMEOUT:-5}"
                if read -t "$timeout" -q "?"; then
                    case $REPLY in
                        [nN]*)
                            echo "❌ Command canceled"
                            return
                            ;;
                        *)
                            echo "✅ Executing..."
                            ;;
                    esac
                else
                    echo ""
                    echo "⏰ Timeout - executing command (use VOICE_CONFIRM=0 to disable)"
                fi
            else
                echo "🎤 Executing voice command: $cmd"
            fi
            
            # Add to history (both in-memory and persistent)
            print -s "$cmd"
            # Force write to history file immediately
            fc -W
            # Execute the command (ensure both stdout and stderr are shown)
            eval "$cmd" 2>&1
            local exit_code=$?
            echo ""  # Add some spacing after command execution
            
            # Show exit code if command failed
            if [[ $exit_code -ne 0 ]]; then
                echo "❌ Command exited with code: $exit_code"
            fi
            
            # Force prompt refresh
            zle && zle reset-prompt
        fi
    fi
}

# Also check for voice commands when we get focus (key press)
voice_check_on_keypress() {
    voice_auto_execute
    zle accept-line
}

# Create a widget for the enhanced enter key
zle -N voice_check_on_keypress

# Bind Enter to check for voice commands before executing
bindkey '^M' voice_check_on_keypress

# Hook into the prompt to check for voice commands
add-zsh-hook precmd voice_auto_execute

# Set up periodic checking using TRAPALRM
voice_periodic_check() {
    voice_auto_execute
    # Reset the alarm for next check
    TMOUT=1
}

# Enable periodic checking (every 1 second)
TMOUT=1
TRAPALRM() {
    voice_periodic_check
}

# Show configuration on load
if [[ "${VOICE_CONFIRM:-0}" == "1" ]]; then
    echo "🎤 Voice auto-execute plugin loaded with confirmation prompts."
    echo "   Set VOICE_CONFIRM=0 to disable confirmations"
    echo "   Set VOICE_TIMEOUT=N to change timeout (current: ${VOICE_TIMEOUT:-5}s)"
else
    echo "🎤 Voice auto-execute plugin loaded. Commands execute automatically."
    echo "   Set VOICE_CONFIRM=1 to enable confirmation prompts"
fi

if [[ "${VOICE_AUTOCORRECT:-1}" == "1" ]]; then
    echo "🔧 Intelligent autocorrect enabled (file/directory names)"
    echo "   Set VOICE_AUTOCORRECT=0 to disable autocorrect"
else
    echo "   Autocorrect disabled - set VOICE_AUTOCORRECT=1 to enable"
fi
