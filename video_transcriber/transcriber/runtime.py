from __future__ import annotations

import ctypes
import glob
import importlib
import os
import subprocess
import sys


def _module_path(module_name: str) -> str | None:
    try:
        module = importlib.import_module(module_name)
        paths = getattr(module, "__path__", None)
        if not paths:
            return None
        return list(paths)[0]
    except Exception:
        return None


def _ensure_cuda_packages_installed() -> None:
    required = ("nvidia.cublas.lib", "nvidia.cudnn.lib")
    missing = [name for name in required if _module_path(name) is None]
    if not missing:
        return

    subprocess.check_call(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--no-cache-dir",
            "nvidia-cublas-cu12",
            "nvidia-cudnn-cu12==9.*",
        ]
    )


def _prepend_ld_library_path(paths: list[str]) -> None:
    cleaned = [path for path in paths if path]
    if not cleaned:
        return

    current = os.environ.get("LD_LIBRARY_PATH", "")
    merged = ":".join(cleaned + ([current] if current else []))
    os.environ["LD_LIBRARY_PATH"] = merged


def _preload_library(patterns: list[str], base_dir: str) -> None:
    for pattern in patterns:
        matches = sorted(glob.glob(os.path.join(base_dir, pattern)))
        if matches:
            ctypes.CDLL(matches[0], mode=ctypes.RTLD_GLOBAL)
            return


def ensure_cuda_runtime(enabled: bool) -> None:
    if not enabled:
        return

    _ensure_cuda_packages_installed()

    cublas_path = _module_path("nvidia.cublas.lib")
    cudnn_path = _module_path("nvidia.cudnn.lib")
    _prepend_ld_library_path([path for path in (cublas_path, cudnn_path) if path])

    if cublas_path:
        _preload_library(["libcublas.so.12", "libcublas.so*"], cublas_path)
    if cudnn_path:
        _preload_library(["libcudnn.so.9", "libcudnn*.so*"], cudnn_path)
