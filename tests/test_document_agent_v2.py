import asyncio

from agents.document_agent_v2 import (
    build_document_agent,
)


async def main():

    agent, adapter = await build_document_agent()

    try:

        result = await agent.ainvoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": """
Analyze the documents for CASE-001.

Use MCP tools to:
1. List the documents.
2. Extract their text.
3. Classify them.
4. Extract key fields.
5. Validate whether the case documents
   are complete.

Report:
- document type
- verified facts
- missing information
- confidence concerns
- risks
- next processing action

Do not make a final claim decision.
""",
                    }
                ]
            }
        )

        print("\n==========================")
        print("DOCUMENT AGENT V2 RESULT")
        print("==========================")

        final_message = result["messages"][-1]

        print(final_message.content)

    finally:

        await adapter.__aexit__(
            None,
            None,
            None,
        )


if __name__ == "__main__":
    asyncio.run(main())