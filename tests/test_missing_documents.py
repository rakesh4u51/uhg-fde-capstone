from graph.workflow import graph


config = {
    "configurable": {
        "thread_id": "CASE-MISSING-001"
    }
}


initial_state = {
    "case_id": "CASE-MISSING-001",

    "claim_data": {
        "case_id": "CASE-MISSING-001",
        "policy_number": "POL-1001",
        "claimant_name": "Test Customer",
        "claim_type": "Medical",
        "claim_amount": 25000,

        "description": (
            "Medical claim submitted "
            "without supporting document."
        ),

        "document_type": "unknown",
        "document_text": "",
        "document_confidence": 0,
    },

    "current_stage": "submitted",
    "status": "submitted",
    "errors": [],
}


print("\n============================")
print("MISSING DOCUMENT TEST")
print("============================")

result = graph.invoke(
    initial_state,
    config=config,
)

print("\n============================")
print("RESULT")
print("============================")

print("Case:", result.get("case_id"))
print("Stage:", result.get("current_stage"))
print("Status:", result.get("status"))
print(
    "Missing Documents:",
    result.get("missing_documents"),
)