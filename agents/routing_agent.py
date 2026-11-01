from langchain_ollama import ChatOllama


llm = ChatOllama(
    model="llama3.1:8b",
    base_url="http://127.0.0.1:11434",
    temperature=0,
)


SYSTEM_PROMPT = """
You are an insurance claim routing assistant.

Your job is to recommend:
1. The appropriate claim handler.
2. Whether specialist review is needed.
3. The appropriate human approval route.

Rules:
- You may recommend routing.
- Never approve a claim.
- Never reject a claim.
- Never settle a claim.
- Final decisions belong to an authorized human.
- Use only the supplied case information.
"""


def run_routing_agent(case_data: dict) -> str:
    """Recommend routing for a claim."""

    prompt = f"""
{SYSTEM_PROMPT}

Case information:

{case_data}

Return:

HANDLER:
SPECIALIST REVIEW:
HUMAN APPROVAL ROUTE:
REASON:
"""

    response = llm.invoke(prompt)

    return response.content