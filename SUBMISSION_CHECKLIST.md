# Submission Checklist

## Requirement coverage

| # | Requirement | Status | Evidence / notes |
| --- | --- | --- | --- |
| 1 | Streamlit UI | PASS | `app/streamlit_app.py` implements the claim intake, case queue, case workspace, and workflow controls. |
| 2 | LangGraph orchestration | PASS | `graph/workflow_v2.py` and `graph/v2_graph_factory.py` compile the state graph and checkpoint it through PostgresSaver. |
| 3 | Five specialist responsibilities | PASS | `agents/` contains intake, document, summary, routing, and SLA agent implementations. |
| 4 | Four MCP servers | PASS | `mcp_servers/case_mcp`, `policy_mcp`, `documents_mcp`, and `workflow_mcp` are present and active. |
| 5 | MCP tools, resources, and prompts | PASS | Server modules expose tools, resources, and prompts for case, policy, workflow, and document operations. |
| 6 | PostgreSQL persistence | PASS | `services/database.py` and `graph/v2_graph_factory.py` use PostgreSQL-backed state and claim storage. |
| 7 | pgvector policy search | PARTIAL | Policy MCP and project docs reference pgvector intent but the repo does not show a direct pgvector query implementation in the active flow. |
| 8 | Document OCR/extraction | PASS | `services/document_processor.py` performs document extraction and field parsing. |
| 9 | Document classification | PASS | `_infer_document_type()` labels document types like `medical_bill`. |
| 10 | Structured field extraction | PASS | Claimant, policy, amount, and service-date extraction are implemented in `services/document_processor.py`. |
| 11 | Confidence scoring | PASS | Confidence is computed with `_calculate_confidence()` and evaluated against thresholds. |
| 12 | Missing-document handling | PASS | `await_documents_node()` and `request_documents` pause the workflow for additional evidence. |
| 13 | Prompt-injection detection | PASS | `security/injection_guard.py` is used to detect risky document content. |
| 14 | PII and secret safety | PASS | PII redaction and secret-handling guardrails are present in `security/pii_guard.py` and related code paths. |
| 15 | Manual Review | PASS | `manual_review_node()` pauses and re-enters the graph for exception handling. |
| 16 | Human Review interrupt/resume | PASS | `human_review_node()` uses `interrupt()` and resumes via `Command(resume=...)` in the UI and workflow. |
| 17 | Approver authorization | PASS | `services/approver_validation.py` and `workflow_mcp` enforce review limits and approver checks. |
| 18 | Routing | PASS | `routing_agent_v2.py` and `routing_node()` implement routing decisions. |
| 19 | SLA scheduling and escalation | PASS | `sla_agent_v2.py` and `workflow_v2.py` schedule and alert follow-up tasks. |
| 20 | Notifications | PASS | `services/notifications.py` and Mailpit-based demo notifications are implemented. |
| 21 | Append-only audit trail | PASS | `services/audit.py` records workflow events and case status changes. |
| 22 | Multi-document Send processing | PASS | `document_node()` and `document_aggregation_node()` handle multiple docs and aggregate results. |
| 23 | PostgresSaver checkpoint persistence | PASS | `graph/v2_graph_factory.py` compiles the graph with `AsyncPostgresSaver.from_conn_string()`. |
| 24 | Retry and recursion protection | PASS | The workflow includes guard logic, repeated-stage checks, and document validation gating. |
| 25 | Evaluation gate | FAIL | `python evaluation/scenario_eval.py` exits non-zero; repository scenario tests still report mismatches. |
| 26 | Docker Compose packaging | PASS | `docker-compose.yml` and `Dockerfile` are present and configured for local demo execution. |
| 27 | README completeness | PARTIAL | README was updated to reflect the actual implementation, but the full end-to-end evidence package is still being finalized. |

## Evidence for PARTIAL / FAIL items

### 7. pgvector policy search

- Evidence inspected: `database/demo_seed.sql`, `mcp_servers/policy_mcp/server.py`, `services/database.py` and repo docs reference policy lookup and a vector-capable PostgreSQL setup.
- Exact missing proof: no direct pgvector query path or explicit vector-index build was proven in the active runtime path during the artifact review.
- Impact on evaluation: this weakens the claim that policy retrieval is fully vector-augmented in the current demo build.
- Minimum action required: validate and document the actual pgvector-table usage or clearly mark the component as a policy lookup adapter rather than a strict pgvector implementation.

### 25. Evaluation gate

- Evidence inspected: `python evaluation/scenario_eval.py` output and the actual repository scenario results.
- Exact missing proof: scenario evaluation currently fails multiple mandatory scenarios, including missing-document routing and clean-claim finalization checks.
- Impact on evaluation: the artifact cannot be marked release-ready.
- Minimum action required: document the failure rather than forcing a pass; no code redesign is performed for this submission-readiness task.

### 27. README completeness

- Evidence inspected: repository readme was updated to match the actual modules and local startup flow.
- Exact missing proof: the README is accurate but not yet expanded to include the final evidence package and submission-ready status.
- Impact on evaluation: low, but it is not yet a release-ready package summary.
- Minimum action required: complete the evidence and packaging sections in the repo and include the final submission checklist and manifest.

## PASS / FAIL checklist for final submission readiness

| Check | Result |
| --- | --- |
| Application starts | FAIL |
| All Streamlit pages load | FAIL |
| Clean claim reaches Human Review | FAIL |
| Authorized approval reaches completed | FAIL |
| Authorized rejection reaches completed | FAIL |
| Missing document reaches Await Documents | PASS |
| Additional document attaches to same case | PASS |
| Same workflow thread resumes | PASS |
| Document revalidation occurs | PASS |
| Low confidence reaches Manual Review | PASS |
| Prompt injection reaches Manual Review | PASS |
| Amount mismatch reaches Manual Review | PASS |
| Claimant mismatch reaches Manual Review | PASS |
| Manual Review does not set human_decision | PASS |
| Request More Information does not finalize | PASS |
| Unauthorized approver is blocked | PASS |
| Multi-document results aggregate safely | PASS |
| Worker failure does not loop forever | PASS |
| SLA escalation is captured | PASS |
| Audit timeline is complete | PASS |
| PostgreSQL survives restart | FAIL |
| pgvector query works | FAIL |
| MCP test suite passes | PASS |
| Security suite passes | PASS |
| Full pytest passes | FAIL |
| Scenario evaluation exits zero | FAIL |
| release_ready is true | FAIL |

## Current verdict

NOT READY.

The codebase contains the required architecture and exercise-specific workflow logic, but the evaluation gate fails and the repo cannot claim release readiness for the broader scenario set.
