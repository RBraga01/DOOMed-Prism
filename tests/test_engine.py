"""Tests for supervising the external Crispy Doom process."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys

import pytest


TESTS_DIRECTORY = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS_DIRECTORY))
sys.path.insert(0, str(TESTS_DIRECTORY.parent / "src"))

from fakes.fake_doom import FakePopenFactory
from pewpew.cli import main
from pewpew.config import RuntimeConfig
from pewpew.engine import DoomProcess, EngineAlreadyRunning


def _runtime_config(tmp_path: Path) -> RuntimeConfig:
    crispy_exe = tmp_path / "crispy-doom"
    iwad = tmp_path / "freedoom1.wad"
    crispy_exe.touch()
    iwad.touch()
    return RuntimeConfig(crispy_exe=crispy_exe, iwad=iwad)


def test_start_launches_configured_windowed_engine_once_and_returns_its_pid(
    tmp_path: Path,
) -> None:
    """Catches a missing launch or an incorrect Crispy Doom command line."""
    config = _runtime_config(tmp_path)
    factory = FakePopenFactory()

    pid = DoomProcess(config, popen_factory=factory).start()

    assert pid == factory.processes[0].pid
    assert len(factory.processes) == 1
    assert factory.processes[0].arguments == [
        str(config.crispy_exe),
        "-iwad",
        str(config.iwad),
        "-window",
        "-width",
        "640",
        "-height",
        "480",
    ]


def test_start_rejects_a_second_launch_while_child_is_running(tmp_path: Path) -> None:
    """Catches accidental duplicate engine processes while the first is live."""
    factory = FakePopenFactory()
    process = DoomProcess(_runtime_config(tmp_path), popen_factory=factory)
    process.start()

    with pytest.raises(EngineAlreadyRunning):
        process.start()

    assert len(factory.processes) == 1


def test_poll_forwards_child_lifecycle_state(tmp_path: Path) -> None:
    """Catches status reporting that ignores the supervised child process."""
    factory = FakePopenFactory()
    process = DoomProcess(_runtime_config(tmp_path), popen_factory=factory)

    assert process.poll() is None
    process.start()
    assert process.poll() is None
    factory.processes[0].returncode = 17
    assert process.poll() == 17


def test_stop_requests_graceful_close_and_waits_before_hard_termination(
    tmp_path: Path,
) -> None:
    """Catches Windows shutdown treating hard process termination as graceful."""
    factory = FakePopenFactory()
    close_requests: list[int] = []

    def close_window(pid: int) -> None:
        close_requests.append(pid)
        factory.processes[0].returncode = 0

    process = DoomProcess(
        _runtime_config(tmp_path),
        popen_factory=factory,
        graceful_close=close_window,
    )
    process.start()

    process.stop(timeout_s=1.25)

    child = factory.processes[0]
    assert close_requests == [child.pid]
    assert child.terminate_calls == 0
    assert child.wait_timeouts == [1.25]
    assert child.kill_calls == 0


def test_stop_hard_terminates_then_uses_a_bounded_final_wait(
    tmp_path: Path,
) -> None:
    """Catches an unbounded final wait or forceful shutdown before WM_CLOSE times out."""
    factory = FakePopenFactory()
    close_requests: list[int] = []
    process = DoomProcess(
        _runtime_config(tmp_path),
        popen_factory=factory,
        graceful_close=close_requests.append,
    )
    process.start()
    child = factory.processes[0]
    child.wait_timeouts_remaining = 1

    process.stop(timeout_s=0.5)

    assert close_requests == [child.pid]
    assert child.terminate_calls == 1
    assert child.wait_timeouts == [0.5, 0.5]
    assert child.kill_calls == 0


def test_stop_hard_terminates_and_waits_when_graceful_close_raises(
    tmp_path: Path,
) -> None:
    """Catches a close-request error bypassing bounded child cleanup."""
    factory = FakePopenFactory()

    def failed_close(_pid: int) -> None:
        raise OSError("injected close-request failure")

    process = DoomProcess(
        _runtime_config(tmp_path),
        popen_factory=factory,
        graceful_close=failed_close,
    )
    process.start()

    process.stop(timeout_s=0.25)

    child = factory.processes[0]
    assert child.terminate_calls == 1
    assert child.wait_timeouts == [0.25]
    assert child.poll() == 0


def test_stop_retains_live_process_after_failed_final_wait_for_retry(
    tmp_path: Path,
) -> None:
    """Catches shutdown discarding supervision state while the child remains live."""
    factory = FakePopenFactory()
    close_requests: list[int] = []

    def close_window(pid: int) -> None:
        close_requests.append(pid)
        if len(close_requests) == 2:
            factory.processes[0].returncode = 0

    process = DoomProcess(
        _runtime_config(tmp_path),
        popen_factory=factory,
        graceful_close=close_window,
    )
    process.start()
    child = factory.processes[0]
    child.wait_timeouts_remaining = 2
    child.terminate_exits = False

    with pytest.raises(subprocess.TimeoutExpired):
        process.stop(timeout_s=0.1)

    with pytest.raises(EngineAlreadyRunning):
        process.start()

    process.stop(timeout_s=0.1)
    process.start()

    assert close_requests == [child.pid, child.pid]
    assert len(factory.processes) == 2


def test_stop_is_idempotent_after_child_shutdown(tmp_path: Path) -> None:
    """Catches a repeated stop request sending duplicate lifecycle signals."""
    factory = FakePopenFactory()
    close_requests: list[int] = []

    def close_window(pid: int) -> None:
        close_requests.append(pid)
        factory.processes[0].returncode = 0

    process = DoomProcess(
        _runtime_config(tmp_path),
        popen_factory=factory,
        graceful_close=close_window,
    )
    process.start()

    process.stop()
    process.stop()

    child = factory.processes[0]
    assert close_requests == [child.pid]
    assert child.terminate_calls == 0
    assert child.wait_timeouts == [3.0]


def test_context_manager_stops_child_when_block_exits_with_an_error(tmp_path: Path) -> None:
    """Catches an orphan child when a caller leaves the context exceptionally."""
    factory = FakePopenFactory()

    with pytest.raises(RuntimeError, match="fail"):
        with DoomProcess(
            _runtime_config(tmp_path),
            popen_factory=factory,
            graceful_close=lambda pid: factory.processes[0].terminate(),
        ) as process:
            process.start()
            raise RuntimeError("fail")

    assert factory.processes[0].terminate_calls == 1


def test_validate_reports_configured_path_types_without_exposing_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Catches diagnostic output that leaks local runtime paths or omits validity."""
    config = _runtime_config(tmp_path)
    monkeypatch.setenv("DOOMED_PRISM_CRISPY_EXE", str(config.crispy_exe))
    monkeypatch.setenv("DOOMED_PRISM_IWAD", str(config.iwad))

    status = main(["validate"])

    captured = capsys.readouterr()
    assert status == 0
    assert "crispy_exe: file (valid)" in captured.out
    assert "iwad: .wad file (valid)" in captured.out
    assert str(config.crispy_exe) not in captured.out
    assert str(config.iwad) not in captured.out
    assert captured.err == ""


