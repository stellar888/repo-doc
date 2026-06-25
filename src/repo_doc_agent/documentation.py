from __future__ import annotations

import difflib
import re
from pathlib import Path, PurePosixPath

from .schemas import DocumentationContext, DocumentationProposal
from .security import path_is_allowed

TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+")
DIFF_PATH_PATTERN = re.compile(r"^diff --git a/(.+?) b/(.+)$")
HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")


def _tokens(text: str) -> set[str]:
    return {
        match.group(0).lower()
        for match in TOKEN_PATTERN.finditer(text)
        if len(match.group(0)) > 1
    }


def _changed_paths(diff: str) -> list[str]:
    paths: list[str] = []
    for line in diff.splitlines():
        match = DIFF_PATH_PATTERN.match(line)
        if match:
            paths.extend([match.group(1), match.group(2)])
        elif line.startswith(("--- a/", "+++ b/")):
            paths.append(line[6:])
    return list(dict.fromkeys(path for path in paths if path != "/dev/null"))


def _iter_allowed_markdown_paths(
    *,
    repository_root: Path,
    allowed_paths: tuple[str, ...],
) -> list[str]:
    root = repository_root.resolve()
    discovered: list[str] = []

    for allowed in allowed_paths:
        if not path_is_allowed(allowed, allowed_paths):
            continue

        allowed_path = _safe_repo_path(root, allowed)
        if allowed.endswith(".md"):
            discovered.append(str(PurePosixPath(allowed)))
            continue

        if not allowed_path.exists() or not allowed_path.is_dir():
            continue

        for markdown_path in sorted(allowed_path.rglob("*.md")):
            if not markdown_path.is_file():
                continue
            relative = markdown_path.relative_to(root).as_posix()
            if path_is_allowed(relative, allowed_paths):
                discovered.append(relative)

    return list(dict.fromkeys(discovered))


def _documentation_heading_tokens(path: Path) -> set[str]:
    try:
        headings = [
            line.lstrip("#").strip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.startswith("#")
        ]
    except (OSError, UnicodeError):
        return set()
    return _tokens(" ".join(headings))


def _score_documentation_path(
    *,
    path: str,
    repository_root: Path,
    diff_tokens: set[str],
    changed_path_tokens: set[str],
) -> int:
    path_tokens = _tokens(path)
    score = 0
    score += len(path_tokens & changed_path_tokens) * 6
    score += len(path_tokens & diff_tokens) * 2

    lower_path = path.lower()
    if "api" in diff_tokens and "api" in path_tokens:
        score += 8
    if diff_tokens & {"endpoint", "route", "request", "response", "status", "v1"}:
        if "api" in path_tokens:
            score += 6
    if diff_tokens & {"config", "configuration", "environment", "variable", "setting"}:
        if path_tokens & {"config", "configuration", "readme"}:
            score += 6
    if diff_tokens & {"agent", "agents", "codex", "workflow", "guidance"}:
        if lower_path == "agents.md":
            score += 8

    target = _safe_repo_path(repository_root, path)
    if target.exists() and target.is_file():
        heading_tokens = _documentation_heading_tokens(target)
        score += len(heading_tokens & diff_tokens) * 3
        score += len(heading_tokens & changed_path_tokens) * 4

    return score


def discover_documentation_candidates(
    *,
    diff: str,
    repository_root: Path,
    allowed_paths: tuple[str, ...],
    limit: int = 5,
) -> list[str]:
    """Find likely Markdown files before asking the model to write a proposal."""
    root = repository_root.resolve()
    diff_tokens = _tokens(diff)
    changed_path_tokens: set[str] = set()
    for path in _changed_paths(diff):
        changed_path_tokens.update(_tokens(path))

    scored: list[tuple[int, str]] = []
    for path in _iter_allowed_markdown_paths(repository_root=root, allowed_paths=allowed_paths):
        score = _score_documentation_path(
            path=path,
            repository_root=root,
            diff_tokens=diff_tokens,
            changed_path_tokens=changed_path_tokens,
        )
        if score > 0:
            scored.append((score, path))

    scored.sort(key=lambda item: (-item[0], item[1]))
    return [path for _, path in scored[:limit]]


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


