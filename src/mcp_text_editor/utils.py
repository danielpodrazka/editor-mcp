import hashlib


def calculate_hash(content: str,line_start=None,line_end=None) -> str:
    """
    Calculate SHA-256 hash of content.

    Args:
        content (str): Content to hash

    Returns:
        str: Hex digest of SHA-256 hash
    """
    if line_start and line_end:
        prefix = f"L{line_start}-{line_end}-"
    else:
        prefix= ""
    return f"{prefix}{hashlib.sha256(content.encode()).hexdigest()[:2]}"
