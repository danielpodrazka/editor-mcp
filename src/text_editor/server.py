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


def generate_diff_preview(
    original_lines: list, modified_lines: list, start: int, end: int
) -> str:
    """
    Generate a diff preview comparing original and modified content.

    Args:
        original_lines (list): List of original file lines
        modified_lines (list): List of modified file lines
        start (int): Start line number of the edit (1-based)
        end (int): End line number of the edit (1-based)

    Returns:
        str: A human-readable diff preview in a format similar to git diff
    """
    diff_lines = []

    # Header
    diff_lines.append(f"@@ Diff preview for lines {start}-{end} @@")

    # Add some context lines before the change
    context_start = max(0, start - 1 - 3)  # 3 lines of context before
    for i in range(context_start, start - 1):
        diff_lines.append(f" {i+1:4d}| {original_lines[i].rstrip()}")

    # Show removed lines
    for i in range(start - 1, end):
        diff_lines.append(f"-{i+1:4d}| {original_lines[i].rstrip()}")

    # Show added lines
    new_content = "".join(
        modified_lines[
            start - 1 : start
            - 1
            + len(modified_lines)
            - len(original_lines)
            + (end - (start - 1))
        ]
    )
    new_lines = new_content.splitlines()
    for i, line in enumerate(new_lines):
        diff_lines.append(f"+{start+i:4d}| {line}")

    # Add some context lines after the change
    context_end = min(len(original_lines), end + 3)  # 3 lines of context after
    for i in range(end, context_end):
        diff_lines.append(f" {i+1:4d}| {original_lines[i].rstrip()}")

    return "\n".join(diff_lines)


def format_line(line_number: int, line_text: str) -> str:
    """
    Format a line with its line number for display.

    Args:
        line_number (int): The line number (1-based)
        line_text (str): The text content of the line

    Returns:
        str: Formatted string with line number and text
    """
    return f"{line_number:4d}| {line_text.rstrip()}"


