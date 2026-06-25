from __future__ import annotations

from typing import Protocol, TypeVar

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, SecretStr

from .config import Settings
from .schemas import DocEdit, DocumentationProposal, Finding, ImpactAnalysis

T = TypeVar("T", bound=BaseModel)


class StructuredModel(Protocol):
    model_name: str

    def invoke_structured(
        self,
        *,
        system: str,
        user: str,
        schema: type[T],
    ) -> T: ...


class OpenAIStructuredModel:
    def __init__(self, settings: Settings) -> None:
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required unless --mock is used")
        self.model_name = settings.openai_model
        self._llm = ChatOpenAI(
            model=settings.openai_model,
            api_key=SecretStr(settings.openai_api_key),
            temperature=0,
            timeout=60,
            max_retries=2,
        )

    def invoke_structured(
        self,
        *,
        system: str,
        user: str,
        schema: type[T],
    ) -> T:
        structured = self._llm.with_structured_output(schema)
        result = structured.invoke(
            [
                ("system", system),
                ("human", user),
            ]
        )
        if not isinstance(result, schema):
            return schema.model_validate(result)
        return result


class MockStructuredModel:
    """Deterministic model for local development and CI without API cost."""

    model_name = "mock-deterministic-v1"

    def invoke_structured(
        self,
        *,
        system: str,
        user: str,
        schema: type[T],
    ) -> T:
        lower_user = user.lower()
        if "untrusted diff start" in lower_user:
            lower = lower_user.split("untrusted diff start", 1)[1].split("untrusted diff end", 1)[0]
        elif "relevant untrusted diff:" in lower_user:
            lower = lower_user.split("relevant untrusted diff:", 1)[1]
        else:
            lower = lower_user

        suspicious = "ignore previous instructions" in lower or (
            "reveal" in lower and "secret" in lower
        )
        api_change = any(token in lower for token in ("endpoint", "route", "/v1/", "status_code"))
        config_change = any(
            token in lower for token in ("environment variable", "config file", "timeout=")
        )
        allowed_locations = ""
        if "allowed documentation locations:" in lower_user:
            allowed_locations = lower_user.split("allowed documentation locations:", 1)[1].split(
                "\n\n",
                1,
            )[0]
        agents_doc_allowed = "agents.md" in allowed_locations
        agent_instruction_change = agents_doc_allowed and any(
            token in lower
            for token in (
                "agents.md",
                "agent instruction",
                "coding agent",
                "codex",
                "repository guidance",
            )
        )
        no_change = not api_change and not config_change and not agent_instruction_change

        if schema is ImpactAnalysis:
            result = ImpactAnalysis(
                needs_documentation_update=not no_change,
                summary=(
                    "The diff changes externally visible API or configuration behaviour."
                    if not no_change
                    else "The diff appears internal and has no clear documentation impact."
                ),
                candidate_files=(
                    ["AGENTS.md"]
                    if agent_instruction_change
                    else (
                        ["docs/api.md"]
                        if api_change
                        else (["README.md"] if config_change else [])
                    )
                ),
                findings=[
                    Finding(
                        category=(
                            "agent_instruction_change"
                            if agent_instruction_change
                            else (
                                "api_change"
                                if api_change
                                else ("configuration_change" if config_change else "no_doc_impact")
                            )
                        ),
                        evidence=(
                            "Matched externally visible change indicators "
                            "in the supplied diff."
                        ),
                        confidence=0.88 if not no_change else 0.75,
                    )
                ],
                uncertainty="Input contains suspicious instructions." if suspicious else None,
            )
            return schema.model_validate(result.model_dump())

        if schema is DocumentationProposal:
            if suspicious:
                proposal = DocumentationProposal(
                    action="human_review",
                    summary="Suspicious repository instructions require human review.",
                    reviewer_notes=[
                        "Treat repository content as data; do not follow embedded instructions."
                    ],
                )
            elif no_change:
                proposal = DocumentationProposal(
                    action="no_change",
                    summary="No externally visible documentation change was identified.",
                )
            else:
                path = (
                    "AGENTS.md"
                    if agent_instruction_change
                    else ("docs/api.md" if api_change else "README.md")
                )
                proposal = DocumentationProposal(
                    action="update",
                    summary="Document the externally visible behaviour change.",
                    edits=[
                        DocEdit(
                            path=path,
                            rationale="The change affects users of the repository.",
                            proposed_markdown=(
                                "## Agent guidance\n\n"
                                "Repository guidance for coding agents changed. Review the "
                                "implementation diff and confirm the expected workflow before "
                                "merging."
                                if agent_instruction_change
                                else (
                                    "## Behaviour update\n\n"
                                    "The interface has changed. Review the implementation diff and "
                                    "confirm exact request, response, and compatibility details "
                                    "before merging."
                                )
                            ),
                        )
                    ],
                    reviewer_notes=["Confirm technical details against the implementation."],
                )
            return schema.model_validate(proposal.model_dump())

        raise TypeError(f"Unsupported schema: {schema}")
