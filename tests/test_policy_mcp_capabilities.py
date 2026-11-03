import asyncio

from fastmcp import Client
from mcp_servers.policy_mcp.server import mcp


async def main():

    async with Client(mcp) as client:

        print("\n=== POLICY TOOLS ===")

        tools = await client.list_tools()

        for tool in tools:
            print(tool.name)

        print("\n=== POLICY RESOURCE TEMPLATES ===")

        templates = await client.list_resource_templates()

        for template in templates:
            print(template.uriTemplate)


if __name__ == "__main__":
    asyncio.run(main())