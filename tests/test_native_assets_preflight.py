import hashlib
import json
from pathlib import Path

import pytest

from scripts.check_native_assets import verify


def test_repository_assets_are_complete():
    assert verify(Path(__file__).resolve().parents[1] / "assets/hyperframes_components") == 45


def test_missing_manifest_has_actionable_error(tmp_path):
    with pytest.raises(ValueError, match="Deploy assets/hyperframes_components"):
        verify(tmp_path)


def test_missing_or_modified_source_blocks_deployment(tmp_path):
    expected = hashlib.sha256(b"original").hexdigest()
    (tmp_path / "MANIFEST.json").write_text(json.dumps({"files": {"card": {"sha256": expected}}}))
    with pytest.raises(ValueError, match="card"):
        verify(tmp_path)
    (tmp_path / "card.html").write_text("changed")
    with pytest.raises(ValueError, match="card"):
        verify(tmp_path)
    (tmp_path / "card.html").write_text("original")
    assert verify(tmp_path) == 1
