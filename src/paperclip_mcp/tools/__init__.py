"""Importing this package registers every tool module on the shared FastMCP instance."""

from paperclip_mcp.tools import (  # noqa: F401
    admin,
    agents,
    approvals,
    decisions,
    goals_projects,
    issues,
    monitoring,
    pipelines,
    routines,
)
