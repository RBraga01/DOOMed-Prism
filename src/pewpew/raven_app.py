"""Optional Raven Framework entry point, kept outside the testable Qt host."""

from __future__ import annotations

from typing import Any

from pewpew.config import RuntimeConfig
from pewpew.host_widget import DoomHostWidget


def _raven_types() -> tuple[type[Any], Any]:
    """Load the separately installed Raven API only when desktop launch is requested."""
    from core.raven_app import RavenApp
    from core.run_app import RunApp

    return RavenApp, RunApp


def _doomed_prism_app_type() -> type[Any]:
    """Build the Raven subclass after its optional base class is available."""
    RavenApp, _ = _raven_types()

    class DoomedPrismApp(RavenApp):
        """Raven app containing the one fixed-position Doom host widget."""

        def __init__(self, config: RuntimeConfig) -> None:
            super().__init__()
            self.host_widget = DoomHostWidget(config)
            self.add_widget(self.host_widget, 0, 0)

    return DoomedPrismApp


def run_desktop(config: RuntimeConfig) -> None:
    """Run the host through Raven with deliberately empty publication-safe credentials."""
    _, RunApp = _raven_types()
    DoomedPrismApp = _doomed_prism_app_type()
    RunApp.run(lambda: DoomedPrismApp(config), app_id="", app_key="")
