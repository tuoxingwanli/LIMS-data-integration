"""Replaceable recording and screenshot adapter boundary."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class CaptureResult:
    success: bool
    artifact_ref: str | None = None
    error: str | None = None


class CaptureAdapter(Protocol):
    mode: str

    def start(self, blind_sample_no: str) -> CaptureResult:
        """Start recording for a blind sample."""

    def stop(self, blind_sample_no: str) -> CaptureResult:
        """Stop recording and take a screenshot."""


class MockCaptureAdapter:
    """Successful protocol stub that creates no local media files."""

    mode = "mock"

    def start(self, blind_sample_no: str) -> CaptureResult:
        return CaptureResult(success=True)

    def stop(self, blind_sample_no: str) -> CaptureResult:
        return CaptureResult(success=True)


def build_capture_adapter(backend: str) -> CaptureAdapter:
    """Build the configured adapter while keeping real capture replaceable."""

    if backend != "mock":
        raise ValueError(
            f"不支持的 CAPTURE_BACKEND: {backend}；当前仅提供 mock 适配器"
        )
    return MockCaptureAdapter()
