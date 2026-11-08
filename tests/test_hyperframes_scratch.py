"""A cloud worker can write only inside the project's folder: the scratch folders then live inside it (hidden), elsewhere they stay beside the project."""
import os
import stat

import pytest

from engine.hyperframes.scratch import scratch_dir


def test_scratch_is_beside_the_project_when_the_parent_is_writable(tmp_path):
    project = tmp_path / "hyperframes"; project.mkdir()
    assert scratch_dir(project, "hyperframes_panel") == tmp_path / "hyperframes_panel"


def test_an_existing_sibling_keeps_its_place_so_local_caches_survive(tmp_path):
    project = tmp_path / "hyperframes"; project.mkdir()
    (tmp_path / "hyperframes_panel").mkdir()
    assert scratch_dir(project, "hyperframes_panel") == tmp_path / "hyperframes_panel"


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores directory permissions")
def test_a_read_only_parent_puts_the_scratch_folder_inside_the_project(tmp_path):
    parent = tmp_path / "workspace-parent"; parent.mkdir()
    project = parent / "ws"; project.mkdir()
    parent.chmod(stat.S_IRUSR | stat.S_IXUSR)
    try:
        folder = scratch_dir(project, "hyperframes_sparse")
        assert folder == project / ".hyperframes-sparse"
        folder.mkdir()                                     # writable: it is inside the project
    finally:
        parent.chmod(stat.S_IRWXU)


def test_the_project_snapshot_skips_the_hidden_scratch_folder():
    from app.render_cloud import service
    import inspect
    assert "startswith('.')" in inspect.getsource(service._render_prepared)         # names starting with a dot are never shipped
