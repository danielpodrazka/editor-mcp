"""Tests for delete_text_file_contents functionality."""

import pytest

from mcp_text_editor.models import DeleteTextFileContentsRequest, FileRange
from mcp_text_editor.service import TextEditorService


@pytest.fixture
def service():
    """Create TextEditorService instance."""
    return TextEditorService()


def test_delete_text_file_contents_basic(service, tmp_path):
    """Test basic delete operation."""
    # Create test file
    test_file = tmp_path / "delete_test.txt"
    test_content = "line1\nline2\nline3\n"
    test_file.write_text(test_content)
    file_path = str(test_file)

    # Calculate initial hash
    initial_hash = service.calculate_hash(test_content)

    # Create delete request
    request = DeleteTextFileContentsRequest(
        file_path=file_path,
        file_hash=initial_hash,
        ranges=[
            FileRange(start=2, end=2, range_hash=service.calculate_hash("line2\n"))
        ],
        encoding="utf-8",
    )

    # Apply delete
    result = service.delete_text_file_contents(request)
    assert file_path in result
    delete_result = result[file_path]
    assert delete_result.result == "ok"

    # Verify changes
    new_content = test_file.read_text()
    assert new_content == "line1\nline3\n"


def test_delete_text_file_contents_hash_mismatch(service, tmp_path):
    """Test deleting with hash mismatch."""
    # Create test file
    test_file = tmp_path / "hash_mismatch_test.txt"
    test_content = "line1\nline2\nline3\n"
    test_file.write_text(test_content)
    file_path = str(test_file)

    # Create delete request with incorrect hash
    request = DeleteTextFileContentsRequest(
        file_path=file_path,
        file_hash="incorrect_hash",
        ranges=[
            FileRange(start=2, end=2, range_hash=service.calculate_hash("line2\n"))
        ],
        encoding="utf-8",
    )

    # Attempt delete
    result = service.delete_text_file_contents(request)
    assert file_path in result
    delete_result = result[file_path]
    assert delete_result.result == "error"
    assert "hash mismatch" in delete_result.reason.lower()


def test_delete_text_file_contents_invalid_ranges(service, tmp_path):
    """Test deleting with invalid ranges."""
    # Create test file
    test_file = tmp_path / "invalid_ranges_test.txt"
    test_content = "line1\nline2\nline3\n"
    test_file.write_text(test_content)
    file_path = str(test_file)

    # Calculate initial hash
    initial_hash = service.calculate_hash(test_content)

    # Create delete request with invalid ranges
    request = DeleteTextFileContentsRequest(
        file_path=file_path,
        file_hash=initial_hash,
        ranges=[FileRange(start=1, end=10, range_hash="hash1")],  # Beyond file length
        encoding="utf-8",
    )

    # Attempt delete
    result = service.delete_text_file_contents(request)
    assert file_path in result
    delete_result = result[file_path]
    assert delete_result.result == "error"
    assert "invalid ranges" in delete_result.reason.lower()


def test_delete_text_file_contents_range_hash_mismatch(service, tmp_path):
    """Test deleting with range hash mismatch."""
    # Create test file
    test_file = tmp_path / "range_hash_test.txt"
    test_content = "line1\nline2\nline3\n"
    test_file.write_text(test_content)
    file_path = str(test_file)

    # Calculate initial hash
    initial_hash = service.calculate_hash(test_content)

    # Create delete request with incorrect range hash
    request = DeleteTextFileContentsRequest(
        file_path=file_path,
        file_hash=initial_hash,
        ranges=[FileRange(start=2, end=2, range_hash="incorrect_hash")],
        encoding="utf-8",
    )

    # Attempt delete
    result = service.delete_text_file_contents(request)
    assert file_path in result
    delete_result = result[file_path]
    assert delete_result.result == "error"
    assert "hash mismatch for range" in delete_result.reason.lower()


def test_delete_text_file_contents_relative_path(service, tmp_path):
    """Test deleting with a relative file path."""
    # Create delete request with relative path
    request = DeleteTextFileContentsRequest(
        file_path="relative/path.txt",
        file_hash="some_hash",
        ranges=[FileRange(start=1, end=1, range_hash="hash1")],
        encoding="utf-8",
    )

    # Attempt delete
    result = service.delete_text_file_contents(request)
    assert "relative/path.txt" in result
    delete_result = result["relative/path.txt"]
    assert delete_result.result == "error"
    assert "no such file or directory" in delete_result.reason.lower()


def test_delete_text_file_contents_empty_ranges(service, tmp_path):
    """Test deleting with empty ranges list."""
    test_file = tmp_path / "empty_ranges.txt"
    test_content = "line1\nline2\nline3\n"
    test_file.write_text(test_content)
    file_path = str(test_file)
    content_hash = service.calculate_hash(test_content)

    # Test empty ranges
    request = DeleteTextFileContentsRequest(
        file_path=file_path,
        file_hash=content_hash,
        ranges=[],  # Empty ranges list
        encoding="utf-8",
    )

    result = service.delete_text_file_contents(request)
    assert file_path in result
    delete_result = result[file_path]
    assert delete_result.result == "error"
    assert "missing required argument: ranges" in delete_result.reason.lower()
