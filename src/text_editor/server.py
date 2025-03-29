import hashlib
import os
import subprocess
import tempfile
from typing import Optional, Dict, Any
import black
from black.report import NothingChanged
from mcp.server.fastmcp import FastMCP


def calculate_id(text: str, start: int = None, end: int = None) -> str:
    """
    Calculate a unique ID for content verification based on the text content.

    The ID is formed by combining a line prefix (if line numbers are provided)
    with a truncated SHA-256 id of the content. This allows quick verification
    that content hasn't changed between operations.

    Args:
        text (str): Content to generate ID for
        start (Optional[int]): Starting line number for the content
        end (Optional[int]): Ending line number for the content
    Returns:
        str: ID string in format: [LinePrefix]-[Truncatedid]
             Example: "L10-15-a7" for content spanning lines 10-15
             Example: "L5-b3" for content on line 5 only
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

    The server uses IDs to ensure file content integrity during editing operations.
    It registers all tools with FastMCP for remote procedure calling.

    Attributes:
        mcp (FastMCP): The MCP server instance for handling tool registrations
        max_edit_lines (int): Maximum number of lines that can be edited with id verification
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

            This is always the first step in the workflow. You must set a file
            before you can use other tools like read, insert, remove, etc.

            Example:
                set_file("/path/to/myfile.txt")

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
        async def skim() -> Dict[str, Any]:
            """
            Read full text from the current file. Good step after set_file.
            """
            if self.current_file_path is None:
                return {"error": "No file path is set. Use set_file first."}
            with open(self.current_file_path, "r", encoding="utf-8") as file:
                lines = file.readlines()
                text = "".join(lines)
            return {
                "text": text,
                "total_lines": len(lines),
                "max_edit_lines": self.max_edit_lines,
            }

        @self.mcp.tool()
        async def read(start: int, end: int) -> Dict[str, Any]:
            """
            Read text from the current file and get its ID for editing operations.

            This is a key step before any editing operation. The returned ID is
            required for overwrite operations to ensure content integrity.

            Workflow:
            1. Call skim() to get the context of the whole file
            1. Call read(20,30) to get content of the range you want to edit (here lines 20 to 30) and its ID
            2. Use the ID in subsequent overwrite operations

            Args:
                start (int, optional): Start line number (1-based indexing).
                end (int, optional): End line number (1-based indexing).

            Returns:
                dict: Dictionary containing the text with each line, and lines range id if file has <= self.max_edit_lines lines
            """
            result = {}

            if self.current_file_path is None:
                return {"error": "No file path is set. Use set_file first."}

            try:
                with open(self.current_file_path, "r", encoding="utf-8") as file:
                    lines = file.readlines()

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
        async def overwrite(
            text: str,
            start: int,
            end: int,
            id: str,
        ) -> Dict[str, Any]:
            """
            Overwrite a range of lines in the current file with new text.


            Args:
                text (str): New text to overwrite the specified range
                start (int): Start line number (1-based)
                end (int): End line number (1-based)
                id (str): id of the lines in the specified range

            Returns:
                dict: Operation result with status and message

            Notes:
                - This tool allows replacing a range of lines with new content
                - The number of new lines can differ from the original range
                - To remove lines, provide an empty string as the text parameter
                - The behavior mimics copy-paste: original lines are removed, new lines are
                  inserted at that position, and any content after the original section
                  is preserved and will follow the new content
                - For Python files (.py extension), syntax checking is performed before writing
                  to ensure the modified code compiles correctly
                - For JavaScript/React files (.js, .jsx extensions), syntax checking is also performed
                  using Babel (via npx) to ensure valid JavaScript/JSX syntax before writing changes
            """
            if self.current_file_path is None:
                return {"error": "No file path is set. Use set_file first."}

            try:
                with open(self.current_file_path, "r", encoding="utf-8") as file:
                    lines = file.readlines()
            except Exception as e:
                return {"error": f"Error reading file: {str(e)}"}

            if start < 1:
                return {"error": "line_start must be at least 1."}

            if end > len(lines):
                return {
                    "error": f"line_end ({end}) exceeds file length ({len(lines)})."
                }

            if start > end:
                return {"error": "line_start cannot be greater than line_end."}

            if end - start + 1 > self.max_edit_lines:
                return {
                    "error": f"Cannot overwrite more than {self.max_edit_lines} lines at once (attempted {end - start + 1} lines)."
                }

            current_content = "".join(lines[start - 1 : end])

            computed_id = calculate_id(current_content, start, end)

            if computed_id != id:
                return {
                    "error": "id verification failed. The content may have been modified since you last read it."
                }

            new_text = text
            if new_text != "" and not new_text.endswith("\n") and end < len(lines):
                new_text += "\n"

            new_lines = new_text.splitlines(True)

            before = lines[: start - 1]
            after = lines[end:]
            modified_lines = before + new_lines + after

            if self.current_file_path.endswith(".py"):
                full_content = "".join(modified_lines)
                try:
                    black.format_file_contents(
                        full_content,
                        fast=True,
                        mode=black.Mode(),
                    )
                except black.InvalidInput as e:
                    return {"error": f"Python syntax error: {str(e)}"}
                except Exception as e:
                    if not isinstance(e, NothingChanged):
                        return {"error": f"Black check raised {type(e)}: {str(e)}"}

            elif self.current_file_path.endswith((".jsx", ".js")):
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".jsx", delete=False
                ) as temp:
                    temp_path = temp.name
                    temp.writelines(modified_lines)

                try:
                    presets = (
                        ["@babel/preset-react"]
                        if self.current_file_path.endswith(".jsx")
                        else ["@babel/preset-env"]
                    )

                    cmd = [
                        "npx",
                        "babel",
                        "--presets",
                        ",".join(presets),
                        "--no-babelrc",
                        temp_path,
                        "--out-file",
                        "/dev/null",  # Output to nowhere, we just want to check syntax
                    ]

                    # Execute Babel to transform (which validates syntax)
                    process = subprocess.run(cmd, capture_output=True, text=True)

                    if process.returncode != 0:
                        error_output = process.stderr

                        filtered_lines = []
                        for line in error_output.split("\n"):
                            if "node_modules/@babel" not in line:
                                filtered_lines.append(line)

                        filtered_error = "\n".join(filtered_lines).strip()

                        if not filtered_error:
                            filtered_error = "JavaScript syntax error detected"

                        return {"error": f"JavaScript syntax error: {filtered_error}"}

                except Exception as e:
                    os.unlink(temp_path)
                    return {"error": f"Error checking JavaScript syntax: {str(e)}"}

                finally:
                    if os.path.exists(temp_path):
                        os.unlink(temp_path)

            try:
                with open(self.current_file_path, "w", encoding="utf-8") as file:
                    file.writelines(modified_lines)

                result = {
                    "status": "success",
                    "message": f"Text overwritten from line {start} to {end}",
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
        async def new_file(absolute_file_path: str) -> Dict[str, Any]:
            """
            Creates a new file.

            This tool should be used when you want to create a new file.
            The file must not exist or be empty for this operation to succeed.

            Args:
                absolute_file_path (str): Path of the new file
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
                text = "# NEW_FILE - REMOVE THIS HEADER"
                with open(self.current_file_path, "w", encoding="utf-8") as file:
                    file.write(text)

                result = {
                    "status": "success",
                    "text": text,
                    "current_file_path": self.current_file_path,
                    "id": calculate_id(text, 1, 1),
                }

                return result
            except Exception as e:
                return {"error": f"Error creating file: {str(e)}"}

        @self.mcp.tool()
        async def find_line(
            search_text: str,
        ) -> Dict[str, Any]:
            """
            Find lines that match provided text in the current file.

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
