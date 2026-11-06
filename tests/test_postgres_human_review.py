from langgraph.types import Command

from graph.workflow_postgres import graph
from services.database import get_connection


case_id = "CASE-PG-" + __import__("uuid").uuid4().hex[:8].upper()
config = {
    "configurable": {
        "thread_id": f"{case_id}-PG-TEST"
    }
}


initial_state = {
    "case_id": case_id,

    "claim_data": {
        "case_id": case_id,
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


with get_connection() as conn:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO public.claims (
                case_id, policy_number, claimant_name, claim_type, claim_amount, description, status
            ) VALUES (%s, %s, %s, %s, %s, %s, 'submitted')
            ON CONFLICT (case_id) DO UPDATE SET
                policy_number = EXCLUDED.policy_number,
                claimant_name = EXCLUDED.claimant_name,
                claim_type = EXCLUDED.claim_type,
                claim_amount = EXCLUDED.claim_amount,
                description = EXCLUDED.description,
                status = EXCLUDED.status
            """,
            (case_id, "POL-1001", "Test Customer", "Medical", 25000.0, "Hospital treatment claim with medical bill."),
        )
        cur.execute(
            """
            INSERT INTO public.documents (
                document_id, case_id, file_name, document_type, extracted_text, confidence, injection_detected
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (document_id) DO UPDATE SET
                case_id = EXCLUDED.case_id,
                file_name = EXCLUDED.file_name,
                document_type = EXCLUDED.document_type,
                extracted_text = EXCLUDED.extracted_text,
                confidence = EXCLUDED.confidence,
                injection_detected = EXCLUDED.injection_detected
            """,
            (f"DOC-{case_id}", case_id, "medical_bill.pdf", "medical_bill", "Hospital bill for Test Customer. Total amount 25000.", 0.98, False),
        )
    conn.commit()

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