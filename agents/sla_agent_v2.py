from langchain.agents import create_agent
from langchain_ollama import ChatOllama

from langchain.agents.middleware import (
    PIIMiddleware,
    ToolCallLimitMiddleware,
    ToolRetryMiddleware,
)

from services.sla_tools import load_sla_tools


model = ChatOllama(
    model="llama3.1:8b",
    base_url="http://127.0.0.1:11434",
    temperature=0,
)


SYSTEM_PROMPT = """
You are the SLA and Communications Agent
for an insurance claims processing system.

Responsibilities:

1. Schedule SLA monitoring actions.
2. Request missing documents where necessary.
3. Send appropriate workflow notifications.
4. Recommend escalation when SLA conditions
   require it.

Rules:

- Use MCP tools for workflow actions.
- Do not claim a notification was sent unless
  the MCP tool executed successfully.
- Keep communications factual.
- Minimize unnecessary personal information.

Human-control rules:

- Never approve a claim.
- Never reject a claim.
- Never settle a claim.
- Final claim decisions belong to an
  authorized human.
"""


async def build_sla_agent():

    tools, adapter = await load_sla_tools()

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
                run_limit=6,
                exit_behavior="end",
            ),
            ToolRetryMiddleware(
                max_retries=2,
                on_failure="continue",
            ),
        ],
    )

    return agent, adapter