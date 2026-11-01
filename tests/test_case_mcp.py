import asyncio
from fastmcp import Client
from mcp_servers.case_mcp.server import mcp


async def main():
    async with Client(mcp) as client:

        print("\n--- Available Tools ---")
        tools = await client.list_tools()
        for tool in tools:
            print(tool.name)

        print("\n--- Testing get_case ---")
        result = await client.call_tool(
            "get_case",
            {"case_id": "CASE-001"}
        )
        print(result)

        print("\n--- Testing list_cases ---")
        result = await client.call_tool(
            "list_cases",
            {}
        )
        print(result)


if __name__ == "__main__":
    asyncio.run(main())