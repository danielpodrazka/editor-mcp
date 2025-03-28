# MCP Text Editor

A Python-based text editor server built with FastMCP that provides tools for file operations. This server enables reading, editing, and managing text files through a standardized API.

## Features

- **File Selection**: Set a file to work with using absolute paths
- **Read Operations**: Read entire files or specific line ranges
- **Edit Operations**: 
  - Insert lines after a specific line
  - Remove lines within a line range
  - Create new files with content
- **File Deletion**: Remove files from the filesystem
- **Hash Verification**: Ensures data integrity during editing operations

## Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/mcp-text-editor.git
cd mcp-text-editor

# Install dependencies
pip install -e .
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

#### 2. `get_text`
Reads text from the current file. Use to get lines_hash for the editing.

**Parameters**:
- `line_start` (int, optional): Start line number (1-based indexing). If omitted but line_end is provided, starts at line 1.
- `line_end` (int, optional): End line number (1-based indexing). If omitted but line_start is provided, goes to the end of the file.

**Returns**:
- Dictionary containing the text with each line prefixed with its line number (e.g., "1|text"), and lines range hash if file has <= MAX_EDIT_LINES lines

**Example output**:
```
{"text": "1|def hello():\n2|    print(\"Hello, world!\")\n3|\n4|hello()", "lines_hash": "L1-4-a1b2c3"}
```

#### 3. `insert_lines`
Insert lines of text after a specific line in the current file.

**Parameters**:
- `lines_hash` (str): Hash of the line at the specified line number
- `line` (int): Line number (1-based) after which to insert text
- `text` (str): Text to insert

**Returns**:
- Operation result with status

**Note**:
- This tool is the preferred way to add new content into a file
- The hash verification ensures the file hasn't changed since you last read it
- The text will be inserted immediately after the specified line
- Use together with remove_lines to replace content
- Don't insert more than 50 lines at a time to prevent hitting limits

#### 4. `remove_lines`
Remove a range of lines from the current file.

**Parameters**:
- `line_start` (int): Start line number (1-based)
- `line_end` (int): End line number (1-based)
- `lines_hash` (str): Hash of the lines in the specified range

**Returns**:
- Operation result with status and message

**Note**:
- The hash verification ensures the file content hasn't changed since you last read it
- Use together with insert_lines to replace content

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
- Operation result with status and hash of the content if applicable

**Note**:
- This tool will fail if the current file exists and is not empty

## Configuration

Environment variables:
- `MAX_EDIT_LINES`: Maximum number of lines that can be edited with hash verification (default: 200)

## Development

### Prerequisites

Install development dependencies:

```bash
pip install pytest pytest-asyncio pytest-cov
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
   
2. **get_text tool**
   - File state validation
   - Reading entire files
   - Reading specific line ranges
   - Edge cases like empty files
   - Invalid range handling

3. **insert_lines tool**
   - Line validation
   - Hash verification
   - Content insertion validation
   
4. **remove_lines tool**
   - Line range validation
   - Hash verification
   - Content removal validation

5. **delete_file tool**
   - File deletion validation

6. **new_file tool**
   - File creation validation
   - Handling existing files

## How it Works

The server uses FastMCP to expose text editing capabilities through a well-defined API. The hash verification system ensures data integrity by verifying that the content hasn't changed between reading and modifying operations.

The hashing mechanism uses SHA-256 to generate a hash of the file content or selected line ranges. For line-specific operations, the hash includes a prefix indicating the line range (e.g., "L10-15-[hash]"). This helps ensure that edits are being applied to the expected content.

## Implementation Details

The main `TextEditorServer` class:

1. Initializes with a FastMCP instance named "text-editor"
2. Sets a configurable `max_edit_lines` limit (default: 200) from environment variables
3. Maintains the current file path as state
4. Registers six primary tools through FastMCP:
   - `set_file`: Validates and sets the current file path
   - `get_text`: Reads content with line numbering and hash generation
   - `insert_lines`: Inserts text after a specific line
   - `remove_lines`: Removes a range of lines
   - `delete_file`: Deletes the current file
   - `new_file`: Creates a new file with content

The server runs using FastMCP's stdio transport by default, making it easy to integrate with various clients.

## Troubleshooting

If you encounter issues:

1. Check file permissions
2. Verify that the file paths are absolute
3. Ensure the environment is using Python 3.7+
4. Validate line numbers (they are 1-based, not 0-based)
5. Confirm hash verification by reading content before attempting to edit it

- Each test provides a detailed message when it fails


## Sample MCP config entry

```json
{
  "mcpServers": {
     "text-editor": {
       "command": "/home/daniel/pp/venvs/mcp-text-editor/bin/python",
       "args": ["/home/daniel/pp/mcp-text-editor/src/text_editor/server.py"],
        "env": {
          "MAX_EDIT_LINES": "10"
        }
     }
  }
}
```