import asyncio

from fastmcp import Client
from mcp_servers.case_mcp.server import mcp


async def main():
    async with Client(mcp) as client:

        print("\n=== TOOLS ===")

        tools = await client.list_tools()

        for tool in tools:
            print(tool.name)

        print("\n=== RESOURCE TEMPLATES ===")

        templates = await client.list_resource_templates()

        for template in templates:
            print(template.uriTemplate)

        print("\n=== PROMPTS ===")

        prompts = await client.list_prompts()

        for prompt in prompts:
            print(prompt.name)


if __name__ == "__main__":
    asyncio.run(main())