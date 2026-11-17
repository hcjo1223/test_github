"""Per-mode directories.

live shares ~/.hedge-fund with the aihf CLI/TUI, so funds built in the
terminal show up in the browser and the other way round. demo lives in its
own subdirectory: synthetic records must never sit next to real ones.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from hedge_fund import paths

from app import config

DEMO_SUBDIR = "web-demo"


@dataclass(frozen=True)
class Workspace:
    mode: config.Mode
    root: Path

    @property
    def mandates(self) -> Path:
        return self.root / "mandates"

    @property
    def paper(self) -> Path:
        return self.root / "paper"

    @property
    def research(self) -> Path:
        return self.root / "research"

    @property
    def cache(self) -> Path:
        return self.root / "cache"

    def ensure(self) -> Workspace:
        """Create the directories; a new workspace starts with the example mandate."""
        if not self.mandates.exists():
            self.mandates.mkdir(parents=True)
            shutil.copy(paths.EXAMPLE_MANDATE, self.mandates / "example.yaml")
        self.paper.mkdir(parents=True, exist_ok=True)
        self.research.mkdir(parents=True, exist_ok=True)
        return self


def workspace_for(mode: config.Mode | None = None) -> Workspace:
    mode = mode or config.get_mode()
    root = config.home() / DEMO_SUBDIR if mode == "demo" else config.home()
    return Workspace(mode=mode, root=root).ensure()
