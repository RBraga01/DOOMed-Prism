"""Pure tests for the input-source protocol stubs (no Qt)."""

from __future__ import annotations

import pytest

from pewpew.input.source import InputSample, PrismInputSource


def test_prism_source_is_a_documented_stub() -> None:
    with pytest.raises(NotImplementedError, match="hardware phase"):
        PrismInputSource().sample(0.0)


def test_input_sample_fields() -> None:
    s = InputSample(
        gaze_xy=(1, 2), activation_edge=True, pause_edge=False, debug_fire_edge=False
    )
    assert s.gaze_xy == (1, 2) and s.activation_edge is True
