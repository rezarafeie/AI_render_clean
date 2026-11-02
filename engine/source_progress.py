"""Supervised native source conversion; no retries or synthetic progress."""
import selectors
import subprocess
import tempfile
import time


def conversion_metrics(seconds, duration, elapsed, now):
    percent = min(100.0, max(0.0, seconds / max(duration, .001) * 100))
    remaining = (duration - seconds) * elapsed / seconds if seconds > 0 and elapsed >= 10 and percent >= 1 else None
    return {"stage_percent": round(percent, 1), "processed_seconds": round(seconds, 2),
            "duration_seconds": duration, "reported_at": now,
            "stage_eta_at": now + max(0, remaining) if remaining is not None else None}


def convert(command, duration, on_progress=None, *, on_metrics=None, stall_seconds=180, deadline_seconds=None):
    deadline = deadline_seconds or max(600, min(14400, duration * 40))
    with tempfile.TemporaryFile() as errors:
        proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=errors)
        selector = selectors.DefaultSelector()
        selector.register(proc.stdout, selectors.EVENT_READ)
        started = advanced = heartbeat = time.monotonic()
        last_time, percent, buffer = 0, 0, b""
        try:
            while True:
                now = time.monotonic()
                if now - started > deadline or now - advanced > stall_seconds:
                    raise TimeoutError("تبدیل فایل ورودی متوقف شد یا از مهلت مجاز گذشت؛ تلاش مجدد خودکار انجام نشد.")
                if on_progress and now - heartbeat >= 5:
                    on_progress(percent)  # also lets the owner honour Cancel/Pause
                    heartbeat = now
                if selector.select(timeout=1):
                    chunk = proc.stdout.read1(65536)
                    if not chunk:
                        break
                    buffer += chunk
                    lines = buffer.split(b"\n"); buffer = lines.pop()
                    for line in lines:
                        if line.startswith(b"out_time_us="):
                            try: current = int(line.split(b"=", 1)[1])
                            except ValueError: continue
                            if current > last_time:
                                advanced, last_time = time.monotonic(), current
                                percent = min(99, max(0, int(current / 1e6 / max(duration, .001) * 100)))
                                if on_progress: on_progress(percent)
                                if on_metrics:
                                    on_metrics(conversion_metrics(current / 1e6, duration, time.monotonic() - started, time.time()))
                elif proc.poll() is not None:
                    break
            code = proc.wait(timeout=5)
            if code:
                errors.seek(0, 2); size = errors.tell(); errors.seek(max(0, size - 1600))
                raise RuntimeError(f"Source conversion failed (exit {code}): {errors.read().decode(errors='replace')}")
            if on_progress: on_progress(100)
        except BaseException:
            if proc.poll() is None:
                proc.terminate()
                try: proc.wait(timeout=5)
                except subprocess.TimeoutExpired: proc.kill(); proc.wait()
            raise
        finally:
            selector.close()
            proc.stdout.close()
