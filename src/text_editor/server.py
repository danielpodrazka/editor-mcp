import hashlib

from mcp.server.fastmcp import FastMCP


def calculate_hash(text: str, line_start=None, line_end=None) -> str:
    """
    Args:
        text (str): Content to hash

    Returns:
        str: Hex digest of SHA-256 hash
    """
    if line_start and line_end:
        prefix = f"L{line_start}-{line_end}-"
    else:
        prefix = ""
    return f"{prefix}{hashlib.sha256(text.encode()).hexdigest()[:2]}"


class TextEditorServer:
    def __init__(self):
        self.mcp = FastMCP("text-editor")

        self.register_tools()

    def register_tools(self):
        @self.mcp.tool()
        async def hello_world() -> str:
            """hello"""
            return "hello"

    def run(self):
        """Run the MCP server."""
        self.mcp.run(transport="stdio")


# Create and run the server if this script is executed directly
if __name__ == "__main__":
    server = TextEditorServer()
    server.run()
