#!/usr/bin/env python3
"""
CAPA Test Automation MCP Server

Exposes ROSA HCP cluster management, AWS resource queries, diagnostics,
and knowledge base search to MCP clients (Claude Code, etc.).
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("capa-automation")

from tools.cluster_tools import register_tools as register_cluster_tools
from tools.aws_tools import register_tools as register_aws_tools
from tools.kb_tools import register_tools as register_kb_tools
from tools.k8s_tools import register_tools as register_k8s_tools
from tools.diagnostic_tools import register_tools as register_diagnostic_tools

register_cluster_tools(mcp)
register_aws_tools(mcp)
register_kb_tools(mcp)
register_k8s_tools(mcp)
register_diagnostic_tools(mcp)

if __name__ == "__main__":
    mcp.run(transport="stdio")
