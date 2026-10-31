"""Contract/binding tests. These do not certify rendered pixels or enable the adapter."""
import hashlib
import json
import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError
from creative.shotcraft_card_flip import CardFlipNative

ROOT=Path(__file__).resolve().parents[1]


def values():
    return dict(resource_id="shotcraft:card-flip-reveal",caption="سه نتیجهٔ روشن",kicker="نمونهٔ آزمایشی",
        front_label="ویژگی",before_label="قبل",after_label="بعد",locale="fa-IR",cards=[dict(name="برنامه‌ریزی",description="از ایده تا برنامه",
        front_lines=["ایدهٔ روشن","برنامهٔ مشخص","اجرای منظم"],before=20,after=10,unit="دقیقه",
        result_label="زمان نمونه",evidence="دادهٔ مصنوعی فقط برای آزمون") for _ in range(3)])


def bind(data,frames=300,source=None):
    original=ROOT/'creative/shotcraft_data/demos/transition/card-flip-reveal/CardFlipReveal.tsx'
    script="""const fs=require('fs');const loader=require('./remotion/shotcraft-card-loader.cjs');
    process.stdout.write(loader.call({getOptions:()=>({spec:JSON.parse(process.argv[1]),width:1920,height:1080,frames:Number(process.argv[2])})},process.argv[3]||fs.readFileSync(process.argv[4],'utf8')));"""
    return subprocess.run(['node','-e',script,json.dumps(data),str(frames),source or '',str(original)],
        cwd=ROOT,capture_output=True,text=True,timeout=20)


def test_copy_and_numbers_are_explicit_and_vendor_motion_is_unchanged():
    path=ROOT/'creative/shotcraft_data/demos/transition/card-flip-reveal/CardFlipReveal.tsx'
    before=hashlib.sha256(path.read_bytes()).hexdigest()
    spec=CardFlipNative.model_validate(values())
    assert '\u200c' in spec.cards[0].name
    result=bind(spec.model_dump());assert result.returncode==0,result.stderr
    code=result.stdout
    for original in ['perspective: 1600','const FLIP = 16','const PRE = 4','const STAGGER = 12','const PEAK_DEG = 194','damping: 15, stiffness: 190',"transform: 'scaleY(-1)'"]:
        assert original in code
    for demo in ['Make a 30s launch film','With ${BRAND.short}','faster first cut','text="Three features. Three outcomes."']:
        assert demo not in code
    assert '"bars":[1,0.5]' in code and '"value":"۱۰"' in code
    assert before==hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize('change',[{'cards':[]},{'caption':'<script>'},{'kicker':' '},{'arbitrary_code':'run()'}])
def test_invalid_root_contract(change):
    data=values();data.update(change)
    with pytest.raises(ValidationError):CardFlipNative.model_validate(data)


@pytest.mark.parametrize('change',[{'before':float('nan')},{'after':-1},{'evidence':''},{'front_lines':['a']},{'unit':'x\ny'}])
def test_invalid_card_contract(change):
    data=values();data['cards'][0].update(change)
    with pytest.raises(ValidationError):CardFlipNative.model_validate(data)


def test_loader_fails_closed_on_short_hold_and_changed_source():
    short=bind(values(),120)
    assert short.returncode!=0 and 'reading holds' in short.stderr
    changed=bind(values(),300,'const FEATURES=[];')
    assert changed.returncode!=0 and 'Pinned features changed' in changed.stderr


def test_zero_comparison_never_generates_nonfinite_ratios():
    data=values()
    for card in data['cards']:card.update(before=0,after=0)
    result=bind(data);assert result.returncode==0,result.stderr
    assert '"bars":[0,0]' in result.stdout
    assert 'NaN' not in result.stdout and 'Infinity' not in result.stdout


def test_bound_tsx_transpiles_with_installed_typescript():
    result=bind(values());assert result.returncode==0,result.stderr
    check=subprocess.run(['node','-e',"""const ts=require('./web/node_modules/typescript');
      const fs=require('fs');const result=ts.transpileModule(fs.readFileSync(0,'utf8'),{
        compilerOptions:{jsx:ts.JsxEmit.React,target:ts.ScriptTarget.ES2022},reportDiagnostics:true,fileName:'CardFlip.tsx'});
      const errors=(result.diagnostics||[]).filter(d=>d.category===ts.DiagnosticCategory.Error);
      if(errors.length){console.error(errors.map(d=>ts.flattenDiagnosticMessageText(d.messageText,' ')));process.exit(1)}
    """],input=result.stdout,cwd=ROOT,capture_output=True,text=True,timeout=20)
    assert check.returncode==0,check.stderr
