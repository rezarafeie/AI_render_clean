import json
from pathlib import Path
import subprocess

import pytest

from creative import motion_graphic as mg, shotcraft


def test_shotcraft_pinned_references_are_complete_and_hash_verified():
    data = shotcraft.manifest()
    assert len(data['cards']) == 8
    for name in data['sha256']:
        assert shotcraft.read_reference(name)
    for item in shotcraft.catalog():
        text = shotcraft.scene_reference(item['id'])
        assert 'REFERENCE FILE demos/' in text
        assert 'REFERENCE FILE references/shots/' in text
        assert not item['native_execution']


def test_reference_paths_and_resource_ids_are_not_user_controlled():
    with pytest.raises(ValueError):
        shotcraft.read_reference('../../.env')
    with pytest.raises(ValueError):
        shotcraft.scene_reference('shotcraft:../../secret')
    with pytest.raises(ValueError):
        mg.ScenePlan(headline='h', idea='i', start=0, end=5, shotcraft_id='bad')


def test_integrity_failure_is_not_silently_used(tmp_path, monkeypatch):
    (tmp_path/'LICENSE').write_text('tampered')
    monkeypatch.setattr(shotcraft, 'ROOT', tmp_path)
    with pytest.raises(ValueError, match='integrity'):
        shotcraft.read_reference('LICENSE', {'sha256': {'LICENSE': 'incorrect'}})


def test_planning_and_authoring_receive_reference_material_and_design_direction():
    assert 'shotcraft:card-stack' in mg.plan_request('یک اکسپلینر')
    plan = mg.MotionPlan(duration=10, design_direction='One shared editorial grid', scenes=[
        mg.ScenePlan(headline='تمرکز', idea='چند مسیر به یک هدف', start=5, end=10,
                     shotcraft_id='shotcraft:bezier-source-converge-merge')])
    request = mg.scene_request(plan, 1, 'یک اکسپلینر')
    assert 'T = 0' in request and 'One shared editorial grid' in request
    assert 'BezierSourceConvergeMerge.tsx' in request
    page = mg.assemble_scenes(plan, [mg.SceneDraft(html='<p>تمرکز</p>', build_js='HM.rise("#s1 p", .2)', timebase='local')])
    assert 'HM._scene(tl, 5, 5,' in page.build_js
    assert page.public()['resource_receipts'][0]['resource_id'] == 'shotcraft:bezier-source-converge-merge'
    assert page.resource_receipts[0]['source_revision'] == shotcraft.REVISION


def test_approved_handoff_does_not_drop_seventh_scene():
    brief = '\n'.join(f'{n}. (3s) تصویر: مسیر | متن روی صفحه: صحنه {n} | روایت: یک مسیر.' for n in range(1, 8))
    plan = mg.MotionPlan(duration=21)
    adopted = mg.apply_handoff(plan, brief)
    assert len(adopted.scenes) == 7 and adopted.scenes[-1].headline == 'صحنه 7'


def test_approved_seven_scene_plan_is_adopted_before_validation(monkeypatch):
    brief = '\n'.join(f'{n}. (2s) تصویر: مسیر | متن روی صفحه: صحنه {n} | روایت: این یک مسیر برای شروع بهتر است.' for n in range(1, 8))
    calls = []
    def ask(*args, **kwargs):
        calls.append(1)
        return mg.MotionPlan(duration=14, scenes=[mg.ScenePlan(
            headline='نباید جایگزین شود', idea='تصویر', narration='متن دیگر',
            start=i*2, end=(i+1)*2) for i in range(7)])
    monkeypatch.setattr(mg.llm, 'ask', ask)
    result = mg.plan(brief)
    assert len(calls) == 1 and len(result.scenes) == 7
    assert result.scenes[0].headline == 'صحنه 1'
    assert result.scenes[0].narration == 'این یک مسیر برای شروع بهتر است.'
    assert not mg.validate_plan(result, max_scenes=8)
    assert mg.validate_plan(result)  # unapproved generation still has its old limit


def test_local_clock_rejects_double_offset_and_pop_strings_and_rise_reveals_opacity():
    kit = Path(mg.KIT) / 'kit.js'
    script = r'''
const assert=require('node:assert/strict');
const el={nodeType:1,style:{}};
global.window=global; global.document={querySelectorAll:()=>[el]};
eval(require('node:fs').readFileSync(process.argv[1],'utf8'));
let calls=[];
const master={}; for(const method of ['fromTo','from','to','set']) master[method]=(...a)=>{calls.push({method,a});return master;};
HM._bind(master,{width:1080,height:1920,duration:20});
HM._scene(master,6.11,6.85,(tl,T,D)=>{assert.equal(T,0);HM.pop('#a',.26,{from:.8});});
assert.equal(calls[0].a[3],6.37);
assert.throws(()=>HM._scene(master,6.11,6.85,()=>HM.pop('#a',12.37)),/outside local/);
assert.throws(()=>HM._scene(master,6.11,6.85,()=>HM.pop('#a',6.5)),/beyond/);
assert.throws(()=>HM.pop('#a',0,{from:'bottom'}),/numeric scale/);
assert.equal(HM._tl,master);
HM.rise('#a',1); const c=calls.at(-1); assert.equal(c.a[2].opacity,1);
assert.throws(()=>HM._scene(master,0,5,tl=>tl.to('#a',{duration:1,repeat:-1},0)),/bounded/);
assert.throws(()=>HM._scene(master,0,5,tl=>tl.to('#a',{duration:1,repeat:1,repeatDelay:4},0)),/beyond/);
console.log('passed');
'''
    result = subprocess.run(['node', '-e', script, str(kit)], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr


def test_registry_does_not_claim_reference_is_a_native_renderer():
    from creative.resources.registry import get_resource
    row = get_resource('shotcraft:card-stack')
    assert row['integration_status'] == 'port-required'
    assert row['availability'] == 'catalog-only'
