"""Cross-platform hardware telemetry for the experimental reports.

The PoC stays platform-agnostic: every read function returns a ``float``
when the underlying sensor is available, or ``None`` when the host
either lacks the sensor or the script does not have the privilege
required to query it (e.g. macOS ``powermetrics`` requires sudo). The
prototype never raises from this module; the campaign scripts that
collect reports keep ``None`` values verbatim and treat the absence of
a measurement as a structural fact rather than an error.

Two access patterns are supported:

* **Snapshot** -- ``snapshot()`` returns a single :class:`HwSnapshot`
  with one value per metric, taken at call time.
* **Sampler** -- ``HwSampler(snapshot).sample(period_seconds)`` returns
  a chronological list of snapshots. The sampler is a synchronous loop
  suitable for the run loop of :mod:`core.pipeline`; it does not use
  threads to keep the prototype portable and the tests deterministic.

The optional dependency on the GPU vendor tools (``nvidia-smi`` on
Linux, ``powermetrics`` on macOS) is hidden behind ``shutil.which`` so
the module imports cleanly even when the tools are missing.

External dependencies:
    Standard library only. ``subprocess`` is invoked with a short
    timeout so a missing or hung sensor tool never blocks a run.
"""

from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field

__all__ = [
    "HwSampler",
    "HwSnapshot",
    "is_platform_supported",
    "snapshot",
]


@dataclass(frozen=True, slots=True)
class HwSnapshot:
    """One cross-platform hardware reading.

    ``None`` means the metric could not be measured on this host (tool
    missing, missing privileges, virtualised environment). The
    campaign reports keep ``None`` to make the absence explicit.
    """

    timestamp: float
    cpu_temp_c: float | None = None
    gpu_temp_c: float | None = None
    soc_temp_c: float | None = None
    cpu_util_pct: float | None = None
    gpu_util_pct: float | None = None
    ram_used_gb: float | None = None
    ram_total_gb: float | None = None
    vram_used_gb: float | None = None
    cpu_watt: float | None = None
    gpu_watt: float | None = None
    memory_pressure_pct: float | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------

_SUPPORTED = frozenset({"Darwin", "Linux"})


def is_platform_supported() -> bool:
    """True when this host has at least one implemented reader."""
    return platform.system() in _SUPPORTED


# ---------------------------------------------------------------------------
# Subprocess helpers
# ---------------------------------------------------------------------------


def _run(command: list[str], *, timeout: float = 2.0) -> str:
    """Run ``command`` and return stdout. Empty string on failure."""
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if completed.returncode != 0:
        return ""
    return completed.stdout


def _use_sudo() -> bool:
    """True when POC_HW_SUDO is set to a truthy value."""
    return os.environ.get("POC_HW_SUDO", "").strip() in ("1", "true", "yes")


def _powermetrics_cmd(*args: str) -> list[str]:
    """Prefix with sudo when POC_HW_SUDO is set."""
    base = ["powermetrics", *args]
    return ["sudo", *base] if _use_sudo() else base


def _first_float(text: str, pattern: str) -> float | None:
    """Return the first float captured by ``pattern`` or ``None``."""
    match = re.search(pattern, text)
    if not match:
        return None
    try:
        return float(match.group(1))
    except (ValueError, IndexError):
        return None


# ---------------------------------------------------------------------------
# macOS readers
# ---------------------------------------------------------------------------


def _macos_cpu_temp() -> float | None:
    """Best-effort CPU temperature on macOS.

    Returns ``None`` when ``powermetrics`` cannot be invoked. When
    ``POC_HW_SUDO`` is set, the command is prefixed with ``sudo`` so
    that a NOPASSWD sudoers rule can supply the required privileges.
    """
    if not shutil.which("powermetrics"):
        return None
    output = _run(
        _powermetrics_cmd("-n", "1", "-i", "1",
                          "--samplers", "cpu_power,thermal", "-b", "1"),
        timeout=3.0,
    )
    return _first_float(output, r"CPU die temperature:\s+([\d.]+)")


def _macos_gpu_temp() -> float | None:
    """GPU temperature on macOS via ``powermetrics`` (sudo required)."""
    if not shutil.which("powermetrics"):
        return None
    output = _run(
        _powermetrics_cmd("-n", "1", "-i", "1",
                          "--samplers", "gpu_power", "-b", "1"),
        timeout=3.0,
    )
    return _first_float(output, r"GPU die temperature:\s+([\d.]+)")


