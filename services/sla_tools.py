from langchain.mcp import MCPAdapter

from mcp_servers.workflow_mcp.server import (
    mcp as workflow_mcp,
)


ALLOWED_SLA_TOOLS = {
    "schedule_sla",
    "send_notification",
    "request_documents",
}


async def load_sla_tools():

    adapter = MCPAdapter(workflow_mcp)

    await adapter.__aenter__()

    all_tools = await adapter.list_tools()

    tools = [
        tool
        for tool in all_tools
        if tool.name in ALLOWED_SLA_TOOLS
    ]

    return tools, adapter