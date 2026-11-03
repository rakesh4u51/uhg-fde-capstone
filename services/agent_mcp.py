import sys

from langchain_mcp_adapters.client import MultiServerMCPClient


def build_mcp_client():
    python = sys.executable

    return MultiServerMCPClient(
        {
            "case": {
                "command": python,
                "args": [
                    "mcp_servers/case_mcp/server.py"
                ],
                "transport": "stdio",
            },
            "policy": {
                "command": python,
                "args": [
                    "mcp_servers/policy_mcp/server.py"
                ],
                "transport": "stdio",
            },
            "documents": {
                "command": python,
                "args": [
                    "mcp_servers/documents_mcp/server.py"
                ],
                "transport": "stdio",
            },
            "workflow": {
                "command": python,
                "args": [
                    "mcp_servers/workflow_mcp/server.py"
                ],
                "transport": "stdio",
            },
        }
    )