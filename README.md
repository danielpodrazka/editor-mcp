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
- `include_line_numbers` (bool, optional): If True, prefixes each line with its line number (default: False)

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

## Troubleshooting

If you encounter issues:

1. Check file permissions
2. Verify that the file paths are absolute
3. Ensure the environment is using Python 3.7+
4. Validate line numbers (they are 1-based, not 0-based)
5. Confirm hash verification by reading content before attempting to edit it

- Each test provides a detailed message when it fails
