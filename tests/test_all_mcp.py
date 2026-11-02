import asyncio

from fastmcp import Client

from mcp_servers.case_mcp.server import mcp as case_mcp
from mcp_servers.policy_mcp.server import mcp as policy_mcp
from mcp_servers.documents_mcp.server import mcp as documents_mcp
from mcp_servers.workflow_mcp.server import mcp as workflow_mcp


async def test_case_mcp():
    print("\n=== CASE MCP ===")

    async with Client(case_mcp) as client:
        tools = await client.list_tools()

        for tool in tools:
            print("Tool:", tool.name)

        result = await client.call_tool(
            "get_case",
            {
                "case_id": "CASE-001"
            },
        )

        print("get_case:", result)


async def test_policy_mcp():
    print("\n=== POLICY MCP ===")

    async with Client(policy_mcp) as client:
        tools = await client.list_tools()

        for tool in tools:
            print("Tool:", tool.name)

        result = await client.call_tool(
            "check_coverage",
            {
                "policy_number": "POL-1001",
                "claim_type": "Medical",
                "claim_amount": 25000,
            },
        )

        print("check_coverage:", result)


async def test_documents_mcp():
    print("\n=== DOCUMENTS MCP ===")

    async with Client(documents_mcp) as client:
        tools = await client.list_tools()

        for tool in tools:
            print("Tool:", tool.name)

        result = await client.call_tool(
            "validate_case_documents",
            {
                "case_id": "CASE-001"
            },
        )

        print("validate_case_documents:", result)


async def test_workflow_mcp():
    print("\n=== WORKFLOW MCP ===")

    async with Client(workflow_mcp) as client:
        tools = await client.list_tools()

        for tool in tools:
            print("Tool:", tool.name)

        result = await client.call_tool(
            "request_approval",
            {
                "case_id": "CASE-001",
                "approver": "Demo Approver",
            },
        )

        print("request_approval:", result)


async def main():
    await test_case_mcp()
    await test_policy_mcp()
    await test_documents_mcp()
    await test_workflow_mcp()

    print("\n==============================")
    print("ALL MCP TESTS COMPLETED")
    print("==============================")


if __name__ == "__main__":
    asyncio.run(main())