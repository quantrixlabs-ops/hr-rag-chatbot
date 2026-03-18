"""Agentic workflows — multi-step task execution for HR operations (Phase E6).

Detects when a user query implies a multi-step task and guides them through it.
Example: "I want to request leave" → collect dates, type, reason → generate summary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# Workflow definitions — each defines a multi-step guided process
WORKFLOW_TRIGGERS = {
    "leave_request": {
        "triggers": ["request leave", "apply for leave", "take time off", "submit pto", "request vacation"],
        "steps": [
            {"id": "type", "prompt": "What type of leave? (vacation, sick, parental, bereavement)", "field": "leave_type"},
            {"id": "start", "prompt": "What is the start date? (YYYY-MM-DD)", "field": "start_date"},
            {"id": "end", "prompt": "What is the end date? (YYYY-MM-DD)", "field": "end_date"},
            {"id": "reason", "prompt": "Briefly describe the reason (optional):", "field": "reason"},
        ],
        "summary_template": (
            "Leave Request Summary:\n"
            "- Type: {leave_type}\n"
            "- From: {start_date} to {end_date}\n"
            "- Reason: {reason}\n\n"
            "To submit this request, please go to the HR portal or contact your manager."
        ),
    },
    "benefits_enrollment": {
        "triggers": ["enroll in benefits", "sign up for insurance", "change my health plan"],
        "steps": [
            {"id": "plan", "prompt": "Which plan would you like? (Basic, Standard, or Premium)", "field": "plan"},
            {"id": "coverage", "prompt": "Individual or family coverage?", "field": "coverage"},
        ],
        "summary_template": (
            "Benefits Enrollment Summary:\n"
            "- Plan: {plan}\n"
            "- Coverage: {coverage}\n\n"
            "To complete enrollment, visit the benefits portal during open enrollment "
            "or contact HR for a special enrollment event."
        ),
    },
}


@dataclass
class WorkflowState:
    workflow_id: str
    current_step: int = 0
    collected: dict = field(default_factory=dict)
    completed: bool = False


def detect_workflow(query: str) -> Optional[str]:
    """Detect if a query triggers a multi-step workflow. Returns workflow_id or None."""
    ql = query.lower()
    for wf_id, wf in WORKFLOW_TRIGGERS.items():
        if any(trigger in ql for trigger in wf["triggers"]):
            return wf_id
    return None


def start_workflow(workflow_id: str) -> dict:
    """Start a workflow and return the first step prompt."""
    wf = WORKFLOW_TRIGGERS.get(workflow_id)
    if not wf:
        return {"error": f"Unknown workflow: {workflow_id}"}
    first_step = wf["steps"][0]
    return {
        "workflow_id": workflow_id,
        "step": 0,
        "total_steps": len(wf["steps"]),
        "prompt": first_step["prompt"],
        "field": first_step["field"],
    }


def advance_workflow(workflow_id: str, step: int, answer: str, collected: dict) -> dict:
    """Process an answer and advance to the next step or complete the workflow."""
    wf = WORKFLOW_TRIGGERS.get(workflow_id)
    if not wf:
        return {"error": f"Unknown workflow: {workflow_id}"}

    current = wf["steps"][step]
    collected[current["field"]] = answer

    next_step = step + 1
    if next_step >= len(wf["steps"]):
        # Workflow complete — generate summary
        # Fill defaults for missing fields
        for s in wf["steps"]:
            if s["field"] not in collected:
                collected[s["field"]] = "(not provided)"
        summary = wf["summary_template"].format(**collected)
        return {
            "workflow_id": workflow_id,
            "completed": True,
            "summary": summary,
            "collected": collected,
        }
    else:
        next = wf["steps"][next_step]
        return {
            "workflow_id": workflow_id,
            "step": next_step,
            "total_steps": len(wf["steps"]),
            "prompt": next["prompt"],
            "field": next["field"],
            "collected": collected,
        }
