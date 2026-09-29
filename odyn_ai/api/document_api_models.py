from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class DocumentExportRequest(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    content: str = Field(min_length=1, max_length=200000)
    filename: str = Field(min_length=1, max_length=200)


class SpreadsheetExportRequest(BaseModel):
    data: list[list[object]] = Field(min_length=1, max_length=10000)
    filename: str = Field(min_length=1, max_length=200)
    sheet_name: str = Field(default="ODYN", max_length=31)
    header: bool = True


class ReportExportRequest(BaseModel):
    format: Literal["pdf", "docx", "xlsx"]
    title: str = Field(min_length=1, max_length=500)
    content: str = Field(min_length=1, max_length=200000)
    filename: str = Field(min_length=1, max_length=200)
    data: list[list[object]] | None = Field(default=None, max_length=10000)
    sheet_name: str = Field(default="ODYN", max_length=31)
    header: bool = True
