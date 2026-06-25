from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class Finding(BaseModel):
    category: Literal[
        "api_change",
        "behaviour_change",
        "configuration_change",
        "security_change",
        "agent_instruction_change",
        "no_doc_impact",
    ]
    evidence: str = Field(min_length=1, max_length=600)
    confidence: float = Field(ge=0, le=1)


class ImpactAnalysis(BaseModel):
    needs_documentation_update: bool
    summary: str = Field(min_length=1, max_length=1_000)
    candidate_files: list[str] = Field(default_factory=list, max_length=10)
    findings: list[Finding] = Field(default_factory=list, max_length=20)
    uncertainty: str | None = Field(default=None, max_length=600)

    @field_validator("candidate_files")
    @classmethod
    def unique_files(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(value))


class DocumentationContext(BaseModel):
    path: str = Field(min_length=1, max_length=300)
    exists: bool
    content: str = Field(default="", max_length=20_000)
    truncated: bool = False


class DocEdit(BaseModel):
    path: str = Field(min_length=1, max_length=300)
    rationale: str = Field(min_length=1, max_length=600)
    proposed_markdown: str = Field(min_length=1, max_length=8_000)
    unified_diff: str | None = Field(default=None, max_length=16_000)


class DocumentationProposal(BaseModel):
    action: Literal["update", "no_change", "human_review"]
    summary: str = Field(min_length=1, max_length=1_000)
    edits: list[DocEdit] = Field(default_factory=list, max_length=5)
    reviewer_notes: list[str] = Field(default_factory=list, max_length=10)


class AgentResult(BaseModel):
    status: Literal["ok", "blocked", "human_review"]
    analysis: ImpactAnalysis
    proposal: DocumentationProposal
    safety_flags: list[str] = Field(default_factory=list)
    prompt_version: str
    model: str
