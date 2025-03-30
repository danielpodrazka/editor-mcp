# MCP Text Editor

A Python-based text editor server built with FastMCP that provides tools for file operations. This server enables reading, editing, and managing text files through a standardized API.

## Features

- **File Selection**: Set a file to work with using absolute paths
- **Read Operations**: 
  - Read entire files with line numbers using `skim`
  - Read specific line ranges with prefixed line numbers
- **Edit Operations**: 
  - Two-step editing process with diff preview
  - Select and overwrite text with ID verification
  - Syntax checking for Python (.py) and JavaScript/React (.js, .jsx) files
  - Create new files with content
- **File Deletion**: Remove files from the filesystem
- **Search Operations**: Find lines containing specific text with line numbers and IDs
## Installation

### Easy Installation with UVX (Recommended)

The easiest way to install the MCP Text Editor is using the provided installation script:

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
2. Install the MCP Text Editor in development mode
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
uv pip install -r requirements.lock
```

### Generating a locked requirements file:
```bash
uv pip compile requirements.in -o requirements.lock
```

## Usage

### Starting the Server

After installation, you can start the MCP Text Editor server using one of these methods:

```bash
# Using the installed script
editor-mcp

# Or using the Python module
python -m text_editor.server
```

### MCP Configuration

You can add the MCP Text Editor to your MCP configuration file:

```json
{
  "mcpServers": {
     "text-editor": {
       "command": "editor-mcp",
       "env": {
         "MAX_EDIT_LINES": "100",
         "ENABLE_JS_SYNTAX_CHECK": "0"
       }
     }
  }
}

"MAX_EDIT_LINES": "100" - The LLM won't be able to overwrite more than 100 lines at a time (default is 50)
"ENABLE_JS_SYNTAX_CHECK": "0" - When editing Javascript/React code, the changes won't be checked for syntax issues
```
### Sample MCP config entry when building from source

```json
{
  "mcpServers": {
     "text-editor": {
       "command": "/home/daniel/pp/venvs/editor-mcp/bin/python",
       "args": ["/home/daniel/pp/editor-mcp/src/text_editor/server.py"],
        "env": {
          "MAX_EDIT_LINES": "100",
          "ENABLE_JS_SYNTAX_CHECK": "0"
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
- Dictionary containing the complete text of the file with line numbers prefixed, total number of lines, and the max edit lines setting

**Example output**:
```
{
  "text": "   1| def hello():\n   2|     print(\"Hello, world!\")\n   3| \n   4| hello()",
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
- Dictionary containing the text of each line prefixed with its line number

**Example output**:
```
{
  "text": "   1| def hello():\n   2|     print(\"Hello, world!\")\n   3| \n   4| hello()",
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
- Dictionary containing the selected text, line range, and ID for verification

**Note**:
- This tool validates the selection against max_edit_lines
- The selection details are stored for use in the overwrite tool
- This must be used before calling the overwrite tool

#### 5. `overwrite`
Prepare to overwrite a range of lines in the current file with new text.

**Parameters**:
- `text` (str): New text to overwrite the selected range

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

The server uses FastMCP to expose text editing capabilities through a well-defined API. The ID verification system ensures data integrity by verifying that the content hasn't changed between reading and modifying operations.

The ID mechanism uses SHA-256 to generate a unique identifier of the file content or selected line ranges. For line-specific operations, the ID includes a prefix indicating the line range (e.g., "L10-15-[hash]"). This helps ensure that edits are being applied to the expected content.

## Implementation Details

The main `TextEditorServer` class:

1. Initializes with a FastMCP instance named "text-editor"
2. Sets a configurable `max_edit_lines` limit (default: 50) from environment variables
3. Maintains the current file path as state
4. Registers nine primary tools through FastMCP:
   - `set_file`: Validates and sets the current file path
   - `skim`: Reads the entire content of a file
   - `read`: Reads text from specified line range
   - `select`: Selects lines for subsequent overwrite operation
   - `overwrite`: Prepares diff preview for changing content
   - `decide`: Applies or cancels pending changes
   - `delete_file`: Deletes the current file
   - `new_file`: Creates a new file
   - `find_line`: Finds lines containing specific text

The server runs using FastMCP's stdio transport by default, making it easy to integrate with various clients.

## Troubleshooting

If you encounter issues:

1. Check file permissions
2. Verify that the file paths are absolute
3. Ensure the environment is using Python 3.7+
4. Validate line numbers (they are 1-based, not 0-based)
5. Confirm ID verification by reading content before attempting to edit it

- Each test provides a detailed message when it fails
