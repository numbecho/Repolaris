"""Extensible Research Algorithm & Biomarker Plugin Registry for Repolaris.

Provides a thread-safe, fault-isolated hook architecture allowing clinical researchers
to register custom QRS detectors, T-end delineators, and post-pipeline beat/study
biomarkers without modifying core Repolaris source files.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

QRSDetectorHook = Callable[[np.ndarray, float], np.ndarray]
TEndDelineatorHook = Callable[[np.ndarray, int, float], int]
BiomarkerHook = Callable[[np.ndarray, float, list[dict[str, Any]], dict[str, Any]], dict[str, Any]]


class PluginRegistry:
    """Thread-safe registry for custom QRS detectors, T-end delineators, and biomarker hooks."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._qrs_detectors: dict[str, QRSDetectorHook] = {}
        self._t_end_delineators: dict[str, TEndDelineatorHook] = {}
        self._biomarkers: dict[str, BiomarkerHook] = {}

    def register_qrs_detector(self, name: str, fn: QRSDetectorHook) -> QRSDetectorHook:
        """Registers a custom QRS detector function `(signal, fs) -> r_peaks_array`."""
        key = name.strip().lower()
        if not key:
            raise ValueError("Plugin name cannot be empty.")
        with self._lock:
            self._qrs_detectors[key] = fn
        return fn

    def register_t_end_delineator(self, name: str, fn: TEndDelineatorHook) -> TEndDelineatorHook:
        """Registers a custom T-end delineator function `(signal, r_peak, fs) -> t_end_sample`."""
        key = name.strip().lower()
        if not key:
            raise ValueError("Plugin name cannot be empty.")
        with self._lock:
            self._t_end_delineators[key] = fn
        return fn

    def register_biomarker(self, name: str, fn: BiomarkerHook) -> BiomarkerHook:
        """Registers a custom study/beat biomarker hook `(signal, fs, beats, summary) -> dict`."""
        key = name.strip().lower()
        if not key:
            raise ValueError("Plugin name cannot be empty.")
        with self._lock:
            self._biomarkers[key] = fn
        return fn

    def unregister_biomarker(self, name: str) -> bool:
        """Removes a registered biomarker hook by name."""
        key = name.strip().lower()
        with self._lock:
            return self._biomarkers.pop(key, None) is not None

    def clear_all(self) -> None:
        """Clears all custom registered plugins while preserving built-in delineators."""
        with self._lock:
            self._qrs_detectors.clear()
            self._t_end_delineators.clear()
            self._biomarkers.clear()
            self._t_end_delineators["phasor"] = _phasor_t_end_plugin

    def get_qrs_detector(self, name: str) -> QRSDetectorHook | None:
        with self._lock:
            return self._qrs_detectors.get(name.strip().lower())

    def get_t_end_delineator(self, name: str) -> TEndDelineatorHook | None:
        with self._lock:
            return self._t_end_delineators.get(name.strip().lower())

    def list_plugins(self) -> dict[str, list[str]]:
        """Returns a dictionary listing all registered plugin names by category."""
        with self._lock:
            return {
                "qrs_detectors": sorted(self._qrs_detectors.keys()),
                "t_end_delineators": sorted(self._t_end_delineators.keys()),
                "biomarkers": sorted(self._biomarkers.keys()),
            }

    def execute_biomarkers(
        self,
        signal: np.ndarray,
        fs: float,
        beats: list[dict[str, Any]],
        summary: dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        """Executes all registered biomarker plugins with strict fault isolation."""
        with self._lock:
            items = list(self._biomarkers.items())

        results: dict[str, dict[str, Any]] = {}
        for name, hook in items:
            try:
                out = hook(signal, float(fs), beats, summary)
                if isinstance(out, dict):
                    results[name] = {"status": "OK", **out}
                else:
                    results[name] = {"status": "OK", "value": out}
            except Exception as exc:
                logger.warning("Custom biomarker plugin %r raised an exception: %s", name, exc)
                results[name] = {
                    "status": "PLUGIN_ERROR",
                    "error": str(exc),
                }
        return results


GLOBAL_PLUGIN_REGISTRY = PluginRegistry()


def register_qrs_detector(name: str) -> Callable[[QRSDetectorHook], QRSDetectorHook]:
    """Decorator to register a custom QRS detector in the global plugin registry."""
    def _decorator(fn: QRSDetectorHook) -> QRSDetectorHook:
        return GLOBAL_PLUGIN_REGISTRY.register_qrs_detector(name, fn)
    return _decorator


def register_t_end_delineator(name: str) -> Callable[[TEndDelineatorHook], TEndDelineatorHook]:
    """Decorator to register a custom T-end delineator in the global plugin registry."""
    def _decorator(fn: TEndDelineatorHook) -> TEndDelineatorHook:
        return GLOBAL_PLUGIN_REGISTRY.register_t_end_delineator(name, fn)
    return _decorator


def register_biomarker(name: str) -> Callable[[BiomarkerHook], BiomarkerHook]:
    """Decorator to register a custom post-pipeline biomarker in the global plugin registry."""
    def _decorator(fn: BiomarkerHook) -> BiomarkerHook:
        return GLOBAL_PLUGIN_REGISTRY.register_biomarker(name, fn)
    return _decorator


def get_registered_plugins() -> dict[str, list[str]]:
    """Lists all registered plugins across QRS detectors, T-end delineators, and biomarkers."""
    return GLOBAL_PLUGIN_REGISTRY.list_plugins()


def clear_registered_plugins() -> None:
    """Clears all registered plugins from the global registry."""
    GLOBAL_PLUGIN_REGISTRY.clear_all()


def _phasor_t_end_plugin(signal: np.ndarray, r_peak: int, fs: float) -> int:
    """Built-in Martínez et al. (2010) Phasor Transform T-end delineator plugin."""
    from repolaris.detection.t_end import detect_t_end

    _, t_end_idx = detect_t_end(signal, r_peak, fs, method="phasor")
    return int(t_end_idx)


GLOBAL_PLUGIN_REGISTRY.register_t_end_delineator("phasor", _phasor_t_end_plugin)
