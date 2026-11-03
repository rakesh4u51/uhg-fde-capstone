import asyncio

from agents.intake_agent_v2 import (
    build_intake_agent,
)


async def main():

    (
        agent,
        case_adapter,
        policy_adapter,
    ) = await build_intake_agent()

    try:

        result = await agent.ainvoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": """
Review claim CASE-001.

Use the available MCP tools to:

1. Retrieve the case.
2. Retrieve its policy.
3. Check whether the Medical claim
   amount 25000 is covered.
4. Check for similar cases.
5. Recommend the next processing step.

Do not make a final claim decision.
""",
                    }
                ]
            }
        )

        print("\n=========================")
        print("INTAKE AGENT V2 RESULT")
        print("=========================")

        final_message = result["messages"][-1]

        print(final_message.content)

    finally:

        await case_adapter.__aexit__(
            None,
            None,
            None,
        )

        await policy_adapter.__aexit__(
            None,
            None,
            None,
        )


if __name__ == "__main__":
    asyncio.run(main())