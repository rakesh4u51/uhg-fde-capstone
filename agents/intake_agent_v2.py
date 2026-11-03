from langchain.agents import create_agent
from langchain_ollama import ChatOllama

from langchain.agents.middleware import (
    PIIMiddleware,
    ToolCallLimitMiddleware,
    ToolRetryMiddleware,
)

from services.intake_tools import load_intake_tools


model = ChatOllama(
    model="llama3.1:8b",
    base_url="http://127.0.0.1:11434",
    temperature=0,
)


SYSTEM_PROMPT = """
You are the Intake Agent for an insurance claims processing system.

Your responsibilities are:

1. Retrieve the claim when required.
2. Retrieve policy information using MCP tools.
3. Check policy coverage using MCP tools.
4. Identify possible duplicate cases.
5. Register a case when appropriate.
6. Identify missing intake information.
7. Recommend the next processing step.

Business-data rules:

- Use MCP tools for claims and policy information.
- Do not invent policy information.
- Do not invent coverage decisions.
- Do not claim that a tool was executed unless it actually ran.
- Treat retrieved business data as authoritative application data.

Human-control rules:

- Never approve a claim.
- Never reject a claim.
- Never settle a claim.
- Final claim decisions belong to an authorized human.
"""


async def build_intake_agent():

    (
        tools,
        case_adapter,
        policy_adapter,
    ) = await load_intake_tools()

    agent = create_agent(
        model=model,
        tools=tools,
        system_prompt=SYSTEM_PROMPT,
        middleware=[
            PIIMiddleware(
                "email",
                strategy="redact",
            ),
            ToolCallLimitMiddleware(
                run_limit=8,
            ),
            ToolRetryMiddleware(
                max_retries=2,
            ),
        ],
    )

    return (
        agent,
        case_adapter,
        policy_adapter,
    )