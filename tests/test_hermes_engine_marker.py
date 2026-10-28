from app import studio_orchestrator as o


def test_marker_names_the_engine_and_is_stripped():
    text = "[موتور: اکسپلینر]\nیک ریلز اینستاگرام بساز"
    assert o._engine_marker(text) == "explainer"
    assert o._ENGINE_MARKER.sub("", text, count=1).lstrip().startswith("یک ریلز")
    assert o._engine_marker("[موتور: صحبتی]\nمتن") == "talking"


def test_plain_messages_have_no_marker():
    assert o._engine_marker("یک ریلز اینستاگرام بساز") is None
    assert o._engine_marker("") is None
    assert o._engine_marker("بعدش [موتور: اکسپلینر]") is None
