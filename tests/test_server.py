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
        content = "This is a test file.\nWith multiple lines.\nThree lines total."
        result = await new_file_fn(empty_temp_file, content)

        assert result["status"] == "success"
        assert "id" in result

        with open(empty_temp_file, "r") as file:
            file_content = file.read()
        assert file_content == content

        result = await new_file_fn(empty_temp_file, "This should fail.")
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
