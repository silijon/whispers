#!/usr/bin/env python3
"""
AI Inference Pipeline
Takes text from stdin and sends it to various AI APIs with configurable prompts.
Supports Anthropic Claude, OpenAI, and OpenAI-compatible endpoints (Ollama, etc.)
"""

import sys
import os
import json
import argparse
from typing import Optional, Dict, Any
import requests
from pathlib import Path

class AIInference:
    def __init__(self, provider: str = "anthropic", api_key: Optional[str] = None,
                 model: Optional[str] = None, api_url: Optional[str] = None,
                 temperature: float = 0.0, max_tokens: int = 1000, 
                 task_type: Optional[str] = "bash"):
        self.provider = provider.lower()
        self.api_key = api_key
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.task_type = task_type
        
        # Set default models and URLs based on provider and task
        if self.provider == "anthropic":
            # Choose optimal Claude model based on task complexity
            if task_type in ['bash', 'translate', 'fix']:
                self.model = model or "claude-3-haiku-20240307"  # Fast & cheap
            elif task_type in ['code', 'summarize']:
                self.model = model or "claude-3-haiku-20240307"  # Still good for most
            else:
                self.model = model or "claude-3-sonnet-20240229"  # More complex tasks
            self.api_url = api_url or "https://api.anthropic.com/v1/messages"
            self.api_key = self.api_key or os.getenv("ANTHROPIC_API_KEY")
        elif self.provider == "openai":
            self.model = model or "gpt-3.5-turbo"
            self.api_url = api_url or "https://api.openai.com/v1/chat/completions"
            self.api_key = self.api_key or os.getenv("OPENAI_API_KEY")
        elif self.provider == "ollama":
            self.model = model or "llama2"
            self.api_url = api_url or "http://localhost:11434/api/chat"
            self.api_key = None  # Ollama doesn't need API key
        elif self.provider == "custom":
            self.model = model or "gpt-3.5-turbo"
            self.api_url = api_url
            self.api_key = self.api_key or os.getenv("API_KEY")
        else:
            raise ValueError(f"Unknown provider: {provider}")
    
    def create_anthropic_request(self, prompt: str, user_input: str) -> Dict[str, Any]:
        """Create request body for Anthropic Claude API"""
        return {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "messages": [
                {"role": "user", "content": f"{prompt}\n\nUser input: {user_input}"}
            ]
        }
    
    def create_openai_request(self, prompt: str, user_input: str) -> Dict[str, Any]:
        """Create request body for OpenAI or compatible API"""
        return {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_input}
            ]
        }
    
    def create_ollama_request(self, prompt: str, user_input: str) -> Dict[str, Any]:
        """Create request body for Ollama API"""
        return {
            "model": self.model,
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_input}
            ],
            "stream": False,
            "options": {
                "temperature": self.temperature,
                "num_predict": self.max_tokens
            }
        }
    
    def send_request(self, prompt: str, user_input: str) -> Optional[str]:
        """Send request to the appropriate AI API and return response"""
        
        # Check that we have a valid API URL
        if not self.api_url:
            print(f"❌ No API URL configured for provider: {self.provider}", file=sys.stderr)
            return None
        
        headers, data = None, None
        
        # Create request based on provider
        if self.provider == "anthropic":
            headers = {
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            }
            data = self.create_anthropic_request(prompt, user_input)
        elif self.provider in ["openai", "custom"]:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            data = self.create_openai_request(prompt, user_input)
        elif self.provider == "ollama":
            headers = {"Content-Type": "application/json"}
            data = self.create_ollama_request(prompt, user_input)
        
        # Send request
        result = None
        try:
            response = requests.post(self.api_url, headers=headers, json=data, timeout=30)
            response.raise_for_status()
            
            # Parse response based on provider
            result = response.json()
            
            if self.provider == "anthropic":
                return result["content"][0]["text"]
            elif self.provider in ["openai", "custom"]:
                return result["choices"][0]["message"]["content"]
            elif self.provider == "ollama":
                return result["message"]["content"]
                
        except requests.RequestException as e:
            print(f"❌ API request failed: {e}", file=sys.stderr)
            if hasattr(e.response, 'text'):
                print(f"Response: {e.response.text}", file=sys.stderr)
            return None
        except (KeyError, IndexError) as e:
            print(f"❌ Unexpected response format: {e}", file=sys.stderr)
            print(f"Response: {result}", file=sys.stderr)
            return None

# Predefined prompts for common tasks
PROMPTS = {
    "bash": """You are a bash command generator. Convert the user's natural language request into a bash command.
Output ONLY the bash command, no explanation or markdown formatting.
Examples:
- "list all files" -> "ls -la"
- "find python files" -> "find . -name '*.py'"
- "show disk usage" -> "df -h"
""",
    
    "translate": """You are a translator. Translate the user's text to the specified language.
Output only the translation, no explanations.""",
    
    "summarize": """You are a text summarizer. Provide a concise summary of the user's input.
Be brief and capture the key points.""",
    
    "code": """You are a code generator. Convert the user's description into working code.
Output only the code, no explanations or markdown formatting.""",
    
    "answer": """You are a helpful assistant. Answer the user's question concisely and accurately.""",
    
    "fix": """You are a grammar and spelling corrector. Fix any errors in the user's text.
Output only the corrected text, no explanations.""",
    
    "explain": """You are an explainer. Provide a clear, simple explanation of what the user is asking about."""
}

