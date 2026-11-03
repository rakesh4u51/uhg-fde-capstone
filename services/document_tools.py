from langchain.mcp import MCPAdapter

from mcp_servers.documents_mcp.server import (
    mcp as documents_mcp,
)


ALLOWED_DOCUMENT_TOOLS = {
    "list_documents",
    "extract_text",
    "classify_document",
    "extract_fields",
    "validate_case_documents",
}


async def load_document_tools():

    adapter = MCPAdapter(
        documents_mcp
    )

    await adapter.__aenter__()

    all_tools = await adapter.list_tools()

    tools = [
        tool
        for tool in all_tools
        if tool.name in ALLOWED_DOCUMENT_TOOLS
    ]

    return tools, adapter