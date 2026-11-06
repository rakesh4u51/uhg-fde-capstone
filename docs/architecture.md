# Architecture

## System components

The service is a hybrid workflow: a Streamlit UI orchestrates the case lifecycle, while a LangGraph `StateGraph` supervises specialist work and manages interrupts/resumes. PostgreSQL is the system of record for claims, documents, workflow thread mappings, and audit events. The MCP boundary isolates operational concerns such as policy lookup, case retrieval, workflow routing, and document validation.

## Data flow

1. The user submits a claim through the Streamlit UI.
2. The UI creates or loads the `case_id` and stores a durable `thread_id` mapping in `public.claim_workflow_threads`.
3. The graph starts at `mcp_validation` and passes control to `supervisor`.
4. The intake and document stages gather claim data and evaluate required evidence.
5. If documents are missing, the system reaches `await_documents`, triggers a request, and pauses with `interrupt()`.
6. After replacement evidence is uploaded, the same case and thread are resumed and revalidated.
7. Summary, routing, and SLA nodes prepare the evidence package for the next decision point.
8. Human Review is reached only after the case is ready and an authorized decision maker is available.
9. Finalization is performed only after a human decision has been recorded.

## MCP boundaries

- Case MCP: case lookup, listing, registration, and similar-case checks.
- Policy MCP: policy coverage and lookup helpers.
- Documents MCP: document validation, extraction, and classification.
- Workflow MCP: dispatch, workload, approval, notification, and SLA actions.

## LangGraph nodes and edges

The active graph in `graph/workflow_v2.py` flows through `mcp_validation -> supervisor -> intake -> ... -> documents -> document_worker -> document_aggregation -> supervisor -> summary -> routing -> sla -> human_review -> supervisor -> finalize` with `await_documents` and `manual_review` interrupt paths. The supervisor decides whether to continue, request more information, route to manual review, or stop for human approval.

## Document fan-out / fan-in

The document stage fans out to one or more `document_worker` tasks using `Send(...)` calls. Each worker processes a single document and returns structured results; the aggregation node merges all results, computes missing-doc requirements, and sets the `document_validation` payload used for continuation gating.

## PostgresSaver and thread identity

The graph is compiled with `AsyncPostgresSaver.from_conn_string(DATABASE_URL)`, which persists graph state checkpoints. A case is associated with a durable `thread_id` in `public.claim_workflow_threads` so that same-case resume operations can continue the original workflow rather than creating a duplicate claim or duplicate thread.

## Case ID versus thread ID

- `case_id` identifies the business claim.
- `thread_id` identifies the LangGraph execution checkpoint lineage.
- The user-facing workflow keeps the same `case_id` throughout; the `thread_id` is reused during same-case resume operations.

## Manual Review and Human Review

- Manual Review resolves extraction failures, mismatches, low confidence, prompt-injection conditions, and missing evidence.
- Human Review is the final authorization stage. It waits for human approval or rejection and does not bypass the workflow guard rails.
