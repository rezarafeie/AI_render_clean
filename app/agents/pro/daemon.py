"""The agent worker's main loop: take the next queued Pro run from the app and run it. `python -m app.agents.pro.daemon`

The container holds only PRO_WORKER_SECRET (to claim runs) and, per run, its short-lived run token. One run at a time per process (PRO_CONCURRENCY
processes may run side by side)."""
from __future__ import annotations

import asyncio
import logging
import os

import httpx

from app.agents.pro.runner import APP, run

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("pro.daemon")


async def main() -> None:
    secret = os.environ["PRO_WORKER_SECRET"]
    async with httpx.AsyncClient(base_url=APP, timeout=60) as client:
        while True:
            try:
                r = await client.post("/internal/pro/claim", headers={"x-pro-worker": secret})
                job = r.json() if r.status_code == 200 else {}
            except Exception as exc:
                log.warning("claim failed: %s", str(exc)[:200])
                job = {}
            if job.get("run"):
                log.info("run %s (chat %s) started", job["run"], job["cid"])
                try:
                    await run(job)
                except Exception:
                    log.exception("run %s crashed", job["run"])
                log.info("run %s ended", job["run"])
                continue
            await asyncio.sleep(3)


if __name__ == "__main__":
    asyncio.run(main())
