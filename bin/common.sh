#!/bin/bash
# Common setup for all scripts in bin/
# This file should be sourced by scripts to set up paths

# Get the directory where the sourcing script is located
if [[ -n "${BASH_SOURCE[0]}" ]]; then
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
else
    SCRIPT_DIR="$(pwd)"
fi

# Set up project structure paths
export PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
export BIN_DIR="${PROJECT_ROOT}/bin"
export SRC_DIR="${PROJECT_ROOT}/src"
export PROMPTS_DIR="${PROJECT_ROOT}/prompts"

# Add directories to PATH so we can call Python scripts directly
export PATH="${SRC_DIR}:${BIN_DIR}:$PATH"
export PYTHONPATH="${SRC_DIR}:$PYTHONPATH"

# Make Python scripts in src/ executable on the fly
if [[ -d "$SRC_DIR" ]]; then
    for script in "$SRC_DIR"/*.py; do
        if [[ -f "$script" ]]; then
            chmod +x "$script" 2>/dev/null || true
        fi
    done
fi