def _normalize_heading(heading: str) -> str:
    return " ".join(heading.strip().strip("#").strip().lower().split())


def _find_markdown_section(markdown: str, heading: str) -> list[tuple[int, int]]:
    target = _normalize_heading(heading)
    lines = markdown.splitlines(keepends=True)
    offsets: list[int] = []
    position = 0
    for line in lines:
        offsets.append(position)
        position += len(line)

    matches: list[tuple[int, int]] = []
    for index, line in enumerate(lines):
        match = HEADING_PATTERN.match(line.rstrip("\n"))
        if not match or _normalize_heading(match.group(2)) != target:
            continue

        level = len(match.group(1))
        start = offsets[index]
        end = len(markdown)
        for next_index in range(index + 1, len(lines)):
            next_match = HEADING_PATTERN.match(lines[next_index].rstrip("\n"))
            if next_match and len(next_match.group(1)) <= level:
                end = offsets[next_index]
                break
        matches.append((start, end))

    return matches


def _replace_markdown_section(*, before: str, heading: str, proposed_markdown: str) -> str:
    matches = _find_markdown_section(before, heading)
    if len(matches) != 1:
        return before

    start, end = matches[0]
    proposed = proposed_markdown.strip() + "\n"
    tail = before[end:]
    if tail and not tail.startswith("\n"):
        proposed += "\n"
    return before[:start] + proposed + tail


def _apply_edit_to_markdown(
    *,
    before: str,
    operation: str,
    target_heading: str | None,
    proposed_markdown: str,
) -> str:
    if operation == "create_file":
        return proposed_markdown.strip() + "\n" if not before else before
    if operation == "replace_section" and target_heading:
        return _replace_markdown_section(
            before=before,
            heading=target_heading,
            proposed_markdown=proposed_markdown,
        )
    return _merge_markdown(before=before, proposed_markdown=proposed_markdown)


def validate_edit_operations(
    proposal: DocumentationProposal,
    contexts: list[DocumentationContext],
) -> list[str]:
    context_by_path = {context.path: context for context in contexts}
    flags: list[str] = []

    for edit in proposal.edits:
        context = context_by_path.get(edit.path)
        exists = bool(context and context.exists)
        before = context.content if context and context.exists else ""

        if edit.operation == "create_file" and exists:
            flags.append(f"invalid_edit_operation:{edit.path}:create_file_exists")

        if edit.operation == "replace_section":
            if not edit.target_heading:
                flags.append(f"invalid_edit_operation:{edit.path}:missing_target_heading")
            elif not exists:
                flags.append(f"invalid_edit_operation:{edit.path}:missing_file")
            else:
                matches = _find_markdown_section(before, edit.target_heading)
                if not matches:
                    flags.append(f"invalid_edit_operation:{edit.path}:heading_not_found")
                elif len(matches) > 1:
                    flags.append(f"invalid_edit_operation:{edit.path}:heading_not_unique")

    return flags


def attach_unified_diffs(
    proposal: DocumentationProposal,
    contexts: list[DocumentationContext],
) -> DocumentationProposal:
    context_by_path = {context.path: context for context in contexts}
    edits = []

    for edit in proposal.edits:
        context = context_by_path.get(edit.path)
        before = context.content if context and context.exists else ""
        after = _apply_edit_to_markdown(
            before=before,
            operation=edit.operation,
            target_heading=edit.target_heading,
            proposed_markdown=edit.proposed_markdown,
        )

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
        after = _apply_edit_to_markdown(
            before=before,
            operation=edit.operation,
            target_heading=edit.target_heading,
            proposed_markdown=edit.proposed_markdown,
        )
        if after == before:
            continue

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(after, encoding="utf-8")
        applied_paths.append(edit.path)

    return applied_paths
