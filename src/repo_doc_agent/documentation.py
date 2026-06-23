from __future__ import annotations

import difflib
from pathlib import Path, PurePosixPath

from .schemas import DocumentationContext, DocumentationProposal
from .security import path_is_allowed


def _safe_repo_path(repository_root: Path, relative_path: str) -> Path:
    root = repository_root.resolve()
    target = root.joinpath(*PurePosixPath(relative_path).parts)
    check_path = target.resolve() if target.exists() else target.parent.resolve()
    if not check_path.is_relative_to(root):
        raise PermissionError(f"Path escapes repository root: {relative_path}")
    return target


def read_documentation(
    *,
    path: str,
    repository_root: Path,
    allowed_paths: tuple[str, ...],
    max_chars: int,
) -> DocumentationContext:
    if not path_is_allowed(path, allowed_paths):
        raise PermissionError(f"Forbidden documentation path: {path}")

    target = _safe_repo_path(repository_root, path)
    if not target.exists():
        return DocumentationContext(path=path, exists=False)
    if not target.is_file():
        raise IsADirectoryError(f"Documentation path is not a file: {path}")

    content = target.read_text(encoding="utf-8")
    truncated = len(content) > max_chars
    return DocumentationContext(
        path=path,
        exists=True,
        content=content[:max_chars],
        truncated=truncated,
    )


def build_unified_diff(*, path: str, before: str, after: str) -> str:
    before_lines = before.splitlines(keepends=True)
    after_lines = after.splitlines(keepends=True)
    return "".join(
        difflib.unified_diff(
            before_lines,
            after_lines,
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
        )
    )


def attach_unified_diffs(
    proposal: DocumentationProposal,
    contexts: list[DocumentationContext],
) -> DocumentationProposal:
    context_by_path = {context.path: context for context in contexts}
    edits = []

    for edit in proposal.edits:
        context = context_by_path.get(edit.path)
        before = context.content if context and context.exists else ""
        proposed = edit.proposed_markdown.strip() + "\n"
        if before and proposed.strip() not in before:
            after = before.rstrip() + "\n\n" + proposed
        else:
            after = proposed

        edits.append(
            edit.model_copy(
                update={
                    "unified_diff": build_unified_diff(
                        path=edit.path,
                        before=before,
                        after=after,
                    )
                }
            )
        )

    return proposal.model_copy(update={"edits": edits})


def _merge_markdown(*, before: str, proposed_markdown: str) -> str:
    proposed = proposed_markdown.strip() + "\n"
    if before and proposed.strip() not in before:
        return before.rstrip() + "\n\n" + proposed
    return proposed if not before else before


def apply_documentation_proposal(
    *,
    proposal: DocumentationProposal,
    repository_root: Path,
    allowed_paths: tuple[str, ...],
) -> list[str]:
    if proposal.action != "update":
        raise ValueError("Only update proposals can be applied")

    applied_paths: list[str] = []
    for edit in proposal.edits:
        if not path_is_allowed(edit.path, allowed_paths):
            raise PermissionError(f"Forbidden documentation path: {edit.path}")

        target = _safe_repo_path(repository_root, edit.path)
        if target.exists() and not target.is_file():
            raise IsADirectoryError(f"Documentation path is not a file: {edit.path}")

        before = target.read_text(encoding="utf-8") if target.exists() else ""
        after = _merge_markdown(before=before, proposed_markdown=edit.proposed_markdown)
        if after == before:
            continue

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(after, encoding="utf-8")
        applied_paths.append(edit.path)

    return applied_paths
