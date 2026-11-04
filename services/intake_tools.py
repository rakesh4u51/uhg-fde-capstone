from services.mcp_compat import MCPAdapter

from mcp_servers.case_mcp.server import (
    mcp as case_mcp,
)

from mcp_servers.policy_mcp.server import (
    mcp as policy_mcp,
)


ALLOWED_INTAKE_TOOLS = {
    "get_case",
    "register_case",
    "find_similar_cases",
    "get_policy",
    "check_coverage",
}


async def load_intake_tools():

    case_adapter = MCPAdapter(
        case_mcp
    )

    policy_adapter = MCPAdapter(
        policy_mcp
    )

    await case_adapter.__aenter__()
    await policy_adapter.__aenter__()

    case_tools = await case_adapter.list_tools()
    policy_tools = await policy_adapter.list_tools()

    tools = [
        tool
        for tool in (
            case_tools
            + policy_tools
        )
        if tool.name in ALLOWED_INTAKE_TOOLS
    ]

    return (
        tools,
        case_adapter,
        policy_adapter,
    )