from __future__ import annotations

from typing import Annotated, Literal, TypeAlias, Union

from pydantic import BaseModel, ConfigDict, Field, NonNegativeInt, model_validator
from pydantic.types import StrictBool, StrictFloat, StrictInt, StrictStr


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceSpan(StrictModel):
    start: NonNegativeInt
    end: NonNegativeInt

    @model_validator(mode="after")
    def ordered(self) -> SourceSpan:
        if self.end < self.start:
            raise ValueError("source span end must be greater than or equal to start")
        return self


class Var(StrictModel):
    kind: Literal["var"]
    name: StrictStr
    source_span: SourceSpan | None = None


class LiteralNode(StrictModel):
    kind: Literal["literal"]
    value: StrictStr | StrictInt | StrictFloat | StrictBool
    source_span: SourceSpan | None = None


class Symbol(StrictModel):
    kind: Literal["symbol"]
    id: StrictStr
    source_span: SourceSpan | None = None


class BoundVariable(StrictModel):
    name: StrictStr
    type: Expr


class Apply(StrictModel):
    kind: Literal["apply"]
    head: Expr
    args: list[Expr]
    source_span: SourceSpan | None = None


class Bind(StrictModel):
    kind: Literal["bind"]
    binder: Expr
    variables: list[BoundVariable]
    body: Expr
    source_span: SourceSpan | None = None


class Forall(StrictModel):
    kind: Literal["forall"]
    variables: list[BoundVariable]
    body: Expr
    source_span: SourceSpan | None = None


class Exists(StrictModel):
    kind: Literal["exists"]
    variables: list[BoundVariable]
    body: Expr
    source_span: SourceSpan | None = None


class BinaryLogic(StrictModel):
    left: Expr
    right: Expr
    source_span: SourceSpan | None = None


class Implies(BinaryLogic):
    kind: Literal["implies"]


class And(BinaryLogic):
    kind: Literal["and"]


class Or(BinaryLogic):
    kind: Literal["or"]


class Not(StrictModel):
    kind: Literal["not"]
    value: Expr
    source_span: SourceSpan | None = None


class Equals(BinaryLogic):
    kind: Literal["equals"]


Expr: TypeAlias = Annotated[
    Union[Var, LiteralNode, Symbol, Apply, Bind, Forall, Exists, Implies, And, Or, Not, Equals],
    Field(discriminator="kind"),
]

for _model in (BoundVariable, Apply, Bind, Forall, Exists, BinaryLogic, Implies, And, Or, Not, Equals):
    _model.model_rebuild()


class CandidateAExpr(StrictModel):
    root: Annotated[Union[Var, LiteralNode, Symbol, Apply, Bind], Field(discriminator="kind")]


class CandidateBExpr(StrictModel):
    root: Annotated[Union[Var, LiteralNode, Symbol, Apply, Bind, Forall, Exists], Field(discriminator="kind")]


class CandidateCExpr(StrictModel):
    root: Annotated[
        Union[Var, LiteralNode, Symbol, Apply, Bind, Forall, Exists, Implies, And, Or, Not, Equals],
        Field(discriminator="kind"),
    ]


class FormalizationBase(StrictModel):
    outcome: Literal["formalization"]


class ClarificationRequired(StrictModel):
    outcome: Literal["clarification_required"]
    issue: StrictStr


class CandidateAFormalization(FormalizationBase):
    ir: Annotated[Union[Var, LiteralNode, Symbol, Apply, Bind], Field(discriminator="kind")]

    @model_validator(mode="after")
    def reject_extended_nodes(self) -> CandidateAFormalization:
        _ensure_allowed_kinds(self.ir, {"var", "literal", "symbol", "apply", "bind"})
        return self


class CandidateBFormalization(FormalizationBase):
    ir: Annotated[Union[Var, LiteralNode, Symbol, Apply, Bind, Forall, Exists], Field(discriminator="kind")]

    @model_validator(mode="after")
    def reject_logic_nodes(self) -> CandidateBFormalization:
        _ensure_allowed_kinds(self.ir, {"var", "literal", "symbol", "apply", "bind", "forall", "exists"})
        return self


class CandidateCFormalization(FormalizationBase):
    ir: Annotated[
        Union[Var, LiteralNode, Symbol, Apply, Bind, Forall, Exists, Implies, And, Or, Not, Equals],
        Field(discriminator="kind"),
    ]


class DirectFormalization(FormalizationBase):
    lean_statement: StrictStr


Result: TypeAlias = Union[
    CandidateAFormalization,
    CandidateBFormalization,
    CandidateCFormalization,
    DirectFormalization,
    ClarificationRequired,
]


def _ensure_allowed_kinds(value: object, allowed: set[str]) -> None:
    if isinstance(value, StrictModel):
        kind = getattr(value, "kind", None)
        if kind is not None and kind not in allowed:
            raise ValueError(f"node kind {kind!r} is not allowed in this candidate")
        for child in value.__dict__.values():
            _ensure_allowed_kinds(child, allowed)
    elif isinstance(value, list):
        for child in value:
            _ensure_allowed_kinds(child, allowed)
