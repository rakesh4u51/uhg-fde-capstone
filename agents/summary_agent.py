from langchain_ollama import ChatOllama


llm = ChatOllama(
    model="llama3.1:8b",
    base_url="http://127.0.0.1:11434",
    temperature=0,
)


SYSTEM_PROMPT = """
You are an insurance claim summary assistant.

Create a concise and grounded case summary.

Use ONLY the information provided.
Do not invent facts, currency, dates, diagnoses, policy terms,
or document details that are not explicitly provided.

Your output must contain:

FACTS:
EVIDENCE:
MISSING INFORMATION:
RISKS:
POLICY STATUS:
NEXT ACTION:

Important rules:
- Never approve a claim.
- Never reject a claim.
- Never settle a claim.
- Final claim decisions belong to an authorized human.
"""


def run_summary_agent(case_data: dict) -> str:
    """Generate a grounded claim case summary."""

    prompt = f"""
{SYSTEM_PROMPT}

Case information:

{case_data}

Generate the case summary.
"""

    response = llm.invoke(prompt)

    return response.content