from pathlib import Path

import pytest
from engine.hyperframes.cli import cli_command


def test_missing_runtime_has_actionable_error(monkeypatch, tmp_path):
    monkeypatch.setattr('engine.hyperframes.cli.shutil.which', lambda _: None)
    monkeypatch.setattr(Path, 'home', lambda: tmp_path)
    monkeypatch.setenv('HYPERFRAMES_CLI', str(tmp_path/'missing'))
    with pytest.raises(RuntimeError, match='rough cut has been preserved'):
        cli_command()


def test_preinstalled_cli_does_not_use_npx(monkeypatch, tmp_path):
    cli = tmp_path/'hyperframes.mjs'
    cli.touch()
    monkeypatch.setenv('HYPERFRAMES_CLI', str(cli))
    monkeypatch.setattr('engine.hyperframes.cli.shutil.which', lambda name: '/bin/node' if name == 'node' else None)
    assert cli_command() == ['/bin/node', str(cli)]


def test_development_npx_is_pinned(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, 'home', lambda: tmp_path)
    monkeypatch.setenv('HYPERFRAMES_CLI', str(tmp_path/'missing'))
    monkeypatch.setattr('engine.hyperframes.cli.shutil.which', lambda name: '/bin/npx' if name == 'npx' else None)
    assert cli_command() == ['/bin/npx', '--yes', 'hyperframes@0.8.161']


def test_check_batches_cover_each_visual_and_ending(tmp_path):
    import json
    from engine.hyperframes.renderer import check_batches
    (tmp_path/'meta.json').write_text(json.dumps({'duration': 120, 'visual_library': [
        {'start': n, 'end': n+2} for n in (20, 25, 46, 91, 96)]}))
    batches = check_batches(tmp_path)
    windows = [tuple(float(t) for t in batch[1].split(',')) for batch in batches]
    assert all(any(start <= t <= end for start, end in windows) for t in [.5,21,26,47,92,97,119.75])
    assert all(0 < end-start <= 4 for start, end in windows)
    assert all('--no-contrast' not in batch for batch in batches)


def test_quality_receipt_invalidates_when_composition_or_asset_changes(tmp_path):
    from engine.hyperframes.renderer import audit_key
    (tmp_path/'index.html').write_text('first')
    (tmp_path/'assets').mkdir()
    image=tmp_path/'assets/image.png'
    image.write_bytes(b'first image')
    initial=audit_key(tmp_path)
    assert audit_key(tmp_path)==initial
    image.write_bytes(b'a different image')
    changed=audit_key(tmp_path)
    assert changed!=initial
    (tmp_path/'index.html').write_text('second')
    assert audit_key(tmp_path)!=changed
