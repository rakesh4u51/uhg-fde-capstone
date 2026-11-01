from langchain_ollama import ChatOllama


llm = ChatOllama(
    model="llama3.1:8b",
    base_url="http://127.0.0.1:11434",
    temperature=0,
)


SYSTEM_PROMPT = """
You are an insurance claims SLA and communications assistant.

Your job is to recommend:
1. The next communication.
2. Missing-document communication if required.
3. SLA monitoring actions.
4. Escalation when appropriate.

Rules:
- Never approve a claim.
- Never reject a claim.
- Never settle a claim.
- Human authorization is required for the final decision.
"""


def run_sla_agent(case_data: dict) -> str:
    """Recommend SLA and communication actions."""

    prompt = f"""
{SYSTEM_PROMPT}

Case information:

{case_data}

Return:

COMMUNICATION:
SLA ACTION:
ESCALATION:
NEXT ACTION:
"""

    response = llm.invoke(prompt)

    return response.content