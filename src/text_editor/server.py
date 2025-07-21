import hashlib
import logging
import os
import re
import subprocess
import tempfile
import ast
import tokenize
import fnmatch
import io
import datetime
import json
import inspect
import functools
from typing import Optional, Dict, Any, Union, Literal
import argparse
import black
from black.report import NothingChanged
from fastmcp import FastMCP
import duckdb


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger("text_editor")


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


def create_logging_tool_decorator(original_decorator, log_callback):
    """
    Create a wrapper around the FastMCP tool decorator that logs tool usage.

    Args:
        original_decorator: The original FastMCP tool decorator
        log_callback: A callback function that will be called with (tool_name, args_dict, response)

    Returns:
        A wrapped decorator function that logs tool usage
    """

    def tool_decorator_with_logging(*args, **kwargs):
        # Get the original decorator with args
        wrapped_decorator = original_decorator(*args, **kwargs)

        def wrapper(func):
            # Create our logging wrapper
            @functools.wraps(func)  # Preserve func's metadata
            async def logged_func(*func_args, **func_kwargs):
                tool_name = func.__name__
                # Convert args to dict for logging
                args_dict = {}
                if func_args and len(func_args) > 0:
                    # Get parameter names from function signature
                    sig = inspect.signature(func)
                    param_names = list(sig.parameters.keys())
                    # Skip self parameter if it exists
                    if param_names and param_names[0] == "self":
                        param_names = param_names[1:]
                    for i, arg in enumerate(func_args):
                        if i < len(param_names):
                            args_dict[param_names[i]] = (
                                str(arg) if isinstance(arg, (bytes, bytearray)) else arg
                            )
                args_dict.update(func_kwargs)

                # Call the original function
                response = await func(*func_args, **func_kwargs)

                # Log the tool usage with the response
                log_callback(tool_name, args_dict, response)

                # Return the response
                return response

            # Apply the original decorator to our logged function
            wrapped_func = wrapped_decorator(logged_func)
            return wrapped_func

        return wrapper

    return tool_decorator_with_logging


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
    - Protected files: Prevent access to sensitive files via pattern matching

    The server uses content hashing to generate unique IDs that ensure file content
    integrity during editing operations. All tools are registered with FastMCP for
    remote procedure calling.

    Edit workflow:
    1. Select content range with the select() tool to identify lines for editing
    2. Propose changes with overwrite() to generate a diff preview
    3. Use confirm() to apply or cancel() to discard the pending modifications

    Attributes:
        mcp (FastMCP): The MCP server instance for handling tool registrations
        max_select_lines (int): Maximum number of lines that can be edited with ID verification
        enable_js_syntax_check (bool): Whether JavaScript syntax checking is enabled
        protected_paths (list): List of file patterns and paths that are restricted from access
        current_file_path (str, optional): Path to the currently active file
        selected_start (int, optional): Start line of the current selection
        selected_end (int, optional): End line of the current selection
        selected_id (str, optional): ID of the current selection for verification
        pending_modified_lines (list, optional): Pending modified lines for preview before committing
        pending_diff (dict, optional): Diff preview of pending changes
    """

    def __init__(self):
        # Initialize MCP server
        self.mcp = FastMCP("text-editor")

        # Initialize DuckDB for usage statistics if enabled
        self.usage_stats_enabled = os.getenv("DUCKDB_USAGE_STATS", "0").lower() in [
            "1",
            "true",
            "yes",
        ]
        if self.usage_stats_enabled:
            self.stats_db_path = os.getenv("STATS_DB_PATH", "text_editor_stats.duckdb")
            self._init_stats_db()
            # Replace the original tool decorator with our wrapper
            # Making sure we preserve all the original functionality
            original_tool = self.mcp.tool
            logger.debug(
                {
                    "message": f"Setting up logging tool decorator using {self.stats_db_path}"
                }
            )
            self.mcp.tool = create_logging_tool_decorator(
                original_tool, self._log_tool_usage
            )
            logger.debug({"msg": "Logging tool decorator set up complete"})
        self.max_select_lines = int(os.getenv("MAX_SELECT_LINES", "50"))
        self.enable_js_syntax_check = os.getenv(
            "ENABLE_JS_SYNTAX_CHECK", "1"
        ).lower() in ["1", "true", "yes"]
        self.fail_on_python_syntax_error = os.getenv(
            "FAIL_ON_PYTHON_SYNTAX_ERROR", "1"
        ).lower() in ["1", "true", "yes"]
        self.fail_on_js_syntax_error = os.getenv(
            "FAIL_ON_JS_SYNTAX_ERROR", "0"
        ).lower() in ["1", "true", "yes"]
        self.protected_paths = (
            os.getenv("PROTECTED_PATHS", "").split(",")
            if os.getenv("PROTECTED_PATHS")
            else []
        )
        self.current_file_path = None
        self.selected_start = None
        self.selected_end = None
        self.selected_id = None
        self.pending_modified_lines = None
        self.pending_diff = None
        self.python_venv = os.getenv("PYTHON_VENV")

        self.register_tools()

    def _init_stats_db(self):
        """Initialize the DuckDB database for storing tool usage statistics."""
        logger.debug({"msg": f"Initializing stats database at {self.stats_db_path}"})
        try:
            # Connect to DuckDB and create the table if it doesn't exist
            with duckdb.connect(self.stats_db_path) as conn:
                logger.debug({"msg": "Connected to DuckDB for initialization"})
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS tool_usage (
                        tool_name VARCHAR,
                        args JSON,
                        response JSON,
                        timestamp TIMESTAMP,
                        current_file VARCHAR,
                        request_id VARCHAR,
                        client_id VARCHAR
                    )
                """)
                conn.commit()
                logger.debug({"msg": "Database tables initialized successfully"})
        except Exception as e:
            logger.debug({"msg": f"Error initializing stats database: {str(e)}"})

    def _log_tool_usage(self, tool_name: str, args: dict, response=None):
        """
        Log tool usage to the DuckDB database if stats are enabled.
        This function is called by the decorator wrapper for each tool invocation.

        Args:
            tool_name (str): Name of the tool being used
            args (dict): Arguments passed to the tool
            response (dict, optional): Response returned by the tool
        """
        # Skip if stats are disabled
        if not hasattr(self, "usage_stats_enabled") or not self.usage_stats_enabled:
            return

        logger.debug({"message": f"Logging tool usage: {tool_name}"})
        client_id = None
        try:
            # Get request ID if available
            request_id = None
            if hasattr(self.mcp, "_mcp_server") and hasattr(
                self.mcp._mcp_server, "request_context"
            ):
                request_id = getattr(
                    self.mcp._mcp_server.request_context, "request_id", None
                )

                if hasattr(self.mcp, "_mcp_server") and hasattr(
                    self.mcp._mcp_server, "request_context"
                ):
                    # Access client_id from meta if available
                    if (
                        hasattr(self.mcp._mcp_server.request_context, "meta")
                        and self.mcp._mcp_server.request_context.meta
                    ):
                        client_id = getattr(
                            self.mcp._mcp_server.request_context.meta, "client_id", None
                        )

            # Safely convert args to serializable format
            safe_args = {}
            for key, value in args.items():
                # Skip large objects and convert non-serializable objects to strings
                if (
                    hasattr(value, "__len__")
                    and not isinstance(value, (str, dict, list, tuple))
                    and len(value) > 1000
                ):
                    safe_args[key] = f"<{type(value).__name__} of length {len(value)}>"
                else:
                    try:
                        # Test if value is JSON serializable
                        json.dumps({key: value})
                        safe_args[key] = value
                    except (TypeError, OverflowError):
                        # If not serializable, convert to string representation
                        safe_args[key] = f"<{type(value).__name__}>"

            # Format arguments as JSON
            args_json = json.dumps(safe_args)

            # Process response - since we're using JSON RPC, responses should already be serializable
            response_json = None
            if response is not None:
                try:
                    response_json = json.dumps(response)
                except (TypeError, OverflowError):
                    # Handle edge cases where something non-serializable might have been returned
                    logger.debug(
                        {
                            "message": f"Non-serializable response received from {tool_name}, converting to string representation"
                        }
                    )
                    if isinstance(response, dict):
                        # For dictionaries, process each value separately
                        safe_response = {}
                        for key, value in response.items():
                            try:
                                json.dumps({key: value})
                                safe_response[key] = value
                            except (TypeError, OverflowError):
                                safe_response[key] = f"<{type(value).__name__}>"
                        response_json = json.dumps(safe_response)
                    else:
                        # For non-dict types, store a basic representation
                        response_json = json.dumps({"result": str(response)})

            logger.debug(
                {"msg": f"Attempting to connect to DuckDB at {self.stats_db_path}"}
            )
            try:
                with duckdb.connect(self.stats_db_path) as conn:
                    logger.debug({"msg": f"Connected to DuckDB successfully"})
                    conn.execute(
                        """
                        INSERT INTO tool_usage (tool_name, args, response, timestamp, current_file, request_id, client_id)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                        (
                            tool_name,
                            args_json,
                            response_json,
                            datetime.datetime.now(),
                            self.current_file_path,
                            request_id,
                            client_id,
                        ),
                    )
                    conn.commit()
                    logger.debug({"msg": f"Insert completed successfully"})
            except Exception as e:
                logger.debug({"msg": f"DuckDB error: {str(e)}"})
        except Exception as e:
            logger.debug({"msg": f"Error logging tool usage: {str(e)}"})

    def register_tools(self):
        @self.mcp.tool()
        async def set_file(filepath: str) -> str:
            """
            Set the current file to work with.

            This is always the first step in the workflow. You must set a file
            before you can use other tools like read, select etc.
            """

            if not os.path.isfile(filepath):
                return f"Error: File not found at '{filepath}'"

            # Check if the file path matches any of the protected paths
            for pattern in self.protected_paths:
                pattern = pattern.strip()
                if not pattern:
                    continue
                # Check for absolute path match
                if filepath == pattern:
                    return f"Error: Access to '{filepath}' is denied due to PROTECTED_PATHS configuration"
                # Check for glob pattern match (e.g., *.env, .env*, etc.)
                if "*" in pattern:
                    # First try matching the full path
                    if fnmatch.fnmatch(filepath, pattern):
                        return f"Error: Access to '{filepath}' is denied due to PROTECTED_PATHS configuration (matches pattern '{pattern}')"

                    # Then try matching just the basename
                    basename = os.path.basename(filepath)
                    if fnmatch.fnmatch(basename, pattern):
                        return f"Error: Access to '{filepath}' is denied due to PROTECTED_PATHS configuration (matches pattern '{pattern}')"

            self.current_file_path = filepath
            return f"File set to: '{filepath}'"

        @self.mcp.tool()
        async def skim() -> Dict[str, Any]:
            """
            Read text from the current file, truncated to the first `SKIM_MAX_LINES` lines.

            Returns:
                dict: lines, total_lines, max_select_lines
            """
            if self.current_file_path is None:
                return {"error": "No file path is set. Use set_file first."}
            with open(self.current_file_path, "r", encoding="utf-8") as file:
                lines = file.readlines()

                formatted_lines = []
                max_lines_to_show = int(os.getenv("SKIM_MAX_LINES", "500"))
                lines_to_process = lines[:max_lines_to_show]

                for i, line in enumerate(lines_to_process, 1):
                    formatted_lines.append((i, line.rstrip()))

            result = {
                "lines": formatted_lines,
                "total_lines": len(lines),
                "max_select_lines": self.max_select_lines,
            }

            # Add hint if file was truncated
            if len(lines) > max_lines_to_show:
                result["truncated"] = True
                result["hint"] = (
                    f"File has {len(lines)} total lines. Only showing first {max_lines_to_show} lines. Use `read` to view specific line ranges or `find_line` to search for content in the remaining lines."
                )

            return result

        @self.mcp.tool()
        async def read(start: int, end: int) -> Dict[str, Any]:
            """
            Read lines from the current file from start line to end line, returning them in a dictionary
            like {"lines":[[1,"text on first line"],[2,"text on second line"]]}. This makes it easier to find the precise lines to select for editing.

            Args:
                start (int, optional): Start line number
                end (int, optional): End line number

            Returns:
                dict: lines, start_line, end_line
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
            Select lines from for subsequent overwrite operation.

            Args:
                start (int): Start line number (1-based)
                end (int): End line number (1-based)

            Returns:
                dict: status, lines, start, end, id, line_count, message
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

                if end - start + 1 > self.max_select_lines:
                    return {
                        "error": f"Cannot select more than {self.max_select_lines} lines at once (attempted {end - start + 1} lines)."
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
            Overwrite the selected lines with new text. Amount of new lines can differ from the original selection

            Args:
                new_lines (dict): Example: {"lines":["line one", "second line"]}

            Returns:
                dict: Diff preview showing the proposed changes, and any syntax errors for JS or Python

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
                "message": "Changes ready to apply. Use confirm() to apply or cancel() to discard.",
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
                    result["message"] += (
                        " It looks like there is a syntax error, but you can choose to fix it in the subsequent edits."
                    )

            return result

        # Later on this tool should be shown conditionally, however, most clients don't support this functionality yet.
        @self.mcp.tool()
        async def confirm() -> Dict[str, Any]:
            """Confirm action"""
            if self.pending_modified_lines is None or self.pending_diff is None:
                return {"error": "No pending changes to apply. Use overwrite first."}

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
        async def cancel() -> Dict[str, Any]:
            """
            Cancel action
            """
            if self.pending_modified_lines is None or self.pending_diff is None:
                return {"error": "No pending changes to discard. Use overwrite first."}

            self.pending_modified_lines = None
            self.pending_diff = None

            return {
                "status": "success",
                "message": "Action cancelled.",
            }

        @self.mcp.tool()
        async def delete_file() -> Dict[str, Any]:
            """
            Delete current file
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
        async def new_file(filepath: str) -> Dict[str, Any]:
            """
            Creates a new file.

            After creating new file, the first line is automatically selected for editing.
            Automatically creates parent directories if they don't exist.

            Args:
                filepath (str): Path of the new file
            Returns:
                dict: Status message with selection info

            """
            self.current_file_path = filepath

            if (
                os.path.exists(self.current_file_path)
                and os.path.getsize(self.current_file_path) > 0
            ):
                return {
                    "error": "Cannot create new file. Current file exists and is not empty."
                }

            try:
                # Create parent directories if they don't exist
                directory = os.path.dirname(self.current_file_path)
                if directory:
                    os.makedirs(directory, exist_ok=True)

                text = "# NEW_FILE - REMOVE THIS HEADER"
                with open(self.current_file_path, "w", encoding="utf-8") as file:
                    file.write(text)

                # Automatically select the first line for editing
                self.selected_start = 1
                self.selected_end = 1
                self.selected_id = calculate_id(text, 1, 1)

                result = {
                    "status": "success",
                    "text": text,
                    "current_file_path": self.current_file_path,
                    "id": self.selected_id,
                    "selected_start": self.selected_start,
                    "selected_end": self.selected_end,
                    "message": "File created successfully. First line is now selected for editing.",
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
                dict: Matching lines with their line numbers, and full text
            """
            if self.current_file_path is None:
                return {"error": "No file path is set. Use set_file first."}

            try:
                with open(self.current_file_path, "r", encoding="utf-8") as file:
                    lines = file.readlines()

                matches = []
                for i, line in enumerate(lines, start=1):
                    if search_text in line:
                        matches.append([i, line])

                result = {
                    "status": "success",
                    "matches": matches,
                    "total_matches": len(matches),
                }

                return result

            except Exception as e:
                return {"error": f"Error searching file: {str(e)}"}

        @self.mcp.tool()
        async def listdir(dirpath: str) -> Dict[str, Any]:
            try:
                return {
                    "filenames": os.listdir(dirpath),
                    "path": dirpath,
                }
            except NotADirectoryError as e:
                return {
                    "error": "Specified path is not a directory.",
                    "path": dirpath,
                }
            except Exception as e:
                return {
                    "error": f"Unexpected error when listing the directory: {str(e)}"
                }

        @self.mcp.tool()
        async def find_function(
            function_name: str,
        ) -> Dict[str, Any]:
            """
            Find a function or method definition in a Python or JS/JSX file. Uses AST parsers.

            Args:
                function_name (str): Name of the function or method to find

            Returns:
                dict: function lines with their line numbers, start_line, and end_line
            """
            if self.current_file_path is None:
                return {"error": "No file path is set. Use set_file first."}

            # Check if the file is a supported type (Python or JavaScript/JSX)
            is_python = self.current_file_path.endswith(".py")
            is_javascript = self.current_file_path.endswith((".js", ".jsx"))

            if not (is_python or is_javascript):
                return {
                    "error": "This tool only works with Python (.py) or JavaScript/JSX (.js, .jsx) files."
                }

            try:
                with open(self.current_file_path, "r", encoding="utf-8") as file:
                    source_code = file.read()
                    lines = source_code.splitlines(True)  # Keep line endings

                # Process JavaScript/JSX files
                if is_javascript:
                    return self._find_js_function(function_name, source_code, lines)

                # For Python files, parse the source code to AST
                tree = ast.parse(source_code)

                # Find the function in the AST
                function_node = None
                class_node = None
                parent_function = None

                # Helper function to find a function or method node
                def find_node(node):
                    nonlocal function_node, class_node, parent_function
                    if isinstance(node, ast.FunctionDef) and node.name == function_name:
                        function_node = node
                        return True
                    # Check for methods in classes
                    elif isinstance(node, ast.ClassDef):
                        for item in node.body:
                            if (
                                isinstance(item, ast.FunctionDef)
                                and item.name == function_name
                            ):
                                function_node = item
                                class_node = node
                                return True
                    # Check for nested functions
                    elif isinstance(node, ast.FunctionDef):
                        for item in node.body:
                            # Find directly nested function definitions
                            if (
                                isinstance(item, ast.FunctionDef)
                                and item.name == function_name
                            ):
                                function_node = item
                                # Store parent function information
                                parent_function = node
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
                        if (
                            i > 0
                            and tokens[i - 1].type == tokenize.NAME
                            and tokens[i - 1].string == "def"
                        ):
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
                        if hasattr(node, "end_lineno") and node.end_lineno:
                            end_line = max(end_line, node.end_lineno)

                    # Specifically look for nested function definitions
                    # by checking for FunctionDef nodes within the function body
                    for node in ast.walk(function_node):
                        if (
                            isinstance(node, ast.FunctionDef)
                            and node is not function_node
                        ):
                            if hasattr(node, "end_lineno") and node.end_lineno:
                                end_line = max(end_line, node.end_lineno)
                else:
                    # Find the closing token of the function (either the next function/class at the same level or the end of file)
                    indent_level = tokens[function_def_index].start[
                        1
                    ]  # Get the indentation of the function
                    in_function = False
                    nested_level = 0
                    for token in tokens[function_def_index + 1 :]:
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
                                if (
                                    current_indent <= indent_level
                                    and token.type == tokenize.NAME
                                    and token.string in ("def", "class")
                                    and nested_level == 0
                                ):
                                    end_line = current_line - 1
                                    break
                                # Track nested blocks
                                elif (
                                    current_indent > indent_level
                                    and token.type == tokenize.NAME
                                ):
                                    if token.string in ("def", "class"):
                                        nested_level += 1
                                    # Look for the end of nested blocks
                                elif (
                                    nested_level > 0 and current_indent <= indent_level
                                ):
                                    nested_level -= 1

                    # If we couldn't find the end, use the last line of the file
                    if end_line == 0:
                        end_line = len(lines)

                # Include decorators if present
                for decorator in function_node.decorator_list:
                    start_line = min(start_line, decorator.lineno)

                # Adjust for methods inside classes
                if class_node:
                    class_body_start = min(
                        item.lineno
                        for item in class_node.body
                        if hasattr(item, "lineno")
                    )
                    if function_node.lineno == class_body_start:
                        # If this is the first method, include the class definition
                        start_line = class_node.lineno

                # Normalize line numbers (1-based for API consistency)
                function_lines = lines[start_line - 1 : end_line]

                # Format the results similar to the read tool
                formatted_lines = []
                for i, line in enumerate(function_lines, start_line):
                    formatted_lines.append((i, line.rstrip()))

                result = {
                    "status": "success",
                    "lines": formatted_lines,
                    "start_line": start_line,
                    "end_line": end_line,
                }

                # Add parent function information if this is a nested function
                if parent_function:
                    result["is_nested"] = True
                    result["parent_function"] = parent_function.name

                return result

            except Exception as e:
                return {"error": f"Error finding function: {str(e)}"}

        @self.mcp.tool()
        async def set_python_path(path: str):
            """
            Set it before running tests so the project is correctly recognized
            """
            os.environ["PYTHONPATH"] = path

        @self.mcp.tool()
        async def run_tests(
            test_path: Optional[str] = None,
            test_name: Optional[str] = None,
            verbose: bool = False,
            collect_only: bool = False,
        ) -> Dict[str, Any]:
            """
            Run pytest tests using the specified Python virtual environment.

            Args:
                test_path (str, optional): Directory or file path containing tests to run
                test_name (str, optional): Specific test function/method to run
                verbose (bool, optional): Run tests in verbose mode
                collect_only (bool, optional): Only collect tests without executing them

            Returns:
                dict: Test execution results including returncode, output, and execution time
            """
            if self.python_venv is None:
                return {
                    "error": "No Python environment found. It needs to be set in the MCP config as environment variable called PYTHON_VENV."
                }
            # Build pytest arguments
            pytest_args = []

            # Add test path if specified
            if test_path:
                pytest_args.append(test_path)

            # Add specific test name if specified
            if test_name:
                pytest_args.append(f"-k {test_name}")

            # Add verbosity flag if specified
            if verbose:
                pytest_args.append("-v")

            # Add collect-only flag if specified
            if collect_only:
                pytest_args.append("--collect-only")

            # Run the tests
            return self._run_tests(pytest_args)

    def _find_js_function(
        self, function_name: str, source_code: str, lines: list
    ) -> Dict[str, Any]:
        """
        Helper method to find JavaScript/JSX function definitions using Babel AST parsing.

        Args:
            function_name (str): Name of the function to find
            source_code (str): Source code content
            lines (list): Source code split by lines with line endings preserved

        Returns:
            dict: Dictionary with function information
        """
        try:
            # First try using Babel for accurate parsing if it's available
            if self.enable_js_syntax_check:
                babel_result = self._find_js_function_babel(
                    function_name, source_code, lines
                )
                if babel_result and not babel_result.get("error"):
                    return babel_result

            # Fallback to regex approach if Babel parsing fails or is disabled
            # Pattern for named function declaration
            # Matches: function functionName(args) { body }
            # Also matches: async function functionName(args) { body }
            function_pattern = re.compile(
                r"(?:async\s+)?function\s+(?P<functionName>\w+)\s*\((?P<functionArguments>[^()]*)\)\s*{",
                re.MULTILINE,
            )

            # Pattern for arrow functions with explicit name
            # Matches: const functionName = (args) => { body } or const functionName = args => { body }
            # Also matches async variants: const functionName = async (args) => { body }
            # Also matches component inner functions: const innerFunction = async () => { ... }
            arrow_pattern = re.compile(
                r"(?:(?:const|let|var)\s+)?(?P<functionName>\w+)\s*=\s*(?:async\s+)?(?:\((?P<functionArguments>[^()]*)\)|(?P<singleArg>\w+))\s*=>\s*{",
                re.MULTILINE,
            )

            # Pattern for object method definitions
            # Matches: functionName(args) { body } in object literals or classes
            # Also matches: async functionName(args) { body }
            method_pattern = re.compile(
                r"(?:^|,|{)\s*(?:async\s+)?(?P<functionName>\w+)\s*\((?P<functionArguments>[^()]*)\)\s*{",
                re.MULTILINE,
            )

            # Pattern for React hooks like useCallback, useEffect, etc.
            # Matches: const functionName = useCallback(async () => { ... }, [deps])
            hook_pattern = re.compile(
                r"const\s+(?P<functionName>\w+)\s*=\s*use\w+\((?:async\s+)?\(?[^{]*\)?\s*=>[^{]*{",
                re.MULTILINE,
            )

            # Search for the function
            matches = []

            # Check all patterns
            for pattern in [
                function_pattern,
                arrow_pattern,
                method_pattern,
                hook_pattern,
            ]:
                for match in pattern.finditer(source_code):
                    if match.groupdict().get("functionName") == function_name:
                        matches.append(match)

            if not matches:
                return {"error": f"Function '{function_name}' not found in the file."}

            # Use the first match
            match = matches[0]
            start_pos = match.start()

            # Find the line number for the start
            start_line = 1
            pos = 0
            for i, line in enumerate(lines, 1):
                next_pos = pos + len(line)
                if pos <= start_pos < next_pos:
                    start_line = i
                    break
                pos = next_pos

            # Find the closing brace that matches the opening brace of the function
            # Count the number of opening and closing braces
            brace_count = 0
            end_pos = start_pos
            in_string = False
            string_delimiter = None
            escaped = False

            for i in range(start_pos, len(source_code)):
                char = source_code[i]

                # Handle strings to avoid counting braces inside strings
                if not escaped and char in ['"', "'", "`"]:
                    if not in_string:
                        in_string = True
                        string_delimiter = char
                    elif char == string_delimiter:
                        in_string = False

                # Check for escape character
                if char == "\\" and not escaped:
                    escaped = True
                    continue

                escaped = False

                # Only count braces outside of strings
                if not in_string:
                    if char == "{":
                        brace_count += 1
                    elif char == "}":
                        brace_count -= 1
                        if brace_count == 0:
                            end_pos = i + 1  # Include the closing brace
                            break

            # Find the end line number
            end_line = 1
            pos = 0
            for i, line in enumerate(lines, 1):
                next_pos = pos + len(line)
                if pos <= end_pos < next_pos:
                    end_line = i
                    break
                pos = next_pos

            # Extract the function lines
            function_lines = lines[start_line - 1 : end_line]

            # Format results like the read tool
            formatted_lines = []
            for i, line in enumerate(function_lines, start_line):
                formatted_lines.append((i, line.rstrip()))

            result = {
                "status": "success",
                "lines": formatted_lines,
                "start_line": start_line,
                "end_line": end_line,
            }

            return result

        except Exception as e:
            return {"error": f"Error finding JavaScript function: {str(e)}"}

    def _find_js_function_babel(
        self, function_name: str, source_code: str, lines: list
    ) -> Dict[str, Any]:
        """
        Use Babel to parse JavaScript/JSX code and find function definitions.

        This provides more accurate function location by using proper AST parsing
        rather than regex pattern matching.

        Args:
            function_name (str): Name of the function to find
            source_code (str): Source code content
            lines (list): Source code split by lines with line endings preserved

        Returns:
            dict: Dictionary with function information or None if Babel fails
        """
        try:
            # Create a temporary file with the source code
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".jsx", delete=False
            ) as temp:
                temp_path = temp.name
                temp.write(source_code)

            # Determine the appropriate Babel preset
            is_jsx = self.current_file_path.endswith(".jsx")
            presets = ["@babel/preset-react"] if is_jsx else ["@babel/preset-env"]

            # Use Babel to output the AST as JSON
            cmd = [
                "npx",
                "babel",
                "--presets",
                ",".join(presets),
                "--plugins",
                # Add the AST plugin that outputs function locations
                "babel-plugin-ast-function-metadata",
                "--no-babelrc",
                temp_path,
                "--out-file",
                "/dev/null",  # Output to nowhere, we just want the AST metadata
            ]

            # Execute Babel to get the AST with function locations
            process = subprocess.run(cmd, capture_output=True, text=True)

            # Clean up the temporary file
            try:
                os.unlink(temp_path)
            except:
                pass

            # If Babel execution failed, return None to fall back to regex
            if process.returncode != 0:
                return None

            # Parse the output to find location data
            output = process.stdout
            # Look for the JSON that has our function location data
            location_data = None
            import json

            try:
                # Extract the JSON output from Babel plugin
                # Format is typically like: FUNCTION_LOCATIONS: {... json data ...}
                match = re.search(r"FUNCTION_LOCATIONS:\s*({.*})", output, re.DOTALL)
                if match:
                    json_str = match.group(1)
                    locations = json.loads(json_str)
                    # Find our specific function
                    location_data = locations.get(function_name)
            except (json.JSONDecodeError, AttributeError) as e:
                return None

            if not location_data:
                return None

            # Get the line information from the location data
            start_line = location_data.get("start", {}).get("line", 0)
            end_line = location_data.get("end", {}).get("line", 0)

            if start_line <= 0 or end_line <= 0:
                return None

            # Extract the function lines
            function_lines = lines[start_line - 1 : end_line]

            # Format results like the read tool
            formatted_lines = []
            for i, line in enumerate(function_lines, start_line):
                formatted_lines.append((i, line.rstrip()))

            result = {
                "status": "success",
                "lines": formatted_lines,
                "start_line": start_line,
                "end_line": end_line,
                "parser": "babel",  # Flag that this was parsed with Babel
            }

            return result

        except Exception as e:
            # If anything goes wrong, return None to fall back to regex approach
            return None

    def _run_tests(self, pytest_args=None, python_venv=None):
        """
        Run pytest tests using the specified Python virtual environment.

        Args:
            pytest_args (list, optional): List of arguments to pass to pytest
            python_venv (str, optional): Path to Python executable in virtual environment
                                     If not provided, uses PYTHON_VENV environment variable

        Returns:
            dict: Test execution results including returncode, output, and execution time
        """
        try:
            # Determine the Python executable to use
            python_venv = (
                python_venv or self.python_venv
            )  # Use the class level python_venv

            # If no venv is specified, use the system Python
            python_cmd = python_venv or "python"

            # Build the command to run pytest
            cmd = [python_cmd, "-m", "pytest"]

            # Add any additional pytest arguments
            if pytest_args:
                cmd.extend(pytest_args)

            # Record the start time
            start_time = datetime.datetime.now()

            # Run the pytest command
            process = subprocess.run(cmd, capture_output=True, text=True)

            # Record the end time and calculate duration
            end_time = datetime.datetime.now()
            duration = (end_time - start_time).total_seconds()

            # Return the results
            return {
                "status": "success" if process.returncode == 0 else "failure",
                "returncode": process.returncode,
                "stdout": process.stdout,
                "stderr": process.stderr,
                "duration": duration,
                "command": " ".join(cmd),
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "command": " ".join(cmd) if "cmd" in locals() else None,
            }

    def run(self, transport="stdio", **transport_kwargs):
        """Run the MCP server."""
        self.mcp.run(transport=transport, **transport_kwargs)


def main():
    """Entry point for the application.

    This function is used both for direct execution and
    when the package is installed via UVX, allowing the
    application to be run using the `editor-mcp` command.
    """

    parser = argparse.ArgumentParser(description="Text Editor MCP Server")
    parser.add_argument(
        "--transport",
        default="stdio",
        choices=["stdio", "http", "streamable-http"],
        help="Transport type",
    )
    parser.add_argument(
        "--host", default="127.0.0.1", help="Host to bind to (for HTTP transport)"
    )
    parser.add_argument(
        "--port", type=int, default=8001, help="Port to bind to (for HTTP transport)"
    )
    parser.add_argument(
        "--path", default="/mcp", help="Path for HTTP endpoint (for HTTP transport)"
    )

    args = parser.parse_args()

    host = os.environ.get("FASTMCP_SERVER_HOST", args.host)
    port = int(os.environ.get("FASTMCP_SERVER_PORT", args.port))
    path = os.environ.get("FASTMCP_SERVER_PATH", args.path)
    transport = os.environ.get("FASTMCP_SERVER_TRANSPORT", args.transport)

    # Normalize transport name for FastMCP
    if transport in ["http", "streamable-http"]:
        transport = "streamable-http"

    # Run the server with the configured transport
    if transport == "streamable-http":
        text_editor_server.run(transport=transport, host=host, port=port, path=path)
    else:
        text_editor_server.run(transport=transport)


text_editor_server = TextEditorServer()
mcp = text_editor_server.mcp
if __name__ == "__main__":
    main()