def load_config(config_file: Optional[str] = None) -> tuple[Dict[str, Any], Optional[Path]]:
    """Load configuration from file if it exists, returns config and path used"""
    config = {}
    loaded_path = None
    
    # Try default locations
    config_paths = []
    if config_file:
        config_paths.append(Path(config_file))
    config_paths.extend([
        Path.home() / ".config" / "ai_inference.json",
        Path("ai_inference.json")
    ])
    
    for path in config_paths:
        if path.exists():
            try:
                with open(path) as f:
                    config = json.load(f)
                print(f"📋 Loaded config from {path}", file=sys.stderr)
                loaded_path = path
                break
            except json.JSONDecodeError as e:
                print(f"⚠️ Invalid JSON in {path}: {e}", file=sys.stderr)
    
    return config, loaded_path

def main():
    parser = argparse.ArgumentParser(description='Send text from stdin to AI APIs')
    
    # Provider selection
    parser.add_argument('--provider', '-p', 
                       choices=['anthropic', 'openai', 'ollama', 'custom'],
                       default='anthropic',
                       help='AI provider to use')
    
    # API configuration
    parser.add_argument('--api-key', '-k',
                       help='API key (or set via environment variable)')
    parser.add_argument('--api-url', '-u',
                       help='API endpoint URL (for custom providers)')
    parser.add_argument('--model', '-m',
                       help='Model to use')
    
    # Prompt configuration
    parser.add_argument('--prompt', '-P',
                       help='System prompt to use')
    parser.add_argument('--prompt-type', '-t',
                       choices=list(PROMPTS.keys()),
                       help='Use a predefined prompt type')
    parser.add_argument('--prompt-file', '-f',
                       help='Read prompt from file')
    
    # Generation parameters
    parser.add_argument('--temperature', type=float, default=0.0,
                       help='Temperature for generation (0.0-1.0)')
    parser.add_argument('--max-tokens', type=int, default=1000,
                       help='Maximum tokens to generate')
    
    # Configuration
    parser.add_argument('--config', '-c',
                       help='Configuration file path')
    parser.add_argument('--save-config',
                       help='Save current settings to config file')
    
    # Output options
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Show request details')
    parser.add_argument('--raw', action='store_true',
                       help='Output raw response without any formatting')
    
    args = parser.parse_args()
    
    # Load config file
    config, config_path = load_config(args.config)
    
    # Command line args override config
    provider = args.provider or config.get('provider', 'anthropic')
    api_key = args.api_key or config.get('api_key')
    api_url = args.api_url or config.get('api_url')
    model = args.model or config.get('model')
    temperature = args.temperature if args.temperature != 0.0 else config.get('temperature', 0.0)
    max_tokens = args.max_tokens if args.max_tokens != 1000 else config.get('max_tokens', 1000)
    
    # Save config if requested
    if args.save_config:
        config_data = {
            'provider': provider,
            'api_key': api_key,
            'api_url': api_url,
            'model': model,
            'temperature': temperature,
            'max_tokens': max_tokens
        }
        config_path = Path(args.save_config)
        with open(config_path, 'w') as f:
            json.dump(config_data, f, indent=2)
        print(f"✅ Saved config to {config_path}", file=sys.stderr)
        return
    
    # Determine prompt
    prompt = None
    if args.prompt:
        prompt = args.prompt
    elif args.prompt_type:
        prompt = PROMPTS[args.prompt_type]
    elif args.prompt_file:
        with open(args.prompt_file) as f:
            prompt = f.read().strip()
    elif 'prompt' in config:
        prompt = config['prompt']
    elif 'prompt_type' in config and config['prompt_type'] in PROMPTS:
        prompt = PROMPTS[config['prompt_type']]
    else:
        prompt = PROMPTS['answer']  # Default prompt
    
    # Initialize AI client
    try:
        ai = AIInference(
            provider=provider,
            api_key=api_key,
            model=model,
            api_url=api_url,
            temperature=temperature,
            max_tokens=max_tokens
        )
    except ValueError as e:
        print(f"❌ {e}", file=sys.stderr)
        sys.exit(1)
    
    if args.verbose:
        if config_path:
            print(f"📋 Config: {config_path}", file=sys.stderr)
        else:
            print("📋 Config: using defaults (no config file found)", file=sys.stderr)
        print(f"🤖 Provider: {provider}", file=sys.stderr)
        print(f"📦 Model: {ai.model}", file=sys.stderr)
        print(f"🌡️ Temperature: {temperature}", file=sys.stderr)
        print(f"💭 Prompt: {prompt[:100]}..." if len(prompt) > 100 else f"💭 Prompt: {prompt}", file=sys.stderr)
        print("", file=sys.stderr)
    
    # Continuously read input from stdin (line by line for streaming)
    try:
        while True:
            user_input = sys.stdin.readline().strip()
            if not user_input:
                # Empty line or EOF - exit gracefully
                break
                
            if args.verbose:
                print(f"📝 Input: {user_input[:100]}..." if len(user_input) > 100 else f"📝 Input: {user_input}", file=sys.stderr)
            
            # Send request
            response = ai.send_request(prompt, user_input)
            
            if response:
                if not args.raw:
                    print(response, flush=True)
                else:
                    # Raw output without newline
                    sys.stdout.write(response)
                    sys.stdout.flush()
            else:
                print("❌ Failed to get response", file=sys.stderr)
                
    except KeyboardInterrupt:
        print("👋 Stopping AI inference...", file=sys.stderr)
    except BrokenPipeError:
        # Pipe was broken (downstream process exited) - exit gracefully
        pass

if __name__ == "__main__":
    main()
