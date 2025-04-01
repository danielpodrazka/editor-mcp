# Editor MCP

A Python-based text editor server built with FastMCP that provides tools for file operations. This server enables reading, editing, and managing text files through a standardized API with a unique multi-step approach that significantly improves code editing accuracy and reliability for LLMs.

## Features

- **File Selection**: Set a file to work with using absolute paths
- **Read Operations**:
  - Read entire files with line numbers using `skim`
  - Read specific line ranges with prefixed line numbers using `read`
  - Find specific text within files using `find_line`
- **Edit Operations**:
  - Two-step editing process with diff preview
  - Select and overwrite text with ID verification
  - Clean editing workflow with select → overwrite → decide pattern
  - Syntax checking for Python (.py) and JavaScript/React (.js, .jsx) files
  - Create new files with content
- **File Management**:
  - Create new files with proper initialization
  - Delete files from the filesystem
- **Safety Features**:
  - Content ID verification to prevent conflicts
  - Line count limits to prevent resource exhaustion
  - Syntax checking to maintain code integrity

## Key Advantages For LLMs

This text editor's unique design solves critical problems that typically affect LLM code editing:

- **Prevents Loss of Context** - Traditional approaches often lead to LLMs losing overview of the codebase after a few edits. This implementation maintains context through the multi-step process.

- **Avoids Resource-Intensive Rewrites** - LLMs typically default to replacing entire files when confused, which is costly, slow, and inefficient. This editor enforces selective edits.

- **Provides Visual Feedback** - The diff preview system allows the LLM to actually see and verify changes before committing them, dramatically reducing errors.

- **Enforces Syntax Checking** - Automatic validation for Python and JavaScript/React ensures that broken code isn't committed.

- **Improves Edit Reasoning** - The multi-step approach gives the LLM time to reason between steps, reducing haphazard token production.

## Resource Management

The editor implements several safeguards to ensure system stability and prevent resource exhaustion:

- **Maximum Edit Lines**: By default, the editor enforces a 50-line limit for any single edit operation
- **Two-Step Editing Process**: Changes are previewed before being applied to prevent unintended modifications
- **Syntax Validation**: Code changes undergo syntax checking before being committed, preventing corruption
- **ID Verification**: Each edit operation verifies the content hasn't changed since it was last read

## Installation

This MCP was developed and tested with Claude Desktop. You can download Claude Desktop on any platform.
For Claude Desktop on Linux,you can use an unofficial installation script (uses official file though), I recommend this repository:
https://github.com/emsi/claude-desktop/tree/main
Once you have Claude Desktop you need to follow instruction below to install this specific MCP.

### Easy Installation with UVX (Recommended)

The easiest way to install the Editor MCP is using the provided installation script:

```bash
# Clone the repository
git clone https://github.com/danielpodrazka/editor-mcp.git
cd editor-mcp

# Run the installation script
chmod +x install.sh
./install.sh
```

This script will:
1. Check if UVX is installed and install it if necessary
2. Install the Editor MCP in development mode
3. Make the `editor-mcp` command available in your PATH

### Manual Installation

#### Using UVX

```bash
# Install directly from GitHub
uvx install git+https://github.com/danielpodrazka/editor-mcp.git

# Or install from a local clone
git clone https://github.com/danielpodrazka/editor-mcp.git
cd editor-mcp
uvx install -e .
```

#### Using Traditional pip

```bash
pip install git+https://github.com/danielpodrazka/editor-mcp.git

# Or from a local clone
git clone https://github.com/danielpodrazka/editor-mcp.git
cd editor-mcp
pip install -e .
```

#### Using Requirements (Legacy)

Install from the lock file:
```bash
uv pip install -r uv.lock
```

### Generating a locked requirements file:
```bash
uv pip compile requirements.in -o uv.lock
```

## Usage

### Starting the Server

After installation, you can start the Editor MCP server using one of these methods:

```bash
# Using the installed script
editor-mcp

# Or using the Python module
python -m text_editor.server
```

### MCP Configuration

You can add the Editor MCP to your MCP configuration file:

