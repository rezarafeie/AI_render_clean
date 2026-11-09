"""Bounded render subprocess supervision; no LLM or provider credentials in child env.

Cloud rollout requires Linux container isolation in addition to this supervisor.
Linux /proc traversal catches nested FFmpeg/Chrome processes even when an engine
starts its own process session. The Pod remains single-job and disposable.
"""
from __future__ import annotations

import json
import os
import queue
import signal
import subprocess
import tempfile
import sys
import threading
import time
from pathlib import Path

from .isolation import isolated_command
from . import offline_guest, socketless


def child_environment(source=None):
    source = os.environ if source is None else source
    allowed = {'PATH', 'HOME', 'TMPDIR', 'PYTHONPATH', 'LANG', 'LC_ALL',
               'REMOTION_BROWSER_EXECUTABLE', 'REMOTION_CONCURRENCY', 'REMOTION_LOOK',
               'TSCAPS_CHROME', 'HYPERFRAMES_BROWSER_PATH', 'HYPERFRAMES_WORKERS'}
    return {**{key: value for key, value in source.items() if key in allowed},
            'PYTHONUNBUFFERED': '1', 'EDITOR_RENDER_CHILD': '1'}


def descendants(root, proc_root=Path('/proc')):
    parents = {}
    if proc_root.is_dir():
        for directory in proc_root.iterdir():
            if not directory.name.isdigit():
                continue
            try:
                data = (directory / 'stat').read_text()
                # Process names may contain spaces or parentheses.
                fields = data[data.rfind(')') + 2:].split()
                parents[int(directory.name)] = int(fields[1])
            except (OSError, ValueError, IndexError):
                continue
    found, pending = [], [root]
    while pending:
        parent = pending.pop()
        children = [pid for pid, ppid in parents.items() if ppid == parent and pid not in found]
        found.extend(children)
        pending.extend(children)
    return found


def process_identity(pid):
    """Linux start-time prevents a delayed SIGKILL from targeting a recycled PID."""
    try:
        data = (Path('/proc') / str(pid) / 'stat').read_text()
        return data[data.rfind(')') + 2:].split()[19]
    except (OSError, IndexError):
        return None


def terminate(process, *, grace=2):
    children = [(pid, process_identity(pid)) for pid in descendants(process.pid)]
    # Kill the private process group too (fallback on macOS, where /proc is absent).
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    for pid, identity in reversed(children):
        if identity is None or process_identity(pid) != identity:
            continue
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=grace)
    except subprocess.TimeoutExpired:
        pass
    for pid, identity in reversed(children):
        if identity is None or process_identity(pid) != identity:
            continue
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    if process.poll() is None:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    process.wait(timeout=5)


def _stderr_tail(handle, limit=2048):
    try:
        size = handle.seek(0, 2)
        handle.seek(max(0, size - limit))
        text = handle.read().decode('utf-8', 'replace')
    except Exception:
        return ''
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    last = lines[-1] if lines else ''
    # A HyperFrames check finding names the scene and how to fix it: keep it whole so the author can repair that scene.
    if 'HyperFramesError' in last:
        return last[-2300:]
    # ffmpeg ends with a bare 'Conversion failed!': the line before it says why.
    return ' | '.join(lines[-3:])[-300:]


def run(spec, workspace: Path, *, on_progress=None, should_cancel=None, isolate_network=False):
    # Manifest contains identity/references but no signed URLs or API credentials.
    manifest = workspace / '.worker-manifest.json'
    with manifest.open('x') as target:
        json.dump(spec.model_dump(), target)
    os.chmod(manifest, 0o600)
    try:
        command = [sys.executable, '-m', 'app.render_cloud.worker',
                   '--manifest', str(manifest), '--workspace', str(workspace)]
        env = child_environment()
        if isolate_network:
            socketless.protect_supervisor()
            if spec.engine in socketless.ENGINES:
                command = [sys.executable, '-m', 'app.render_cloud.socketless', '--', *command]
            else:
                from . import native_loopback
                if native_loopback.available():
                    command = [sys.executable, '-m', 'app.render_cloud.native_loopback', *command]
                elif offline_guest.available():
                    command = [sys.executable, '-m', 'app.render_cloud.socketless', '--',
                               sys.executable, '-m', 'app.render_cloud.offline_guest', str(workspace)]
                else:
                    command = isolated_command(command)
                    env['EDITOR_RENDER_ISOLATED'] = '1'
        errlog = tempfile.TemporaryFile()           # only its scrubbed tail is ever reported
        process = subprocess.Popen(command,
                                   env=env, start_new_session=True,
                                   stdout=subprocess.PIPE, stderr=errlog, text=True)
    except BaseException:
        manifest.unlink(missing_ok=True)
        raise
    reports = queue.Queue(maxsize=32)

    def drain():
        # Never buffer complete untrusted Chromium/FFmpeg logs in RAM.
        while True:
            line = process.stdout.readline(2048)
            if not line:
                break
            try:
                event = json.loads(line)
                value = event.get('progress')
                if event.get('state') == 'rendering' and isinstance(value, (int, float)) and 0 <= value <= 100:
                    reports.put_nowait(value)
            except (ValueError, TypeError, AttributeError, queue.Full):
                continue

    reader = threading.Thread(target=drain, daemon=True)
    reader.start()
    deadline = time.monotonic() + spec.timeout_seconds
    try:
        while process.poll() is None:
            if should_cancel and should_cancel():
                raise InterruptedError('Render cancelled')
            if time.monotonic() >= deadline:
                raise TimeoutError('Render wall-time exceeded')
            try:
                progress = reports.get(timeout=.1)
            except queue.Empty:
                continue
            if on_progress:
                on_progress(progress)
        if process.returncode:
            raise RuntimeError('Render child failed: ' + _stderr_tail(errlog))
        output = workspace / spec.output
        if (output.is_symlink() or not output.resolve().is_relative_to(workspace.resolve())
                or not output.is_file() or not output.stat().st_size):
            raise RuntimeError('Render output missing')
        return output
    finally:
        terminate(process)
        reader.join(timeout=2)
        process.stdout.close()
        manifest.unlink(missing_ok=True)
