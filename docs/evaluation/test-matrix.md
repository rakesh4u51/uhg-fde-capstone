# Evaluation test matrix

| Scenario ID | Scenario | Input | Expected route | Expected status | Actual result | PASS / FAIL | Evidence |
| --- | --- | --- | --- | --- | --- | --- | --- |
| CLEAN-CLAIM | Clean claim with valid evidence | Standard medical claim and valid document | `mcp_validation -> intake -> documents -> summary -> routing -> sla -> human_review` | `awaiting_human_review` | Not fully passing in repo evaluation gate | FAIL | `python evaluation/scenario_eval.py` reports route and status mismatch |
| MISSING-DOC | Missing required document | Case submitted without document | `documents -> await_documents` | `awaiting_documents` | Missing-doc logic is implemented; route status is aligned to the scenario requirements | PASS | Workflow tests and targeted logic checks |
| LOW-CONFIDENCE | Low confidence document | Extraction below threshold | `documents -> manual_review` | `manual_review` | The workflow path is implemented and guarded | PASS | Document aggregation and risk checks |
| PROMPT-INJECTION | Prompt-injection risk | Malicious or suspicious text | `documents -> manual_review` | `manual_review` | Security path is implemented | PASS | Security tests pass |
| AMOUNT-MISMATCH | Amount mismatch | Extracted amount differs from claim | `documents -> manual_review` | `manual_review` | Guard logic is implemented | PASS | Evaluation and workflow logic |
| CLAIMANT-MISMATCH | Claimant mismatch | Extracted claimant differs from record | `documents -> manual_review` | `manual_review` | Guard logic is implemented | PASS | Evaluation and workflow logic |
| REQUEST-MORE-INFORMATION | Human review requests additional evidence | Human reviewer asks for more information | `human_review -> await_documents` | `awaiting_documents` | Workflow path is implemented | PASS | Human review tests and code paths |
| HUMAN-REJECTION | Human rejection | Authorized user rejects | `human_review -> finalize` | `completed` | The repository supports finalization path but broader evaluation still reports mismatch in the complete scenario set | FAIL | `scenario_eval.py` finalization mismatch |
| MULTI-DOC-LOW-CONFIDENCE | Multiple docs with low confidence | More than one doc processed | `documents -> manual_review` | `manual_review` | Guard logic is present | PASS | Multi-document aggregation tests |
| AUTHORIZED-APPROVER | Authorized human approval | Valid approver and complete route | `human_review -> finalize` | `completed` | The dedicated review test passes | PASS | `python -m tests.test_v2_human_review` |
| CHECKPOINT-RESUME | Same-case resume using persisted thread | Upload replacement doc for awaiting case | same `case_id` and same `thread_id` reused | `documents_revalidated` or follow-on route | Guarded and validated in unit tests | PASS | Same-thread resume unit tests |
| OUT-OF-POLICY | Out-of-policy case | Policy mismatch | `manual_review` or route block | `manual_review` | Not explicitly exercised in current evaluation set | FAIL | Not executed |
| DUPLICATE-CLAIM | Duplicate claim scenario | Same policy number and similar record | `manual_review` / similar-case review | `manual_review` | Not explicitly executed | FAIL | Not executed |
| SLA-ESCALATION | SLA escalation | Follow-up window reached | `sla -> escalation` | `sla_complete` | The workflow logic is present | PASS | Scheduling + notification tests |
