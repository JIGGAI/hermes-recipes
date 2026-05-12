"""Workflow runner subsystem — port of clawrecipes/src/lib/workflows/.

Subpackage layout (mirrors the TS source):
  - types.py            ← workflow-types.ts
  - io.py               ← workflow-runner-io.ts
  - lock_liveness.py    ← lock-liveness.ts
  - error_classify.py   ← workflow-error-classify.ts
  - outbound_sanitize.py ← outbound-sanitize.ts (canonical sanitizer)
  - utils.py            ← workflow-utils.ts
  - approvals.py        ← workflow-approvals.ts
  - queue.py            ← workflow-queue.ts            (Phase 4b)
  - runner.py           ← workflow-runner.ts           (Phase 4b)
  - tick.py             ← workflow-tick.ts             (Phase 4b)
  - node_executor.py    ← workflow-node-executor.ts    (Phase 4c)
  - node_output_readers.py ← workflow-node-output-readers.ts (Phase 4c)
  - worker.py           ← workflow-worker.ts           (Phase 4c)
"""