```json
{
  "mcpServers": {
     "text-editor": {
       "command": "editor-mcp",
       "env": {
         "MAX_EDIT_LINES": "100",
         "ENABLE_JS_SYNTAX_CHECK": "0",
         "FAIL_ON_PYTHON_SYNTAX_ERROR": "1",
         "FAIL_ON_JS_SYNTAX_ERROR": "0"
       }
     }
  }
}
```
Explanation of env variables:

"MAX_EDIT_LINES": "100" - The LLM won't be able to overwrite more than 100 lines at a time (default is 50)

"ENABLE_JS_SYNTAX_CHECK": "0" - When editing Javascript/React code, the changes won't be checked for syntax issues

"FAIL_ON_PYTHON_SYNTAX_ERROR": "1" - When editing Python code, syntax errors will automatically cancel the overwrite action (default is enabled)

"FAIL_ON_JS_SYNTAX_ERROR": "0" - When editing Javascript/React code, syntax errors will NOT automatically cancel the overwrite action (default is disabled)

### Sample MCP config entry when building from source

```json
{
  "mcpServers": {
     "text-editor": {
       "command": "/home/daniel/pp/venvs/editor-mcp/bin/python",
       "args": ["/home/daniel/pp/editor-mcp/src/text_editor/server.py"],
        "env": {
          "MAX_EDIT_LINES": "100",
          "ENABLE_JS_SYNTAX_CHECK": "0",
          "FAIL_ON_PYTHON_SYNTAX_ERROR": "1",
          "FAIL_ON_JS_SYNTAX_ERROR": "0"
        }
     }
  }
}
```

### Available Tools

#### 1. `set_file`
Sets the current file to work with.

**Parameters**:
- `absolute_file_path` (str): Absolute path to the file

**Returns**:
- Confirmation message with the file path

#### 2. `skim`
Reads full text from the current file. Each line is prefixed with its line number.

**Returns**:
- Dictionary containing lines with their line numbers as keys, total number of lines, and the max edit lines setting

**Example output**:
```
{
  "lines": {
    "1": "def hello():",
    "2": "    print(\"Hello, world!\")",
    "3": "",
    "4": "hello()"
  },
  "total_lines": 4,
  "max_edit_lines": 50
}
```

#### 3. `read`
Reads text from the current file from start line to end line.

**Parameters**:
- `start` (int): Start line number (1-based indexing)
- `end` (int): End line number (1-based indexing)

**Returns**:
- Dictionary containing lines with their line numbers as keys, along with start and end line information

**Example output**:
```
{
  "lines": {
    "1": "def hello():",
    "2": "    print(\"Hello, world!\")",
    "3": "",
    "4": "hello()"
  },
  "start_line": 1,
  "end_line": 4
}
```

#### 4. `select`
Select a range of lines from the current file for subsequent overwrite operation.

**Parameters**:
- `start` (int): Start line number (1-based)
- `end` (int): End line number (1-based)

**Returns**:
- Dictionary containing the selected lines, line range, and ID for verification

**Note**:
- This tool validates the selection against max_edit_lines
- The selection details are stored for use in the overwrite tool
- This must be used before calling the overwrite tool

#### 5. `overwrite`
Prepare to overwrite a range of lines in the current file with new text.

**Parameters**:
- `new_lines` (list): List of new lines to overwrite the selected range

**Returns**:
- Diff preview showing the proposed changes

**Note**:
- This is the first step in a two-step process:
  1. First call overwrite() to generate a diff preview
  2. Then call decide() to accept or cancel the pending changes
- This tool allows replacing the previously selected lines with new content
- The number of new lines can differ from the original selection
- For Python files (.py extension), syntax checking is performed before writing
- For JavaScript/React files (.js, .jsx extensions), syntax checking is optional and can be disabled via the `ENABLE_JS_SYNTAX_CHECK` environment variable

#### 6. `decide`
Apply or cancel pending changes from the overwrite operation.

**Parameters**:
- `decision` (str): Either 'accept' to apply changes or 'cancel' to discard them

**Returns**:
- Operation result with status and message

