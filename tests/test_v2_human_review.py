import asyncio
import uuid

from langgraph.types import Command

from graph.v2_graph_factory import get_v2_graph


THREAD_ID = f"CASE-001-V2-AIO-{uuid.uuid4().hex[:12]}"
config = {
    "configurable": {
        "thread_id": THREAD_ID
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


async def main():
    print("\n==============================")
    print("STARTING CLAIM WORKFLOW")
    print("==============================")

    async with get_v2_graph() as graph:
        result = await graph.ainvoke(
            initial_state,
            config=config,
        )

        assert result.get("status") != "completed", "Case completed before human review"
        assert result.get("human_decision") is None, "Human decision exists before review"

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

        result = await graph.ainvoke(
            Command(resume=human_input),
            config=config,
        )

        assert result.get("status") == "completed"
        assert result.get("current_stage") == "finalized"
        assert result.get("human_decision") == "approved"
        assert result.get("human_reviewer") == "Demo Approver"

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
        print("===============================")


if __name__ == "__main__":
    asyncio.run(main())
