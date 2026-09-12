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


Scalar: TypeAlias = StrictStr | StrictInt | StrictFloat | StrictBool


class AVar(StrictModel):
    kind: Literal["var"]
    name: StrictStr
    source_span: SourceSpan | None = None


class ALiteral(StrictModel):
    kind: Literal["literal"]
    value: Scalar
    source_span: SourceSpan | None = None


class ASymbol(StrictModel):
    kind: Literal["symbol"]
    id: StrictStr
    source_span: SourceSpan | None = None


class ABoundVariable(StrictModel):
    name: StrictStr
    type: AExpr


class AApply(StrictModel):
    kind: Literal["apply"]
    head: AExpr
    args: list[AExpr]
    source_span: SourceSpan | None = None


class ABind(StrictModel):
    kind: Literal["bind"]
    binder: AExpr
    variables: list[ABoundVariable]
    body: AExpr
    source_span: SourceSpan | None = None


AExpr: TypeAlias = Annotated[Union[AVar, ALiteral, ASymbol, AApply, ABind], Field(discriminator="kind")]


class BVar(StrictModel):
    kind: Literal["var"]
    name: StrictStr
    source_span: SourceSpan | None = None


class BLiteral(StrictModel):
    kind: Literal["literal"]
    value: Scalar
    source_span: SourceSpan | None = None


class BSymbol(StrictModel):
    kind: Literal["symbol"]
    id: StrictStr
    source_span: SourceSpan | None = None


class BBoundVariable(StrictModel):
    name: StrictStr
    type: BExpr


class BApply(StrictModel):
    kind: Literal["apply"]
    head: BExpr
    args: list[BExpr]
    source_span: SourceSpan | None = None


class BBind(StrictModel):
    kind: Literal["bind"]
    binder: BExpr
    variables: list[BBoundVariable]
    body: BExpr
    source_span: SourceSpan | None = None


class BForall(StrictModel):
    kind: Literal["forall"]
    variables: list[BBoundVariable]
    body: BExpr
    source_span: SourceSpan | None = None


class BExists(StrictModel):
    kind: Literal["exists"]
    variables: list[BBoundVariable]
    body: BExpr
    source_span: SourceSpan | None = None


BExpr: TypeAlias = Annotated[
    Union[BVar, BLiteral, BSymbol, BApply, BBind, BForall, BExists],
    Field(discriminator="kind"),
]


class CVar(StrictModel):
    kind: Literal["var"]
    name: StrictStr
    source_span: SourceSpan | None = None


class CLiteral(StrictModel):
    kind: Literal["literal"]
    value: Scalar
    source_span: SourceSpan | None = None


class CSymbol(StrictModel):
    kind: Literal["symbol"]
    id: StrictStr
    source_span: SourceSpan | None = None


class CBoundVariable(StrictModel):
    name: StrictStr
    type: CExpr


class CApply(StrictModel):
    kind: Literal["apply"]
    head: CExpr
    args: list[CExpr]
    source_span: SourceSpan | None = None


class CBind(StrictModel):
    kind: Literal["bind"]
    binder: CExpr
    variables: list[CBoundVariable]
    body: CExpr
    source_span: SourceSpan | None = None


class CForall(StrictModel):
    kind: Literal["forall"]
    variables: list[CBoundVariable]
    body: CExpr
    source_span: SourceSpan | None = None


class CExists(StrictModel):
    kind: Literal["exists"]
    variables: list[CBoundVariable]
    body: CExpr
    source_span: SourceSpan | None = None


class CBinary(StrictModel):
    left: CExpr
    right: CExpr
    source_span: SourceSpan | None = None


class CImplies(CBinary):
    kind: Literal["implies"]


class CAnd(CBinary):
    kind: Literal["and"]


class COr(CBinary):
    kind: Literal["or"]


class CNot(StrictModel):
    kind: Literal["not"]
    value: CExpr
    source_span: SourceSpan | None = None


class CEquals(CBinary):
    kind: Literal["equals"]


CExpr: TypeAlias = Annotated[
    Union[CVar, CLiteral, CSymbol, CApply, CBind, CForall, CExists,
          CImplies, CAnd, COr, CNot, CEquals],
    Field(discriminator="kind"),
]


for _model in (
    ABoundVariable, AApply, ABind,
    BBoundVariable, BApply, BBind, BForall, BExists,
    CBoundVariable, CApply, CBind, CForall, CExists, CBinary,
    CImplies, CAnd, COr, CNot, CEquals,
):
    _model.model_rebuild()


class FormalizationBase(StrictModel):
    outcome: Literal["formalization"]


class ClarificationRequired(StrictModel):
    outcome: Literal["clarification_required"]
    issue: StrictStr


class CandidateAFormalization(FormalizationBase):
    ir: AExpr


class CandidateBFormalization(FormalizationBase):
    ir: BExpr


class CandidateCFormalization(FormalizationBase):
    ir: CExpr


class DirectFormalization(FormalizationBase):
    lean_statement: StrictStr


Result: TypeAlias = Union[
    CandidateAFormalization, CandidateBFormalization, CandidateCFormalization,
    DirectFormalization, ClarificationRequired,
]
