"""User interpretation is separate from device observations and execution authority."""
from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, StringConstraints, model_validator

from app.schemas.wearable import ContractModel, EvidenceReference, Revision, Text


ReflectionText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)]


class ReflectionFields(ContractModel):
    """Editable hypotheses, including the user's reported facts; never a diagnosis."""
    facts: ReflectionText
    interpretation: ReflectionText
    emotions: ReflectionText
    needs: ReflectionText

    @model_validator(mode='after')
    def some_content(self):
        if not any((self.facts, self.interpretation, self.emotions, self.needs)):
            raise ValueError('at least one reflection field must contain text')
        return self


class Understanding(ContractModel):
    schema_version: Literal["understanding.v0.1"] = "understanding.v0.1"
    understanding_id: Text
    revision: Revision
    status: Literal["proposed", "confirmed", "rejected", "invalidated"]
    interpretation: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
    fields: ReflectionFields | None = None
    origin: Literal["agent_hypothesis", "user_report"]
    evidence_refs: list[EvidenceReference] = Field(min_length=1, max_length=200)
    created_at: AwareDatetime
    updated_at: AwareDatetime
    confirmed_revision: Revision | None = None
    confirmed_at: AwareDatetime | None = None
    invalidation_reason: Text | None = None

    @model_validator(mode="after")
    def version_state(self):
        if self.updated_at < self.created_at:
            raise ValueError("understanding update predates creation")
        if self.status == "confirmed":
            if self.confirmed_revision != self.revision or self.confirmed_at is None:
                raise ValueError("confirmation must refer to current revision")
            if not self.created_at <= self.confirmed_at <= self.updated_at:
                raise ValueError("confirmation outside object timeline")
        elif self.confirmed_revision is not None or self.confirmed_at is not None:
            raise ValueError("unconfirmed understanding cannot retain confirmation")
        if (self.status == "invalidated") != (self.invalidation_reason is not None):
            raise ValueError("only invalidated understanding requires invalidation reason")
        if self.origin == "user_report" and not any(r.kind == "user_report" for r in self.evidence_refs):
            raise ValueError("user interpretation requires a user report reference")
        return self
