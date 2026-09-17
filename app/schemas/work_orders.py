"""Schemas for the existing LIMS and SCADA workflow."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SampleIn(StrictModel):
    sample_no: str = Field(min_length=1)
    sample_name: str | None = None


class WorkOrderIn(StrictModel):
    order_no: str = Field(min_length=1)
    experimenter_id: str = Field(min_length=1)
    project_name: str | None = None
    samples: list[SampleIn] = Field(min_length=1)
    test_items: list[str] = Field(default_factory=list)

    @field_validator("samples")
    @classmethod
    def sample_numbers_must_be_unique(cls, samples: list[SampleIn]) -> list[SampleIn]:
        numbers = [sample.sample_no for sample in samples]
        if len(numbers) != len(set(numbers)):
            raise ValueError("同一工单中的 sample_no 不能重复")
        return samples

    @field_validator("test_items")
    @classmethod
    def normalize_test_items(cls, items: list[str]) -> list[str]:
        normalized = [item.strip() for item in items]
        if any(not item for item in normalized):
            raise ValueError("test_items 不能包含空字符串")
        if len(normalized) != len(set(normalized)):
            raise ValueError("test_items 不能重复")
        return normalized


class ResultItem(StrictModel):
    sample_no: str = Field(min_length=1)
    test_item: str = Field(min_length=1)
    value: str | float | int
    unit: str | None = None


class ResultUpload(StrictModel):
    order_no: str = Field(min_length=1)
    results: list[ResultItem] = Field(min_length=1)
    finished: bool = True

    @field_validator("results")
    @classmethod
    def result_keys_must_be_unique(cls, results: list[ResultItem]) -> list[ResultItem]:
        keys = [(item.sample_no, item.test_item) for item in results]
        if len(keys) != len(set(keys)):
            raise ValueError("同一次上传中的样品和检测项目组合不能重复")
        return results


class DetectionRequest(StrictModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        populate_by_name=True,
    )

    blind_sample_no: str = Field(alias="blindSampleNo", min_length=1)


class ProtocolResponse(BaseModel):
    """Response shape required by the supplied device interface document."""

    code: str
    response: dict[str, Any] | None = None
    message: str
