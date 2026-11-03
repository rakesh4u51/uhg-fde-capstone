import asyncio

from agents.routing_agent_v2 import (
    build_routing_agent,
)


async def main():

    (
        agent,
        case_adapter,
        workflow_adapter,
    ) = await build_routing_agent()

    try:

        result = await agent.ainvoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": """
Route claim CASE-001.

Use MCP tools to:

1. Retrieve the claim.
2. Inspect available workload.
3. Identify an appropriate handler.
4. Request human approval.

Report:
- selected handler
- routing reason
- human approval route
- next action

Do not approve or reject the claim.
""",
                    }
                ]
            }
        )

        print("\n========================")
        print("ROUTING AGENT V2 RESULT")
        print("========================")

        print(
            result["messages"][-1].content
        )

    finally:

        await case_adapter.__aexit__(
            None, None, None
        )
        await workflow_adapter.__aexit__(
            None, None, None
        )


if __name__ == "__main__":
    asyncio.run(main())