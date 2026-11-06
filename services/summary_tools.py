from services.mcp_compat import MCPAdapter

from mcp_servers.case_mcp.server import (
    mcp as case_mcp,
)

from mcp_servers.policy_mcp.server import (
    mcp as policy_mcp,
)

from mcp_servers.documents_mcp.server import (
    mcp as documents_mcp,
)


ALLOWED_SUMMARY_TOOLS = {
    "get_case",
    "get_policy",
    "check_coverage",
    "list_documents",
    "extract_text",
    "classify_document",
    "extract_fields",
    "validate_case_documents",
    "save_summary",
}


async def load_summary_tools():
    """Load only the MCP tools permitted for Summary Agent."""

    case_adapter = MCPAdapter(case_mcp)
    policy_adapter = MCPAdapter(policy_mcp)
    document_adapter = MCPAdapter(documents_mcp)

    await case_adapter.__aenter__()
    await policy_adapter.__aenter__()
    await document_adapter.__aenter__()

    case_tools = await case_adapter.list_tools()
    policy_tools = await policy_adapter.list_tools()
    document_tools = await document_adapter.list_tools()

    all_tools = (
        case_tools
        + policy_tools
        + document_tools
    )

    allowed_tools = [
        tool
        for tool in all_tools
        if tool.name in ALLOWED_SUMMARY_TOOLS
    ]

    return (
        allowed_tools,
        case_adapter,
        policy_adapter,
        document_adapter,
    )