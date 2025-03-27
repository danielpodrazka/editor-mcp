# MCP Text Editor

A Python-based text editor server built with FastMCP that provides tools for file operations. This server enables reading, editing, and managing text files through a standardized API.

## Features

- **File Selection**: Set a file to work with using absolute paths
- **Read Operations**: Read entire files or specific line ranges
- **Edit Operations**: Three editing modes:
  - Insert text at a specific line
  - Overwrite text within a line range
  - Create new files or replace content entirely
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
Reads text from the current file.

**Parameters**:
- `line_start` (int, optional): Start line number (1-based indexing)
- `line_end` (int, optional): End line number (1-based indexing)
- `include_line_numbers` (bool, optional): If True, prefixes each line with its line number (default: True)

**Returns**:
- Dictionary containing the text (optionally with line numbers) and its hash if the file has fewer than MAX_EDIT_LINES lines

**Example output with line numbers**:
```
1 | def hello():
2 |     print("Hello, world!")
3 | 
4 | hello()
```

#### 3. `edit_text`
Edits text in the current file using various modes.

**Parameters**:
- `mode` (str): Edit mode - 'insert', 'overwrite', or 'create'
- `text` (str): Text to insert, overwrite, or create
- `line` (int, optional): Line number for insert mode (1-based)
- `line_start` (int, optional): Start line for overwrite mode (1-based)
- `line_end` (int, optional): End line for overwrite mode (1-based)
- `lines_hash` (str, optional): Hash of line(s) being modified (required for insert and overwrite)

**Returns**:
- Operation result with status and new hash if applicable

**Note**: In overwrite mode, you can:
- Replace a smaller number of lines with a larger number (e.g., replace 2 lines with 10)
- Replace lines with an empty string to remove them (e.g., replace 10 lines with nothing)
- The number of new lines doesn't need to match the original range
- The behavior works like copy-paste: original lines are removed, new content is inserted at that position, and any content that follows remains intact

#### 4. `delete_current_file`
Deletes the currently set file.

**Returns**:
- Operation result with status and message

## Configuration

Environment variables:
- `MAX_EDIT_LINES`: Maximum number of lines that can be edited with hash verification (default: 50)

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

3. **edit_text tool**
   - Insert mode validation
   - Overwrite mode validation
   - Create mode validation
   - Hash verification
   
4. **delete_current_file tool**
   - File deletion validation

## How it Works

The server uses FastMCP to expose text editing capabilities through a well-defined API. The hash verification system ensures data integrity by verifying that the content hasn't changed between reading and modifying operations.

The hashing mechanism uses SHA-256 to generate a hash of the file content or selected line ranges. For line-specific operations, the hash includes a prefix indicating the line range (e.g., "L10-15-[hash]"). This helps ensure that edits are being applied to the expected content.

## Implementation Details

The main `TextEditorServer` class:

1. Initializes with a FastMCP instance named "text-editor"
2. Sets a configurable `max_edit_lines` limit (default: 50) from environment variables
3. Maintains the current file path as state
4. Registers four primary tools through FastMCP:
   - `set_file`: Validates and sets the current file path
   - `get_text`: Reads content with optional line numbering and hash generation
   - `edit_text`: Provides three editing modes with hash verification
   - `delete_current_file`: Removes files with proper cleanup

The server runs using FastMCP's stdio transport by default, making it easy to integrate with various clients.

## Troubleshooting

If you encounter issues:

1. Check file permissions
2. Verify that the file paths are absolute
3. Ensure the environment is using Python 3.7+
4. Validate line numbers (they are 1-based, not 0-based)
5. Confirm hash verification by reading content before attempting to edit it

- Each test provides a detailed message when it fails
