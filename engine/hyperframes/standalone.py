"""Check and render ONE authored page (index.html) with the pinned HyperFrames CLI.

Unlike the Talking Reel path there is no speaker video, no meta.json and no sparse rendering: a motion graphic is a single page, so the
whole page is checked and then rendered. The check's findings are returned as data, split into what must be fixed before rendering
(lint and runtime errors) and what is only worth one attempt (layout and contrast).
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import shutil

from .cli import cli_command
from .renderer import HyperFramesError, _render_cli, summarize_failure


def ensure_browser() -> None:
    """HyperFrames looks for its own headless Chrome; a server that ships Chromium (REMOTION_BROWSER_EXECUTABLE / chromium) is pointed at it."""
    if os.environ.get("HYPERFRAMES_BROWSER_PATH"):
        return
    # chrome-headless-shell in HyperFrames' own cache is the fast capture path (BeginFrame): plain Chromium falls back to screenshots, ~10x slower on a CPU-only server.
    cache = Path.home() / ".cache" / "hyperframes" / "chrome" / "chrome-headless-shell"
    if cache.is_dir() and any(cache.glob("*/chrome-headless-shell-*/chrome-headless-shell")):
        return
    for candidate in (os.environ.get("REMOTION_BROWSER_EXECUTABLE"), shutil.which("chromium"), shutil.which("google-chrome"), shutil.which("chromium-browser")):
        if candidate and Path(candidate).is_file():
            os.environ["HYPERFRAMES_BROWSER_PATH"] = candidate
            return


@dataclass
class CheckResult:
    ran: bool = False
    blocking: list[str] = field(default_factory=list)       # lint / runtime errors: the page cannot be rendered correctly
    quality: list[str] = field(default_factory=list)        # layout / contrast errors: worth one repair, never fatal
    notes: list[str] = field(default_factory=list)          # informational findings and "the check did not run"

    @property
    def clean(self) -> bool:
        return self.ran and not self.blocking and not self.quality


def _findings(report: dict) -> tuple[list[str], list[str], list[str]]:
    """(blocking, quality, notes). Warnings are notes only: they include transient overlaps sampled in the middle of a wipe."""
    blocking, quality, notes = [], [], []
    for section in ("lint", "runtime", "layout", "motion", "contrast"):
        for item in (report.get(section) or {}).get("findings", []):
            severity = item.get("severity")
            if severity not in {"error", "warning"}:
                continue
            line = f"{section}: {item.get('code', 'finding')}: {str(item.get('message', ''))[:240]}"
            if _check_deadline(section, item):
                notes.append(line)
                continue
            if item.get("selector"):
                line += f" [{str(item['selector'])[:80]}]"
            hint = item.get("fixHint") or item.get("fix")
            if hint:
                line += f" Fix: {str(hint)[:200]}"
            if severity == "warning":
                notes.append(line)
            else:
                (blocking if section in {"lint", "runtime"} else quality).append(line)
    return blocking, quality, notes[:6]


def _check_deadline(section: str, item: dict) -> bool:
    # The CLI's own watchdog is not evidence of broken authored code.
    # Do not classify arbitrary JavaScript errors containing 'timeout' this way.
    return (section == "runtime" and item.get("code") == "check_runtime_failure"
            and "check did not finish within its deadline" in str(item.get("message", "")).lower())


def check(project: Path, *, timeout: int = 240, should_cancel: Optional[Callable[[], bool]] = None) -> CheckResult:
    """Run ``hyperframes check``. A check that cannot finish in time is reported as "not run": rendering still validates what matters."""
    ensure_browser()
    started = time.time()
    process = subprocess.Popen([*cli_command(), "check", "."], cwd=project, env={**os.environ, "NO_COLOR": "1"}, text=True,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    deadline = time.monotonic() + timeout
    while True:
        try:
            stdout, stderr = process.communicate(timeout=3)
            break
        except subprocess.TimeoutExpired:
            if (should_cancel and should_cancel()) or time.monotonic() > deadline:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.communicate(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.communicate()
                if should_cancel and should_cancel():
                    raise HyperFramesError("canceled")
                return CheckResult(notes=["the quality check did not finish in time; the render itself still validates the page"])
    result = CheckResult(ran=True)
    reports = sorted((project / ".hyperframes/artifacts/checks").glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if reports and reports[0].stat().st_mtime >= started - 1:
        try:
            report = json.loads(reports[0].read_text())
            result.blocking, result.quality, result.notes = _findings(report)
            if any(_check_deadline("runtime", item) for item in (report.get("runtime") or {}).get("findings", [])):
                result.ran = False
        except (OSError, ValueError, TypeError):
            pass
    if process.returncode and result.ran and not result.blocking and not result.quality:
        result.blocking = [summarize_failure("\n".join(part for part in (stdout, stderr) if part), 700)]
    return result


def render(project: Path, output: Path, *, timeout: int = 900, on_progress: Optional[Callable[[int], None]] = None,
           should_cancel: Optional[Callable[[], bool]] = None) -> Path:
    ensure_browser()
    output.parent.mkdir(parents=True, exist_ok=True)
    return _render_cli(project, output, timeout=timeout, on_progress=on_progress, should_cancel=should_cancel)
