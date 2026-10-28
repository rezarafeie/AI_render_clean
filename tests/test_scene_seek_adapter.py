"""The removed authored-code adapter is replaced by the owned template timeline."""
import json
import shutil
import subprocess
import pytest
from engine.hyperframes.builder import _timeline_script
from engine.hyperframes.schema import VisualBeat


def test_owned_timeline_is_paused_and_seekable():
    if not shutil.which('node'):
        pytest.skip('Node required')
    code=_timeline_script([VisualBeat(id='a',start=0,end=3,title='۱۲ گام',visual_type='kinetic_type')])
    harness = """const window={}; const calls=[];
    const fakeTimeline={fromTo(...a){calls.push(['fromTo',...a]);return this},to(...a){calls.push(['to',...a]);return this},seek(t){calls.push(['seek',t])}};
    const gsap={timeline(options){if(!options.paused)throw Error('not paused');return fakeTimeline}};
    """
    result=subprocess.run(['node','-e',harness+code+';console.log(JSON.stringify(calls))'],capture_output=True,text=True,check=True)
    calls=json.loads(result.stdout)
    assert calls[-1]==['seek',0]
    assert all(c[3].get('immediateRender') is False for c in calls if c[0]=='fromTo' and c[1]=='#a .beat-inner')
