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
        return server

    @pytest.fixture
    def temp_file(self):
        """Create a temporary file for testing."""
        content = "Line 1\nLine 2\nLine 3\nLine 4\nLine 5\n"
        with tempfile.NamedTemporaryFile(mode="w+", delete=False) as f:
            f.write(content)
            temp_path = f.name

        yield temp_path

        # Cleanup
        if os.path.exists(temp_path):
            os.unlink(temp_path)

    @pytest.fixture
    def empty_temp_file(self):
        """Create an empty temporary file for testing."""
        with tempfile.NamedTemporaryFile(mode="w+", delete=False) as f:
            temp_path = f.name

        yield temp_path

        # Cleanup
        if os.path.exists(temp_path):
            os.unlink(temp_path)

    def get_tool_fn(self, server, tool_name):
        """Helper to get the tool function from the server."""
        # Access the tool directly based on the internal structure
        tools_dict = server.mcp._tool_manager._tools
        return tools_dict[tool_name].fn

    @pytest.mark.asyncio
    async def test_set_file_valid(self, server, temp_file):
        """Test setting a valid file path."""
        set_file_fn = self.get_tool_fn(server, "set_file")

        # Call the tool function directly
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
        # First set the file
        set_file_fn = self.get_tool_fn(server, "set_file")
        await set_file_fn(temp_file)

        # Then get the text
        get_text_fn = self.get_tool_fn(server, "get_text")
        result = await get_text_fn()

        # Verify result
        assert "text" in result
        assert "lines_hash" in result
        assert "Line 1\nLine 2\nLine 3\nLine 4\nLine 5\n" == result["text"]

        # Verify hash
        expected_hash = calculate_hash("Line 1\nLine 2\nLine 3\nLine 4\nLine 5\n")
        assert expected_hash == result["lines_hash"]

    @pytest.mark.asyncio
    async def test_get_text_line_range(self, server, temp_file):
        """Test getting a specific range of lines from a file."""
        # First set the file
        set_file_fn = self.get_tool_fn(server, "set_file")
        await set_file_fn(temp_file)

        # Get lines 2-4
        get_text_fn = self.get_tool_fn(server, "get_text")
        result = await get_text_fn(2, 4)

        # Verify result
        assert "text" in result
        assert "lines_hash" in result
        assert "Line 2\nLine 3\nLine 4\n" == result["text"]

        # Verify hash includes line range
        expected_hash = calculate_hash("Line 2\nLine 3\nLine 4\n", 2, 4)
        assert expected_hash == result["lines_hash"]

    @pytest.mark.asyncio
    async def test_get_text_only_start_line(self, server, temp_file):
        """Test getting text with only start line specified."""
        set_file_fn = self.get_tool_fn(server, "set_file")
        await set_file_fn(temp_file)

        # Get from line 3 to end
        get_text_fn = self.get_tool_fn(server, "get_text")
        result = await get_text_fn(3)

        # Verify result
        assert "Line 3\nLine 4\nLine 5\n" == result["text"]
        expected_hash = calculate_hash("Line 3\nLine 4\nLine 5\n", 3, 5)
        assert expected_hash == result["lines_hash"]

    @pytest.mark.asyncio
    async def test_get_text_only_end_line(self, server, temp_file):
        """Test getting text with only end line specified."""
        set_file_fn = self.get_tool_fn(server, "set_file")
        await set_file_fn(temp_file)

        # Get from start to line 2
        get_text_fn = self.get_tool_fn(server, "get_text")
        result = await get_text_fn(None, 2)

        # Verify result
        assert "Line 1\nLine 2\n" == result["text"]
        expected_hash = calculate_hash("Line 1\nLine 2\n", 1, 2)
        assert expected_hash == result["lines_hash"]

    @pytest.mark.asyncio
    async def test_get_text_invalid_range(self, server, temp_file):
        """Test getting text with an invalid line range."""
        set_file_fn = self.get_tool_fn(server, "set_file")
        await set_file_fn(temp_file)

        get_text_fn = self.get_tool_fn(server, "get_text")

        # Start line greater than end line
        result = await get_text_fn(4, 2)
        assert "error" in result
        assert "line_start cannot be greater than line_end" in result["error"]

        # Start line less than 1
        result = await get_text_fn(0, 3)
        assert "error" in result
        assert "line_start must be at least 1" in result["error"]

    @pytest.mark.asyncio
    async def test_get_text_range_exceeding_file(self, server, temp_file):
        """Test getting a line range that exceeds the file's line count."""
        set_file_fn = self.get_tool_fn(server, "set_file")
        await set_file_fn(temp_file)

        # End line beyond file length
        get_text_fn = self.get_tool_fn(server, "get_text")
        result = await get_text_fn(3, 10)

        # Should adjust to file length
        assert "Line 3\nLine 4\nLine 5\n" == result["text"]
        expected_hash = calculate_hash("Line 3\nLine 4\nLine 5\n", 3, 5)
        assert expected_hash == result["lines_hash"]

    @pytest.mark.asyncio
    async def test_get_text_empty_file(self, server, empty_temp_file):
        """Test getting text from an empty file."""
        set_file_fn = self.get_tool_fn(server, "set_file")
        await set_file_fn(empty_temp_file)

        get_text_fn = self.get_tool_fn(server, "get_text")
        result = await get_text_fn()

        assert result["text"] == ""
        expected_hash = calculate_hash("")
        assert expected_hash == result["lines_hash"]

    def test_calculate_hash_function(self):
        """Test the calculate_hash function directly."""
        # Test with no line range
        text = "Some test content"
        hash_no_range = calculate_hash(text)
        expected = hashlib.sha256(text.encode()).hexdigest()[:2]
        assert hash_no_range == expected

        # Test with line range
        hash_with_range = calculate_hash(text, 1, 3)
        assert hash_with_range.startswith("L1-3-")
        assert hash_with_range.endswith(expected)

    @pytest.mark.asyncio
    async def test_get_text_large_file(self, server):
        """Test getting text from a file larger than 50 lines."""
        # Create a temporary file with more than 50 lines
        with tempfile.NamedTemporaryFile(mode="w+", delete=False) as f:
            for i in range(60):
                f.write(f"Line {i + 1}\n")
            large_file_path = f.name

        try:
            # Set the file
            set_file_fn = self.get_tool_fn(server, "set_file")
            await set_file_fn(large_file_path)

            # Get the entire file
            get_text_fn = self.get_tool_fn(server, "get_text")
            result = await get_text_fn()

            # Verify 'lines_hash' is not included when file is > 50 lines
            assert "text" in result
            assert "lines_hash" not in result
            assert "range > 50 so no hash." in result["info"]
            assert len(result["text"].splitlines()) == 60

            # Now get a small subset of lines (e.g., lines 5-15)
            result = await get_text_fn(5, 15)

            # Verify 'lines_hash' is included when selection is <= 50 lines
            assert "text" in result
            assert "lines_hash" in result
            assert len(result["text"].splitlines()) == 11  # Lines 5-15 inclusive

            # Get a large subset of lines (e.g., lines 5-60)
            result = await get_text_fn(5, 60)

            # Verify 'lines_hash' is not included when selection is > 50 lines
            assert "text" in result
            assert "lines_hash" not in result
            assert len(result["text"].splitlines()) == 56  # Lines 5-60 inclusive

        finally:
            # Clean up
            if os.path.exists(large_file_path):
                os.unlink(large_file_path)