def _macos_soc_temp() -> float | None:
    """SoC temperature on macOS via ``powermetrics`` (sudo required)."""
    return _macos_cpu_temp()  # same sensor on Apple Silicon


def _macos_cpu_watt() -> float | None:
    """CPU power in watts from ``powermetrics`` (sudo required)."""
    if not shutil.which("powermetrics"):
        return None
    output = _run(
        _powermetrics_cmd("-n", "1", "-i", "1",
                          "--samplers", "cpu_power", "-b", "1"),
        timeout=3.0,
    )
    mw = _first_float(output, r"CPU Power:\s+([\d.]+)\s*mW")
    return mw / 1000.0 if mw is not None else None


def _macos_gpu_watt() -> float | None:
    """GPU power in watts from ``powermetrics`` (sudo required)."""
    if not shutil.which("powermetrics"):
        return None
    output = _run(
        _powermetrics_cmd("-n", "1", "-i", "1",
                          "--samplers", "gpu_power", "-b", "1"),
        timeout=3.0,
    )
    mw = _first_float(output, r"GPU Power:\s+([\d.]+)\s*mW")
    return mw / 1000.0 if mw is not None else None


def _macos_cpu_util() -> float | None:
    """Whole-system CPU usage percent from ``top``.

    ``top -l 1 -n 0`` prints one sample and exits. The first ``CPU usage:``
    line has ``user``, ``sys``, ``idle`` percentages.
    """
    output = _run(["top", "-l", "1", "-n", "0"], timeout=2.0)
    user = _first_float(output, r"CPU usage:\s+([\d.]+)% user")
    sysv = _first_float(output, r"CPU usage:\s+[\d.]+% user,\s+([\d.]+)% sys")
    if user is None or sysv is None:
        return None
    return user + sysv


def _macos_ram() -> tuple[float, float]:
    """Returns ``(used_gb, total_gb)`` from ``vm_stat`` and ``sysctl``."""
    total_gb: float | None = _first_float(
        _run(["sysctl", "-n", "hw.memsize"]), r"([\d.]+)"
    )
    if total_gb is None:
        return (float("nan"), float("nan"))
    total_gb /= 1024 ** 3
    output = _run(["vm_stat"])
    free = _first_float(output, r"Pages free:\s+([\d.]+)")
    active = _first_float(output, r"Pages active:\s+([\d.]+)")
    inactive = _first_float(output, r"Pages inactive:\s+([\d.]+)")
    speculative = _first_float(output, r"Pages speculative:\s+([\d.]+)")
    wired = _first_float(output, r"Pages wired down:\s+([\d.]+)")
    compressor = _first_float(output, r"Pages occupied by compressor:\s+([\d.]+)")
    if free is None:
        return (float("nan"), total_gb)
    page_size = 16384  # standard on Apple Silicon; ``vm_stat`` always reports this
    used_pages = 0.0
    for value in (active, inactive, speculative, wired, compressor):
        if value is not None:
            used_pages += value
    used_gb = (used_pages * page_size) / (1024 ** 3)
    return (used_gb, total_gb)


def _macos_memory_pressure() -> float | None:
    """Memory pressure percentage from ``memory_pressure``.

    Returns ``None`` on hosts that do not provide the tool (older macOS).
    """
    if not shutil.which("memory_pressure"):
        return None
    output = _run(["memory_pressure", "-Q"], timeout=2.0)
    return _first_float(output, r"System-wide memory free percentage:\s+([\d.]+)")


# ---------------------------------------------------------------------------
# Linux readers
# ---------------------------------------------------------------------------


def _linux_nvidia(field: str) -> float | None:
    """Read one field from ``nvidia-smi`` or ``None``."""
    if not shutil.which("nvidia-smi"):
        return None
    output = _run(
        [
            "nvidia-smi",
            f"--query-gpu={field}",
            "--format=csv,noheader,nounits",
        ],
        timeout=2.0,
    )
    return _first_float(output, r"([\d.]+)")


def _linux_cpu_temp() -> float | None:
    """CPU package temperature from ``sensors`` (lm-sensors)."""
    if not shutil.which("sensors"):
        return None
    output = _run(["sensors", "-j"], timeout=2.0)
    return _first_float(output, r'"Package id 0":\s*\{[^}]*"temp1_input":\s*([\d.]+)')


