from __future__ import annotations

import json

from .schemas import AgentResult


def agent_next_action(result: AgentResult) -> str:
    if result.status == "blocked":
        return "stop_for_safety_review"
    if result.status == "human_review" or result.proposal.action == "human_review":
        return "request_human_review"
    if result.proposal.action == "update":
        return "update_documentation"
    return "no_documentation_change"


def check_exit_code(result: AgentResult) -> int:
    if result.status == "ok" and result.proposal.action == "no_change":
        return 0
    if result.status == "ok" and result.proposal.action == "update":
        return 2
    if result.status == "human_review":
        return 3
    return 4


def render_agent_json_result(result: AgentResult) -> str:
    edit_paths = [edit.path for edit in result.proposal.edits]
    can_apply = result.status == "ok" and result.proposal.action == "update"
    payload = {
        "schema_version": 1,
        "status": result.status,
        "action": result.proposal.action,
        "next_action": agent_next_action(result),
        "check_exit_code": check_exit_code(result),
        "needs_documentation_update": result.analysis.needs_documentation_update,
        "can_apply": can_apply,
        "apply_command": "repo-doc analyse --apply" if can_apply else None,
        "summary": result.proposal.summary or result.analysis.summary,
        "candidate_files": result.analysis.candidate_files,
        "edit_paths": edit_paths,
        "edits": [
            {
                "path": edit.path,
                "operation": edit.operation,
                "target_heading": edit.target_heading,
            }
            for edit in result.proposal.edits
        ],
        "documentation_files": edit_paths or result.analysis.candidate_files,
        "safety_flags": result.safety_flags,
        "reviewer_notes": result.proposal.reviewer_notes,
        "uncertainty": result.analysis.uncertainty,
        "model": result.model,
        "prompt_version": result.prompt_version,
    }
    return json.dumps(payload, indent=2) + "\n"
