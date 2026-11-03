from langchain.mcp import MCPAdapter

from mcp_servers.case_mcp.server import (
    mcp as case_mcp,
)

from mcp_servers.workflow_mcp.server import (
    mcp as workflow_mcp,
)


ALLOWED_ROUTING_TOOLS = {
    "get_case",
    "get_workload",
    "assign_case",
    "request_approval",
}


async def load_routing_tools():

    case_adapter = MCPAdapter(case_mcp)
    workflow_adapter = MCPAdapter(workflow_mcp)

    await case_adapter.__aenter__()
    await workflow_adapter.__aenter__()

    case_tools = await case_adapter.list_tools()
    workflow_tools = await workflow_adapter.list_tools()

    tools = [
        tool
        for tool in case_tools + workflow_tools
        if tool.name in ALLOWED_ROUTING_TOOLS
    ]

    return (
        tools,
        case_adapter,
        workflow_adapter,
    )