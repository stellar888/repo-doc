from __future__ import annotations

from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from .config import Settings
from .documentation import (
    attach_unified_diffs,
    discover_documentation_candidates,
    read_documentation,
    validate_edit_operations,
)
from .model import StructuredModel
from .prompts import ANALYSIS_TEMPLATE, PROMPT_VERSION, PROPOSAL_TEMPLATE, SYSTEM_POLICY
from .schemas import AgentResult, DocumentationContext, DocumentationProposal, ImpactAnalysis
from .security import contains_secret, scan_untrusted_text, validate_proposal_paths


class AgentState(TypedDict, total=False):
    raw_diff: str
    diff: str
    safety_flags: list[str]
    analysis: ImpactAnalysis
    documentation_contexts: list[DocumentationContext]
    proposal: DocumentationProposal
    status: str


def build_graph(*, settings: Settings, model: StructuredModel) -> Any:
    allowed = settings.allowed_paths

    def read_context(
        *,
        path: str,
        repository_root: Path,
        flags: list[str],
    ) -> DocumentationContext | None:
        try:
            context = read_documentation(
                path=path,
                repository_root=repository_root,
                allowed_paths=allowed,
                max_chars=settings.max_doc_chars,
            )
            if contains_secret(context.content):
                flags.append(f"possible_secret_in_documentation:{path}")
                context = context.model_copy(
                    update={"content": "[REDACTED: possible secret-like value detected]"}
                )
            if context.truncated:
                flags.append(f"documentation_context_truncated:{path}")
            return context
        except PermissionError:
            flags.append(f"forbidden_candidate_path:{path}")
        except (OSError, UnicodeError) as exc:
            flags.append(f"unreadable_candidate_path:{path}:{type(exc).__name__}")
        return None

    def prepare(state: AgentState) -> AgentState:
        raw = state["raw_diff"]
        truncated = raw[: settings.max_diff_chars]
        flags = scan_untrusted_text(truncated)
        if len(raw) > settings.max_diff_chars:
            flags.append("input_truncated")
        return {"diff": truncated, "safety_flags": flags}

    def route_after_prepare(state: AgentState) -> str:
        if "possible_secret_in_input" in state.get("safety_flags", []):
            return "blocked_input"
        return "analyse"

    def blocked_input(state: AgentState) -> AgentState:
        flags = list(dict.fromkeys(state.get("safety_flags", [])))
        return {
            "analysis": ImpactAnalysis(
                needs_documentation_update=False,
                summary="Secret-like input was detected before model execution.",
                candidate_files=[],
                findings=[],
                uncertainty="The diff was not sent to the model.",
            ),
            "proposal": DocumentationProposal(
                action="human_review",
                summary="Secret-like input was detected before model execution.",
                edits=[],
                reviewer_notes=flags,
            ),
            "safety_flags": flags,
            "status": "blocked",
        }

    def analyse(state: AgentState) -> AgentState:
        prompt = ANALYSIS_TEMPLATE.format(
            allowed_paths=", ".join(allowed),
            diff=state["diff"],
        )
        analysis = model.invoke_structured(
            system=SYSTEM_POLICY,
            user=prompt,
            schema=ImpactAnalysis,
        )
        return {"analysis": analysis}

    def route_after_analysis(state: AgentState) -> str:
        analysis = state["analysis"]
        if not analysis.needs_documentation_update:
            return "no_change"
        return "read_docs"

    def read_docs(state: AgentState) -> AgentState:
        flags = list(state.get("safety_flags", []))
        contexts: list[DocumentationContext] = []
        repository_root = Path(settings.repository_root)
        analysis = state["analysis"]
        discovered_candidates = discover_documentation_candidates(
            diff=state["diff"],
            repository_root=repository_root,
            allowed_paths=allowed,
        )
        candidate_files = list(
            dict.fromkeys(analysis.candidate_files or discovered_candidates)
        )[:10]
        analysis = analysis.model_copy(update={"candidate_files": candidate_files})

        for path in candidate_files:
            context = read_context(path=path, repository_root=repository_root, flags=flags)
            if context:
                contexts.append(context)

        return {
            "analysis": analysis,
            "documentation_contexts": contexts,
            "safety_flags": list(dict.fromkeys(flags)),
        }

    def no_change(state: AgentState) -> AgentState:
        return {
            "proposal": DocumentationProposal(
                action="no_change",
                summary=state["analysis"].summary,
                reviewer_notes=["No write operation was attempted."],
            )
        }

    def propose(state: AgentState) -> AgentState:
        prompt = PROPOSAL_TEMPLATE.format(
            allowed_paths=", ".join(allowed),
            analysis_json=state["analysis"].model_dump_json(indent=2),
            documentation_context_json=(
                "[\n"
                + ",\n".join(
                    context.model_dump_json(indent=2)
                    for context in state.get("documentation_contexts", [])
                )
                + "\n]"
            ),
            diff=state["diff"],
        )
        proposal = model.invoke_structured(
            system=SYSTEM_POLICY,
            user=prompt,
            schema=DocumentationProposal,
        )
        return {"proposal": proposal}

    def read_edit_docs(state: AgentState) -> AgentState:
        flags = list(state.get("safety_flags", []))
        contexts = list(state.get("documentation_contexts", []))
        context_paths = {context.path for context in contexts}
        repository_root = Path(settings.repository_root)

        for edit in state["proposal"].edits:
            if edit.path in context_paths:
                continue
            context = read_context(path=edit.path, repository_root=repository_root, flags=flags)
            if context:
                contexts.append(context)
                context_paths.add(context.path)

        return {
            "documentation_contexts": contexts,
            "safety_flags": list(dict.fromkeys(flags)),
        }

    def patch(state: AgentState) -> AgentState:
        return {
            "proposal": attach_unified_diffs(
                state["proposal"],
                state.get("documentation_contexts", []),
            )
        }

    def validate(state: AgentState) -> AgentState:
        flags = list(state.get("safety_flags", []))
        proposal = state["proposal"]

        invalid_paths = validate_proposal_paths(
            [edit.path for edit in proposal.edits],
            allowed,
        )
        if invalid_paths:
            flags.extend(f"forbidden_path:{path}" for path in invalid_paths)

        flags.extend(
            validate_edit_operations(
                proposal,
                state.get("documentation_contexts", []),
            )
        )

        if contains_secret(proposal.model_dump_json()):
            flags.append("possible_secret_in_output")

        blocking = any(
            flag.startswith(
                (
                    "forbidden_path:",
                    "forbidden_candidate_path:",
                    "invalid_edit_operation:",
                    "possible_secret_in_output",
                )
            )
            for flag in flags
        )
        review_required = any(
            flag.startswith(
                (
                    "suspicious_input:",
                    "possible_secret_in_documentation:",
                    "documentation_context_truncated:",
                )
            )
            for flag in flags
        )

        if blocking:
            status = "blocked"
            proposal = DocumentationProposal(
                action="human_review",
                summary="The proposal failed a deterministic safety gate.",
                reviewer_notes=flags,
            )
        elif review_required:
            status = "human_review"
            proposal = DocumentationProposal(
                action="human_review",
                summary="Repository context requires human review before applying documentation.",
                reviewer_notes=list(dict.fromkeys([*flags, *proposal.reviewer_notes])),
            )
        elif proposal.action == "human_review":
            status = "human_review"
        else:
            status = "ok"

        return {"safety_flags": list(dict.fromkeys(flags)), "proposal": proposal, "status": status}

    graph = StateGraph(AgentState)
    graph.add_node("prepare", prepare)
    graph.add_node("blocked_input", blocked_input)
    graph.add_node("analyse", analyse)
    graph.add_node("read_docs", read_docs)
    graph.add_node("no_change", no_change)
    graph.add_node("propose", propose)
    graph.add_node("read_edit_docs", read_edit_docs)
    graph.add_node("patch", patch)
    graph.add_node("validate", validate)

    graph.add_edge(START, "prepare")
    graph.add_conditional_edges(
        "prepare",
        route_after_prepare,
        {"blocked_input": "blocked_input", "analyse": "analyse"},
    )
    graph.add_edge("blocked_input", END)
    graph.add_conditional_edges(
        "analyse",
        route_after_analysis,
        {"no_change": "no_change", "read_docs": "read_docs"},
    )
    graph.add_edge("no_change", "validate")
    graph.add_edge("read_docs", "propose")
    graph.add_edge("propose", "read_edit_docs")
    graph.add_edge("read_edit_docs", "patch")
    graph.add_edge("patch", "validate")
    graph.add_edge("validate", END)
    return graph.compile()


def run_agent(*, diff: str, settings: Settings, model: StructuredModel) -> AgentResult:
    graph = build_graph(settings=settings, model=model)
    final = graph.invoke({"raw_diff": diff})
    return AgentResult(
        status=final["status"],
        analysis=final["analysis"],
        proposal=final["proposal"],
        safety_flags=final["safety_flags"],
        prompt_version=PROMPT_VERSION,
        model=model.model_name,
    )
