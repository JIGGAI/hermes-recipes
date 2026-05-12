"""Built-in markdown templates used by the team scaffolder.

Port of clawrecipes/src/lib/scaffold-templates.ts. These two templates are
the README/TICKETS docs dropped into every team workspace; they're plain
text so we keep them inline.
"""


def render_team_md(team_id: str) -> str:
    return (
        f"# {team_id}\n\n"
        "Shared workspace for this agent team.\n\n"
        "## Workflow\n"
        "- Stages: backlog → in-progress → testing → done\n"
        "- Backlog: work/backlog/\n"
        "- In progress: work/in-progress/\n"
        "- Testing / QA: work/testing/\n"
        "- Done: work/done/\n\n"
        "## QA verification\n"
        "Before moving a ticket from work/testing/ → work/done/, record verification results.\n"
        "- Template: notes/QA_CHECKLIST.md\n"
        "- Preferred: create work/testing/<ticket>.testing-verified.md\n\n"
        "## Folders\n"
        "- inbox/ — requests\n"
        "- outbox/ — deliverables\n"
        "- shared-context/ — curated shared context + append-only agent outputs\n"
        "- shared/ — legacy shared artifacts (back-compat)\n"
        "- notes/ — plan + status + templates\n"
        "- work/ — working files\n"
    )


def render_tickets_md(team_id: str) -> str:
    return (
        f"# Tickets — {team_id}\n\n"
        "## Workflow\n"
        "- Stages: backlog → in-progress → testing → done\n"
        "- Backlog tickets live in work/backlog/\n"
        "- In-progress tickets live in work/in-progress/\n"
        "- Testing / QA tickets live in work/testing/\n"
        "- Done tickets live in work/done/\n\n"
        "### QA handoff (dev → test)\n"
        "When development is complete:\n"
        "- Move the ticket file to work/testing/\n"
        "- Assign to test (set `Owner: test`)\n"
        "- Add clear test instructions / repro steps\n\n"
        "### QA verification (test → done)\n"
        "Before moving a ticket to done, QA must record verification.\n"
        "- Template: notes/QA_CHECKLIST.md\n"
        "- Preferred: create work/testing/<ticket>.testing-verified.md\n\n"
        "## Naming\n"
        "- Filename ordering is the queue: 0001-..., 0002-...\n\n"
        "## Required fields\n"
        "Each ticket should include:\n"
        "- Title\n"
        "- Context\n"
        "- Requirements\n"
        "- Acceptance criteria\n"
        "- Owner (dev/devops/lead/test)\n"
        "- Status (queued/in-progress/testing/done)\n\n"
        "## Example\n\n"
        "```md\n"
        "# 0001-example-ticket\n\n"
        "Owner: dev\n"
        "Status: queued\n\n"
        "## Context\n"
        "...\n\n"
        "## Requirements\n"
        "- ...\n\n"
        "## Acceptance criteria\n"
        "- ...\n\n"
        "## How to test\n"
        "- ...\n"
        "```\n"
    )
