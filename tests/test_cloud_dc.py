import time
from pathlib import Path

from app.render_cloud.ledger import Ledger

DCS = ['EU-CZ-1', 'EU-RO-1', 'US-TX-3']


def make(tmp_path):
    return Ledger(Path(tmp_path) / 'ledger.sqlite')


def test_unknown_data_centers_keep_the_configured_order(tmp_path):
    assert make(tmp_path).dc_order(DCS) == DCS


def test_a_silent_data_center_is_left_out_and_the_next_one_comes_first(tmp_path):
    ledger = make(tmp_path)
    ledger.dc_mark_bad('EU-CZ-1', 600)
    assert ledger.dc_order(DCS) == ['EU-RO-1', 'US-TX-3']


def test_the_data_center_that_worked_last_is_preferred(tmp_path):
    ledger = make(tmp_path)
    ledger.dc_mark_ok('US-TX-3')
    assert ledger.dc_order(DCS)[0] == 'US-TX-3'


def test_a_success_ends_the_cooldown(tmp_path):
    ledger = make(tmp_path)
    ledger.dc_mark_bad('EU-CZ-1', 600)
    ledger.dc_mark_ok('EU-CZ-1')
    assert 'EU-CZ-1' in ledger.dc_order(DCS)


def test_when_every_data_center_is_in_cooldown_the_earliest_to_recover_comes_first(tmp_path):
    ledger = make(tmp_path)
    ledger.dc_mark_bad('EU-RO-1', 100)
    ledger.dc_mark_bad('EU-CZ-1', 300)
    ledger.dc_mark_bad('US-TX-3', 200)
    assert ledger.dc_order(DCS) == ['EU-RO-1', 'US-TX-3', 'EU-CZ-1']


def test_cooldown_expires(tmp_path):
    ledger = make(tmp_path)
    ledger.dc_mark_bad('EU-CZ-1', 0.05)
    time.sleep(0.1)
    assert ledger.dc_order(DCS) == DCS
