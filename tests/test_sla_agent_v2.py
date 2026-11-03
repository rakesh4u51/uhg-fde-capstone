import asyncio

from agents.sla_agent_v2 import (
    build_sla_agent,
)


async def main():

    agent, adapter = await build_sla_agent()

    try:

        result = await agent.ainvoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": """
Prepare SLA and communication handling
for CASE-001.

The case is currently awaiting
human approval.

Use available MCP tools where appropriate.

Report:
- SLA action
- communication
- escalation requirement
- next action

Do not make a final claim decision.
""",
                    }
                ]
            }
        )

        print("\n====================")
        print("SLA AGENT V2 RESULT")
        print("====================")

        print(
            result["messages"][-1].content
        )

    finally:

        await adapter.__aexit__(
            None, None, None
        )


if __name__ == "__main__":
    asyncio.run(main())