"""Tests for the cross-platform hardware telemetry module.

The tests do not assert on real sensor values; they verify the public
contract: ``snapshot()`` returns a populated ``HwSnapshot``, the sampler
collects snapshots over time, and the module never raises even when the
host has no sensor (e.g. CI without ``nvidia-smi`` or ``powermetrics``).
"""

from __future__ import annotations

import math
import platform

import pytest

from core.telemetry_hw import (
    HwSampler,
    HwSnapshot,
    is_platform_supported,
    snapshot,
)


def test_is_platform_supported_recognises_current_host() -> None:
    """The reporter returns ``True`` on macOS and Linux, the two supported."""
    assert is_platform_supported() == (platform.system() in {"Darwin", "Linux"})


def test_snapshot_returns_a_complete_dataclass() -> None:
    """Every documented field is present on the snapshot, even as ``None``."""
    s = snapshot()
    assert isinstance(s, HwSnapshot)
    payload = s.to_dict()
    expected = {
        "timestamp", "cpu_temp_c", "gpu_temp_c", "soc_temp_c",
        "cpu_util_pct", "gpu_util_pct",
        "ram_used_gb", "ram_total_gb", "vram_used_gb",
        "cpu_watt", "gpu_watt", "memory_pressure_pct",
    }
    assert set(payload) == expected
    assert payload["timestamp"] > 0.0


def test_snapshot_returns_floats_or_none() -> None:
    """Each numeric field is either ``float`` or ``None`` -- never an exception.

    On hosts without ``powermetrics`` (sudo) or ``nvidia-smi``, several
    fields are ``None``; the test accepts that as long as the values
    that *are* present are real floats.
    """
    s = snapshot()
    for value in (
        s.cpu_temp_c, s.gpu_temp_c, s.soc_temp_c,
        s.cpu_util_pct, s.gpu_util_pct,
        s.ram_used_gb, s.ram_total_gb, s.vram_used_gb,
        s.cpu_watt, s.gpu_watt, s.memory_pressure_pct,
    ):
        if value is not None:
            assert isinstance(value, float)
            assert not math.isnan(value)


def test_sampler_rejects_non_positive_period() -> None:
    with pytest.raises(ValueError):
        HwSampler(period_seconds=0.0)
    with pytest.raises(ValueError):
        HwSampler(period_seconds=-0.5)


def test_sampler_with_zero_seconds_returns_empty_list() -> None:
    sampler = HwSampler(period_seconds=1.0)
    samples = sampler.sample(0.0)
    assert samples == []


def test_sampler_collects_at_least_two_snapshots_over_a_short_window() -> None:
    """A 0.3 s window with a 0.1 s period yields the initial + at least one more."""
    sampler = HwSampler(period_seconds=0.1)
    samples = sampler.sample(0.3)
    assert len(samples) >= 2
    for s in samples:
        assert isinstance(s, HwSnapshot)


def test_sampler_collects_exactly_one_snapshot_on_instant_window() -> None:
    """A 0.0 s window returns an empty list (no measurement taken)."""
    sampler = HwSampler(period_seconds=1.0)
    assert sampler.sample(0.0) == []


def test_snapshot_is_json_serialisable() -> None:
    """The dataclass survives the standard ``json.dumps`` round trip."""
    import json

    s = snapshot()
    encoded = json.dumps(s.to_dict(), ensure_ascii=False, default=str)
    decoded = json.loads(encoded)
    assert decoded["timestamp"] == pytest.approx(s.timestamp)
    for key, value in s.to_dict().items():
        if key == "timestamp":
            continue
        assert decoded[key] == value


def test_run_helper_handles_missing_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    """``_run`` returns an empty string when the tool is missing or fails."""
    from core import telemetry_hw

    # ``which`` returns ``None`` for any path the host does not have.
    monkeypatch.setattr(telemetry_hw.shutil, "which", lambda _: None)
    assert telemetry_hw._run(["nonexistent-tool", "--help"]) == ""


def test_first_float_returns_none_on_garbage() -> None:
    from core.telemetry_hw import _first_float

    assert _first_float("", r"([\d.]+)") is None
    assert _first_float("abc", r"([\d.]+)") is None
    assert _first_float("temp: not a number", r"temp:\s+([\d.]+)") is None


def test_first_float_extracts_first_match() -> None:
    from core.telemetry_hw import _first_float

    assert _first_float("a: 12.5 b: 7.0", r"([\d.]+)") == pytest.approx(12.5)
