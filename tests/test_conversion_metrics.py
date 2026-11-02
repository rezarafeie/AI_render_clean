from engine.source_progress import conversion_metrics


def test_real_processed_media_time_drives_percentage_and_eta():
    value = conversion_metrics(25, 100, 50, 1000)
    assert value['stage_percent'] == 25
    assert value['stage_eta_at'] == 1150


def test_no_eta_without_enough_observations():
    assert conversion_metrics(0, 100, 50, 1000)['stage_eta_at'] is None
    assert conversion_metrics(5, 100, 2, 1000)['stage_eta_at'] is None


def test_progress_bounded_and_completed_eta_not_negative():
    value = conversion_metrics(101, 100, 50, 1000)
    assert value['stage_percent'] == 100
    assert value['stage_eta_at'] == 1000


def test_reporter_persists_stage_measurements_and_drops_them_on_stage_change(tmp_path, monkeypatch):
    from app import talking_reel, render_stats
    monkeypatch.setattr(render_stats, 'estimate', lambda *args: None)
    progress, stage = talking_reel._render_reporter(tmp_path)
    stage('rendering source preparation', 'convert')
    progress(2)
    progress.metrics(conversion_metrics(25, 100, 50, 1000))
    state = talking_reel.load(tmp_path)
    assert state['render_metrics']['stage_percent'] == 25
    assert 'render_eta_at' not in state['render_metrics']
    stage('rendering shot', 'shot 1')
    assert 'render_metrics' not in talking_reel.load(tmp_path)


def test_whole_render_estimate_requires_real_history(tmp_path, monkeypatch):
    from app import talking_reel, render_stats
    monkeypatch.setattr(render_stats, 'estimate', lambda *args: {'high_s':500, 'samples':3})
    progress, stage = talking_reel._render_reporter(tmp_path)
    stage('rendering source preparation', 'convert')
    progress.metrics(conversion_metrics(25, 100, 50, 1000))
    metrics = talking_reel.load(tmp_path)['render_metrics']
    assert metrics['estimate_samples'] == 3
    assert metrics['render_eta_at'] >= metrics['stage_eta_at']
    stage('rendering shot', 'shot 1')
    metrics = talking_reel.load(tmp_path)['render_metrics']
    assert metrics['render_eta_at'] and 'stage_percent' not in metrics
