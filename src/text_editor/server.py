import hashlib
import os
import subprocess
import tempfile
import ast
import tokenize
import io
from typing import Optional, Dict, Any, Union, Literal
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
) -> dict:
    """
    Generate a diff preview comparing original and modified content.

    Args:
        original_lines (list): List of original file lines
        modified_lines (list): List of modified file lines
        start (int): Start line number of the edit (1-based)
        end (int): End line number of the edit (1-based)

    Returns:
        dict: A dictionary with keys prefixed with + or - to indicate additions/deletions
              Format: [("-1", "removed line"), ("+1", "added line")]
    """
    diffs = []
    # Add some context lines before the change
    context_start = max(0, start - 1 - 3)  # 3 lines of context before
    for i in range(context_start, start - 1):
        diffs.append((i + 1, original_lines[i].rstrip()))
    # Show removed lines
    for i in range(start - 1, end):
        diffs.append((f"-{i+1}", original_lines[i].rstrip()))

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
        diffs.append((f"+{start+i}", line))
    context_end = min(len(original_lines), end + 3)  # 3 lines of context after
    for i in range(end, context_end):
        diffs.append((i + 1, original_lines[i].rstrip()))
    return {
        "diff_lines": diffs,
    }


class TextEditorServer:
    """
    A server implementation for a text editor application using FastMCP.

    This class provides a comprehensive set of tools for manipulating text files in a
    controlled and safe manner. It implements a structured editing workflow with content
    verification to prevent conflicts during editing operations.

    Primary features:
    - File management: Setting active file, creating new files, and deleting files
    - Content access: Reading full file content or specific line ranges
    - Text search: Finding lines matching specific text patterns
    - Safe editing: Two-step edit process with diff preview and confirmation
    - Syntax validation: Automatic syntax checking for Python and JavaScript files

    The server uses content hashing to generate unique IDs that ensure file content
    integrity during editing operations. All tools are registered with FastMCP for
    remote procedure calling.

    Edit workflow:
    1. Select content range with the select() tool to identify lines for editing
    2. Propose changes with overwrite() to generate a diff preview
    3. Confirm changes with decide() to apply or cancel the pending modifications

    Attributes:
        mcp (FastMCP): The MCP server instance for handling tool registrations
        max_edit_lines (int): Maximum number of lines that can be edited with ID verification
        enable_js_syntax_check (bool): Whether JavaScript syntax checking is enabled
        current_file_path (str, optional): Path to the currently active file
        selected_start (int, optional): Start line of the current selection
        selected_end (int, optional): End line of the current selection
        selected_id (str, optional): ID of the current selection for verification
        pending_modified_lines (list, optional): Pending modified lines for preview before committing
        pending_diff (dict, optional): Diff preview of pending changes
    """

    def __init__(self):
        self.mcp = FastMCP("text-editor")
        self.max_edit_lines = int(os.getenv("MAX_EDIT_LINES", "50"))
        self.enable_js_syntax_check = os.getenv(
            "ENABLE_JS_SYNTAX_CHECK", "1"
        ).lower() in ["1", "true", "yes"]
        self.fail_on_python_syntax_error = os.getenv(
            "FAIL_ON_PYTHON_SYNTAX_ERROR", "1"
        ).lower() in ["1", "true", "yes"]
        self.fail_on_js_syntax_error = os.getenv(
            "FAIL_ON_JS_SYNTAX_ERROR", "0"
        ).lower() in ["1", "true", "yes"]
        self.current_file_path = None
        self.selected_start = None
        self.selected_end = None
        self.selected_id = None
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
            Read full text from the current file. Each line is indexed by its line number as a dictionary.

            Returns:
                dict: Dictionary containing:
                    - lines (list): Lines with line numbers
                    - total_lines (int): Total number of lines in the file
                    - max_edit_lines (int): Maximum number of lines that can be edited at once
            """
            if self.current_file_path is None:
                return {"error": "No file path is set. Use set_file first."}
            with open(self.current_file_path, "r", encoding="utf-8") as file:
                lines = file.readlines()

                formatted_lines = []
                for i, line in enumerate(lines, 1):
                    formatted_lines.append((i, line.rstrip()))

            return {
                "lines": formatted_lines,
                "total_lines": len(lines),
                "max_edit_lines": self.max_edit_lines,
            }

        @self.mcp.tool()
        async def read(start: int, end: int) -> Dict[str, Any]:
            """
            Read lines from the current file from start line to end line, returning them in a dictionary
            where keys are line numbers and values are the line contents.

            Args:
                start (int, optional): Start line number (1-based indexing).
                end (int, optional): End line number (1-based indexing).

            Returns:
                dict: Dictionary containing:
                    - lines (list): Lines with line numbers
                    - start_line (int): First line number in the range
                    - end_line (int): Last line number in the range
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
                    return {
                        "error": f"{start=} cannot be greater than {end=}. {len(lines)=}"
                    }

                selected_lines = lines[start - 1 : end]

                formatted_lines = []
                for i, line in enumerate(selected_lines, start):
                    formatted_lines.append((i, line.rstrip()))

                result["lines"] = formatted_lines
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
                dict: Dictionary containing:
                    - status (str): Success status of the operation
                    - lines (list): Selected line contents
                    - start (int): Start line number of the selection
                    - end (int): End line number of the selection
                    - id (str): Unique identifier for content verification
                    - line_count (int): Number of lines selected
                    - message (str): Human-readable success message
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

                # Convert selected lines to a list without line numbers
                lines_content = [line.rstrip() for line in selected_lines]

                result = {
                    "status": "success",
                    "lines": lines_content,
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
            new_lines: dict,
        ) -> Dict[str, Any]:
            """
            Prepare to overwrite a range of lines in the current file with new text.

            This is the first step in a two-step process:
            1. First call overwrite() to generate a diff preview
            2. Then call decide() to accept or cancel the pending changes

            Args:
                new_lines (dict): List of new lines to overwrite the selected range. Wrapped in "lines" key. Example:
                {"lines":["line one", "second line"]}

            Returns:
                dict: Diff preview showing the proposed changes

            Notes:
                - This tool allows replacing the previously selected lines with new content
                - The number of new lines can differ from the original selection
                - For Python files (.py extension), syntax checking is performed before writing
                - For JavaScript/React files (.js, .jsx extensions), syntax checking is optional
                  and controlled by the ENABLE_JS_SYNTAX_CHECK environment variable
            """
            new_lines = new_lines.get("lines")
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

            processed_new_lines = []
            for line in new_lines:
                if not line.endswith("\n"):
                    processed_new_lines.append(line + "\n")
                else:
                    processed_new_lines.append(line)

            if (
                processed_new_lines
                and end < len(lines)
                and not processed_new_lines[-1].endswith("\n")
            ):
                processed_new_lines[-1] += "\n"

            before = lines[: start - 1]
            after = lines[end:]
            modified_lines = before + processed_new_lines + after
            diff_result = generate_diff_preview(lines, modified_lines, start, end)
            error = None
            if self.current_file_path.endswith(".py"):
                full_content = "".join(modified_lines)
                try:
                    black.format_file_contents(
                        full_content,
                        fast=True,
                        mode=black.Mode(),
                    )
                except black.InvalidInput as e:
                    error = {
                        "error": f"Python syntax error: {str(e)}",
                        "diff_lines": diff_result,
                        "auto_cancel": self.fail_on_python_syntax_error,
                    }
                except Exception as e:
                    if not isinstance(e, NothingChanged):
                        error = {
                            "error": f"Black check raised {type(e)}: {str(e)}",
                            "diff_lines": diff_result,
                        }

            elif self.enable_js_syntax_check and self.current_file_path.endswith(
                (".jsx", ".js")
            ):
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

                        error = {
                            "error": f"JavaScript syntax error: {filtered_error}",
                            "diff_lines": diff_result,
                            "auto_cancel": self.fail_on_js_syntax_error,
                        }

                except Exception as e:
                    os.unlink(temp_path)
                    error = {
                        "error": f"Error checking JavaScript syntax: {str(e)}",
                        "diff_lines": diff_result,
                    }

                finally:
                    if os.path.exists(temp_path):
                        os.unlink(temp_path)

            self.pending_modified_lines = modified_lines
            self.pending_diff = diff_result

            result = {
                "status": "preview",
                "message": "Changes ready to apply. Use decide('accept') to apply or decide('cancel') to discard.",
                "diff_lines": diff_result["diff_lines"],
                "start": start,
                "end": end,
            }
            if error:
                result.update(error)
                if error.get("auto_cancel", False):
                    self.pending_modified_lines = None
                    self.pending_diff = None
                    result["status"] = "auto_cancelled"
                    result["message"] = (
                        "Changes automatically cancelled due to syntax error. The lines are still selected."
                    )
                else:
                    result["message"] = (
                        "It looks like there is a syntax error, but you can choose to fix it in the subsequent edits."
                    )

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

        @self.mcp.tool()
        async def find_function(
            function_name: str,
        ) -> Dict[str, Any]:
            """
            Find a function or method definition in the current Python file.

            This tool uses Python's AST and tokenize modules to accurately identify
            function boundaries including decorators and docstrings.

            Args:
                function_name (str): Name of the function or method to find

            Returns:
                dict: Dictionary containing the function lines with their line numbers,
                      start_line, and end_line
            """
            if self.current_file_path is None:
                return {"error": "No file path is set. Use set_file first."}

            if not self.current_file_path.endswith(".py"):
                return {"error": "This tool only works with Python files."}

            try:
                with open(self.current_file_path, "r", encoding="utf-8") as file:
                    source_code = file.read()
                    lines = source_code.splitlines(True)  # Keep line endings

                # Parse the source code to AST
                tree = ast.parse(source_code)

                # Find the function in the AST
                function_node = None
                class_node = None

                # Helper function to find a function or method node
                def find_node(node):
                    nonlocal function_node, class_node
                    if isinstance(node, ast.FunctionDef) and node.name == function_name:
                        function_node = node
                        return True
                    # Check for methods in classes
                    elif isinstance(node, ast.ClassDef):
                        for item in node.body:
                            if isinstance(item, ast.FunctionDef) and item.name == function_name:
                                function_node = item
                                class_node = node
                                return True
                    # Recursively search for nested functions/methods
                    for child in ast.iter_child_nodes(node):
                        if find_node(child):
                            return True
                    return False

                # Search for the function in the AST
                find_node(tree)

                if not function_node:
                    return {
                        "error": f"Function or method '{function_name}' not found in the file."
                    }

                # Get the line range for the function
                start_line = function_node.lineno
                end_line = 0

                # Find the end line by looking at tokens
                with open(self.current_file_path, "rb") as file:
                    tokens = list(tokenize.tokenize(file.readline))

                # Find the function definition token
                function_def_index = -1
                for i, token in enumerate(tokens):
                    if token.type == tokenize.NAME and token.string == function_name:
                        if i > 0 and tokens[i-1].type == tokenize.NAME and tokens[i-1].string == "def":
                            function_def_index = i
                            break

                if function_def_index == -1:
                    # Fallback - use AST to determine the end
                    # First, get the end_lineno from the function node itself
                    end_line = function_node.end_lineno or start_line
                    # Then walk through all nodes inside the function to find the deepest end_lineno
                    # This handles nested functions and statements properly
                    # Walk through all nodes inside the function to find the deepest end_lineno
                    # This handles nested functions and statements properly
                    for node in ast.walk(function_node):
                        if hasattr(node, 'end_lineno') and node.end_lineno:
                            end_line = max(end_line, node.end_lineno)
                    
                    # Specifically look for nested function definitions
                    # by checking for FunctionDef nodes within the function body
                    for node in ast.walk(function_node):
                        if isinstance(node, ast.FunctionDef) and node is not function_node:
                            if hasattr(node, 'end_lineno') and node.end_lineno:
                                end_line = max(end_line, node.end_lineno)
                else:
                    # Find the closing token of the function (either the next function/class at the same level or the end of file)
                    indent_level = tokens[function_def_index].start[1]  # Get the indentation of the function
                    in_function = False
                    nested_level = 0
                    for token in tokens[function_def_index+1:]:
                        current_line = token.start[0]
                        if current_line > start_line:
                            # Start tracking when we're inside the function body
                            if not in_function and token.string == ":":
                                in_function = True
                                continue
                            
                            # Track nested blocks by indentation
                            if in_function:
                                current_indent = token.start[1]
                                # Find a token at the same indentation level as the function definition
                                # but only if we're not in a nested block
                                if (current_indent <= indent_level and token.type == tokenize.NAME
                                        and token.string in ("def", "class") and nested_level == 0):
                                    end_line = current_line - 1
                                    break
                                # Track nested blocks
                                elif current_indent > indent_level and token.type == tokenize.NAME:
                                    if token.string in ("def", "class"):
                                        nested_level += 1
                                    # Look for the end of nested blocks
                                elif nested_level > 0 and current_indent <= indent_level:
                                        nested_level -= 1

                    # If we couldn't find the end, use the last line of the file
                    if end_line == 0:
                        end_line = len(lines)

                # Include decorators if present
                for decorator in function_node.decorator_list:
                    start_line = min(start_line, decorator.lineno)

                # Adjust for methods inside classes
                if class_node:
                    class_body_start = min(item.lineno for item in class_node.body if hasattr(item, 'lineno'))
                    if function_node.lineno == class_body_start:
                        # If this is the first method, include the class definition
                        start_line = class_node.lineno

                # Normalize line numbers (1-based for API consistency)
                function_lines = lines[start_line-1:end_line]

                # Format the results similar to the read tool
                formatted_lines = []
                for i, line in enumerate(function_lines, start_line):
                    formatted_lines.append((i, line.rstrip()))

                result = {
                    "status": "success",
                    "lines": formatted_lines,
                    "start_line": start_line,
                    "end_line": end_line
                }

                return result

            except Exception as e:
                return {"error": f"Error finding function: {str(e)}"}

    def run(self):
        """Run the MCP server."""
        self.mcp.run(transport="stdio")


def main():
    """Entry point for the application.

    This function is used both for direct execution and
    when the package is installed via UVX, allowing the
    application to be run using the `editor-mcp` command.
    """
    server = TextEditorServer()
    server.run()


if __name__ == "__main__":
    main()
