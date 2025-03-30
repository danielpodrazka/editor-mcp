#!/bin/bash
# Easy installation script for MCP Text Editor using UVX

# Check if UVX is installed
if ! command -v uvx &> /dev/null; then
    echo "UVX not found. Installing UVX..."
    curl -sS https://raw.githubusercontent.com/astral-sh/uv/main/scripts/install.sh | sh

    # Add UV to PATH for this session
    export PATH="$HOME/.cargo/bin:$PATH"
fi

# Install the package
echo "Installing MCP Text Editor..."
uvx install -e .

echo "MCP Text Editor installed successfully!"
echo "You can now run it using the 'editor-mcp' command"