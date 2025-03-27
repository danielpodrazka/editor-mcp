import hashlib


def calculate_hash(content: str) -> str:
    """
    Calculate SHA-256 hash of content.

    Args:
        content (str): Content to hash

    Returns:
        str: Hex digest of SHA-256 hash
    """
    return hashlib.sha256(content.encode()).hexdigest()
