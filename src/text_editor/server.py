import hashlib
import os
from typing import Optional, Dict, Any

from mcp.server.fastmcp import FastMCP


def calculate_hash(text: str, line_start: int = None, line_end: int = None) -> str:
    """
    Args:
        text (str): Content to hash
        line_start (Optional[int]): Starting line number
        line_end (Optional[int]): Ending line number

    Returns:
        str: Hex digest of SHA-256 hash
    """
    if line_start and line_end:
        prefix = f"L{line_start}-{line_end}-"
    else:
        prefix = ""
    return f"{prefix}{hashlib.sha256(text.encode()).hexdigest()[:2]}"


class TextEditorServer:
    """
    A server implementation for a text editor application using FastMCP.

    This class provides a set of tools for interacting with text files, including:
    - Setting the current file to work with
    - Reading text content from files
    - Editing file content through separate tools for inserting, removing, and overwriting text
    - Creating new files
    - Deleting files

    The server uses hashing to ensure file content integrity during editing operations.
    It registers all tools with FastMCP for remote procedure calling.

    Attributes:
        mcp (FastMCP): The MCP server instance for handling tool registrations
        max_edit_lines (int): Maximum number of lines that can be edited with hash verification
        current_file_path (str, optional): Path to the currently active file
    """

    def __init__(self):
        self.mcp = FastMCP("text-editor")
        self.max_edit_lines = int(os.getenv("MAX_EDIT_LINES", "50"))
        self.current_file_path = None

        self.register_tools()

    def register_tools(self):
        @self.mcp.tool()
        async def set_file(absolute_file_path: str) -> str:
            """
            Set the current file to work with.

            Args:
                absolute_file_path (str): Absolute path to the file

            Returns:
                str: Confirmation message with the file path
            """

            if not os.path.isfile(absolute_file_path):
                return f"Error: File not found at '{absolute_file_path}'"

            self.current_file_path = absolute_file_path
            return f"File set to: '{absolute_file_path}'"

        @self.mcp.tool()
        async def get_text(
            line_start: Optional[int] = None,
            line_end: Optional[int] = None,
        ) -> Dict[str, Any]:
            """
            Read text from the current file.

            Args:
                line_start (int, optional): Start line number (1-based indexing). If omitted but line_end is provided, starts at line 1.
                line_end (int, optional): End line number (1-based indexing). If omitted but line_start is provided, goes to the end of the file.

            Returns:
                dict: Dictionary containing the text with each line prefixed with its line number (e.g., "1|text"), and lines range hash if file has <= self.max_edit_lines lines
            """
            result = {}

            if self.current_file_path is None:
                return {"error": "No file path is set. Use set_file first."}

            try:
                with open(self.current_file_path, "r", encoding="utf-8") as file:
                    lines = file.readlines()
                if line_start is None and line_end is None:
                    numbered_lines = []
                    for i, line in enumerate(lines, start=1):
                        numbered_lines.append(f"{i}|{line}")
                    text = "".join(numbered_lines)
                    result["text"] = text
                    result["info"] = "No line_start/line_end provided so no hash"
                    return result

                if line_start is None:
                    line_start = 1
                if line_end is None:
                    line_end = len(lines)
                if line_start < 1:
                    return {"error": "line_start must be at least 1"}
                if line_end > len(lines):
                    line_end = len(lines)
                if line_start > line_end:
                    return {"error": "line_start cannot be greater than line_end"}

                selected_lines = lines[line_start - 1 : line_end]
                numbered_lines = []
                for i, line in enumerate(selected_lines, start=line_start):
                    numbered_lines.append(f"{i}|{line}")

                text = "".join(numbered_lines)
                result["text"] = text
                if len(selected_lines) <= self.max_edit_lines:
                    original_text = "".join(selected_lines)
                    result["lines_hash"] = calculate_hash(
                        original_text, line_start, line_end
                    )
                else:
                    result["info"] = (
                        f"{len(selected_lines)=} > {self.max_edit_lines=} so no hash."
                    )
                return result

            except Exception as e:
                return {"error": f"Error reading file: {str(e)}"}

        @self.mcp.tool()
        async def insert_lines(
            text: str,
            line: int,
            lines_hash: str,
        ) -> Dict[str, Any]:
            """
            Insert lines of text after a specific line in the current file.

            Args:
                text (str): Text to insert
                line (int): Line number (1-based) after which to insert text
                lines_hash (str): Hash of the line at the specified line number

            Returns:
                dict: Operation result with status and new hash if applicable

            Notes:
                - This tool is the preferred way to add new content into a file
                - The hash verification ensures the file hasn't changed since you last read it
                - The text will be inserted immediately after the specified line
                - Use together with remove_lines to replace content (instead of overwrite_text)
            """
            if self.current_file_path is None:
                return {"error": "No file path is set. Use set_file first."}

            try:
                with open(self.current_file_path, "r", encoding="utf-8") as file:
                    lines = file.readlines()
            except Exception as e:
                return {"error": f"Error reading file: {str(e)}"}

            if line < 1 or line > len(lines):
                return {
                    "error": f"Invalid line number: {line}. File has {len(lines)} lines."
                }

            line_content = lines[line - 1]
            computed_hash = calculate_hash(line_content, line, line)

            if computed_hash != lines_hash:
                return {
                    "error": "Hash verification failed. The line may have been modified since you last read it."
                }

            lines.insert(line, text if text.endswith("\n") else text + "\n")

            try:
                with open(self.current_file_path, "w", encoding="utf-8") as file:
                    file.writelines(lines)

                result = {
                    "status": "success",
                    "message": f"Text inserted after line {line}",
                }

                new_line_hash = calculate_hash(
                    text if text.endswith("\n") else text + "\n", line + 1, line + 1
                )
                result["new_line_hash"] = new_line_hash

                return result
            except Exception as e:
                return {"error": f"Error writing to file: {str(e)}"}

        @self.mcp.tool()
        async def remove_lines(
            line_start: int,
            line_end: int,
            lines_hash: str,
        ) -> Dict[str, Any]:
            """
            Remove a range of lines from the current file.

            Args:
                line_start (int): Start line number (1-based)
                line_end (int): End line number (1-based)
                lines_hash (str): Hash of the lines in the specified range

            Returns:
                dict: Operation result with status and message

            Notes:
                - This tool allows removing a specific range of lines from a file
                - The hash verification ensures the file content hasn't changed since you last read it
                - Use together with insert_lines to replace content
            """
            if self.current_file_path is None:
                return {"error": "No file path is set. Use set_file first."}

            try:
                with open(self.current_file_path, "r", encoding="utf-8") as file:
                    lines = file.readlines()
            except Exception as e:
                return {"error": f"Error reading file: {str(e)}"}

            if line_start < 1:
                return {"error": "line_start must be at least 1."}

            if line_end > len(lines):
                return {
                    "error": f"line_end ({line_end}) exceeds file length ({len(lines)})."
                }

            if line_start > line_end:
                return {"error": "line_start cannot be greater than line_end."}

            if line_end - line_start + 1 > 200:
                return {
                    "error": f"Cannot remove more than 200 lines at once (attempted {line_end - line_start + 1} lines)."
                }

            current_content = "".join(lines[line_start - 1 : line_end])
            computed_hash = calculate_hash(current_content, line_start, line_end)

            if computed_hash != lines_hash:
                return {
                    "error": "Hash verification failed. The content may have been modified since you last read it."
                }

            before = lines[: line_start - 1]
            after = lines[line_end:]
            modified_lines = before + after

            try:
                with open(self.current_file_path, "w", encoding="utf-8") as file:
                    file.writelines(modified_lines)

                result = {
                    "status": "success",
                    "message": f"Lines {line_start} to {line_end} removed",
                }

                return result
            except Exception as e:
                return {"error": f"Error writing to file: {str(e)}"}

        @self.mcp.tool()
        async def delete_current_file() -> Dict[str, Any]:
            """
            Delete the currently set file.

            Returns:
                dict: Operation result with status and message
            """

            if self.current_file_path is None:
                return {"error": "No file path is set. Use set_file first."}

            try:
                if not os.path.exists(self.current_file_path):
                    return {"error": f"File '{self.current_file_path}' does not exist."}

                os.remove(self.current_file_path)

                deleted_path = self.current_file_path

                self.current_file_path = None

                return {
                    "status": "success",
                    "message": f"File '{deleted_path}' was successfully deleted.",
                }
            except Exception as e:
                return {"error": f"Error deleting file: {str(e)}"}

        @self.mcp.tool()
        async def new_file(
            absolute_file_path: str,
            text: str,
        ) -> Dict[str, Any]:
            """
            Create a new file with the provided content.

            This tool should be used when you want to create a new file.
            The file must not exist or be empty for this operation to succeed.

            Args:
                absolute_file_path (str): Path of the new file
                text (str): Content to write to the new file

            Returns:
                dict: Operation result with status and hash of the content if applicable

            Notes:
                - This tool will fail if the current file exists and is not empty.
                - Use set_file first to specify the file path.
            """
            self.current_file_path = absolute_file_path

            if (
                os.path.exists(self.current_file_path)
                and os.path.getsize(self.current_file_path) > 0
            ):
                return {
                    "error": "Cannot create new file. Current file exists and is not empty."
                }

            try:
                with open(self.current_file_path, "w", encoding="utf-8") as file:
                    file.write(text)

                result = {
                    "status": "success",
                    "message": "File created successfully",
                }
                if len(text.splitlines()) <= self.max_edit_lines:
                    result["lines_hash"] = calculate_hash(text)

                return result
            except Exception as e:
                return {"error": f"Error creating file: {str(e)}"}

    def run(self):
        """Run the MCP server."""
        self.mcp.run(transport="stdio")


if __name__ == "__main__":
    server = TextEditorServer()
    server.run()
