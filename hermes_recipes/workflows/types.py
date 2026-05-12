"""Workflow / Run / Approval shapes.

Port of clawrecipes/src/lib/workflows/workflow-types.ts. The TS file is mostly
type aliases on top of free-form dicts; we keep the Python port faithful to
that by using ``TypedDict`` (so the runtime data stays as plain dicts that JSON
round-trips through). Node kinds, edges, and lanes are ``Literal`` aliases.
"""

from typing import Any, Literal, TypedDict

WorkflowLane = Literal["backlog", "in-progress", "testing", "done"]
WorkflowEdgeOn = Literal["success", "error", "always"]
NodeStateStatus = Literal["success", "error", "waiting"]
ApprovalStatus = Literal["pending", "approved", "rejected"]
# Built-in node kinds — extra kinds are accepted (str fallback) for forward compat.
WorkflowNodeKind = Literal[
    "llm", "human_approval", "writeback", "tool", "handoff", "start", "end"
]


class WorkflowNodeAssignment(TypedDict, total=False):
    agentId: str


class WorkflowNodeInput(TypedDict, total=False):
    from_: list[str]  # JSON field is "from"; alias rename below


class WorkflowNodeOutput(TypedDict, total=False):
    path: str
    schema: str


class WorkflowNodeAction(TypedDict, total=False):
    promptTemplatePath: str
    promptTemplate: str
    tool: str
    args: dict[str, Any]
    writebackPaths: list[str]
    approvalBindingId: str
    model: str
    provider: str


class WorkflowNode(TypedDict, total=False):
    id: str
    kind: str
    name: str
    assignedTo: WorkflowNodeAssignment
    input: dict[str, Any]
    action: dict[str, Any]
    output: WorkflowNodeOutput
    lane: WorkflowLane


class WorkflowTrigger(TypedDict, total=False):
    kind: str
    cron: str
    tz: str


class WorkflowEdge(TypedDict, total=False):
    from_: str  # rename target for JSON key "from"
    to: str
    on: WorkflowEdgeOn


class Workflow(TypedDict, total=False):
    id: str
    name: str
    triggers: list[dict[str, Any]]
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]


class NodeState(TypedDict, total=False):
    status: NodeStateStatus
    ts: str
    message: str


class RunWorkflowRef(TypedDict, total=False):
    file: str
    id: str | None
    name: str | None


class RunTicketRef(TypedDict, total=False):
    file: str
    number: str
    lane: WorkflowLane


class RunTrigger(TypedDict, total=False):
    kind: str
    at: str


class RunEvent(TypedDict, total=False):
    ts: str
    type: str
    # Plus arbitrary additional fields per event.


class RunLog(TypedDict, total=False):
    runId: str
    createdAt: str
    updatedAt: str
    teamId: str
    workflow: RunWorkflowRef
    ticket: RunTicketRef
    trigger: RunTrigger
    triggerInput: dict[str, Any]
    status: str
    priority: int
    claimedBy: str | None
    claimExpiresAt: str | None
    nextNodeIndex: int
    nodeStates: dict[str, NodeState]
    events: list[dict[str, Any]]
    nodeResults: list[dict[str, Any]]


class ApprovalRecord(TypedDict, total=False):
    runId: str
    teamId: str
    workflowFile: str
    nodeId: str
    bindingId: str
    requestedAt: str
    status: ApprovalStatus
    decidedAt: str
    ticket: str
    runLog: str
    note: str
    resumedAt: str
    resumedStatus: str
    resumeError: str


VALID_LANES: tuple[WorkflowLane, ...] = ("backlog", "in-progress", "testing", "done")
