"""Tests verifying strict isolation and self-containment of patterns/confidence_band_handler."""

from __future__ import annotations

import ast
from pathlib import Path


def test_pattern_has_zero_slopgate_imports():
    """Verify that patterns/confidence_band_handler does NOT import from slopgate."""
    pattern_root = Path(__file__).resolve().parent.parent / "patterns" / "confidence_band_handler"
    py_files = list(pattern_root.glob("**/*.py"))
    assert len(py_files) >= 3, f"Expected at least 3 python files in pattern root, found {len(py_files)}"

    for py_file in py_files:
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith("slopgate"), (
                        f"Pattern file {py_file.name} illegally imports '{alias.name}'. "
                        "Pattern must remain 100% decoupled from the host application."
                    )
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                assert not module.startswith("slopgate"), (
                    f"Pattern file {py_file.name} illegally imports from '{module}'. "
                    "Pattern must remain 100% decoupled from the host application."
                )


def test_pattern_imports_and_instantiates_cleanly():
    """Verify that pattern classes can be imported and instantiated standalone."""
    import sys

    pattern_dir = Path(__file__).resolve().parent.parent / "patterns" / "confidence_band_handler"
    if str(pattern_dir) not in sys.path:
        sys.path.insert(0, str(pattern_dir))

    from bands import compute_choice_confidence
    from gate import ConfidenceGate
    from handler import AgentContext, ConfidenceBandHandler

    assert compute_choice_confidence([0.9, 0.1]) == 0.8
    gate = ConfidenceGate()
    ctx = AgentContext(identifier="test#1", results=[])
    handler = ConfidenceBandHandler(gate, lambda: ctx)
    assert handler.name == "confidence-band-handler"
