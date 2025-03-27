"""Core service logic for the MCP Text Editor Server."""

from typing import Dict, List, Optional, Tuple

from .models import (
    DeleteTextFileContentsRequest,
    EditFileOperation,
    EditPatch,
    EditResult,
    FileRange,
)
from .utils import calculate_hash


class TextEditorService:
    """Service class for text file operations."""

    @staticmethod
    def read_file(
        file_path: str, start: int = 1, end: Optional[int] = None
    ) -> Tuple[str, int, int]:
        """Read file contents within specified line range."""
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        # Adjust line numbers to 0-based index
        start = max(1, start) - 1
        end = len(lines) if end is None else min(end, len(lines))

        selected_lines = lines[start:end]
        content = "".join(selected_lines)

        return content, start + 1, end

    @staticmethod
    def validate_patches(patches: List[EditPatch], total_lines: int) -> bool:
        """Validate patches for overlaps and bounds."""
        # Sort patches by start
        sorted_patches = sorted(patches, key=lambda x: x.start)

        prev_end = 0
        for patch in sorted_patches:
            if patch.start <= prev_end:
                return False
            patch_end = patch.end or total_lines
            if patch_end > total_lines:
                return False
            prev_end = patch_end

        return True

    def edit_file(
        self, file_path: str, operation: EditFileOperation
    ) -> Dict[str, EditResult]:
        """Edit file contents with conflict detection."""
        current_hash = None
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                current_content = f.read()
                current_hash = calculate_hash(current_content)

            # Check for conflicts
            if current_hash != operation.hash:
                return {
                    file_path: EditResult(
                        result="error",
                        reason="Content hash mismatch",
                        hash=current_hash,
                    )
                }

            # Split content into lines
            lines = current_content.splitlines(keepends=True)

            # Validate patches
            if not self.validate_patches(operation.patches, len(lines)):
                return {
                    file_path: EditResult(
                        result="error",
                        reason="Invalid patch ranges",
                        hash=current_hash,
                    )
                }

            # Apply patches
            new_lines = lines.copy()
            for patch in operation.patches:
                start_idx = patch.start - 1
                end_idx = patch.end if patch.end else len(lines)
                patch_lines = patch.contents.splitlines(keepends=True)
                new_lines[start_idx:end_idx] = patch_lines

            # Write new content
            new_content = "".join(new_lines)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(new_content)

            new_hash = calculate_hash(new_content)
            return {
                file_path: EditResult(
                    result="ok",
                    hash=new_hash,
                    reason=None,
                )
            }

        except FileNotFoundError as e:
            return {
                file_path: EditResult(
                    result="error",
                    reason=str(e),
                    hash=None,
                )
            }
        except Exception as e:
            return {
                file_path: EditResult(
                    result="error",
                    reason=str(e),
                    hash=None,  # Don't return the current hash on error
                )
            }

    @staticmethod
    def validate_ranges(ranges: List[FileRange], total_lines: int) -> bool:
        """Validate ranges for overlaps and bounds."""
        # Sort ranges by start line
        sorted_ranges = sorted(ranges, key=lambda x: x.start)

        prev_end = 0
        for range_ in sorted_ranges:
            if range_.start <= prev_end:
                return False  # Overlapping ranges
            if range_.start < 1:
                return False  # Invalid start line
            range_end = range_.end or total_lines
            if range_end > total_lines:
                return False  # Exceeding file length
            if range_.end is not None and range_.end < range_.start:
                return False  # End before start
            prev_end = range_end

        return True
