import hashlib
import os
from typing import Optional, Dict, Any

from mcp.server.fastmcp import FastMCP


def calculate_id(text: str, start: int = None, end: int = None) -> str:
    """
    Args:
        text (str): Content to id
        start (Optional[int]): Starting line number
        end (Optional[int]): Ending line number

    Returns:
        str: Hex digest of SHA-256 id
    """
    prefix = ""
    if start and end:
        prefix = f"L{start}-{end}-"
        if start == end:
            prefix = f"L{start}-"

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

    The server uses iding to ensure file content integrity during editing operations.
    It registers all tools with FastMCP for remote procedure calling.

    Attributes:
        mcp (FastMCP): The MCP server instance for handling tool registrations
        max_edit_lines (int): Maximum number of lines that can be edited with id verification
        current_file_path (str, optional): Path to the currently active file
    """

    def __init__(self):
        self.mcp = FastMCP("text-editor")
        self.max_edit_lines = int(os.getenv("MAX_EDIT_LINES", "200"))
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
        async def read(
            start: Optional[int] = None,
            end: Optional[int] = None,
        ) -> Dict[str, Any]:
            """
            Read text from the current file. Use to get id for the editing.

            Args:
                start (int, optional): Start line number (1-based indexing). If omitted but end is provided, starts at line 1.
                end (int, optional): End line number (1-based indexing). If omitted but start is provided, goes to the end of the file.

            Returns:
                dict: Dictionary containing the text with each line, and lines range id if file has <= self.max_edit_lines lines
            """
            result = {}

            if self.current_file_path is None:
                return {"error": "No file path is set. Use set_file first."}

            try:
                with open(self.current_file_path, "r", encoding="utf-8") as file:
                    lines = file.readlines()

                if start is None:
                    start = 1
                if end is None:
                    end = len(lines)
                if start < 1:
                    return {"error": "start must be at least 1"}
                if end > len(lines):
                    end = len(lines)
                if start > end:
                    return {"error": "start cannot be greater than end"}

                selected_lines = lines[start - 1 : end]

                text = "".join(selected_lines)
                result["text"] = text
                if len(selected_lines) <= self.max_edit_lines:
                    original_text = "".join(selected_lines)
                    result["id"] = calculate_id(original_text, start, end)
                else:
                    result["info"] = (
                        f"{len(selected_lines)=} > {self.max_edit_lines=} so no id."
                    )
                return result

            except Exception as e:
                return {"error": f"Error reading file: {str(e)}"}

        @self.mcp.tool()
        async def insert(
            id: str,
            line: int,
            text: str,
        ) -> Dict[str, Any]:
            """
            Insert lines of text after a specific line in the current file.
            Please don't insert more than 50 lines at a time to prevent hitting limits.

            Args:
                id (str): id of the line at the specified line number
                line (int): Line number (1-based) after which to insert text
                text (str): Text to insert.

            Returns:
                dict: Operation result with status

            Notes:
                - This tool is the preferred way to add new content into a file
                - The id verification ensures the file hasn't changed since you last read it
                - The text will be inserted immediately after the specified line
                - Use together with remove_lines to replace content
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
            computed_id = calculate_id(line_content, line, line)

            if computed_id != id:
                return {
                    "error": "id verification failed. The line may have been modified since you last read it."
                }

            lines.insert(line, text if text.endswith("\n") else text + "\n")

            try:
                with open(self.current_file_path, "w", encoding="utf-8") as file:
                    file.writelines(lines)

                result = {
                    "status": "success",
                    "message": f"Text inserted after line {line}",
                }
                return result
            except Exception as e:
                return {"error": f"Error writing to file: {str(e)}"}

        @self.mcp.tool()
        async def remove(
            id: str,
            start: int,
            end: int,
        ) -> Dict[str, Any]:
            """
            Remove a range of lines from the current file.

            Args:
                start (int): Start line number (1-based)
                end (int): End line number (1-based)
                id (str): id of the lines in the specified range

            Returns:
                dict: Operation result with status and message

            Notes:
                - The id verification ensures the file content hasn't changed since you last read it
                - Use together with insert to replace content
            """
            if self.current_file_path is None:
                return {"error": "No file path is set. Use set_file first."}

            try:
                with open(self.current_file_path, "r", encoding="utf-8") as file:
                    lines = file.readlines()
            except Exception as e:
                return {"error": f"Error reading file: {str(e)}"}

            if start < 1:
                return {"error": "start must be at least 1."}

            if end > len(lines):
                return {"error": f"end ({end}) exceeds file length ({len(lines)})."}

            if start > end:
                return {"error": "start cannot be greater than end."}

            current_content = "".join(lines[start - 1 : end])
            computed_id = calculate_id(current_content, start, end)

            if computed_id != id:
                return {
                    "error": "id verification failed. The content may have been modified since you last read it."
                }

            before = lines[: start - 1]
            after = lines[end:]
            modified_lines = before + after

            try:
                with open(self.current_file_path, "w", encoding="utf-8") as file:
                    file.writelines(modified_lines)

                result = {
                    "status": "success",
                    "message": f"Lines {start} to {end} removed",
                }

                return result
            except Exception as e:
                return {"error": f"Error writing to file: {str(e)}"}

        @self.mcp.tool()
        async def delete_file() -> Dict[str, Any]:
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
                dict: Operation result with status and id of the content if applicable

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
                    result["id"] = calculate_id(text)

                return result
            except Exception as e:
                return {"error": f"Error creating file: {str(e)}"}

        @self.mcp.tool()
        async def find_line(
            search_text: str,
        ) -> Dict[str, Any]:
            """
            Find lines that match provided text in the current file. Can be used to get the ID before calling insert

            Args:
                search_text (str): Text to search for in the file

            Returns:
                dict: Dictionary containing matching lines with their line numbers, id, and full text
            """
            if self.current_file_path is None:
                return {"error": "No file path is set. Use set_file first."}

            try:
                with open(self.current_file_path, "r", encoding="utf-8") as file:
                    lines = file.readlines()

                matches = []
                for i, line in enumerate(lines, start=1):
                    if search_text in line:
                        line_id = calculate_id(line, i, i)
                        matches.append({"line_number": i, "id": line_id, "text": line})

                result = {
                    "status": "success",
                    "matches": matches,
                    "total_matches": len(matches),
                }

                return result

            except Exception as e:
                return {"error": f"Error searching file: {str(e)}"}

    def run(self):
        """Run the MCP server."""
        self.mcp.run(transport="stdio")


if __name__ == "__main__":
    server = TextEditorServer()
    server.run()
