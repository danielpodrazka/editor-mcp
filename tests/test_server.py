import os
import pytest
import tempfile
import hashlib

from src.text_editor.server import TextEditorServer, calculate_hash


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
    async def test_get_text_no_file_set(self, server):
        """Test getting text when no file is set."""
        get_text_fn = self.get_tool_fn(server, "get_text")

        result = await get_text_fn()

        assert "error" in result
        assert "No file path is set" in result["error"]

    @pytest.mark.asyncio
    async def test_get_text_entire_file(self, server, temp_file):
        """Test getting the entire content of a file."""

        set_file_fn = self.get_tool_fn(server, "set_file")
        await set_file_fn(temp_file)

        get_text_fn = self.get_tool_fn(server, "get_text")
        result = await get_text_fn()

        assert "text" in result
        assert "1|Line 1\n2|Line 2\n3|Line 3\n4|Line 4\n5|Line 5\n" == result["text"]
        assert "lines_hash" in result

    @pytest.mark.asyncio
    async def test_get_text_line_range(self, server, temp_file):
        """Test getting a specific range of lines from a file."""

        set_file_fn = self.get_tool_fn(server, "set_file")
        await set_file_fn(temp_file)

        get_text_fn = self.get_tool_fn(server, "get_text")
        result = await get_text_fn(2, 4)

        assert "text" in result
        assert "lines_hash" in result
        assert "2|Line 2\n3|Line 3\n4|Line 4\n" == result["text"]

        expected_hash = calculate_hash("Line 2\nLine 3\nLine 4\n", 2, 4)
        assert expected_hash == result["lines_hash"]

    @pytest.mark.asyncio
    async def test_get_text_only_start_line(self, server, temp_file):
        """Test getting text with only start line specified."""
        set_file_fn = self.get_tool_fn(server, "set_file")
        await set_file_fn(temp_file)

        get_text_fn = self.get_tool_fn(server, "get_text")
        result = await get_text_fn(3)

        assert "3|Line 3\n4|Line 4\n5|Line 5\n" == result["text"]
        expected_hash = calculate_hash("Line 3\nLine 4\nLine 5\n", 3, 5)
        assert expected_hash == result["lines_hash"]

    @pytest.mark.asyncio
    async def test_get_text_only_end_line(self, server, temp_file):
        """Test getting text with only end line specified."""
        set_file_fn = self.get_tool_fn(server, "set_file")
        await set_file_fn(temp_file)

        get_text_fn = self.get_tool_fn(server, "get_text")
        result = await get_text_fn(None, 2)

        assert "1|Line 1\n2|Line 2\n" == result["text"]
        expected_hash = calculate_hash("Line 1\nLine 2\n", 1, 2)
        assert expected_hash == result["lines_hash"]

    @pytest.mark.asyncio
    async def test_get_text_invalid_range(self, server, temp_file):
        """Test getting text with an invalid line range."""
        set_file_fn = self.get_tool_fn(server, "set_file")
        await set_file_fn(temp_file)

        get_text_fn = self.get_tool_fn(server, "get_text")

        result = await get_text_fn(4, 2)
        assert "error" in result
        assert "line_start cannot be greater than line_end" in result["error"]

        result = await get_text_fn(0, 3)
        assert "error" in result
        assert "line_start must be at least 1" in result["error"]

    @pytest.mark.asyncio
    async def test_get_text_range_exceeding_file(self, server, temp_file):
        """Test getting a line range that exceeds the file's line count."""
        set_file_fn = self.get_tool_fn(server, "set_file")
        await set_file_fn(temp_file)

        get_text_fn = self.get_tool_fn(server, "get_text")
        result = await get_text_fn(3, 10)

        assert "3|Line 3\n4|Line 4\n5|Line 5\n" == result["text"]

    def test_calculate_hash_function(self):
        """Test the calculate_hash function directly."""

        text = "Some test content"
        hash_no_range = calculate_hash(text)
        expected = hashlib.sha256(text.encode()).hexdigest()[:2]
        assert hash_no_range == expected

        hash_with_range = calculate_hash(text, 1, 3)
        assert hash_with_range.startswith("L1-3-")
        assert hash_with_range.endswith(expected)

    @pytest.mark.asyncio
    async def test_get_text_large_file(self, server):
        """Test getting text from a file larger than MAX_EDIT_LINES lines."""
        more_than_max_lines = server.max_edit_lines + 10
        with tempfile.NamedTemporaryFile(mode="w+", delete=False) as f:
            for i in range(more_than_max_lines):
                f.write(f"Line {i + 1}\n")
            large_file_path = f.name

        try:
            set_file_fn = self.get_tool_fn(server, "set_file")
            await set_file_fn(large_file_path)

            get_text_fn = self.get_tool_fn(server, "get_text")
            result = await get_text_fn()

            assert "text" in result
            assert (
                f"len(selected_lines)={more_than_max_lines} > self.max_edit_lines={server.max_edit_lines} so no hash."
                in result["info"]
            )
            assert len(result["text"].splitlines()) == more_than_max_lines

            result = await get_text_fn(5, 15)

            assert "text" in result
            assert "lines_hash" in result
            assert len(result["text"].splitlines()) == 11

            result = await get_text_fn(5, server.max_edit_lines + 10)

            assert "text" in result
            assert "lines_hash" not in result
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
        assert "lines_hash" in result

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
    async def test_insert_lines(self, server, temp_file):
        """Test insert_lines functionality."""

        set_file_fn = self.get_tool_fn(server, "set_file")
        await set_file_fn(temp_file)

        get_text_fn = self.get_tool_fn(server, "get_text")
        result = await get_text_fn(2, 2)
        line_content = result["text"]
        line_hash = result["lines_hash"]

        insert_lines_fn = self.get_tool_fn(server, "insert_lines")
        new_text = "This is a new inserted line."
        result = await insert_lines_fn(text=new_text, line=2, lines_hash=line_hash)

        assert result["status"] == "success"

        result = await get_text_fn()
        assert new_text in result["text"]

        lines = result["text"].splitlines()
        assert "Line 2" in lines[1]
        assert new_text in lines[2]
        assert "Line 3" in lines[3]

        result = await insert_lines_fn(
            text="This should fail.", line=2, lines_hash="invalid-hash"
        )
        assert "error" in result
        assert "Hash verification failed" in result["error"]

    @pytest.mark.asyncio
    async def test_remove_lines(self, server, temp_file):
        """Test remove_lines functionality."""

        set_file_fn = self.get_tool_fn(server, "set_file")
        await set_file_fn(temp_file)

        # First, read the entire file to verify initial state
        get_text_fn = self.get_tool_fn(server, "get_text")
        initial_result = await get_text_fn()
        assert (
            "1|Line 1\n2|Line 2\n3|Line 3\n4|Line 4\n5|Line 5\n"
            == initial_result["text"]
        )

        # Get hash for lines 2-4
        result = await get_text_fn(2, 4)
        lines_hash = result["lines_hash"]

        # Remove lines 2-4
        remove_lines_fn = self.get_tool_fn(server, "remove_lines")
        result = await remove_lines_fn(line_start=2, line_end=4, lines_hash=lines_hash)

        assert result["status"] == "success"
        assert "Lines 2 to 4 removed" in result["message"]

        # Verify the file now only has lines 1 and 5
        result = await get_text_fn()
        lines = result["text"].splitlines()
        assert len(lines) == 2
        assert "Line 1" in lines[0]
        assert "Line 5" in lines[1]

        # Test hash verification failure
        result = await get_text_fn(1, 1)
        line_hash = result["lines_hash"]

        result = await remove_lines_fn(
            line_start=1, line_end=1, lines_hash="invalid-hash"
        )
        assert "error" in result
        assert "Hash verification failed" in result["error"]

    @pytest.mark.asyncio
    async def test_remove_lines_validation(self, server, temp_file):
        """Test remove_lines validation checks."""

        set_file_fn = self.get_tool_fn(server, "set_file")
        await set_file_fn(temp_file)

        remove_lines_fn = self.get_tool_fn(server, "remove_lines")

        # Test no file set
        server.current_file_path = None
        result = await remove_lines_fn(line_start=1, line_end=2, lines_hash="dummy")
        assert "error" in result
        assert "No file path is set" in result["error"]

        # Reset file path
        await set_file_fn(temp_file)

        # Test line_start < 1
        result = await remove_lines_fn(line_start=0, line_end=2, lines_hash="dummy")
        assert "error" in result
        assert "line_start must be at least 1" in result["error"]

        # Test line_end > file length
        result = await remove_lines_fn(line_start=1, line_end=10, lines_hash="dummy")
        assert "error" in result
        assert "line_end (10) exceeds file length" in result["error"]

        # Test line_start > line_end
        result = await remove_lines_fn(line_start=3, line_end=2, lines_hash="dummy")
        assert "error" in result
        assert "line_start cannot be greater than line_end" in result["error"]

    @pytest.mark.asyncio
    async def test_replace_text_with_remove_and_insert(self, server, temp_file):
        """Test using remove_lines and insert_lines together to replace content (replacing overwrite_text)."""

        set_file_fn = self.get_tool_fn(server, "set_file")
        await set_file_fn(temp_file)

        # First, read the file to verify initial state
        get_text_fn = self.get_tool_fn(server, "get_text")
        initial_result = await get_text_fn()
        assert (
            "1|Line 1\n2|Line 2\n3|Line 3\n4|Line 4\n5|Line 5\n"
            == initial_result["text"]
        )

        # Get hash for lines 2-4 that we want to replace
        result = await get_text_fn(2, 4)
        lines_hash = result["lines_hash"]

        # Step 1: Remove lines 2-4
        remove_lines_fn = self.get_tool_fn(server, "remove_lines")
        result = await remove_lines_fn(line_start=2, line_end=4, lines_hash=lines_hash)
        assert result["status"] == "success"

        # Step 2: Get hash for the line before where we want to insert (now line 1)
        result = await get_text_fn(1, 1)
        line_1_hash = result["lines_hash"]

        # Step 3: Insert new content after line 1
        insert_lines_fn = self.get_tool_fn(server, "insert_lines")
        new_text = "Completely new line 2.\nAnd new line 3.\nAnd new line 4."
        result = await insert_lines_fn(text=new_text, line=1, lines_hash=line_1_hash)
        assert result["status"] == "success"

        # Verify final content
        result = await get_text_fn()
        lines = result["text"].splitlines()

        assert len(lines) == 5
        assert "Line 1" in lines[0]
        assert "Completely new line 2" in lines[1]
        assert "And new line 3" in lines[2]
        assert "And new line 4" in lines[3]
        assert "Line 5" in lines[4]
