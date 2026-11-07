"""Restricted render child; the parent runner owns signed transport.

Mount only a single prepared workspace; no production DB, Redis or provider keys.
Run under an external wall-time/process-group supervisor and network isolation.
"""
import argparse
import json
import os
from pathlib import Path

from .contracts import RenderSpec
from .engines import execute
from .isolation import enable_loopback


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--workspace', type=Path, required=True)
    args = parser.parse_args()
    args.workspace = args.workspace.resolve()
    args.manifest = args.manifest.resolve()
    if os.environ.get('EDITOR_RENDER_ISOLATED') == '1':
        # Only loopback is brought up in the new Linux network namespace.
        # Chromium's local asset server works; no external/metadata network does.
        enable_loopback()
    spec = RenderSpec.model_validate_json(args.manifest.read_text())
    os.chdir(args.workspace)
    result = execute(spec, args.workspace,
                     on_progress=lambda percent: print(json.dumps({'state': 'rendering', 'progress': percent}), flush=True))
    print(json.dumps({'state': 'rendered', 'output': result.name}), flush=True)


if __name__ == '__main__':
    main()
