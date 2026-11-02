from langgraph.types import Command

from graph.workflow_postgres import graph


config = {
    "configurable": {
        "thread_id": "CASE-001-PG-TEST"
    }
}


initial_state = {
    "case_id": "CASE-001",

    "claim_data": {
        "case_id": "CASE-001",
        "policy_number": "POL-1001",
        "claimant_name": "Test Customer",
        "claim_type": "Medical",
        "claim_amount": 25000,
        "description": (
            "Hospital treatment claim with medical bill."
        ),

        "document_type": "medical_bill",
        "document_text": (
            "Hospital bill for Test Customer. "
            "Total amount 25000."
        ),
        "document_confidence": 0.98,
    },

    "current_stage": "submitted",
    "status": "submitted",
    "errors": [],
}


print("\n==============================")
print("STARTING CLAIM WORKFLOW")
print("==============================")

result = graph.invoke(
    initial_state,
    config=config,
)

print("\n==============================")
print("WORKFLOW PAUSED FOR HUMAN")
print("==============================")

print("Case:", result.get("case_id"))
print("Status:", result.get("status"))
print("Stage:", result.get("current_stage"))

print("\n==============================")
print("SIMULATING HUMAN REVIEW")
print("==============================")

human_input = {
    "decision": "approved",
    "rationale": (
        "Reviewed claim evidence and "
        "supporting information."
    ),
    "reviewer": "Demo Approver",
}

result = graph.invoke(
    Command(resume=human_input),
    config=config,
)

print("\n==============================")
print("WORKFLOW RESUMED")
print("==============================")

print("Case:", result.get("case_id"))
print(
    "Human Decision:",
    result.get("human_decision"),
)
print(
    "Rationale:",
    result.get("human_rationale"),
)
print(
    "Reviewer:",
    result.get("human_reviewer"),
)
print(
    "Final Status:",
    result.get("status"),
)
print(
    "Final Stage:",
    result.get("current_stage"),
)
print(
    "Final Result:",
    result.get("final_result"),
)

print("\n==============================")
print("HUMAN REVIEW TEST COMPLETE")
print("==============================")