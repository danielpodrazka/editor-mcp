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
    def __init__(self):
        self.mcp = FastMCP("text-editor")
        self.max_edit_lines = os.getenv("MAX_EDIT_LINES", 50)
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
            line_start: Optional[int] = None, line_end: Optional[int] = None
        ) -> Dict[str, Any]:
            """
            Read text from the current file.

            Args:
                line_start (int, optional): Start line number (1-based indexing). If omitted but line_end is provided, starts at line 1.
                line_end (int, optional): End line number (1-based indexing). If omitted but line_start is provided, goes to the end of the file.

            Returns:
                dict: Dictionary containing the text, and its hash if file has <= self.max_edit_lines lines
            """

            if self.current_file_path is None:
                return {"error": "No file path is set. Use set_file first."}

            try:
                with open(self.current_file_path, "r", encoding="utf-8") as file:
                    lines = file.readlines()

                if line_start is not None or line_end is not None:
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
                    text = "".join(selected_lines)

                    result = {"text": text}
                    if len(selected_lines) <= self.max_edit_lines:
                        result["lines_hash"] = calculate_hash(
                            text, line_start, line_end
                        )

                    return result
                else:
                    text = "".join(lines)
                    result = {"text": text}

                    if len(lines) <= self.max_edit_lines:
                        result["lines_hash"] = calculate_hash(text)
                    else:
                        result["info"] = f"range > {self.max_edit_lines=} so no hash."

                    return result
            except Exception as e:
                return {"error": f"Error reading file: {str(e)}"}

        @self.mcp.tool()
        async def edit_text(
            mode: str,
            text: str,
            line: Optional[int] = None,
            line_start: Optional[int] = None,
            line_end: Optional[int] = None,
            lines_hash: Optional[str] = None,
        ) -> Dict[str, Any]:
            """
            Edit text in the current file in various modes.

            Args:
                mode (str): Edit mode - 'insert', 'overwrite', or 'create'
                text (str): Text to insert, overwrite, or create
                line (int, optional): Line number for insert mode (1-based)
                line_start (int, optional): Start line for overwrite mode (1-based)
                line_end (int, optional): End line for overwrite mode (1-based)
                lines_hash (str, optional): Hash of line(s) being modified (required for insert and overwrite)

            Returns:
                dict: Operation result with status and new hash if applicable

            Notes:
                - In overwrite mode, the number of new lines can differ from the original range.
                  For example, you can replace 2 lines with 10 lines, or replace 10 lines with nothing (empty string).
                - When replacing content with an empty string, the lines within the specified range will be removed.
                - The behavior mimics copy-paste: original lines are removed, new lines are inserted at that position,
                  and any content after the original section is preserved and will follow the new content.
            """

            if self.current_file_path is None:
                return {"error": "No file path is set. Use set_file first."}

            if mode not in ["insert", "overwrite", "create"]:
                return {
                    "error": f"Invalid mode: '{mode}'. Must be 'insert', 'overwrite', or 'create'."
                }

            if mode == "create":
                if (
                    os.path.exists(self.current_file_path)
                    and os.path.getsize(self.current_file_path) > 0
                ):
                    return {
                        "error": "Create mode requires a non-existent file or an empty file. "
                        "Current file exists and is not empty."
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

            try:
                with open(self.current_file_path, "r", encoding="utf-8") as file:
                    lines = file.readlines()
            except Exception as e:
                return {"error": f"Error reading file: {str(e)}"}

            if mode == "insert":
                if line is None:
                    return {"error": "Insert mode requires a line number."}

                if lines_hash is None:
                    return {"error": "Insert mode requires a lines_hash."}

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

            if mode == "overwrite":
                if line_start is None or line_end is None:
                    return {
                        "error": "Overwrite mode requires both line_start and line_end."
                    }

                if lines_hash is None:
                    return {"error": "Overwrite mode requires a lines_hash."}

                if line_start < 1:
                    return {"error": "line_start must be at least 1."}

                if line_end > len(lines):
                    return {
                        "error": f"line_end ({line_end}) exceeds file length ({len(lines)})."
                    }

                if line_start > line_end:
                    return {"error": "line_start cannot be greater than line_end."}

                current_content = "".join(lines[line_start - 1 : line_end])

                computed_hash = calculate_hash(current_content, line_start, line_end)

                if computed_hash != lines_hash:
                    return {
                        "error": "Hash verification failed. The content may have been modified since you last read it."
                    }

                new_text = text
                if not new_text.endswith("\n") and line_end < len(lines):
                    new_text += "\n"

                new_lines = new_text.splitlines(True)

                before = lines[: line_start - 1]
                after = lines[line_end:]
                modified_lines = before + new_lines + after

                try:
                    with open(self.current_file_path, "w", encoding="utf-8") as file:
                        file.writelines(modified_lines)

                    result = {
                        "status": "success",
                        "message": f"Text overwritten from line {line_start} to {line_end}",
                    }

                    if len(new_lines) <= self.max_edit_lines:
                        new_content = "".join(new_lines)
                        result["lines_hash"] = calculate_hash(
                            new_content, line_start, line_start + len(new_lines) - 1
                        )

                    return result
                except Exception as e:
                    return {"error": f"Error writing to file: {str(e)}"}

            return {"error": "Unknown error occurred."}

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

    def run(self):
        """Run the MCP server."""
        self.mcp.run(transport="stdio")


if __name__ == "__main__":
    server = TextEditorServer()
    server.run()
