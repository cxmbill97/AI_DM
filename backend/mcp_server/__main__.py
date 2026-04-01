"""Entry point: python -m mcp_server

Runs the MCP server over stdio transport (default).
Compatible with Claude Desktop, Cursor, and any MCP-capable client.

To register with Claude Desktop, add to your claude_desktop_config.json:
{
  "mcpServers": {
    "deduction-game": {
      "command": "uv",
      "args": ["run", "python", "-m", "mcp_server"],
      "cwd": "/path/to/project/backend"
    }
  }
}
"""

from mcp_server.server import mcp

if __name__ == "__main__":
    mcp.run()
