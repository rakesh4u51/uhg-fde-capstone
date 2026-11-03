import asyncio

from agents.summary_agent_v2 import (
    build_summary_agent,
)


async def main():
    (
        agent,
        case_adapter,
        policy_adapter,
        document_adapter,
    ) = await build_summary_agent()

    try:
        result = await agent.ainvoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": """
Prepare a grounded human-review summary
for claim CASE-001.

Use the available MCP tools to retrieve:

1. The claim.
2. Its policy.
3. Coverage information.
4. Claim documents.
5. Extracted document fields.
6. Document-completeness information.

Return:

FACTS:
EVIDENCE:
POLICY STATUS:
MISSING INFORMATION:
RISKS:
VALIDATION ISSUES:
NEXT ACTION:

Do not make a final claim decision.
""",
                    }
                ]
            }
        )

        print("\n========================")
        print("SUMMARY AGENT V2 RESULT")
        print("========================")

        final_message = result["messages"][-1]

        print(final_message.content)

    finally:
        await case_adapter.__aexit__(
            None, None, None
        )
        await policy_adapter.__aexit__(
            None, None, None
        )
        await document_adapter.__aexit__(
            None, None, None
        )


if __name__ == "__main__":
    asyncio.run(main())