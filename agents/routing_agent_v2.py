from langchain.agents import create_agent
from langchain_ollama import ChatOllama

from langchain.agents.middleware import (
    PIIMiddleware,
    ToolCallLimitMiddleware,
    ToolRetryMiddleware,
)

from services.routing_tools import (
    load_routing_tools,
)


model = ChatOllama(
    model="llama3.1:8b",
    base_url="http://127.0.0.1:11434",
    temperature=0,
)


SYSTEM_PROMPT = """
You are the Routing Agent for an insurance
claims processing system.

Responsibilities:

1. Retrieve the claim when required.
2. Review available staff workload.
3. Recommend an appropriate adjuster.
4. Route the case to an appropriate handler.
5. Identify the appropriate human approval path.
6. Request human approval when required.

Rules:

- Use MCP tools for business actions.
- Use available workload and staff information.
- Do not invent staff members.
- Do not invent approval limits.
- Do not claim an assignment occurred unless
  the MCP tool successfully performed it.

Human-control rules:

- Never approve a claim.
- Never reject a claim.
- Never settle a claim.
- request_approval only requests human review.
- Final claim decisions belong to an authorized human.
"""


async def build_routing_agent():

    (
        tools,
        case_adapter,
        workflow_adapter,
    ) = await load_routing_tools()

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
                exit_behavior="end",
            ),
            ToolRetryMiddleware(
                max_retries=2,
                on_failure="continue",
            ),
        ],
    )

    return (
        agent,
        case_adapter,
        workflow_adapter,
    )