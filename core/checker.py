"""Gi.Ve Engine - Hardware Checker.

Analyzes RAM/CPU/GPU and recommends Local vs Cloud AI mode.
Outputs both machine-readable JSON and a human-friendly message
intended for non-technical users.

Run directly:
    python core/checker.py
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from typing import Optional


# Conservative thresholds. A low-end laptop should NOT be told it can
# run a 13B model locally.
MIN_RAM_LOCAL_GB = 16
MIN_RAM_LOCAL_LIGHT_GB = 8
MIN_VRAM_LOCAL_GB = 6
MIN_CPU_CORES_LOCAL = 4


@dataclass
class HardwareReport:
    os_name: str
    os_release: str
    cpu_model: str
    cpu_cores_physical: Optional[int]
    cpu_cores_logical: Optional[int]
    ram_total_gb: float
    ram_available_gb: float
    gpu_name: Optional[str]
    gpu_vram_gb: Optional[float]
    recommendation: str           # "local" | "local_light" | "cloud"
    confidence: str               # "high" | "medium" | "low"
    friendly_message: str         # Italian, non-technical


def _detect_ram_gb() -> tuple[float, float]:
    """Return (total_gb, available_gb). 0.0 if unknown."""
    try:
        import psutil  # type: ignore

        vm = psutil.virtual_memory()
        return round(vm.total / 1024 ** 3, 2), round(vm.available / 1024 ** 3, 2)
    except ImportError:
        pass

    meminfo = "/proc/meminfo"
    if os.path.exists(meminfo):
        total_kb = avail_kb = 0
        with open(meminfo, "r", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("MemTotal:"):
                    total_kb = int(line.split()[1])
                elif line.startswith("MemAvailable:"):
                    avail_kb = int(line.split()[1])
        if total_kb:
            return round(total_kb / 1024 ** 2, 2), round(avail_kb / 1024 ** 2, 2)

    return 0.0, 0.0


def _detect_cpu() -> tuple[str, Optional[int], Optional[int]]:
    """Return (model_name, physical_cores, logical_cores)."""
    model = platform.processor() or platform.machine() or "Unknown CPU"

    physical = logical = None
    try:
        import psutil  # type: ignore

        physical = psutil.cpu_count(logical=False)
        logical = psutil.cpu_count(logical=True)
    except ImportError:
        logical = os.cpu_count()

    if sys.platform.startswith("linux") and os.path.exists("/proc/cpuinfo"):
        try:
            with open("/proc/cpuinfo", "r", encoding="utf-8") as fh:
                for line in fh:
                    if line.lower().startswith("model name"):
                        model = line.split(":", 1)[1].strip()
                        break
        except OSError:
            pass

    return model, physical, logical


def _detect_gpu() -> tuple[Optional[str], Optional[float]]:
    """Best-effort GPU + VRAM detection. NVIDIA first, then generic."""
    nvidia_smi = shutil.which("nvidia-smi")
    if nvidia_smi:
        try:
            out = subprocess.check_output(
                [
                    nvidia_smi,
                    "--query-gpu=name,memory.total",
                    "--format=csv,noheader,nounits",
                ],
                stderr=subprocess.DEVNULL,
                timeout=5,
            ).decode("utf-8").strip()
            if out:
                first = out.splitlines()[0]
                name, mem_mib = [p.strip() for p in first.split(",")]
                return name, round(float(mem_mib) / 1024, 2)
        except (subprocess.SubprocessError, ValueError):
            pass

    if sys.platform.startswith("linux") and shutil.which("lspci"):
        try:
            out = subprocess.check_output(
                ["lspci"], stderr=subprocess.DEVNULL, timeout=5
            ).decode("utf-8", errors="ignore")
            for line in out.splitlines():
                lower = line.lower()
                if "vga" in lower or "3d controller" in lower:
                    return line.split(":", 2)[-1].strip(), None
        except subprocess.SubprocessError:
            pass

    return None, None


def _decide(ram_gb: float, vram_gb: Optional[float], cores: Optional[int]) -> tuple[str, str]:
    has_gpu = vram_gb is not None and vram_gb >= MIN_VRAM_LOCAL_GB
    enough_cpu = (cores or 0) >= MIN_CPU_CORES_LOCAL

    if ram_gb >= MIN_RAM_LOCAL_GB and has_gpu and enough_cpu:
        return "local", "high"
    if ram_gb >= MIN_RAM_LOCAL_LIGHT_GB and enough_cpu:
        return "local_light", "medium"
    return "cloud", "high" if ram_gb > 0 else "low"


def _friendly_message(rec: str, ram_gb: float, gpu_name: Optional[str]) -> str:
    gpu_part = f"GPU rilevata: {gpu_name}." if gpu_name else "Nessuna GPU dedicata rilevata."
    if rec == "local":
        return (
            f"Ottime notizie. Il tuo computer ({ram_gb} GB RAM) e' pronto per "
            f"eseguire l'IA in locale. {gpu_part} "
            "Lavorerai veloce, in privato e senza costi cloud."
        )
    if rec == "local_light":
        return (
            f"Il tuo computer ({ram_gb} GB RAM) puo' usare l'IA in locale in "
            f"modalita' leggera. {gpu_part} "
            "Per i lavori piu' complessi useremo il cloud automaticamente."
        )
    return (
        f"Useremo l'IA in cloud per darti la massima qualita' senza appesantire "
        f"il tuo dispositivo ({ram_gb} GB RAM). {gpu_part} "
        "Nessuna configurazione richiesta da parte tua."
    )


def run() -> HardwareReport:
    cpu_model, phys, logi = _detect_cpu()
    ram_total, ram_avail = _detect_ram_gb()
    gpu_name, gpu_vram = _detect_gpu()
    rec, conf = _decide(ram_total, gpu_vram, logi or phys)

    return HardwareReport(
        os_name=platform.system(),
        os_release=platform.release(),
        cpu_model=cpu_model,
        cpu_cores_physical=phys,
        cpu_cores_logical=logi,
        ram_total_gb=ram_total,
        ram_available_gb=ram_avail,
        gpu_name=gpu_name,
        gpu_vram_gb=gpu_vram,
        recommendation=rec,
        confidence=conf,
        friendly_message=_friendly_message(rec, ram_total, gpu_name),
    )


def main() -> int:
    report = run()
    payload = asdict(report)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    print()
    print("=" * 60)
    print("Gi.Ve Engine - Check Hardware")
    print("=" * 60)
    print(report.friendly_message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
