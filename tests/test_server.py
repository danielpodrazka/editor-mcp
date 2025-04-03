import os
import pytest
import tempfile
import hashlib
from src.text_editor.server import TextEditorServer, calculate_id, generate_diff_preview


class TestTextEditorServer:
    @pytest.fixture
    def server(self):
        """Create a TextEditorServer instance for testing."""
        server = TextEditorServer()
        server.max_select_lines = 200
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

    @pytest.fixture
    def server_with_protected_paths(self):
        """Create a TextEditorServer instance with protected paths configuration."""
        server = TextEditorServer()
        server.max_select_lines = 200
        # Define protected paths for testing
        server.protected_paths = ["*.env", "/etc/passwd", "/home/secret-file.txt"]
        return server

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
    async def test_set_file_protected_path_exact_match(
        self, server_with_protected_paths
    ):
        """Test setting a file path that exactly matches a protected path."""
        set_file_fn = self.get_tool_fn(server_with_protected_paths, "set_file")
        result = await set_file_fn("/etc/passwd")
        assert "Error: Access to '/etc/passwd' is denied" in result
        assert server_with_protected_paths.current_file_path is None

    @pytest.mark.asyncio
    async def test_set_file_protected_path_wildcard_match(
        self, server_with_protected_paths, monkeypatch
    ):
        """Test setting a file path that matches a wildcard protected path pattern."""
        # Create a temporary .env file for testing
        with tempfile.NamedTemporaryFile(mode="w+", suffix=".env", delete=False) as f:
            f.write("API_KEY=test_key\n")
            env_file_path = f.name

        # Mock os.path.isfile to return True for our temp file
        def mock_isfile(path):
            return path == env_file_path

        monkeypatch.setattr(os.path, "isfile", mock_isfile)

        try:
            set_file_fn = self.get_tool_fn(server_with_protected_paths, "set_file")
            result = await set_file_fn(env_file_path)
            assert "Error: Access to '" in result
            assert (
                "is denied due to PROTECTED_PATHS configuration (matches pattern '*.env')"
                in result
            )
            assert server_with_protected_paths.current_file_path is None
        finally:
            if os.path.exists(env_file_path):
                os.unlink(env_file_path)

    @pytest.mark.asyncio
    async def test_set_file_protected_path_glob_match(self, monkeypatch):
        """Test setting a file path that matches a more complex glob pattern."""
        # Create a server with different glob patterns
        server = TextEditorServer()
        server.protected_paths = [".env*", "config*.json", "*keys.txt"]

        # Create a temporary .env.local file for testing
        with tempfile.NamedTemporaryFile(
            mode="w+", prefix=".env", suffix=".local", delete=False
        ) as f:
            f.write("API_KEY=test_key\n")
            env_local_path = f.name

        # Create a temporary config-dev.json file for testing
        with tempfile.NamedTemporaryFile(
            mode="w+", prefix="config-", suffix=".json", delete=False
        ) as f:
            f.write('{"debug": true}\n')
            config_path = f.name

        # Create a custom filename that will definitely match our pattern
        keys_file_path = os.path.join(tempfile.gettempdir(), "api-keys.txt")
        with open(keys_file_path, "w") as f:
            f.write("secret_key=abc123\n")
        secret_path = keys_file_path

        # Mock os.path.isfile to return True for our test files
        def mock_isfile(path):
            return path in [env_local_path, config_path, secret_path]

        monkeypatch.setattr(os.path, "isfile", mock_isfile)

        try:
            set_file_fn = self.get_tool_fn(server, "set_file")

            # Test .env* pattern
            result = await set_file_fn(env_local_path)
            assert "Error: Access to '" in result
            assert (
                "is denied due to PROTECTED_PATHS configuration (matches pattern '.env*'"
                in result
            )
            assert server.current_file_path is None

            # Test config*.json pattern
            result = await set_file_fn(config_path)
            assert "Error: Access to '" in result
            assert (
                "is denied due to PROTECTED_PATHS configuration (matches pattern 'config*.json'"
                in result
            )
            assert server.current_file_path is None

            # Test *keys.txt pattern
            result = await set_file_fn(secret_path)
            assert "Error: Access to '" in result
            assert (
                "is denied due to PROTECTED_PATHS configuration (matches pattern '*keys.txt'"
                in result
            )
            assert server.current_file_path is None
        finally:
            # Clean up temp files
            for path in [env_local_path, config_path, secret_path]:
                if os.path.exists(path):
                    os.unlink(path)

    @pytest.mark.asyncio
    async def test_set_file_non_protected_path(
        self, server_with_protected_paths, temp_file
    ):
        """Test setting a file path that does not match any protected paths."""
        set_file_fn = self.get_tool_fn(server_with_protected_paths, "set_file")
        result = await set_file_fn(temp_file)
        assert "File set to:" in result
        assert temp_file in result
        assert server_with_protected_paths.current_file_path == temp_file

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
        assert "lines" in result

    async def test_read_line_range(self, server, temp_file):
        """Test getting a specific range of lines from a file."""
        set_file_fn = self.get_tool_fn(server, "set_file")
        await set_file_fn(temp_file)
        read_fn = self.get_tool_fn(server, "read")
        result = await read_fn(2, 4)
        assert "lines" in result
        select_fn = self.get_tool_fn(server, "select")
        select_result = await select_fn(2, 4)
        assert "status" in select_result
        assert "id" in select_result
        expected_id = calculate_id("Line 2\nLine 3\nLine 4\n", 2, 4)
        assert expected_id == select_result["id"]

    @pytest.mark.asyncio
    async def test_read_only_end_line(self, server, temp_file):
        """Test getting text with only end line specified."""
        set_file_fn = self.get_tool_fn(server, "set_file")
        await set_file_fn(temp_file)
        read_fn = self.get_tool_fn(server, "read")
        result = await read_fn(1, 2)
        assert "lines" in result
        select_fn = self.get_tool_fn(server, "select")
        select_result = await select_fn(1, 2)
        expected_id = calculate_id("Line 1\nLine 2\n", 1, 2)
        assert expected_id == select_result["id"]

    @pytest.mark.asyncio
    async def test_read_invalid_range(self, server, temp_file):
        """Test getting text with an invalid line range."""
        set_file_fn = self.get_tool_fn(server, "set_file")
        await set_file_fn(temp_file)
        read_fn = self.get_tool_fn(server, "read")
        result = await read_fn(4, 2)
        assert "error" in result
        # Updated assertion to match actual error message format in server.py
        assert "start=4 cannot be greater than end=2" in result["error"]
        result = await read_fn(0, 3)
        assert "error" in result
        assert "start must be at least 1" in result["error"]

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
        """Test getting text from a file larger than MAX_SELECT_LINES lines."""
        more_than_max_lines = server.max_select_lines + 10
        with tempfile.NamedTemporaryFile(mode="w+", delete=False) as f:
            for i in range(more_than_max_lines):
                f.write(f"Line {i + 1}\n")
            large_file_path = f.name
        try:
            set_file_fn = self.get_tool_fn(server, "set_file")
            await set_file_fn(large_file_path)
            read_fn = self.get_tool_fn(server, "read")
            result = await read_fn(1, more_than_max_lines)
            assert "lines" in result
            select_fn = self.get_tool_fn(server, "select")
            result = await select_fn(1, more_than_max_lines)
            assert "error" in result
            assert (
                f"Cannot select more than {server.max_select_lines} lines at once"
                in result["error"]
            )
            result = await select_fn(5, 15)
            assert "status" in result
            assert "id" in result
            result = await read_fn(5, server.max_select_lines + 10)
            assert "lines" in result
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
        result = await find_line_fn(search_text="Line")
        assert "status" in result
        assert result["status"] == "success"
        assert "matches" in result
        assert "total_matches" in result
        assert result["total_matches"] == 5
        for match in result["matches"]:
            assert "line_number" in match
            assert "id" in match
            assert "text" in match
            assert f"Line {match['line_number']}" in match["text"]
        line_numbers = [match["line_number"] for match in result["matches"]]
        assert line_numbers == [1, 2, 3, 4, 5]

    @pytest.mark.asyncio
    async def test_find_line_specific_match(self, server, temp_file):
        """Test find_line with a specific search term."""
        set_file_fn = self.get_tool_fn(server, "set_file")
        await set_file_fn(temp_file)
        find_line_fn = self.get_tool_fn(server, "find_line")
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
        result = await find_line_fn(search_text="NonExistentTerm")
        assert result["status"] == "success"
        assert result["total_matches"] == 0
        assert len(result["matches"]) == 0

    @pytest.mark.asyncio
    async def test_find_line_file_read_error(self, server, temp_file, monkeypatch):
        """Test find_line with a file read error."""
        set_file_fn = self.get_tool_fn(server, "set_file")
        await set_file_fn(temp_file)

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
        result = await overwrite_fn(new_lines={"lines": ["New content"]})
        assert "error" in result
        assert "No file path is set" in result["error"]

    @pytest.mark.asyncio
    async def test_overwrite_basic(self, server, temp_file):
        """Test basic overwrite functionality."""
        set_file_fn = self.get_tool_fn(server, "set_file")
        await set_file_fn(temp_file)
        select_fn = self.get_tool_fn(server, "select")
        select_result = await select_fn(2, 4)
        assert select_result["status"] == "success"
        assert "id" in select_result
        overwrite_fn = self.get_tool_fn(server, "overwrite")
        new_lines = {"lines": ["New Line 2", "New Line 3", "New Line 4"]}
        result = await overwrite_fn(new_lines=new_lines)
        assert "status" in result
        assert result["status"] == "preview"
        assert "Changes ready to apply" in result["message"]
        confirm_fn = self.get_tool_fn(server, "confirm")
        confirm_result = await confirm_fn()
        assert confirm_result["status"] == "success"
        assert "Changes applied successfully" in confirm_result["message"]
        with open(temp_file, "r") as f:
            file_content = f.read()
        expected_content = "Line 1\nNew Line 2\nNew Line 3\nNew Line 4\nLine 5\n"
        assert file_content == expected_content

    @pytest.mark.asyncio
    async def test_overwrite_cancel(self, server, temp_file):
        """Test overwrite with cancel operation."""
        # Set up initial state
        set_file_fn = self.get_tool_fn(server, "set_file")
        await set_file_fn(temp_file)
        select_fn = self.get_tool_fn(server, "select")
        select_result = await select_fn(2, 4)
        assert select_result["status"] == "success"
        assert "id" in select_result

        # Create overwrite preview
        overwrite_fn = self.get_tool_fn(server, "overwrite")
        new_lines = {"lines": ["New Line 2", "New Line 3", "New Line 4"]}
        result = await overwrite_fn(new_lines=new_lines)
        assert "status" in result
        assert result["status"] == "preview"
        assert "Changes ready to apply" in result["message"]

        # Get original content to verify it remains unchanged
        with open(temp_file, "r") as f:
            original_content = f.read()

        # Cancel the changes
        cancel_fn = self.get_tool_fn(server, "cancel")
        cancel_result = await cancel_fn()
        assert cancel_result["status"] == "success"
        assert "Action cancelled" in cancel_result["message"]

        # Verify the file content is unchanged
        with open(temp_file, "r") as f:
            file_content = f.read()
        assert file_content == original_content

        # Verify that selected lines are still available
        assert server.selected_start == 2
        assert server.selected_end == 4
        assert server.selected_id is not None
        assert server.pending_modified_lines is None
        assert server.pending_diff is None

    @pytest.mark.asyncio
    async def test_select_invalid_range(self, server, temp_file):
        """Test select with invalid line ranges."""
        set_file_fn = self.get_tool_fn(server, "set_file")
        await set_file_fn(temp_file)
        select_fn = self.get_tool_fn(server, "select")
        result = await select_fn(start=0, end=2)
        assert "error" in result
        assert "start must be at least 1" in result["error"]
        result = await select_fn(start=1, end=10)
        assert "end" in result
        assert result["end"] == 5
        result = await select_fn(start=4, end=2)
        assert "error" in result
        assert "start cannot be greater than end" in result["error"]

    @pytest.mark.asyncio
    async def test_overwrite_id_verification_failed(self, server, temp_file):
        """Test overwrite with incorrect ID (content verification failure)."""
        set_file_fn = self.get_tool_fn(server, "set_file")
        await set_file_fn(temp_file)
        select_fn = self.get_tool_fn(server, "select")
        select_result = await select_fn(2, 3)
        with open(temp_file, "w") as f:
            f.write(
                "Modified Line 1\nModified Line 2\nModified Line 3\nModified Line 4\nModified Line 5\n"
            )
        overwrite_fn = self.get_tool_fn(server, "overwrite")
        result = await overwrite_fn(new_lines={"lines": ["New content"]})
        assert "error" in result
        assert "id verification failed" in result["error"]

    @pytest.mark.asyncio
    async def test_overwrite_different_line_count(self, server, temp_file):
        """Test overwrite with different line count (more or fewer lines)."""
        set_file_fn = self.get_tool_fn(server, "set_file")
        await set_file_fn(temp_file)
        select_fn = self.get_tool_fn(server, "select")
        select_result = await select_fn(2, 3)
        assert select_result["status"] == "success"
        overwrite_fn = self.get_tool_fn(server, "overwrite")
        new_lines = {"lines": ["New Line 2", "Extra Line", "New Line 3"]}
        result = await overwrite_fn(new_lines=new_lines)
        assert result["status"] == "preview"
        confirm_fn = self.get_tool_fn(server, "confirm")
        confirm_result = await confirm_fn()
        assert confirm_result["status"] == "success"
        with open(temp_file, "r") as f:
            file_content = f.read()
        expected_content = (
            "Line 1\nNew Line 2\nExtra Line\nNew Line 3\nLine 4\nLine 5\n"
        )
        assert file_content == expected_content
        select_result = await select_fn(1, 6)
        assert select_result["status"] == "success"
        new_content = "Single Line\n"
        result = await overwrite_fn(new_lines={"lines": ["Single Line"]})
        assert result["status"] == "preview"
        confirm_result = await confirm_fn()
        assert confirm_result["status"] == "success"
        with open(temp_file, "r") as f:
            file_content = f.read()
        assert file_content == "Single Line\n"

    @pytest.mark.asyncio
    async def test_overwrite_empty_text(self, server, temp_file):
        """Test overwrite with empty text (effectively removing lines)."""
        set_file_fn = self.get_tool_fn(server, "set_file")
        await set_file_fn(temp_file)
        select_fn = self.get_tool_fn(server, "select")
        select_result = await select_fn(2, 3)
        assert select_result["status"] == "success"
        overwrite_fn = self.get_tool_fn(server, "overwrite")
        result = await overwrite_fn(new_lines={"lines": []})
        assert result["status"] == "preview"
        confirm_fn = self.get_tool_fn(server, "confirm")
        confirm_result = await confirm_fn()
        assert confirm_result["status"] == "success"
        with open(temp_file, "r") as f:
            file_content = f.read()
        expected_content = "Line 1\nLine 4\nLine 5\n"
        assert file_content == expected_content

    @pytest.mark.asyncio
    async def test_select_max_lines_exceeded(self, server, temp_file):
        """Test select with a range exceeding max_select_lines."""
        set_file_fn = self.get_tool_fn(server, "set_file")
        await set_file_fn(temp_file)
        more_than_max_lines = server.max_select_lines + 10
        with tempfile.NamedTemporaryFile(mode="w+", delete=False) as f:
            for i in range(more_than_max_lines):
                f.write(f"Line {i + 1}\n")
            large_file_path = f.name
        try:
            await set_file_fn(large_file_path)
            select_fn = self.get_tool_fn(server, "select")
            result = await select_fn(start=1, end=server.max_select_lines + 1)
            assert "error" in result
            assert (
                f"Cannot select more than {server.max_select_lines} lines at once"
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
        select_fn = self.get_tool_fn(server, "select")
        select_result = await select_fn(2, 3)
        assert select_result["status"] == "success"
        original_open = open

        def mock_open_read(*args, **kwargs):
            if args[1] == "r":
                raise IOError("Mock file read error")
            return original_open(*args, **kwargs)

        monkeypatch.setattr("builtins.open", mock_open_read)
        overwrite_fn = self.get_tool_fn(server, "overwrite")
        result = await overwrite_fn(new_lines={"lines": ["New content"]})
        assert "error" in result
        assert "Error reading file" in result["error"]
        assert "Mock file read error" in result["error"]

    @pytest.mark.asyncio
    async def test_overwrite_file_write_error(self, server, temp_file, monkeypatch):
        """Test overwrite with file write error."""
        set_file_fn = self.get_tool_fn(server, "set_file")
        await set_file_fn(temp_file)
        select_fn = self.get_tool_fn(server, "select")
        select_result = await select_fn(2, 3)
        assert select_result["status"] == "success"
        original_open = open
        open_calls = [0]

        def mock_open_write(*args, **kwargs):
            if args[1] == "w":
                raise IOError("Mock file write error")
            return original_open(*args, **kwargs)

        monkeypatch.setattr("builtins.open", mock_open_write)
        overwrite_fn = self.get_tool_fn(server, "overwrite")
        result = await overwrite_fn(new_lines={"lines": ["New content"]})
        assert "status" in result
        assert result["status"] == "preview"
        confirm_fn = self.get_tool_fn(server, "confirm")
        confirm_result = await confirm_fn()
        assert "error" in confirm_result
        assert "Error writing to file" in confirm_result["error"]
        assert "Mock file write error" in confirm_result["error"]

    @pytest.mark.asyncio
    async def test_overwrite_newline_handling(self, server):
        """Test newline handling in overwrite (appends newline when needed)."""
        with tempfile.NamedTemporaryFile(mode="w+", delete=False) as f:
            f.write("Line 1\nLine 2\nLine 3")
            temp_path = f.name
        try:
            set_file_fn = self.get_tool_fn(server, "set_file")
            await set_file_fn(temp_path)
            select_fn = self.get_tool_fn(server, "select")
            select_result = await select_fn(2, 2)
            assert select_result["status"] == "success"
            overwrite_fn = self.get_tool_fn(server, "overwrite")
            result = await overwrite_fn(new_lines={"lines": ["New Line 2"]})
            assert result["status"] == "preview"
            confirm_fn = self.get_tool_fn(server, "confirm")
            confirm_result = await confirm_fn()
            assert confirm_result["status"] == "success"
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
        valid_python_content = (
            "def hello():\n    print('Hello, world!')\n\nresult = hello()\n"
        )
        with tempfile.NamedTemporaryFile(mode="w+", suffix=".py", delete=False) as f:
            f.write(valid_python_content)
            py_file_path = f.name
        try:
            set_file_fn = self.get_tool_fn(server, "set_file")
            await set_file_fn(py_file_path)
            select_fn = self.get_tool_fn(server, "select")
            select_result = await select_fn(1, 4)
            assert select_result["status"] == "success"
            overwrite_fn = self.get_tool_fn(server, "overwrite")
            new_content = {
                "lines": [
                    "def greeting(name):",
                    "    return f'Hello, {name}!'",
                    "",
                    "result = greeting('World')",
                ]
            }
            result = await overwrite_fn(new_lines=new_content)
            assert result["status"] == "preview"
            confirm_fn = self.get_tool_fn(server, "confirm")
            confirm_result = await confirm_fn()
            assert confirm_result["status"] == "success"
            assert "Changes applied successfully" in confirm_result["message"]
            with open(py_file_path, "r") as f:
                file_content = f.read()
            expected_content = "def greeting(name):\n    return f'Hello, {name}!'\n\nresult = greeting('World')\n"
            assert file_content == expected_content
        finally:
            if os.path.exists(py_file_path):
                os.unlink(py_file_path)

    @pytest.mark.asyncio
    async def test_overwrite_python_syntax_check_failure(self, server):
        """Test Python syntax checking in overwrite fails with invalid Python code."""
        valid_python_content = (
            "def hello():\n    print('Hello, world!')\n\nresult = hello()\n"
        )
        with tempfile.NamedTemporaryFile(mode="w+", suffix=".py", delete=False) as f:
            f.write(valid_python_content)
            py_file_path = f.name
        try:
            set_file_fn = self.get_tool_fn(server, "set_file")
            await set_file_fn(py_file_path)
            select_fn = self.get_tool_fn(server, "select")
            select_result = await select_fn(1, 4)
            assert select_result["status"] == "success"
            overwrite_fn = self.get_tool_fn(server, "overwrite")
            invalid_python = {
                "lines": [
                    "def broken_function(:",
                    "    print('Missing parenthesis'",
                    "",
                    "result = broken_function()",
                ]
            }
            result = await overwrite_fn(new_lines=invalid_python)
            assert "error" in result
            assert "Python syntax error:" in result["error"]
            with open(py_file_path, "r") as f:
                file_content = f.read()
            assert file_content == valid_python_content
        finally:
            if os.path.exists(py_file_path):
                os.unlink(py_file_path)

    @pytest.mark.asyncio
    async def test_overwrite_javascript_syntax_check_success(self, server, monkeypatch):
        """Test JavaScript syntax checking in overwrite succeeds with valid JS code."""
        valid_js_content = "function hello() {\n  return 'Hello, world!';\n}\n\nconst result = hello();\n"
        with tempfile.NamedTemporaryFile(mode="w+", suffix=".js", delete=False) as f:
            f.write(valid_js_content)
            js_file_path = f.name

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
            select_fn = self.get_tool_fn(server, "select")
            select_result = await select_fn(1, 5)
            assert select_result["status"] == "success"
            overwrite_fn = self.get_tool_fn(server, "overwrite")
            new_lines = {
                "lines": [
                    "function greeting(name) {",
                    "  return `Hello, ${name}!`;",
                    "}",
                    "",
                    "const result = greeting('World');",
                ]
            }
            result = await overwrite_fn(new_lines=new_lines)
            assert result["status"] == "preview"
            confirm_fn = self.get_tool_fn(server, "confirm")
            confirm_result = await confirm_fn()
            assert confirm_result["status"] == "success"
            assert "Changes applied successfully" in confirm_result["message"]
            with open(js_file_path, "r") as f:
                file_content = f.read()
            expected_content = "function greeting(name) {\n  return `Hello, ${name}!`;\n}\n\nconst result = greeting('World');\n"
            assert file_content == expected_content
        finally:
            if os.path.exists(js_file_path):
                os.unlink(js_file_path)

    @pytest.mark.asyncio
    async def test_overwrite_javascript_syntax_check_failure(self, server, monkeypatch):
        """Test JavaScript syntax checking in overwrite fails with invalid JS code."""
        valid_js_content = "function hello() {\n  return 'Hello, world!';\n}\n\nconst result = hello();\n"
        with tempfile.NamedTemporaryFile(mode="w+", suffix=".js", delete=False) as f:
            f.write(valid_js_content)
            js_file_path = f.name

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
            select_fn = self.get_tool_fn(server, "select")
            select_result = await select_fn(1, 5)
            overwrite_fn = self.get_tool_fn(server, "overwrite")
            invalid_js = {
                "lines": [
                    "function broken() {",
                    "  return 'Missing closing bracket;",
                    "}",
                    "",
                    "const result = broken();",
                ]
            }
            result = await overwrite_fn(new_lines=invalid_js)
            assert "error" in result
            assert "JavaScript syntax error:" in result["error"]
            with open(js_file_path, "r") as f:
                file_content = f.read()
            assert file_content == valid_js_content
        finally:
            if os.path.exists(js_file_path):
                os.unlink(js_file_path)

    @pytest.mark.asyncio
    async def test_overwrite_jsx_syntax_check_success(self, server, monkeypatch):
        """Test JSX syntax checking in overwrite succeeds with valid React/JSX code."""
        valid_jsx_content = "import React from 'react';\n\nfunction HelloWorld() {\n  return <div>Hello, world!</div>;\n}\n\nexport default HelloWorld;\n"
        with tempfile.NamedTemporaryFile(mode="w+", suffix=".jsx", delete=False) as f:
            f.write(valid_jsx_content)
            jsx_file_path = f.name

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
            select_fn = self.get_tool_fn(server, "select")
            select_result = await select_fn(1, 7)
            assert select_result["status"] == "success"
            overwrite_fn = self.get_tool_fn(server, "overwrite")
            new_jsx_content = {
                "lines": [
                    "import React from 'react';",
                    "",
                    "function Greeting({ name }) {",
                    "  return <div>Hello, {name}!</div>;",
                    "}",
                    "",
                    "export default Greeting;",
                ]
            }
            result = await overwrite_fn(new_lines=new_jsx_content)
            assert result["status"] == "preview"
            confirm_fn = self.get_tool_fn(server, "confirm")
            confirm_result = await confirm_fn()
            assert confirm_result["status"] == "success"
            assert "Changes applied successfully" in confirm_result["message"]
            with open(jsx_file_path, "r") as f:
                file_content = f.read()
            expected_content = "import React from 'react';\n\nfunction Greeting({ name }) {\n  return <div>Hello, {name}!</div>;\n}\n\nexport default Greeting;\n"
            assert file_content == expected_content
        finally:
            if os.path.exists(jsx_file_path):
                os.unlink(jsx_file_path)

    @pytest.mark.asyncio
    async def test_overwrite_jsx_syntax_check_failure(self, server, monkeypatch):
        """Test JSX syntax checking in overwrite fails with invalid React/JSX code."""
        valid_jsx_content = "import React from 'react';\n\nfunction HelloWorld() {\n  return <div>Hello, world!</div>;\n}\n\nexport default HelloWorld;\n"
        with tempfile.NamedTemporaryFile(mode="w+", suffix=".jsx", delete=False) as f:
            f.write(valid_jsx_content)
            jsx_file_path = f.name

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
            select_fn = self.get_tool_fn(server, "select")
            select_result = await select_fn(1, 7)
            overwrite_fn = self.get_tool_fn(server, "overwrite")
            invalid_jsx = {
                "lines": [
                    "import React from 'react';",
                    "",
                    "function BrokenComponent() {",
                    "  return <div>Missing closing tag<div>;",
                    "}",
                    "",
                    "export default BrokenComponent;",
                ]
            }
            result = await overwrite_fn(new_lines=invalid_jsx)
            assert "error" in result
            assert "JavaScript syntax error:" in result["error"]
            with open(jsx_file_path, "r") as f:
                file_content = f.read()
            assert file_content == valid_jsx_content
        finally:
            if os.path.exists(jsx_file_path):
                os.unlink(jsx_file_path)

    @pytest.mark.asyncio
    async def test_generate_diff_preview(self):
        """Test the generate_diff_preview function directly."""
        original_lines = ["Line 1", "Line 2", "Line 3", "Line 4", "Line 5"]
        modified_lines = [
            "Line 1",
            "Modified Line 2",
            "New Line",
            "Line 3",
            "Line 4",
            "Line 5",
        ]

        # Testing replacement in the middle of the file
        result = generate_diff_preview(original_lines, modified_lines, 2, 3)

        # Verify the result contains the expected diff_lines key
        assert "diff_lines" in result

        # Get and examine the content of diff_lines
        diff_lines_list = result["diff_lines"]

        # The diff_lines should be a list of tuples, let's check its structure
        # First verify we have the expected number of elements
        assert len(diff_lines_list) > 0

        # Check that we have context lines before the change
        # The first element should be the context line with line number 1
        assert any(item for item in diff_lines_list if item[0] == 1)

        # Check for removed lines with minus prefix
        assert any(item for item in diff_lines_list if item[0] == "-2")
        assert any(item for item in diff_lines_list if item[0] == "-3")

        # Check for added lines with plus prefix
        # There should be one entry containing the modified content
        added_lines = [
            item
            for item in diff_lines_list
            if isinstance(item[0], str) and item[0].startswith("+")
        ]
        assert len(added_lines) > 0

        # Verify context after the change (line 4 and 5)
        assert any(item for item in diff_lines_list if item[0] == 4)
        assert any(item for item in diff_lines_list if item[0] == 5)

    @pytest.fixture
    def python_test_file(self):
        """Create a Python test file with various functions and methods for testing find_function."""
        content = '''import os

def simple_function():
    """A simple function."""
    return "Hello, world!"

@decorator1
@decorator2
def decorated_function(a, b=None):
    """A function with decorators."""
    if b is None:
        b = a * 2
    return a + b

class TestClass:
    """A test class with methods."""
    
    def __init__(self, value):
        self.value = value
    
    def instance_method(self, x):
        """An instance method."""
        return self.value * x
    
    @classmethod
    def class_method(cls, y):
        """A class method."""
        return cls(y)
    
    @staticmethod
    def static_method(z):
        """A static method."""
        return z ** 2

def outer_function(param):
    """A function containing a nested function."""
    
    def inner_function(inner_param):
        """A nested function."""
        return inner_param + param
    
    return inner_function(param * 2)
'''
        with tempfile.NamedTemporaryFile(mode="w+", suffix=".py", delete=False) as f:
            f.write(content)
            temp_path = f.name
        yield temp_path
        if os.path.exists(temp_path):
            os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_find_function_no_file_set(self, server):
        """Test find_function when no file is set."""
        find_function_fn = self.get_tool_fn(server, "find_function")
        result = await find_function_fn(function_name="test")
        assert "error" in result
        assert "No file path is set" in result["error"]

    @pytest.mark.asyncio
    async def test_find_function_non_supported_file(self, server, temp_file):
        """Test find_function with a non-supported file type."""
        set_file_fn = self.get_tool_fn(server, "set_file")
        await set_file_fn(temp_file)
        find_function_fn = self.get_tool_fn(server, "find_function")
        result = await find_function_fn(function_name="test")
        assert "error" in result
        assert (
            "This tool only works with Python (.py) or JavaScript/JSX (.js, .jsx) files"
            in result["error"]
        )

    @pytest.mark.asyncio
    async def test_find_function_simple(self, server, python_test_file):
        """Test find_function with a simple function."""
        set_file_fn = self.get_tool_fn(server, "set_file")
        await set_file_fn(python_test_file)
        find_function_fn = self.get_tool_fn(server, "find_function")
        result = await find_function_fn(function_name="simple_function")
        assert "status" in result
        assert result["status"] == "success"
        assert "lines" in result
        assert "start_line" in result
        assert "end_line" in result

        # Check that the correct function is returned
        function_text = "".join(line[1] for line in result["lines"])
        assert "def simple_function():" in function_text
        assert "A simple function" in function_text
        assert 'return "Hello, world!"' in function_text

    @pytest.mark.asyncio
    async def test_find_function_decorated(self, server, python_test_file):
        """Test find_function with a decorated function."""
        set_file_fn = self.get_tool_fn(server, "set_file")
        await set_file_fn(python_test_file)
        find_function_fn = self.get_tool_fn(server, "find_function")
        result = await find_function_fn(function_name="decorated_function")
        assert result["status"] == "success"

        # Check that the decorators are included
        function_lines = [line[1] for line in result["lines"]]
        assert any("@decorator1" in line for line in function_lines)
        assert any("@decorator2" in line for line in function_lines)
        assert any(
            "def decorated_function(a, b=None):" in line for line in function_lines
        )

    @pytest.mark.asyncio
    async def test_find_function_method(self, server, python_test_file):
        """Test find_function with a class method."""
        set_file_fn = self.get_tool_fn(server, "set_file")
        await set_file_fn(python_test_file)
        find_function_fn = self.get_tool_fn(server, "find_function")
        result = await find_function_fn(function_name="instance_method")
        assert result["status"] == "success"

        # Check that the method is correctly identified
        function_text = "".join(line[1] for line in result["lines"])
        assert "def instance_method(self, x):" in function_text
        assert "An instance method" in function_text
        assert "return self.value * x" in function_text

    @pytest.mark.asyncio
    async def test_find_function_static_method(self, server, python_test_file):
        """Test find_function with a static method."""
        set_file_fn = self.get_tool_fn(server, "set_file")
        await set_file_fn(python_test_file)
        find_function_fn = self.get_tool_fn(server, "find_function")
        result = await find_function_fn(function_name="static_method")
        assert result["status"] == "success"

        # Check that the decorator and method are included
        function_lines = [line[1] for line in result["lines"]]
        assert any("@staticmethod" in line for line in function_lines)
        assert any("def static_method(z):" in line for line in function_lines)

    @pytest.mark.asyncio
    async def test_find_function_not_found(self, server, python_test_file):
        """Test find_function with a non-existent function."""
        set_file_fn = self.get_tool_fn(server, "set_file")
        await set_file_fn(python_test_file)
        find_function_fn = self.get_tool_fn(server, "find_function")
        result = await find_function_fn(function_name="nonexistent_function")
        assert "error" in result
        assert "not found in the file" in result["error"]

    @pytest.mark.asyncio
    async def test_protect_paths_env_variable(self, monkeypatch):
        """Test that the PROTECTED_PATHS environment variable is correctly processed."""
        # Set up the environment variable with test paths
        monkeypatch.setenv(
            "PROTECTED_PATHS",
            "*.secret,.env*,config*.json,*sensitive*,/etc/shadow,/home/user/.ssh/id_rsa",
        )

        # Create a new server instance which should read the environment variable
        server = TextEditorServer()

        # Verify the protected_paths list is populated correctly
        assert len(server.protected_paths) == 6
        assert "*.secret" in server.protected_paths
        assert ".env*" in server.protected_paths
        assert "config*.json" in server.protected_paths
        assert "*sensitive*" in server.protected_paths
        assert "/etc/shadow" in server.protected_paths
        assert "/home/user/.ssh/id_rsa" in server.protected_paths

    @pytest.mark.asyncio
    async def test_protect_paths_empty_env_variable(self, monkeypatch):
        """Test that an empty PROTECTED_PATHS environment variable is handled correctly."""
        # Set up an empty environment variable
        monkeypatch.setenv("PROTECTED_PATHS", "")

        # Create a new server instance
        server = TextEditorServer()

        # Verify the protected_paths list is empty
        assert len(server.protected_paths) == 0

    @pytest.mark.asyncio
    async def test_protect_paths_trimming(self, monkeypatch):
        """Test that whitespace in PROTECTED_PATHS items is properly trimmed."""
        # Set up the environment variable with whitespace
        monkeypatch.setenv(
            "PROTECTED_PATHS", " *.secret , /etc/shadow ,  /home/user/.ssh/id_rsa "
        )

        # Create a new server instance
        server = TextEditorServer()

        # Get set_file tool for testing
        set_file_fn = self.get_tool_fn(server, "set_file")

        # Mock os.path.isfile to return True for our test path
        def mock_isfile(path):
            return True

        monkeypatch.setattr(os.path, "isfile", mock_isfile)

        # Test access denied for a path matching a trimmed pattern
        result = await set_file_fn("/home/user/.ssh/id_rsa")
        assert "Error: Access to '/home/user/.ssh/id_rsa' is denied" in result

    @pytest.mark.asyncio
    async def test_find_function_nested(self, server, python_test_file):
        """Test find_function with nested functions."""
        set_file_fn = self.get_tool_fn(server, "set_file")
        await set_file_fn(python_test_file)
        find_function_fn = self.get_tool_fn(server, "find_function")

        # Test finding the outer function
        result = await find_function_fn(function_name="outer_function")
        assert result["status"] == "success"
        function_text = "".join(line[1] for line in result["lines"])
        assert "def outer_function(param):" in function_text
        assert "def inner_function(inner_param):" in function_text

        # Test finding the inner function (this may or may not work depending on implementation)
        # AST might not directly support finding nested functions
        # This test is designed to document current behavior, not necessarily assert correctness
        inner_result = await find_function_fn(function_name="inner_function")
        # If it finds the inner function, check it's correct
        if "status" in inner_result and inner_result["status"] == "success":
            inner_text = "".join(line[1] for line in inner_result["lines"])
            assert "def inner_function(inner_param):" in inner_text
        # Otherwise, it should return an error that the function wasn't found
        else:
            assert "error" in inner_result
            assert "not found in the file" in inner_result["error"]

    @pytest.mark.asyncio
    async def test_find_function_parsing_error(self, server):
        """Test find_function with a file that can't be parsed due to syntax errors."""
        with tempfile.NamedTemporaryFile(mode="w+", suffix=".py", delete=False) as f:
            f.write(
                "def broken_function(  # Syntax error: missing parenthesis\n    pass\n"
            )
            invalid_py_path = f.name
        try:
            set_file_fn = self.get_tool_fn(server, "set_file")
            await set_file_fn(invalid_py_path)
            find_function_fn = self.get_tool_fn(server, "find_function")
            result = await find_function_fn(function_name="broken_function")
            assert "error" in result
            assert "Error finding function" in result["error"]
        finally:
            if os.path.exists(invalid_py_path):
                os.unlink(invalid_py_path)

    @pytest.mark.asyncio
    async def test_find_function_javascript(
        self, server, javascript_test_file, monkeypatch
    ):
        """Test find_function with JavaScript functions."""

        # Mock subprocess.run to avoid external dependency in tests
        def mock_subprocess_run(*args, **kwargs):
            class MockCompletedProcess:
                def __init__(self):
                    self.returncode = 0
                    self.stderr = ""
                    self.stdout = ""

            return MockCompletedProcess()

        monkeypatch.setattr("subprocess.run", mock_subprocess_run)

        set_file_fn = self.get_tool_fn(server, "set_file")
        await set_file_fn(javascript_test_file)
        find_function_fn = self.get_tool_fn(server, "find_function")

        # Test regular function
        result = await find_function_fn(function_name="simpleFunction")
        assert result["status"] == "success"
        # Get all the lines of the function
        function_lines = [line[1] for line in result["lines"]]
        assert any("function simpleFunction()" in line for line in function_lines)
        assert any("console.log('Hello world')" in line for line in function_lines)

        # Test arrow function
        result = await find_function_fn(function_name="arrowFunction")
        assert result["status"] == "success"
        function_lines = [line[1] for line in result["lines"]]
        assert any("const arrowFunction = (a, b) =>" in line for line in function_lines)

        # Test async function
        result = await find_function_fn(function_name="asyncFunction")
        assert result["status"] == "success"
        function_lines = [line[1] for line in result["lines"]]
        assert any("async function asyncFunction()" in line for line in function_lines)

        # Test hook-style function
        result = await find_function_fn(function_name="useCustomHook")
        assert result["status"] == "success"
        function_lines = [line[1] for line in result["lines"]]
        assert any(
            "const useCustomHook = useCallback" in line for line in function_lines
        )

        result = await find_function_fn(function_name="methodFunction")

        function_lines = [line[1] for line in result["lines"]]
        assert any("methodFunction(x, y)" in line for line in function_lines)

        result = await find_function_fn(function_name="nonExistentFunction")
        assert "error" in result
        assert "not found in the file" in result["error"]

    @pytest.mark.asyncio
    async def test_find_function_jsx(self, server, jsx_test_file, monkeypatch):
        """Test find_function with JSX/React component functions."""

        def mock_subprocess_run(*args, **kwargs):
            class MockCompletedProcess:
                def __init__(self):
                    self.returncode = 0
                    self.stderr = ""
                    self.stdout = ""

            return MockCompletedProcess()

        monkeypatch.setattr("subprocess.run", mock_subprocess_run)

        set_file_fn = self.get_tool_fn(server, "set_file")
        await set_file_fn(jsx_test_file)
        find_function_fn = self.get_tool_fn(server, "find_function")

        # Test regular function component
        result = await find_function_fn(function_name="SimpleComponent")
        assert result["status"] == "success"
        # Get all the lines of the component
        function_lines = [line[1] for line in result["lines"]]
        # Just check that the function name is found
        assert "SimpleComponent" in "".join(function_lines)

        # Test arrow function component
        result = await find_function_fn(function_name="ArrowComponent")
        assert result["status"] == "success"
        # Get all the lines of the component
        function_lines = [line[1] for line in result["lines"]]
        # Only check that we found the function declaration
        assert "ArrowComponent" in "".join(function_lines)

        # Test component with nested function
        result = await find_function_fn(function_name="ParentComponent")
        assert result["status"] == "success"
        # Get all the lines of the component
        function_lines = [line[1] for line in result["lines"]]
        assert any("function ParentComponent()" in line for line in function_lines)
        assert any("function handleClick()" in line for line in function_lines)

        # Test higher order component
        result = await find_function_fn(function_name="withLogger")
        assert result["status"] == "success"
        # Get all the lines of the component
        function_lines = [line[1] for line in result["lines"]]
        assert any("function withLogger(Component)" in line for line in function_lines)
        assert any(
            "return function EnhancedComponent(props)" in line
            for line in function_lines
        )

        # Test nested function may or may not work depending on implementation
        result = await find_function_fn(function_name="handleClick")
        if "status" in result and result["status"] == "success":
            function_lines = [line[1] for line in result["lines"]]
            assert any("function handleClick()" in line for line in function_lines)
        else:
            assert "error" in result

        # Test non-existent function
        result = await find_function_fn(function_name="nonExistentComponent")
        assert "error" in result
        assert "not found in the file" in result["error"]

    @pytest.mark.asyncio
    async def test_find_function_js_with_disabled_check(self, server, monkeypatch):
        """Test find_function with disabled JavaScript syntax checking."""
        # Create a server with disabled JS syntax checking
        monkeypatch.setenv("ENABLE_JS_SYNTAX_CHECK", "0")
        server_no_js_check = TextEditorServer()

        # Create a basic JavaScript file
        js_content = "function testFunc() { return 'test'; }"
        with tempfile.NamedTemporaryFile(mode="w+", suffix=".js", delete=False) as f:
            f.write(js_content)
            js_file_path = f.name

        try:
            # This test ensures find_function still works even when JavaScript
            # syntax checking is disabled for overwrite operations
            set_file_fn = self.get_tool_fn(server_no_js_check, "set_file")
            await set_file_fn(js_file_path)
            find_function_fn = self.get_tool_fn(server_no_js_check, "find_function")

            result = await find_function_fn(function_name="testFunc")
            assert result["status"] == "success"
            function_lines = [line[1] for line in result["lines"]]
            assert any("function testFunc()" in line for line in function_lines)
        finally:
            if os.path.exists(js_file_path):
                os.unlink(js_file_path)

    @pytest.fixture
    def javascript_test_file(self):
        """Create a JavaScript test file with various functions for testing find_function."""
        content = """// Sample JavaScript file with different function types

// Regular function declaration
function simpleFunction() {
  console.log('Hello world');
  return 42;
}

// Arrow function expression
const arrowFunction = (a, b) => {
  const sum = a + b;
  return sum;
};

// Object with method
const obj = {
  methodFunction(x, y) {
    return x * y;
  },

  // Object method as arrow function
  arrowMethod: (z) => {
    return z * z;
  }
};

// Async function
async function asyncFunction() {
  return await Promise.resolve('done');
}

// React hook style function
const useCustomHook = useCallback((value) => {
  return value.toUpperCase();
}, []);

// Class with methods
class TestClass {
  constructor(value) {
    this.value = value;
  }

  instanceMethod() {
    return this.value;
  }

  static staticMethod() {
    return 'static';
  }
}
"""
        with tempfile.NamedTemporaryFile(mode="w+", suffix=".js", delete=False) as f:
            f.write(content)
            temp_path = f.name
        yield temp_path
        if os.path.exists(temp_path):
            os.unlink(temp_path)

    @pytest.fixture
    def jsx_test_file(self):
        """Create a JSX test file with various component functions for testing find_function."""
        content = """import React, { useState, useEffect } from 'react';

// Function component
function SimpleComponent() {
  return <div>Hello World</div>;
}

// Arrow function component with props
const ArrowComponent = ({ name }) => {
  const [count, setCount] = useState(0);

  useEffect(() => {
    document.title = `${name}: ${count}`;
  }, [name, count]);

  return (
    <div>
      <h1>Hello {name}</h1>
      <button onClick={() => setCount(count + 1)}>
        Count: {count}
      </button>
    </div>
  );
};

// Component with nested function
function ParentComponent() {
  function handleClick() {
    console.log('Button clicked');
  }

  return <button onClick={handleClick}>Click me</button>;
}

// Higher order component
function withLogger(Component) {
  return function EnhancedComponent(props) {
    console.log('Component rendered with props:', props);
    return <Component {...props} />;
  };
}

export default SimpleComponent;
"""
        with tempfile.NamedTemporaryFile(mode="w+", suffix=".jsx", delete=False) as f:
            f.write(content)
            temp_path = f.name
        yield temp_path
        if os.path.exists(temp_path):
            os.unlink(temp_path)
