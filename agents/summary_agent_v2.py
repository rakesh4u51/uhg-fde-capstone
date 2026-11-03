from langchain.agents import create_agent
from langchain_ollama import ChatOllama

from langchain.agents.middleware import (
    PIIMiddleware,
    ToolCallLimitMiddleware,
    ToolRetryMiddleware,
)

from services.summary_tools import (
    load_summary_tools,
)


model = ChatOllama(
    model="llama3.1:8b",
    base_url="http://127.0.0.1:11434",
    temperature=0,
)


SYSTEM_PROMPT = """
You are the Summary Agent for an insurance
claims processing system.

Your responsibility is to create a concise,
grounded human-review summary.

Use MCP tools to retrieve verified:
- case information
- policy information
- coverage results
- document information
- extracted document fields
- document validation results

Return these sections:

FACTS:
EVIDENCE:
POLICY STATUS:
MISSING INFORMATION:
RISKS:
VALIDATION ISSUES:
NEXT ACTION:

Grounding rules:
- Use only information returned by MCP tools.
- Clearly separate facts from recommendations.
- Do not invent policy details.
- Do not invent document details.
- Do not invent currency, dates, diagnoses,
  identities, or evidence.
- If information is unavailable, state that it
  is unavailable.

Human-control rules:
- Never approve a claim.
- Never reject a claim.
- Never settle a claim.
- Final claim decisions belong to an authorized human.
"""


async def build_summary_agent():
    (
        tools,
        case_adapter,
        policy_adapter,
        document_adapter,
    ) = await load_summary_tools()

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
                run_limit=10,
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
        policy_adapter,
        document_adapter,
    )