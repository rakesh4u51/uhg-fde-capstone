from langchain_ollama import ChatOllama


llm = ChatOllama(
    model="llama3.1:8b",
    temperature=0,
)


SYSTEM_PROMPT = """
You are an insurance claim intake assistant.

Your responsibilities are:
1. Review the submitted claim.
2. Identify the policy number.
3. Identify the claim type.
4. Identify the claim amount.
5. Identify obvious missing information.
6. Recommend the next processing step.

Important rules:
- Never approve or reject a claim.
- Never make a final claim decision.
- Final decisions must be made by an authorized human.
- Keep the response short and factual.
"""


def run_intake_agent(claim: dict) -> str:
    """Run initial AI analysis on a submitted claim."""

    prompt = f"""
{SYSTEM_PROMPT}

Claim information:

Case ID: {claim.get("case_id")}
Policy number: {claim.get("policy_number")}
Claimant: {claim.get("claimant_name")}
Claim type: {claim.get("claim_type")}
Claim amount: {claim.get("claim_amount")}
Description: {claim.get("description", "")}

Provide the intake assessment.
"""

    response = llm.invoke(prompt)

    return response.content


if __name__ == "__main__":

    test_claim = {
        "case_id": "CASE-001",
        "policy_number": "POL-1001",
        "claimant_name": "Test Customer",
        "claim_type": "Medical",
        "claim_amount": 25000,
        "description": "Hospital treatment claim with medical bill.",
    }

    print(run_intake_agent(test_claim))

    from langchain_ollama import ChatOllama


llm = ChatOllama(
    model="llama3.1:8b",
    temperature=0,
)


SYSTEM_PROMPT = """
You are an insurance claim intake assistant.

Your responsibilities are:
1. Review the submitted claim.
2. Identify the policy number.
3. Identify the claim type.
4. Identify the claim amount.
5. Identify obvious missing information.
6. Recommend the next processing step.

Important rules:
- Never approve or reject a claim.
- Never make a final claim decision.
- Final decisions must be made by an authorized human.
- Keep the response short and factual.
"""


def run_intake_agent(claim: dict) -> str:
    """Run initial AI analysis on a submitted claim."""

    prompt = f"""
{SYSTEM_PROMPT}

Claim information:

Case ID: {claim.get("case_id")}
Policy number: {claim.get("policy_number")}
Claimant: {claim.get("claimant_name")}
Claim type: {claim.get("claim_type")}
Claim amount: {claim.get("claim_amount")}
Description: {claim.get("description", "")}

Provide the intake assessment.
"""

    response = llm.invoke(prompt)

    return response.content


if __name__ == "__main__":

    test_claim = {
        "case_id": "CASE-001",
        "policy_number": "POL-1001",
        "claimant_name": "Test Customer",
        "claim_type": "Medical",
        "claim_amount": 25000,
        "description": "Hospital treatment claim with medical bill.",
    }

    print(run_intake_agent(test_claim))