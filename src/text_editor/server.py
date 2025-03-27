import hashlib
import os
from typing import Optional, Dict, Any

from mcp.server.fastmcp import FastMCP


def calculate_hash(text: str, line_start=None, line_end=None) -> str:
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
        self.current_file_path = None  # Initialize with no file path set

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
            # Verify the file exists
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
                dict: Dictionary containing the text and its hash
            """
            # Check if a file is set
            if self.current_file_path is None:
                return {"error": "No file path is set. Use set_file first."}

            try:
                with open(self.current_file_path, "r", encoding="utf-8") as file:
                    lines = file.readlines()

                # Handle line range specification
                if line_start is not None or line_end is not None:
                    # Set defaults if only one bound is specified
                    if line_start is None:
                        line_start = 1
                    if line_end is None:
                        line_end = len(lines)

                    # Adjust for 1-based indexing
                    if line_start < 1:
                        return {"error": "line_start must be at least 1"}

                    if line_end > len(lines):
                        line_end = len(lines)

                    if line_start > line_end:
                        return {"error": "line_start cannot be greater than line_end"}

                    # Extract the specified lines (adjusting for 0-based indexing in Python)
                    selected_lines = lines[line_start - 1 : line_end]
                    text = "".join(selected_lines)
                    lines_hash = calculate_hash(text, line_start, line_end)
                else:
                    # Return the entire file
                    text = "".join(lines)
                    lines_hash = calculate_hash(text)

                return {"text": text, "lines_hash": lines_hash}
            except Exception as e:
                return {"error": f"Error reading file: {str(e)}"}

    def run(self):
        """Run the MCP server."""
        self.mcp.run(transport="stdio")


# Create and run the server if this script is executed directly
if __name__ == "__main__":
    server = TextEditorServer()
    server.run()