**Note**:
- This is the second step in the two-step process after using overwrite
- The selection is removed upon successful application of changes

#### 7. `delete_file`
Delete the currently set file.

**Returns**:
- Operation result with status and message

#### 8. `new_file`
Creates a new file.

**Parameters**:
- `absolute_file_path` (str): Path of the new file

**Returns**:
- Operation result with status and id of the content if applicable

**Note**:
- This tool will fail if the current file exists and is not empty

#### 9. `find_line`
Find lines that match provided text in the current file.

**Parameters**:
- `search_text` (str): Text to search for in the file

**Returns**:
- Dictionary containing matching lines with their line numbers, id, and full text

**Example output**:
```
{
  "status": "success",
  "matches": [
    {
      "line_number": 2,
      "id": "L2-a1",
      "text": "    print(\"Hello, world!\")\n"
    }
  ],
  "total_matches": 1
}
```

**Note**:
- Returns an error if no file path is set
- Searches for exact text matches within each line
- The id can be used for subsequent edit operations
## Configuration

Environment variables:
- `MAX_EDIT_LINES`: Maximum number of lines that can be edited with hash verification (default: 50)
- `ENABLE_JS_SYNTAX_CHECK`: Controls whether JavaScript/JSX syntax checking is enabled (default: 1)
  - Set to "0", "false", or "no" to disable JavaScript syntax checking
  - Useful if you don't have Babel and related dependencies installed
- `FAIL_ON_PYTHON_SYNTAX_ERROR`: Controls whether Python syntax errors automatically cancel the overwrite operation (default: 1)
  - When enabled, syntax errors in Python files will cause the overwrite action to be automatically cancelled
  - The lines will remain selected so you can fix the error and try again
- `FAIL_ON_JS_SYNTAX_ERROR`: Controls whether JavaScript/JSX syntax errors automatically cancel the overwrite operation (default: 0)
  - When enabled, syntax errors in JavaScript/JSX files will cause the overwrite action to be automatically cancelled
  - The lines will remain selected so you can fix the error and try again

## Development

### Prerequisites

The editor-mcp requires:
- Python 3.7+
- FastMCP package
- black (for Python code formatting checks)
- Babel (for JavaScript/JSX syntax checks if working with those files)

Install development dependencies:

```bash
# Using pip
pip install pytest pytest-asyncio pytest-cov

# Using uv
uv pip install pytest pytest-asyncio pytest-cov
```

For JavaScript/JSX syntax validation, you need Node.js and Babel. The text editor uses `npx babel` to check JS/JSX syntax when editing these file types:

```bash
# Required for JavaScript/JSX syntax checking
npm install --save-dev @babel/core @babel/cli @babel/preset-env @babel/preset-react
# You can also install these globally if you prefer
# npm install -g @babel/core @babel/cli @babel/preset-env @babel/preset-react
```

The editor requires:
- `@babel/core` and `@babel/cli` - Core Babel packages for syntax checking
- `@babel/preset-env` - For standard JavaScript (.js) files
- `@babel/preset-react` - For React JSX (.jsx) files

### Running Tests

```bash
# Run tests
pytest -v

# Run tests with coverage
pytest -v --cov=text_editor
```

### Test Structure

The test suite covers:

1. **set_file tool**
   - Setting valid files
   - Setting non-existent files
   
2. **read tool**
   - File state validation
   - Reading entire files
   - Reading specific line ranges
   - Edge cases like empty files
   - Invalid range handling

3. **select tool**
   - Line range validation
   - Selection validation against max_edit_lines
   - Selection storage for subsequent operations

4. **overwrite tool**
   - Verification of selected content using ID
   - Content replacement validation
   - Syntax checking for Python and JavaScript/React files
   - Generation of diff preview for changes

5. **decide tool**
   - Applying or canceling pending changes
   - Two-step verification process
   
6. **delete_file tool**
   - File deletion validation

7. **new_file tool**
   - File creation validation
   - Handling existing files

8. **find_line tool**
   - Finding text matches in files
   - Handling specific search terms
   - Error handling for non-existent files
   - Handling cases with no matches
   - Handling existing files