def _linux_cpu_util() -> float | None:
    """Whole-system CPU usage from ``top`` (Linux)."""
    output = _run(["top", "-bn", "1"], timeout=2.0)
    return _first_float(
        output,
        r"%Cpu\(s\):\s+([\d.]+)\s+us,\s+([\d.]+)\s+sy",
    )


def _linux_meminfo() -> tuple[float, float]:
    """Returns ``(used_gb, total_gb)`` from ``/proc/meminfo``."""
    try:
        content = open("/proc/meminfo", encoding="utf-8").read()
    except OSError:
        return (float("nan"), float("nan"))
    total = _first_float(content, r"MemTotal:\s+(\d+)")
    available = _first_float(content, r"MemAvailable:\s+(\d+)")
    if total is None or available is None:
        return (float("nan"), float("nan"))
    used_kb = max(total - available, 0)
    return (used_kb / 1024 ** 2, total / 1024 ** 2)


# ---------------------------------------------------------------------------
# macmon integration (Apple Silicon, no sudo required)
# ---------------------------------------------------------------------------


def _macmon_snapshot() -> HwSnapshot | None:
    """Read one JSON sample from ``macmon pipe``.

    Returns ``None`` when ``macmon`` is missing or the output cannot be
    parsed.  ``macmon`` is the preferred reader on macOS because it
    exposes CPU/GPU temperature, power, and usage without sudo on Apple
    Silicon.

    ``macmon pipe`` is a streaming command (one JSON line per interval);
    we read exactly one line then terminate the process.
    """
    if not shutil.which("macmon"):
        return None
    import json as _json

    try:
        proc = subprocess.Popen(
            ["macmon", "pipe", "-i", "100"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        line = proc.stdout.readline()  # type: ignore[union-attr]
        proc.terminate()
        proc.wait(timeout=2)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if not line:
        return None
    try:
        data = _json.loads(line)
    except (_json.JSONDecodeError, KeyError):
        return None
    temp = data.get("temp", {})
    mem = data.get("memory", {})
    ram_total = mem.get("ram_total", 0) / (1024 ** 3)
    ram_used = mem.get("ram_usage", 0) / (1024 ** 3)
    cpu_temp = temp.get("cpu_temp_avg")
    gpu_temp = temp.get("gpu_temp_avg")
    return HwSnapshot(
        timestamp=time.time(),
        cpu_temp_c=cpu_temp if cpu_temp and cpu_temp > 0 else None,
        gpu_temp_c=gpu_temp if gpu_temp and gpu_temp > 0 else None,
        soc_temp_c=None,
        cpu_util_pct=data.get("cpu_usage_pct"),
        gpu_util_pct=data.get("gpu_scaled_ratio"),
        ram_used_gb=ram_used,
        ram_total_gb=ram_total,
        vram_used_gb=None,  # unified memory on Apple Silicon
        cpu_watt=data.get("cpu_power"),
        gpu_watt=data.get("gpu_power"),
        memory_pressure_pct=None,
    )


# ---------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------


def snapshot() -> HwSnapshot:
    """Return a one-shot hardware snapshot for the current host."""
    system = platform.system()
    now = time.time()
    if system == "Darwin":
        # macmon is preferred: temperature + power without sudo
        mac = _macmon_snapshot()
        if mac is not None:
            # fill in metrics macmon doesn't provide
            pressure = _macos_memory_pressure()
            if pressure is not None:
                pressure = max(0.0, min(100.0, 100.0 - pressure))
            return HwSnapshot(
                timestamp=mac.timestamp,
                cpu_temp_c=mac.cpu_temp_c,
                gpu_temp_c=mac.gpu_temp_c,
                soc_temp_c=mac.soc_temp_c,
                cpu_util_pct=mac.cpu_util_pct,
                gpu_util_pct=mac.gpu_util_pct,
                ram_used_gb=mac.ram_used_gb,
                ram_total_gb=mac.ram_total_gb,
                vram_used_gb=mac.vram_used_gb,
                cpu_watt=mac.cpu_watt,
                gpu_watt=mac.gpu_watt,
                memory_pressure_pct=pressure,
            )
        # fallback to powermetrics / top / vm_stat
        cpu_temp = _macos_cpu_temp()
        gpu_temp = _macos_gpu_temp()
        soc_temp = _macos_soc_temp()
        cpu_util = _macos_cpu_util()
        gpu_util = None  # ``top`` does not expose per-GPU utilisation on macOS
        ram_used, ram_total = _macos_ram()
        vram_used = None  # Apple Silicon uses unified memory; no separate VRAM
        cpu_watt = _macos_cpu_watt()
        gpu_watt = _macos_gpu_watt()
        pressure = _macos_memory_pressure()
        if pressure is not None:
            pressure = max(0.0, min(100.0, 100.0 - pressure))
    elif system == "Linux":
        cpu_temp = _linux_cpu_temp()
        gpu_temp = _linux_nvidia("temperature.gpu")
        soc_temp = None
        cpu_util = _linux_cpu_util()
        gpu_util = _linux_nvidia("utilization.gpu")
        ram_used, ram_total = _linux_meminfo()
        vram_used = _linux_nvidia("memory.used")
        cpu_watt = _linux_nvidia("power.draw") if shutil.which("nvidia-smi") else None
        gpu_watt = cpu_watt
        pressure = None
    else:
        cpu_temp = gpu_temp = soc_temp = None
        cpu_util = gpu_util = None
        ram_used = ram_total = float("nan")
        vram_used = cpu_watt = gpu_watt = pressure = None
    return HwSnapshot(
        timestamp=now,
        cpu_temp_c=cpu_temp,
        gpu_temp_c=gpu_temp,
        soc_temp_c=soc_temp,
        cpu_util_pct=cpu_util,
        gpu_util_pct=gpu_util,
        ram_used_gb=ram_used,
        ram_total_gb=ram_total,
        vram_used_gb=vram_used,
        cpu_watt=cpu_watt,
        gpu_watt=gpu_watt,
        memory_pressure_pct=pressure,
    )


# ---------------------------------------------------------------------------
# Sampler
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class HwSampler:
    """Collect a sequence of :class:`HwSnapshot` over a fixed window.

    The sampler is intentionally synchronous: the run loop of
    :func:`core.pipeline.run_request` is sequential and adding threads
    here would force the tests to deal with races. The caller chooses
    how often to sample by passing ``period_seconds``.
    """

    period_seconds: float = 1.0
    snapshots: list[HwSnapshot] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.period_seconds <= 0.0:
            raise ValueError("period_seconds deve essere positivo")

    def sample(self, seconds: float) -> list[HwSnapshot]:
        """Sample for ``seconds`` and return the collected snapshots.

        The first snapshot is taken immediately; subsequent ones every
        ``period_seconds``. The function never raises; ``None`` fields
        simply remain ``None`` when the host has no sensor.
        """
        if seconds < 0.0:
            raise ValueError("seconds deve essere non negativo")
        self.snapshots = []
        if seconds == 0.0:
            return self.snapshots
        self.snapshots.append(snapshot())
        end = time.time() + seconds
        while True:
            now = time.time()
            if now >= end:
                break
            time.sleep(min(self.period_seconds, end - now))
            self.snapshots.append(snapshot())
        return self.snapshots

    def sample_until(self, stop_event) -> list[HwSnapshot]:
        """Sample until ``stop_event.is_set()`` becomes ``True``.

        Designed for ``threading.Event`` integration: the caller starts
        this method on a background thread, then sets the event when the
        instrumented operation completes. The first snapshot is taken
        immediately; subsequent ones every ``period_seconds`` until the
        event fires. ``None`` event handling degrades to a single sample.
        """
        self.snapshots = []
        if stop_event is None:
            self.snapshots.append(snapshot())
            return self.snapshots
        self.snapshots.append(snapshot())
        while not stop_event.is_set():
            if stop_event.wait(self.period_seconds):
                break
            self.snapshots.append(snapshot())
        return self.snapshots


# ---------------------------------------------------------------------------
# Re-export for tooling
# ---------------------------------------------------------------------------


if sys.platform == "darwin":  # pragma: no cover - module attribute
    system = "macos"
elif sys.platform.startswith("linux"):  # pragma: no cover - module attribute
    system = "linux"
else:  # pragma: no cover - module attribute
    system = "unsupported"
