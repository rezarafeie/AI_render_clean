"""A long quiet model call keeps the step alive: its line shows the minutes passed."""
import time

from creative import claude_talking as ct


def test_a_slow_call_updates_the_step_with_the_time_passed():
    seen = []
    result = ct._waiting(lambda percent, text: seen.append((percent, text)), 18, "دارم برنامه‌ریزی می‌کنم", lambda: (time.sleep(0.35), "plan")[1], every=0.1)
    assert result == "plan"
    assert len(seen) >= 2 and all(p == 18 and t.startswith("دارم برنامه‌ریزی می‌کنم… (0:0") for p, t in seen)


def test_a_fast_call_adds_nothing_and_an_error_still_stops_the_beat():
    seen = []
    assert ct._waiting(lambda *a: seen.append(a), 18, "x", lambda: 7, every=0.05) == 7 and seen == []
    try:
        ct._waiting(lambda *a: seen.append(a), 18, "x", lambda: (_ for _ in ()).throw(ValueError("boom")), every=0.05)
    except ValueError:
        pass
    count = len(seen)
    time.sleep(0.2)
    assert len(seen) == count
