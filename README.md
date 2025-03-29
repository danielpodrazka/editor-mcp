# MCP Text Editor

A Python-based text editor server built with FastMCP that provides tools for file operations. This server enables reading, editing, and managing text files through a standardized API.

## Features

- **File Selection**: Set a file to work with using absolute paths
- **Read Operations**: Read entire files or specific line ranges
- **Edit Operations**: 
  - Overwrite text in a specified line range
  - Create new files with content
- **File Deletion**: Remove files from the filesystem
- **Search Operations**: Find lines containing specific text
## Installation

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

```bash
python -m text_editor.server
```

### Available Tools

#### 1. `set_file`
Sets the current file to work with.

**Parameters**:
- `absolute_file_path` (str): Absolute path to the file

**Returns**:
- Confirmation message with the file path

#### 2. `skim`
Reads full text from the current file.

**Returns**:
- Dictionary containing the complete text of the file

**Example output**:
```
{"text": "def hello():\n    print(\"Hello, world!\")\n\nhello()"}
```

#### 3. `read`
Reads text from the current file and gets its ID for editing operations.

**Parameters**:
- `start` (int): Start line number (1-based indexing)
- `end` (int): End line number (1-based indexing)

**Returns**:
- Dictionary containing the text and lines range id if file has <= MAX_EDIT_LINES lines

**Example output**:
```
{"text": "def hello():\n    print(\"Hello, world!\")\n\nhello()", "id": "L1-4-a1b2c3"}
```

#### 4. `overwrite`
Overwrite a range of lines in the current file with new text.

**Parameters**:
- `text` (str): New text to replace the specified range
- `start` (int): Start line number (1-based)
- `end` (int): End line number (1-based)
- `id` (str): ID of the lines in the specified range

**Returns**:
- Operation result with status and message

**Note**:
- This tool allows replacing a range of lines with new content
- The number of new lines can differ from the original range
- To remove lines, provide an empty string as the text parameter
- The behavior mimics copy-paste: original lines are removed, new lines are inserted at that position
- Small ranges like 10-20 lines are better to prevent hitting limits

#### 5. `delete_file`
Delete the currently set file.

**Returns**:
- Operation result with status and message

#### 6. `new_file`
Create a new file with the provided content.

**Parameters**:
- `absolute_file_path` (str): Path of the new file
- `text` (str): Content to write to the new file

**Returns**:
- Operation result with status and id of the content if applicable

**Note**:
- This tool will fail if the current file exists and is not empty

#### 7. `find_line`
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
- `MAX_EDIT_LINES`: Maximum number of lines that can be edited with hash verification (default: 200)

## Development

### Prerequisites

The mcp-text-editor requires:
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

For JavaScript/JSX syntax validation, you need Node.js and Babel:

```bash
# Install babel for JavaScript validation (if needed)
npm install --save-dev @babel/core @babel/cli @babel/preset-env @babel/preset-react
```

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

3. **overwrite tool**
   - Line range validation
   - ID verification
   - Content replacement validation
   
4. **delete_file tool**
   - File deletion validation

5. **new_file tool**
   - File creation validation
   - Handling existing files

6. **find_line tool**
   - Finding text matches in files
   - Handling specific search terms
   - Error handling for non-existent files
   - Handling cases with no matches
   - Handling existing files

## Dependency Configuration

### Sample requirements.in file

For uv installations, you can create a `requirements.in` file with your direct dependencies:

```
# Core dependencies
mcp-server
black

# Development dependencies
pytest
pytest-asyncio
pytest-cov
```

### Sample requirements.txt

For pip installations, you can create a `requirements.txt` file:

```
mcp-server>=0.1.0
black>=23.0.0
pytest>=7.0.0
pytest-asyncio>=0.18.0
pytest-cov>=2.12.0
```

### Sample pyproject.toml

For modern Python package management, you can use a `pyproject.toml` file:

```toml
[build-system]
requires = ["setuptools>=42", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "mcp-text-editor"
version = "0.1.0"
description = "A Python-based text editor server built with FastMCP"
readme = "README.md"
requires-python = ">=3.7"
license = {text = "MIT"}
dependencies = [
    "mcp-server>=0.1.0",
    "black>=23.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0.0",
    "pytest-asyncio>=0.18.0", 
    "pytest-cov>=2.12.0",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = "test_*.py"
```

## How it Works

The server uses FastMCP to expose text editing capabilities through a well-defined API. The ID verification system ensures data integrity by verifying that the content hasn't changed between reading and modifying operations.

The ID mechanism uses SHA-256 to generate a unique identifier of the file content or selected line ranges. For line-specific operations, the ID includes a prefix indicating the line range (e.g., "L10-15-[hash]"). This helps ensure that edits are being applied to the expected content.

## Implementation Details

The main `TextEditorServer` class:

1. Initializes with a FastMCP instance named "text-editor"
2. Sets a configurable `max_edit_lines` limit (default: 200) from environment variables
3. Maintains the current file path as state
4. Registers seven primary tools through FastMCP:
   - `set_file`: Validates and sets the current file path
   - `skim`: Reads the entire content of a file
   - `read`: Reads content and generates content IDs
   - `overwrite`: Replaces text in a specified line range
   - `delete_file`: Deletes the current file
   - `new_file`: Creates a new file with content
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


## Sample MCP config entry

```json
{
  "mcpServers": {
     "text-editor": {
       "command": "/home/daniel/pp/venvs/mcp-text-editor/bin/python",
       "args": ["/home/daniel/pp/mcp-text-editor/src/text_editor/server.py"],
        "env": {
          "MAX_EDIT_LINES": "100"
        }
     }
  }
}
```