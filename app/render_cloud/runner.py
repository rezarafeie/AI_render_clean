"""Single-job Pod entrypoint: scoped download -> isolated engine -> scoped upload."""
from __future__ import annotations

import hashlib
import os
import tempfile
import time
from pathlib import Path

from . import supervisor, transfer
from .mailbox import Envelope, Reporter, get_json


def run(envelope: Envelope, hosts, *, report_factory=Reporter,
        download=transfer.download, render=supervisor.run, upload=transfer.upload):
    if envelope.expires_at <= time.time() or envelope.expires_at > time.time() + 21600:
        raise ValueError('Worker bootstrap expired or exceeds maximum lifetime')
    reporter = report_factory(envelope, hosts)
    from .resources import Meter
    meter=Meter()
    reporter.report('preparing')
    try:
        with tempfile.TemporaryDirectory(prefix='editorgpt-render-') as temporary:
            workspace = Path(temporary)
            if reporter.check_cancel():
                raise InterruptedError('Render cancelled')
            reporter.report('downloading')
            download(envelope.spec, envelope.downloads, workspace, hosts,
                     should_cancel=reporter.check_cancel)
            reporter.report('rendering', 0)
            output = render(envelope.spec, workspace, on_progress=reporter.render_progress,
                            should_cancel=reporter.check_cancel, isolate_network=True)
            reporter.report('uploading', 0)
            upload(output, envelope.output_put, hosts, should_cancel=reporter.check_cancel)
            digest = hashlib.sha256()
            with output.open('rb') as source:
                for block in iter(lambda: source.read(1024 * 1024), b''):
                    digest.update(block)
            # Uploaded is NOT completed: the VPS must independently validate and
            # publish its candidate, then delete the dedicated Pod.
            reporter.report('uploading', 100, uploaded=True, sha256=digest.hexdigest(), size=output.stat().st_size,
                            resources=meter.finish())
    except BaseException as error:
        try:
            reporter.report('cancelled' if isinstance(error, InterruptedError) else 'failed')
        except Exception:
            pass  # Independent reaper remains authoritative if reporting fails.
        raise


def main():
    hosts = {v.strip() for v in os.environ.get('RENDER_STORAGE_HOSTS', '').split(',') if v.strip()}
    url = os.environ.pop('EDITOR_RENDER_BOOTSTRAP_URL', '')
    if not hosts or not url:
        raise SystemExit('Scoped worker bootstrap is not configured')
    try:
        envelope = Envelope.model_validate(get_json(url, hosts))
        run(envelope, hosts)
    except BaseException:
        # Never print a traceback containing signed URLs, project copy or tokens.
        raise SystemExit('Render worker failed; inspect scoped execution status') from None


if __name__ == '__main__':
    main()