## How it Works

### The Multi-Step Editing Approach

Unlike traditional code editing approaches where LLMs simply search for lines to edit and make replacements (often leading to confusion after multiple edits), this editor implements a structured multi-step workflow that dramatically improves editing accuracy:

1. **set_file** - First, the LLM sets which file it wants to edit
2. **skim** - The LLM reads the entire file to gain a complete overview
3. **read** - The LLM examines specific sections relevant to the task, with lines shown alongside numbers for better context
4. **select** - When ready to edit, the LLM selects specific lines (limited to a configurable number, default 50)
5. **overwrite** - The LLM proposes replacement content, resulting in a git diff-style preview that shows exactly what will change
6. **decide** - After reviewing the preview, the LLM can accept or cancel the changes

This structured workflow forces the LLM to reason carefully about each edit and prevents common errors like accidentally overwriting entire files. By seeing previews of changes before committing them, the LLM can verify its edits are correct.

### ID Verification System

The server uses FastMCP to expose text editing capabilities through a well-defined API. The ID verification system ensures data integrity by verifying that the content hasn't changed between reading and modifying operations.

The ID mechanism uses SHA-256 to generate a unique identifier of the file content or selected line ranges. For line-specific operations, the ID includes a prefix indicating the line range (e.g., "L10-15-[hash]"). This helps ensure that edits are being applied to the expected content.

## Implementation Details

The main `TextEditorServer` class:

1. Initializes with a FastMCP instance named "text-editor"
2. Sets a configurable `max_edit_lines` limit (default: 50) from environment variables
3. Maintains the current file path as state
4. Registers nine primary tools through FastMCP:
   - `set_file`: Validates and sets the current file path
   - `skim`: Reads the entire content of a file, returning a dictionary of line numbers to line text
   - `read`: Reads lines from specified line range, returning a structured dictionary of line content
   - `select`: Selects lines for subsequent overwrite operation
   - `overwrite`: Takes a list of new lines and prepares diff preview for changing content
   - `decide`: Applies or cancels pending changes
   - `delete_file`: Deletes the current file
   - `new_file`: Creates a new file
   - `find_line`: Finds lines containing specific text

The server runs using FastMCP's stdio transport by default, making it easy to integrate with various clients.

## System Prompt for Best Results

For optimal results with AI assistants, it's recommended to use the system prompt (see [system_prompt.md](system_prompt.md)) that helps guide the AI in making manageable, safe edits.

This system prompt helps the AI assistant:

1. **Make incremental changes** - Breaking down edits into smaller parts
2. **Maintain code integrity** - Making changes that keep the code functional
3. **Work within resource limits** - Avoiding operations that could overwhelm the system
4. **Follow a verification workflow** - Doing final checks for errors after edits

By incorporating this system prompt when working with AI assistants, you'll get more reliable editing behavior and avoid common pitfalls in automated code editing.

## Known Issues

This issue should be fixed now but in case it still happens I leave the solution here:

Sometimes when `overwrite` tool is used, the Claude Desktop stops working and a message about temporary disruption is displayed. I reported this to Claude. If you come across this error, you can restart Claude Desktop and try again. Try making a small change first, if it works, it's more likely the tool will continue working in the active chat.
The message that is displayed when this happens:
```
Claude will return soon
Claude.ai is currently experiencing a temporary service disruption. We’re working on it, please check back soon.
```

Here is a temporary way to walk around this issue:
Create a new chat with the following prompt:
```
Create a new file in `./hello_world.txt` and replace the content with text: "hello world"
```
This will create a file called hello_world.txt in your home directory.

After this, you should be able to use the chat with this tool normally.
![example.png](example.png)
## Troubleshooting

If you encounter issues:

1. Check file permissions
2. Verify that the file paths are absolute
3. Ensure the environment is using Python 3.7+


## Inspiration

Inspired by a similar project: https://github.com/tumf/mcp-text-editor, which at first I forked, however I decided to rewrite the whole codebase from scratch so only the general idea stayed the same.
