import os
import pytest
import tempfile
import hashlib

from src.text_editor.server import TextEditorServer, calculate_id


class TestTextEditorServer:
    @pytest.fixture
    def server(self):
        """Create a TextEditorServer instance for testing."""
        server = TextEditorServer()
        server.max_edit_lines = 200
        return server

    @pytest.fixture
    def temp_file(self):
        """Create a temporary file for testing."""
        content = "Line 1\nLine 2\nLine 3\nLine 4\nLine 5\n"
        with tempfile.NamedTemporaryFile(mode="w+", delete=False) as f:
            f.write(content)
            temp_path = f.name

        yield temp_path

        if os.path.exists(temp_path):
            os.unlink(temp_path)

    @pytest.fixture
    def empty_temp_file(self):
        """Create an empty temporary file for testing."""
        with tempfile.NamedTemporaryFile(mode="w+", delete=False) as f:
            temp_path = f.name

        yield temp_path

        if os.path.exists(temp_path):
            os.unlink(temp_path)

    def get_tool_fn(self, server, tool_name):
        """Helper to get the tool function from the server."""

        tools_dict = server.mcp._tool_manager._tools
        return tools_dict[tool_name].fn

    @pytest.mark.asyncio
    async def test_set_file_valid(self, server, temp_file):
        """Test setting a valid file path."""
        set_file_fn = self.get_tool_fn(server, "set_file")

        result = await set_file_fn(temp_file)

        assert "File set to:" in result
        assert temp_file in result
        assert server.current_file_path == temp_file

    @pytest.mark.asyncio
    async def test_set_file_invalid(self, server):
        """Test setting a non-existent file path."""
        set_file_fn = self.get_tool_fn(server, "set_file")

        non_existent_path = "/path/to/nonexistent/file.txt"
        result = await set_file_fn(non_existent_path)

        assert "Error: File not found" in result
        assert server.current_file_path is None

    @pytest.mark.asyncio
    async def test_read_no_file_set(self, server):
        """Test getting text when no file is set."""
        read_fn = self.get_tool_fn(server, "read")

        result = await read_fn(1, 10)

        assert "error" in result
        assert "No file path is set" in result["error"]

    @pytest.mark.asyncio
    async def test_read_entire_file(self, server, temp_file):
        """Test getting the entire content of a file."""
        set_file_fn = self.get_tool_fn(server, "set_file")
        await set_file_fn(temp_file)

        read_fn = self.get_tool_fn(server, "read")
        result = await read_fn(1, 5)

        assert "text" in result
        assert "Line 1\nLine 2\nLine 3\nLine 4\nLine 5\n" == result["text"]
        assert "id" in result

    async def test_read_line_range(self, server, temp_file):
        """Test getting a specific range of lines from a file."""

        set_file_fn = self.get_tool_fn(server, "set_file")
        await set_file_fn(temp_file)

        read_fn = self.get_tool_fn(server, "read")
        result = await read_fn(2, 4)

        assert "text" in result
        assert "id" in result
        assert "Line 2\nLine 3\nLine 4\n" == result["text"]

        expected_id = calculate_id("Line 2\nLine 3\nLine 4\n", 2, 4)
        assert expected_id == result["id"]

    @pytest.mark.asyncio
    async def test_read_only_end_line(self, server, temp_file):
        """Test getting text with only end line specified."""
        set_file_fn = self.get_tool_fn(server, "set_file")
        await set_file_fn(temp_file)

        read_fn = self.get_tool_fn(server, "read")
        result = await read_fn(1, 2)
        expected_id = calculate_id("Line 1\nLine 2\n", 1, 2)
        assert expected_id == result["id"]

    @pytest.mark.asyncio
    async def test_read_invalid_range(self, server, temp_file):
        """Test getting text with an invalid line range."""
        set_file_fn = self.get_tool_fn(server, "set_file")
        await set_file_fn(temp_file)

        read_fn = self.get_tool_fn(server, "read")

        result = await read_fn(4, 2)
        assert "error" in result
        assert "start cannot be greater than end" in result["error"]

        result = await read_fn(0, 3)
        assert "error" in result
        assert "start must be at least 1" in result["error"]

    @pytest.mark.asyncio
    async def test_read_range_exceeding_file(self, server, temp_file):
        """Test getting a line range that exceeds the file's line count."""
        set_file_fn = self.get_tool_fn(server, "set_file")
        await set_file_fn(temp_file)

        read_fn = self.get_tool_fn(server, "read")
        result = await read_fn(3, 10)

        assert "Line 3\nLine 4\nLine 5\n" == result["text"]

    def test_calculate_id_function(self):
        """Test the calculate_id function directly."""

        text = "Some test content"
        id_no_range = calculate_id(text)
        expected = hashlib.sha256(text.encode()).hexdigest()[:2]
        assert id_no_range == expected

        id_with_range = calculate_id(text, 1, 3)
        assert id_with_range.startswith("L1-3-")
        assert id_with_range.endswith(expected)

    @pytest.mark.asyncio
    async def test_read_large_file(self, server):
        """Test getting text from a file larger than MAX_EDIT_LINES lines."""
        more_than_max_lines = server.max_edit_lines + 10
        with tempfile.NamedTemporaryFile(mode="w+", delete=False) as f:
            for i in range(more_than_max_lines):
                f.write(f"Line {i + 1}\n")
            large_file_path = f.name

        try:
            set_file_fn = self.get_tool_fn(server, "set_file")
            await set_file_fn(large_file_path)

            read_fn = self.get_tool_fn(server, "read")
            result = await read_fn(1, more_than_max_lines)

            assert "text" in result
            assert (
                f"len(selected_lines)={more_than_max_lines} > self.max_edit_lines={server.max_edit_lines} so no id."
                in result["info"]
            )
            assert len(result["text"].splitlines()) == more_than_max_lines

            result = await read_fn(5, 15)

            assert "text" in result
            assert "id" in result
            assert len(result["text"].splitlines()) == 11

            result = await read_fn(5, server.max_edit_lines + 10)

            assert "text" in result
            assert "id" not in result
            assert len(result["text"].splitlines()) == server.max_edit_lines + 6

        finally:
            if os.path.exists(large_file_path):
                os.unlink(large_file_path)

    @pytest.mark.asyncio
    async def test_new_file(self, server, empty_temp_file):
        """Test new_file functionality."""

        set_file_fn = self.get_tool_fn(server, "set_file")
        await set_file_fn(empty_temp_file)

        new_file_fn = self.get_tool_fn(server, "new_file")
        result = await new_file_fn(empty_temp_file)

        assert result["status"] == "success"
        assert "id" in result

        result = await new_file_fn(empty_temp_file)
        assert "error" in result

    @pytest.mark.asyncio
    async def test_delete_file(self, server):
        """Test delete_file tool."""

        with tempfile.NamedTemporaryFile(mode="w+", delete=False) as f:
            f.write("Test content to delete")
            temp_path = f.name

        try:
            delete_file_fn = self.get_tool_fn(server, "delete_file")
            result = await delete_file_fn()
            assert "error" in result
            assert "No file path is set" in result["error"]

            set_file_fn = self.get_tool_fn(server, "set_file")
            await set_file_fn(temp_path)

            result = await delete_file_fn()
            assert result["status"] == "success"
            assert "successfully deleted" in result["message"]
            assert temp_path in result["message"]

            assert not os.path.exists(temp_path)

            assert server.current_file_path is None

            result = await set_file_fn(temp_path)
            assert "Error: File not found" in result

            assert server.current_file_path is None

        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_delete_file_permission_error(self, server, monkeypatch):
        """Test delete_file with permission error."""

        with tempfile.NamedTemporaryFile(mode="w+", delete=False) as f:
            f.write("Test content")
            temp_path = f.name

        try:
            set_file_fn = self.get_tool_fn(server, "set_file")
            await set_file_fn(temp_path)

            def mock_remove(path):
                raise PermissionError("Permission denied")

            monkeypatch.setattr(os, "remove", mock_remove)

            delete_file_fn = self.get_tool_fn(server, "delete_file")
            result = await delete_file_fn()

            assert "error" in result
            assert "Permission denied" in result["error"]

            assert server.current_file_path == temp_path

        finally:
            monkeypatch.undo()
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_find_line_no_file_set(self, server):
        """Test find_line with no file set."""
        find_line_fn = self.get_tool_fn(server, "find_line")

        result = await find_line_fn(search_text="Line")

        assert "error" in result
        assert "No file path is set" in result["error"]

    @pytest.mark.asyncio
    async def test_find_line_basic(self, server, temp_file):
        """Test basic find_line functionality."""
        set_file_fn = self.get_tool_fn(server, "set_file")
        await set_file_fn(temp_file)

        find_line_fn = self.get_tool_fn(server, "find_line")

        # Search for a common term that should be in all lines
        result = await find_line_fn(search_text="Line")

        assert "status" in result
        assert result["status"] == "success"
        assert "matches" in result
        assert "total_matches" in result
        assert result["total_matches"] == 5

        # Verify structure of the matches
        for match in result["matches"]:
            assert "line_number" in match
            assert "id" in match
            assert "text" in match
            assert f"Line {match['line_number']}" in match["text"]

        # Verify the line numbers are sequential
        line_numbers = [match["line_number"] for match in result["matches"]]
        assert line_numbers == [1, 2, 3, 4, 5]

    @pytest.mark.asyncio
    async def test_find_line_specific_match(self, server, temp_file):
        """Test find_line with a specific search term."""
        set_file_fn = self.get_tool_fn(server, "set_file")
        await set_file_fn(temp_file)

        find_line_fn = self.get_tool_fn(server, "find_line")

        # Search for a term that should only be in one line
        result = await find_line_fn(search_text="Line 3")

        assert result["status"] == "success"
        assert result["total_matches"] == 1
        assert len(result["matches"]) == 1
        assert result["matches"][0]["line_number"] == 3
        assert "Line 3" in result["matches"][0]["text"]

    @pytest.mark.asyncio
    async def test_find_line_no_matches(self, server, temp_file):
        """Test find_line with a search term that doesn't exist."""
        set_file_fn = self.get_tool_fn(server, "set_file")
        await set_file_fn(temp_file)

        find_line_fn = self.get_tool_fn(server, "find_line")

        # Search for a non-existent term
        result = await find_line_fn(search_text="NonExistentTerm")

        assert result["status"] == "success"
        assert result["total_matches"] == 0
        assert len(result["matches"]) == 0

    @pytest.mark.asyncio
    async def test_find_line_file_read_error(self, server, temp_file, monkeypatch):
        """Test find_line with a file read error."""
        set_file_fn = self.get_tool_fn(server, "set_file")
        await set_file_fn(temp_file)

        # Mock open to raise an exception
        def mock_open(*args, **kwargs):
            raise IOError("Mock file read error")

        monkeypatch.setattr("builtins.open", mock_open)

        find_line_fn = self.get_tool_fn(server, "find_line")
        result = await find_line_fn(search_text="Line")

        assert "error" in result
        assert "Error searching file" in result["error"]
        assert "Mock file read error" in result["error"]

    @pytest.mark.asyncio
    async def test_overwrite_no_file_set(self, server):
        """Test overwrite when no file is set."""
        overwrite_fn = self.get_tool_fn(server, "overwrite")

        result = await overwrite_fn(text="New content", start=1, end=2, id="some-id")

        assert "error" in result
        assert "No file path is set" in result["error"]

    @pytest.mark.asyncio
    async def test_overwrite_basic(self, server, temp_file):
        """Test basic overwrite functionality."""
        set_file_fn = self.get_tool_fn(server, "set_file")
        await set_file_fn(temp_file)

        # First read the content to get the ID
        read_fn = self.get_tool_fn(server, "read")
        read_result = await read_fn(2, 4)

        # Now overwrite lines 2-4
        overwrite_fn = self.get_tool_fn(server, "overwrite")
        new_content = "New Line 2\nNew Line 3\nNew Line 4\n"
        result = await overwrite_fn(
            text=new_content, start=2, end=4, id=read_result["id"]
        )

        assert "status" in result
        assert result["status"] == "success"
        assert "Text overwritten from line 2 to 4" in result["message"]

        # Verify the file was actually modified
        with open(temp_file, "r") as f:
            file_content = f.read()

        expected_content = "Line 1\nNew Line 2\nNew Line 3\nNew Line 4\nLine 5\n"
        assert file_content == expected_content

    @pytest.mark.asyncio
    async def test_overwrite_invalid_range(self, server, temp_file):
        """Test overwrite with invalid line ranges."""
        set_file_fn = self.get_tool_fn(server, "set_file")
        await set_file_fn(temp_file)

        overwrite_fn = self.get_tool_fn(server, "overwrite")

        # Test with start < 1
        result = await overwrite_fn(text="New content", start=0, end=2, id="some-id")
        assert "error" in result
        assert "line_start must be at least 1" in result["error"]

        # Test with end > file length
        result = await overwrite_fn(text="New content", start=1, end=10, id="some-id")
        assert "error" in result
        assert "line_end (10) exceeds file length" in result["error"]

        # Test with start > end
        result = await overwrite_fn(text="New content", start=4, end=2, id="some-id")
        assert "error" in result
        assert "line_start cannot be greater than line_end" in result["error"]

    @pytest.mark.asyncio
    async def test_overwrite_id_verification_failed(self, server, temp_file):
        """Test overwrite with incorrect ID (content verification failure)."""
        set_file_fn = self.get_tool_fn(server, "set_file")
        await set_file_fn(temp_file)

        overwrite_fn = self.get_tool_fn(server, "overwrite")

        # Use an incorrect ID
        result = await overwrite_fn(
            text="New content", start=2, end=3, id="incorrect-id"
        )

        assert "error" in result
        assert "id verification failed" in result["error"]

    @pytest.mark.asyncio
    async def test_overwrite_different_line_count(self, server, temp_file):
        """Test overwrite with different line count (more or fewer lines)."""
        set_file_fn = self.get_tool_fn(server, "set_file")
        await set_file_fn(temp_file)

        # First read the content to get the ID
        read_fn = self.get_tool_fn(server, "read")
        read_result = await read_fn(2, 3)

        # Replace 2 lines with 3 lines
        overwrite_fn = self.get_tool_fn(server, "overwrite")
        new_content = "New Line 2\nExtra Line\nNew Line 3\n"
        result = await overwrite_fn(
            text=new_content, start=2, end=3, id=read_result["id"]
        )

        assert result["status"] == "success"

        # Verify the file content
        with open(temp_file, "r") as f:
            file_content = f.read()

        expected_content = (
            "Line 1\nNew Line 2\nExtra Line\nNew Line 3\nLine 4\nLine 5\n"
        )
        assert file_content == expected_content

        # Now read again for new ID
        read_result = await read_fn(1, 6)

        # Replace 6 lines with 1 line
        new_content = "Single Line\n"
        result = await overwrite_fn(
            text=new_content, start=1, end=6, id=read_result["id"]
        )

        assert result["status"] == "success"

        # Verify the file content
        with open(temp_file, "r") as f:
            file_content = f.read()

        assert file_content == "Single Line\n"

    @pytest.mark.asyncio
    async def test_overwrite_empty_text(self, server, temp_file):
        """Test overwrite with empty text (effectively removing lines)."""
        set_file_fn = self.get_tool_fn(server, "set_file")
        await set_file_fn(temp_file)

        # First read the content to get the ID
        read_fn = self.get_tool_fn(server, "read")
        read_result = await read_fn(2, 3)

        # Replace with empty string (remove lines 2-3)
        overwrite_fn = self.get_tool_fn(server, "overwrite")
        result = await overwrite_fn(text="", start=2, end=3, id=read_result["id"])

        assert result["status"] == "success"

        # Verify the file content
        with open(temp_file, "r") as f:
            file_content = f.read()

        expected_content = "Line 1\nLine 4\nLine 5\n"
        assert file_content == expected_content

    @pytest.mark.asyncio
    async def test_overwrite_max_lines_exceeded(self, server, temp_file):
        """Test overwrite with a range exceeding max_edit_lines."""
        set_file_fn = self.get_tool_fn(server, "set_file")
        await set_file_fn(temp_file)

        # Create a temporary file with more than max_edit_lines
        more_than_max_lines = server.max_edit_lines + 10
        with tempfile.NamedTemporaryFile(mode="w+", delete=False) as f:
            for i in range(more_than_max_lines):
                f.write(f"Line {i + 1}\n")
            large_file_path = f.name

        try:
            await set_file_fn(large_file_path)

            overwrite_fn = self.get_tool_fn(server, "overwrite")
            result = await overwrite_fn(
                text="New content", start=1, end=server.max_edit_lines + 1, id="some-id"
            )

            assert "error" in result
            assert (
                f"Cannot overwrite more than {server.max_edit_lines} lines at once"
                in result["error"]
            )

        finally:
            if os.path.exists(large_file_path):
                os.unlink(large_file_path)

    @pytest.mark.asyncio
    async def test_overwrite_file_read_error(self, server, temp_file, monkeypatch):
        """Test overwrite with file read error."""
        set_file_fn = self.get_tool_fn(server, "set_file")
        await set_file_fn(temp_file)

        # Mock open to raise an exception during read
        original_open = open

        def mock_open_read(*args, **kwargs):
            if args[1] == "r":
                raise IOError("Mock file read error")
            return original_open(*args, **kwargs)

        monkeypatch.setattr("builtins.open", mock_open_read)

        overwrite_fn = self.get_tool_fn(server, "overwrite")
        result = await overwrite_fn(text="New content", start=1, end=3, id="some-id")

        assert "error" in result
        assert "Error reading file" in result["error"]
        assert "Mock file read error" in result["error"]

    @pytest.mark.asyncio
    async def test_overwrite_file_write_error(self, server, temp_file, monkeypatch):
        """Test overwrite with file write error."""
        set_file_fn = self.get_tool_fn(server, "set_file")
        await set_file_fn(temp_file)

        # First read the content to get the ID
        read_fn = self.get_tool_fn(server, "read")
        read_result = await read_fn(2, 3)

        # Mock open for writing to raise an exception
        original_open = open
        open_calls = [0]

        def mock_open_write(*args, **kwargs):
            if args[1] == "w":
                raise IOError("Mock file write error")
            return original_open(*args, **kwargs)

        monkeypatch.setattr("builtins.open", mock_open_write)

        overwrite_fn = self.get_tool_fn(server, "overwrite")
        result = await overwrite_fn(
            text="New content", start=2, end=3, id=read_result["id"]
        )

        assert "error" in result
        assert "Error writing to file" in result["error"]
        assert "Mock file write error" in result["error"]

    @pytest.mark.asyncio
    async def test_overwrite_newline_handling(self, server):
        """Test newline handling in overwrite (appends newline when needed)."""
        # Create a file with text that doesn't end with a newline
        with tempfile.NamedTemporaryFile(mode="w+", delete=False) as f:
            f.write("Line 1\nLine 2\nLine 3")  # No trailing newline
            temp_path = f.name

        try:
            set_file_fn = self.get_tool_fn(server, "set_file")
            await set_file_fn(temp_path)

            # First read the content to get the ID
            read_fn = self.get_tool_fn(server, "read")
            read_result = await read_fn(2, 2)

            # Replace line 2
            overwrite_fn = self.get_tool_fn(server, "overwrite")
            result = await overwrite_fn(
                text="New Line 2",  # No trailing newline
                start=2,
                end=2,
                id=read_result["id"],
            )

            assert result["status"] == "success"

            # Verify the file content, should add newline
            with open(temp_path, "r") as f:
                file_content = f.read()

            expected_content = "Line 1\nNew Line 2\nLine 3"
            assert file_content == expected_content

        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_overwrite_python_syntax_check_success(self, server):
        """Test Python syntax checking in overwrite succeeds with valid Python code."""
        # Create a temporary Python file with valid code
        valid_python_content = (
            "def hello():\n    print('Hello, world!')\n\nresult = hello()\n"
        )
        with tempfile.NamedTemporaryFile(mode="w+", suffix=".py", delete=False) as f:
            f.write(valid_python_content)
            py_file_path = f.name

        try:
            set_file_fn = self.get_tool_fn(server, "set_file")
            await set_file_fn(py_file_path)

            read_fn = self.get_tool_fn(server, "read")
            read_result = await read_fn(1, 4)

            # Modify with valid Python code
            overwrite_fn = self.get_tool_fn(server, "overwrite")
            new_content = "def greeting(name):\n    return f'Hello, {name}!'\n\nresult = greeting('World')\n"
            result = await overwrite_fn(
                text=new_content, start=1, end=4, id=read_result["id"]
            )

            assert result["status"] == "success"
            assert "Text overwritten" in result["message"]

            # Verify the file was updated
            with open(py_file_path, "r") as f:
                file_content = f.read()

            assert file_content == new_content

        finally:
            if os.path.exists(py_file_path):
                os.unlink(py_file_path)

    @pytest.mark.asyncio
    async def test_overwrite_python_syntax_check_failure(self, server):
        """Test Python syntax checking in overwrite fails with invalid Python code."""
        # Create a temporary Python file with valid code
        valid_python_content = (
            "def hello():\n    print('Hello, world!')\n\nresult = hello()\n"
        )
        with tempfile.NamedTemporaryFile(mode="w+", suffix=".py", delete=False) as f:
            f.write(valid_python_content)
            py_file_path = f.name

        try:
            set_file_fn = self.get_tool_fn(server, "set_file")
            await set_file_fn(py_file_path)

            read_fn = self.get_tool_fn(server, "read")
            read_result = await read_fn(1, 4)

            # Try to replace with invalid Python code (syntax error)
            overwrite_fn = self.get_tool_fn(server, "overwrite")
            invalid_python = "def broken_function(:\n    print('Missing parenthesis'\n\nresult = broken_function()\n"
            result = await overwrite_fn(
                text=invalid_python, start=1, end=4, id=read_result["id"]
            )

            assert "error" in result
            assert "Python syntax error:" in result["error"]

            # Verify the file was not modified
            with open(py_file_path, "r") as f:
                file_content = f.read()

            assert file_content == valid_python_content  # File should remain unchanged

        finally:
            if os.path.exists(py_file_path):
                os.unlink(py_file_path)

    @pytest.mark.asyncio
    async def test_overwrite_javascript_syntax_check_success(self, server, monkeypatch):
        """Test JavaScript syntax checking in overwrite succeeds with valid JS code."""
        # Create a temporary JS file with valid code
        valid_js_content = "function hello() {\n  return 'Hello, world!';\n}\n\nconst result = hello();\n"
        with tempfile.NamedTemporaryFile(mode="w+", suffix=".js", delete=False) as f:
            f.write(valid_js_content)
            js_file_path = f.name

        # Mock the subprocess.run to simulate successful Babel execution
        def mock_subprocess_run(*args, **kwargs):
            class MockCompletedProcess:
                def __init__(self):
                    self.returncode = 0
                    self.stderr = ""
                    self.stdout = ""

            return MockCompletedProcess()

        monkeypatch.setattr("subprocess.run", mock_subprocess_run)

        try:
            set_file_fn = self.get_tool_fn(server, "set_file")
            await set_file_fn(js_file_path)

            read_fn = self.get_tool_fn(server, "read")
            read_result = await read_fn(1, 5)

            # Modify with valid JavaScript code
            overwrite_fn = self.get_tool_fn(server, "overwrite")
            new_js_content = "function greeting(name) {\n  return `Hello, ${name}!`;\n}\n\nconst result = greeting('World');\n"
            result = await overwrite_fn(
                text=new_js_content, start=1, end=5, id=read_result["id"]
            )

            assert result["status"] == "success"
            assert "Text overwritten" in result["message"]

            # Verify the file was updated
            with open(js_file_path, "r") as f:
                file_content = f.read()

            assert file_content == new_js_content

        finally:
            if os.path.exists(js_file_path):
                os.unlink(js_file_path)

    @pytest.mark.asyncio
    async def test_overwrite_javascript_syntax_check_failure(self, server, monkeypatch):
        """Test JavaScript syntax checking in overwrite fails with invalid JS code."""
        # Create a temporary JS file with valid code
        valid_js_content = "function hello() {\n  return 'Hello, world!';\n}\n\nconst result = hello();\n"
        with tempfile.NamedTemporaryFile(mode="w+", suffix=".js", delete=False) as f:
            f.write(valid_js_content)
            js_file_path = f.name

        # Mock the subprocess.run to simulate Babel execution failure
        def mock_subprocess_run(*args, **kwargs):
            class MockCompletedProcess:
                def __init__(self):
                    self.returncode = 1
                    self.stderr = "SyntaxError: Unexpected token (1:19)"
                    self.stdout = ""

            return MockCompletedProcess()

        monkeypatch.setattr("subprocess.run", mock_subprocess_run)

        try:
            set_file_fn = self.get_tool_fn(server, "set_file")
            await set_file_fn(js_file_path)

            read_fn = self.get_tool_fn(server, "read")
            read_result = await read_fn(1, 5)

            # Try to replace with invalid JavaScript code
            overwrite_fn = self.get_tool_fn(server, "overwrite")
            invalid_js = "function broken() {\n  return 'Missing closing bracket;\n}\n\nconst result = broken();\n"
            result = await overwrite_fn(
                text=invalid_js, start=1, end=5, id=read_result["id"]
            )

            assert "error" in result
            assert "JavaScript syntax error:" in result["error"]

            # Verify the file was not modified
            with open(js_file_path, "r") as f:
                file_content = f.read()

            assert file_content == valid_js_content  # File should remain unchanged

        finally:
            if os.path.exists(js_file_path):
                os.unlink(js_file_path)

    @pytest.mark.asyncio
    async def test_overwrite_jsx_syntax_check_success(self, server, monkeypatch):
        """Test JSX syntax checking in overwrite succeeds with valid React/JSX code."""
        # Create a temporary JSX file with valid code
        valid_jsx_content = "import React from 'react';\n\nfunction HelloWorld() {\n  return <div>Hello, world!</div>;\n}\n\nexport default HelloWorld;\n"
        with tempfile.NamedTemporaryFile(mode="w+", suffix=".jsx", delete=False) as f:
            f.write(valid_jsx_content)
            jsx_file_path = f.name

        # Mock the subprocess.run to simulate successful Babel execution
        def mock_subprocess_run(*args, **kwargs):
            class MockCompletedProcess:
                def __init__(self):
                    self.returncode = 0
                    self.stderr = ""
                    self.stdout = ""

            return MockCompletedProcess()

        monkeypatch.setattr("subprocess.run", mock_subprocess_run)

        try:
            set_file_fn = self.get_tool_fn(server, "set_file")
            await set_file_fn(jsx_file_path)

            read_fn = self.get_tool_fn(server, "read")
            read_result = await read_fn(1, 7)

            # Modify with valid JSX code
            overwrite_fn = self.get_tool_fn(server, "overwrite")
            new_jsx_content = "import React from 'react';\n\nfunction Greeting({ name }) {\n  return <div>Hello, {name}!</div>;\n}\n\nexport default Greeting;\n"
            result = await overwrite_fn(
                text=new_jsx_content, start=1, end=7, id=read_result["id"]
            )

            assert result["status"] == "success"
            assert "Text overwritten" in result["message"]

            # Verify the file was updated
            with open(jsx_file_path, "r") as f:
                file_content = f.read()

            assert file_content == new_jsx_content

        finally:
            if os.path.exists(jsx_file_path):
                os.unlink(jsx_file_path)

    @pytest.mark.asyncio
    async def test_overwrite_jsx_syntax_check_failure(self, server, monkeypatch):
        """Test JSX syntax checking in overwrite fails with invalid React/JSX code."""
        # Create a temporary JSX file with valid code
        valid_jsx_content = "import React from 'react';\n\nfunction HelloWorld() {\n  return <div>Hello, world!</div>;\n}\n\nexport default HelloWorld;\n"
        with tempfile.NamedTemporaryFile(mode="w+", suffix=".jsx", delete=False) as f:
            f.write(valid_jsx_content)
            jsx_file_path = f.name

        # Mock the subprocess.run to simulate Babel execution failure
        def mock_subprocess_run(*args, **kwargs):
            class MockCompletedProcess:
                def __init__(self):
                    self.returncode = 1
                    self.stderr = "SyntaxError: Unexpected token (4:10)"
                    self.stdout = ""

            return MockCompletedProcess()

        monkeypatch.setattr("subprocess.run", mock_subprocess_run)

        try:
            set_file_fn = self.get_tool_fn(server, "set_file")
            await set_file_fn(jsx_file_path)

            read_fn = self.get_tool_fn(server, "read")
            read_result = await read_fn(1, 7)

            # Try to replace with invalid JSX code
            overwrite_fn = self.get_tool_fn(server, "overwrite")
            invalid_jsx = "import React from 'react';\n\nfunction BrokenComponent() {\n  return <div>Missing closing tag<div>;\n}\n\nexport default BrokenComponent;\n"
            result = await overwrite_fn(
                text=invalid_jsx, start=1, end=7, id=read_result["id"]
            )

            assert "error" in result
            assert "JavaScript syntax error:" in result["error"]

            # Verify the file was not modified
            with open(jsx_file_path, "r") as f:
                file_content = f.read()

            assert file_content == valid_jsx_content  # File should remain unchanged

        finally:
            if os.path.exists(jsx_file_path):
                os.unlink(jsx_file_path)