class TextEditorServer:
    """
    A server implementation for a text editor application using FastMCP.

    This class provides a set of tools for interacting with text files, including:
    - Setting the current file to work with
    - Reading text content from files
    - Editing file content through separate tools for selecting and overwriting text
    - Creating new files
    - Deleting files

    The server uses IDs to ensure file content integrity during editing operations.
    It registers all tools with FastMCP for remote procedure calling.

    The editor implements a two-step edit process:
    1. First, the overwrite tool creates a diff preview of the changes
    2. Then, the decide tool allows accepting or canceling the pending changes

    Attributes:
        mcp (FastMCP): The MCP server instance for handling tool registrations
        max_edit_lines (int): Maximum number of lines that can be edited with id verification
        current_file_path (str, optional): Path to the currently active file
        selected_start (int, optional): Start line of the current selection
        selected_end (int, optional): End line of the current selection
        selected_id (str, optional): ID of the current selection for verification
        pending_modified_lines (list, optional): Pending modified lines for preview before committing
        pending_diff (str, optional): Diff preview of pending changes
        selected_id (str, optional): ID of the current selection for verification
    """

    def __init__(self):
        self.mcp = FastMCP("text-editor")
        self.max_edit_lines = int(os.getenv("MAX_EDIT_LINES", "50"))
        self.current_file_path = None
        self.selected_start = None
        self.selected_end = None
        self.selected_id = None
        # Attributes for pending changes
        self.pending_modified_lines = None
        self.pending_diff = None

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
            Read full text from the current file. Each line is prefixed its line number. Good step after set_file.
            """
            if self.current_file_path is None:
                return {"error": "No file path is set. Use set_file first."}
            with open(self.current_file_path, "r", encoding="utf-8") as file:
                lines = file.readlines()

                # Format lines with line numbers
                formatted_lines = []
                for i, line in enumerate(lines, 1):
                    formatted_lines.append(format_line(i, line))

                text = "\n".join(formatted_lines)
            return {
                "text": text,
                "total_lines": len(lines),
                "max_edit_lines": self.max_edit_lines,
            }

        @self.mcp.tool()
        async def read(start: int, end: int) -> Dict[str, Any]:
            """
            Read text from the current file from start line to end line.

            Args:
                start (int, optional): Start line number (1-based indexing).
                end (int, optional): End line number (1-based indexing).

            Returns:
                dict: Dictionary containing the text of each line prefixed with its line number
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

                formatted_lines = []
                for i, line in enumerate(selected_lines, start):
                    formatted_lines.append(format_line(i, line))

                formatted_text = "\n".join(formatted_lines)

                result["text"] = formatted_text
                result["start_line"] = start
                result["end_line"] = end

                return result

            except Exception as e:
                return {"error": f"Error reading file: {str(e)}"}

        @self.mcp.tool()
        async def select(
            start: int,
            end: int,
        ) -> Dict[str, Any]:
            """
            Select a range of lines from the current file for subsequent overwrite operation.

            This validates the selection against max_edit_lines and stores the selection
            details for use in the overwrite tool.

            Args:
                start (int): Start line number (1-based)
                end (int): End line number (1-based)

            Returns:
                dict: Dictionary containing the selected text, line range, and ID for verification
            """
            if self.current_file_path is None:
                return {"error": "No file path is set. Use set_file first."}

            try:
                with open(self.current_file_path, "r", encoding="utf-8") as file:
                    lines = file.readlines()

                if start < 1:
                    return {"error": "start must be at least 1."}

                if end > len(lines):
                    end = len(lines)

                if start > end:
                    return {"error": "start cannot be greater than end."}

                if end - start + 1 > self.max_edit_lines:
                    return {
                        "error": f"Cannot select more than {self.max_edit_lines} lines at once (attempted {end - start + 1} lines)."
                    }

                selected_lines = lines[start - 1 : end]
                text = "".join(selected_lines)

                current_id = calculate_id(text, start, end)

                self.selected_start = start
                self.selected_end = end
                self.selected_id = current_id

                result = {
                    "status": "success",
                    "text": text,
                    "start": start,
                    "end": end,
                    "id": current_id,
                    "line_count": len(selected_lines),
                    "message": f"Selected lines {start} to {end} for editing.",
                }

                return result

            except Exception as e:
                return {"error": f"Error selecting lines: {str(e)}"}

        @self.mcp.tool()
        async def overwrite(
            text: str,
        ) -> Dict[str, Any]:
            """
            Prepare to overwrite a range of lines in the current file with new text.

            This is the first step in a two-step process:
            1. First call overwrite() to generate a diff preview
            2. Then call decide() to accept or cancel the pending changes

            Args:
                text (str): New text to overwrite the selected range

            Returns:
                dict: Diff preview showing the proposed changes

            Notes:
                - This tool allows replacing the previously selected lines with new content
                - The number of new lines can differ from the original selection
                - For Python files (.py extension), syntax checking is performed before writing
                - For JavaScript/React files (.js, .jsx extensions), syntax checking is also performed
            """
            if self.current_file_path is None:
                return {"error": "No file path is set. Use set_file first."}

            if (
                self.selected_start is None
                or self.selected_end is None
                or self.selected_id is None
            ):
                return {"error": "No selection has been made. Use select tool first."}

            try:
                with open(self.current_file_path, "r", encoding="utf-8") as file:
                    lines = file.readlines()
            except Exception as e:
                return {"error": f"Error reading file: {str(e)}"}

            start = self.selected_start
            end = self.selected_end
            id = self.selected_id

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

            # Generate diff preview
            diff_preview = generate_diff_preview(lines, modified_lines, start, end)

            # Store pending changes for later application
            self.pending_modified_lines = modified_lines
            self.pending_diff = diff_preview

            result = {
                "status": "preview",
                "message": "Changes ready to apply. Use decide('accept') to apply or decide('cancel') to discard.",
                "diff_preview": diff_preview,
                "start": start,
                "end": end,
            }

            return result

        @self.mcp.tool()
        async def decide(
            decision: str,
        ) -> Dict[str, Any]:
            """
            Apply or cancel pending changes from the overwrite operation.

            This is the second step in the two-step process:
            1. First call overwrite() to generate a diff preview
            2. Then call decide() to accept or cancel the pending changes

            Args:
                decision (str): Either 'accept' to apply changes or 'cancel' to discard them

            Returns:
                dict: Operation result with status and message
            """
            if self.pending_modified_lines is None or self.pending_diff is None:
                return {"error": "No pending changes to apply. Use overwrite first."}

            if decision.lower() not in ["accept", "cancel"]:
                return {"error": "Decision must be either 'accept' or 'cancel'."}

            if decision.lower() == "cancel":
                self.pending_modified_lines = None
                self.pending_diff = None

                return {
                    "status": "success",
                    "message": "Changes cancelled.",
                }

            try:
                with open(self.current_file_path, "w", encoding="utf-8") as file:
                    file.writelines(self.pending_modified_lines)

                result = {
                    "status": "success",
                    "message": f"Changes applied successfully.",
                }

                self.selected_start = None
                self.selected_end = None
                self.selected_id = None
                self.pending_modified_lines = None
                self.pending_diff = None

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