def test_validate_reports_named_configuration_errors_without_paths(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Catches invalid-local-configuration diagnostics that hide the error type."""
    monkeypatch.delenv("DOOMED_PRISM_CRISPY_EXE", raising=False)
    monkeypatch.delenv("DOOMED_PRISM_IWAD", raising=False)

    status = main(["validate"])

    captured = capsys.readouterr()
    assert status == 2
    assert "ConfigurationError: DOOMED_PRISM_CRISPY_EXE is required" in captured.err
    assert captured.out == ""


def test_run_desktop_validates_configuration_before_loading_the_optional_host(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Catches Raven loading before local runtime configuration is validated."""
    monkeypatch.delenv("DOOMED_PRISM_CRISPY_EXE", raising=False)
    monkeypatch.delenv("DOOMED_PRISM_IWAD", raising=False)

    status = main(["run-desktop"])

    captured = capsys.readouterr()
    assert status == 2
    assert captured.out == ""
    assert captured.err == "ConfigurationError: DOOMED_PRISM_CRISPY_EXE is required\n"


def test_start_passes_a_unique_frame_segment_name_through_the_child_environment(
    tmp_path: Path,
) -> None:
    """Catches a missing or non-unique DOOMED_PRISM_FB_NAME for the export patch."""
    factory = FakePopenFactory()
    engine = DoomProcess(_runtime_config(tmp_path), popen_factory=factory)

    engine.start()

    name = engine.frame_segment_name
    assert name is not None and name.startswith("doomed-prism-fb-")
    assert factory.processes[0].env["DOOMED_PRISM_FB_NAME"] == name

    other = DoomProcess(_runtime_config(tmp_path), popen_factory=FakePopenFactory())
    other.start()
    assert other.frame_segment_name != name


def test_stop_clears_the_segment_name_after_the_child_exits(tmp_path: Path) -> None:
    """Catches a stale segment name lingering after shutdown."""
    factory = FakePopenFactory()

    def close_window(pid: int) -> None:
        factory.processes[0].returncode = 0

    engine = DoomProcess(
        _runtime_config(tmp_path), popen_factory=factory, graceful_close=close_window
    )
    engine.start()
    engine.stop()

    assert engine.frame_segment_name is None
