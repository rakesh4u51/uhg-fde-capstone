# Workflow documentation

## Clean flow

1. Claim is submitted.
2. Intake validates the case and policy context.
3. Document processing runs.
4. Summary and routing prepare the decision package.
5. SLA scheduling occurs.
6. The case reaches `awaiting_human_review`.
7. Human Review finalizes the claim.

## Missing-document flow

1. Required evidence is absent.
2. The document stage sets `missing_documents`.
3. The workflow calls `request_documents` and transitions to `awaiting_documents`.
4. The case pauses with `interrupt()`.
5. The same case is resumed after uploaded evidence is attached.
6. The new document is processed and revalidated before any continuation.

## Low-confidence flow

1. Extracted text does not meet the threshold.
2. The workflow marks `low_confidence`.
3. The case is sent to Manual Review.
4. A human reviewer can request a clearer document or resolve the risk with operational context.

## Security flow

1. The document pipeline checks for prompt-injection risk.
2. Data from the document is treated as untrusted.
3. If injection or mismatch risk is raised, the workflow blocks automatic continuation.
4. The case is routed to Manual Review instead of Human Review.

## Additional-document flow

1. The case is in `awaiting_documents`.
2. The operator uploads a replacement document in the Case Workspace.
3. The file is saved against the same `case_id`.
4. The workflow retrieves the original `thread_id` and resumes the same state.
5. The document is revalidated and the flow continues from the document checkpoint.

## Human Review flow

1. The workflow reaches `awaiting_human_review`.
2. An approver or reviewer reviews the final package.
3. A human decision such as approved or rejected is recorded.
4. Finalization occurs only after that explicit human response.

## Restart / recovery flow

1. The graph is compiled with PostgresSaver.
2. Thread mappings are stored in `public.claim_workflow_threads`.
3. If the case is paused, operators can resume the same checkpoint.
4. The workflow validates whether the checkpoint is still in a valid pause state before resuming.
