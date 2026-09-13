#!/usr/bin/env python3
"""
paperclip-mcp — MCP server for the Paperclip AI agent orchestration platform.

Exposes Paperclip's REST API (v0.3.x) as MCP tools for the human operator layer:
issues, agents, goals, projects, approvals, costs, routines, decisions, pipelines.

Documentation: https://github.com/paperclipai/paperclip
MCP spec:      https://modelcontextprotocol.io

Configuration is read from environment variables; see paperclip_mcp.core and .env.example.
"""

from __future__ import annotations

import argparse

import paperclip_mcp.tools  # noqa: F401  (registers all tools)
from paperclip_mcp.core import mcp

__all__ = ["mcp", "main"]


def main() -> None:
    """CLI entry point — invoked via `paperclip-mcp` or `python -m paperclip_mcp`."""
    parser = argparse.ArgumentParser(
        prog="paperclip-mcp",
        description="MCP server for the Paperclip AI agent orchestration platform.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Bind address. Use 0.0.0.0 only in trusted local networks.",
    )
    parser.add_argument("--port", type=int, default=9011, help="Bind port.")
    parser.add_argument(
        "--transport",
        default="streamable-http",
        choices=["streamable-http", "sse", "stdio"],
        help=(
            "MCP transport protocol. "
            "'streamable-http' for Claude Code / mcp-proxy; "
            "'stdio' for Claude Desktop."
        ),
    )
    args = parser.parse_args()

    if args.transport == "stdio":
        mcp.run(transport="stdio")
    else:
        mcp.run(transport=args.transport, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
