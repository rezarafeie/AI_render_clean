"""Owned comparison assets and source binding; real render QA is separate."""
import hashlib
import io
import json
import subprocess
from pathlib import Path

from PIL import Image
import pytest
from pydantic import ValidationError
from creative.shotcraft_compare import BeforeAfterNative,canonical_image,stage_images,restore_inputs,validate_assets

ROOT=Path(__file__).resolve().parents[1]


def image_bytes(color='blue',size=(1920,1080),mode='RGB'):
    out=io.BytesIO();Image.new(mode,size,color).save(out,format='PNG');return out.getvalue()


def data(**patch):
    return dict(resource_id='shotcraft:before-after-slider-scrub',caption='دو وضعیت واقعی',before_label='قبل',after_label='بعد',
                before_asset='assets/compare-'+'a'*64+'.png',after_asset='assets/compare-'+'b'*64+'.png',comparison_basis='دو تصویر ارائه‌شدهٔ همان صفحه',locale='fa-IR',**patch)


@pytest.mark.parametrize('patch',[{'before_asset':'/etc/passwd'},{'after_asset':'https://example.com/image.png'},
    {'before_asset':'assets/../secret.png'},{'caption':'<script>'},{'comparison_basis':''},{'before_label':'x\ny'}])
def test_comparison_rejects_unbounded_or_executable_inputs(patch):
    value=data();value.update(patch)
    with pytest.raises(ValidationError):BeforeAfterNative.model_validate(value)


@pytest.mark.parametrize('raw',[b'not an image',image_bytes(size=(200,200)),image_bytes(size=(1920,1200)),image_bytes(color=(0,0,0,0),mode='RGBA')])
def test_unsupported_media_fails_closed(raw):
    with pytest.raises((ValueError,OSError)):canonical_image(raw)


@pytest.mark.parametrize('mode,color,transparent',[('RGB','white',(255,255,255)),('L',255,255)])
def test_png_transparency_without_alpha_is_rejected(mode,color,transparent):
    out=io.BytesIO()
    Image.new(mode,(1920,1080),color).save(out,format='PNG',transparency=transparent)
    with pytest.raises(ValueError,match='Transparent'):canonical_image(out.getvalue())


def test_canonical_pixels_remove_metadata_but_preserve_color_profile():
    from PIL import ImageCms
    profile=ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
    image=Image.new('RGB',(1920,1080),'blue');exif=Image.Exif();exif[270]='private description'
    out=io.BytesIO();image.save(out,format='PNG',exif=exif,icc_profile=profile)
    raw,_=canonical_image(out.getvalue())
    with Image.open(io.BytesIO(raw)) as clean:
        assert not clean.getexif()
        assert set(clean.info)=={'icc_profile'}
        assert clean.info['icc_profile']==profile


def owned_image(tmp_path,name,color):
    root=tmp_path/'attachments';root.mkdir(exist_ok=True)
    aid=name*32;path=root/(aid+'.png');path.write_bytes(image_bytes(color))
    return root,{'kind':'image','id':aid,'path':str(path)}


def test_server_intake_persists_opaque_images_and_retry_restores_them(tmp_path):
    root,first=owned_image(tmp_path,'a','blue');_,second=owned_image(tmp_path,'b','red')
    directory=tmp_path/'job';directory.mkdir()
    rows=stage_images(directory,root,[first,second]);assert len(rows)==2
    assert all(set(row)=={'attachment_id','asset','sha256','width','height'} for row in rows)
    work=directory/'work';restore_inputs(directory,work,rows)
    value=data();value.update(before_asset=rows[0]['asset'],after_asset=rows[1]['asset'])
    paths,digests=validate_assets(work,BeforeAfterNative.model_validate(value))
    assert digests==[r['sha256'] for r in rows] and all(p.is_relative_to(work) for p in paths)
    paths[0].write_bytes(image_bytes('green'))
    with pytest.raises(ValueError,match='integrity'):validate_assets(work,BeforeAfterNative.model_validate(value))
    restore_inputs(directory,work,rows)
    assert validate_assets(work,BeforeAfterNative.model_validate(value))[1]==digests


def test_attachment_path_and_id_must_match_the_owned_conversation(tmp_path):
    root,item=owned_image(tmp_path,'a','blue');directory=tmp_path/'job';directory.mkdir()
    outside=tmp_path/'other';outside.mkdir();foreign=outside/('a'*32+'.png');foreign.write_bytes(image_bytes())
    item['path']=str(foreign)
    with pytest.raises(ValueError,match='not owned'):stage_images(directory,root,[item])
    link=root/('a'*32+'.png');link.unlink();link.symlink_to(foreign);item['path']=str(link)
    with pytest.raises(ValueError,match='not owned'):stage_images(directory,root,[item])


def test_duplicate_states_and_different_dimensions_are_not_a_comparison(tmp_path):
    root,item=owned_image(tmp_path,'a','blue');directory=tmp_path/'job';directory.mkdir()
    rows=stage_images(directory,root,[item,item]);assert len(rows)==1
    work=directory/'work';restore_inputs(directory,work,rows)
    value=data();value.update(before_asset=rows[0]['asset'],after_asset=rows[0]['asset'])
    with pytest.raises(ValueError,match='different supplied states'):validate_assets(work,BeforeAfterNative.model_validate(value))


def test_unqualified_reference_images_are_not_enabled_as_comparison_inputs(tmp_path):
    root,item=owned_image(tmp_path,'a','blue');Path(item['path']).write_bytes(image_bytes(size=(1080,1920)))
    assert stage_images(tmp_path/'job',root,[item])==[]


def test_motion_intake_preserves_private_inputs_across_work_cleanup(monkeypatch,tmp_path):
    from app import motion_graphic as motion
    monkeypatch.setattr(motion,'ROOT',tmp_path/'studio')
    cid='c'*32;owner='owner'
    root=motion.ROOT/owner/cid/'attachments';root.mkdir(parents=True)
    aid='a'*32;source=root/(aid+'.png');source.write_bytes(image_bytes())
    record=motion.create(cid,owner,'Compare the supplied images',attachments=[{'id':aid,'kind':'image','path':str(source)}])
    assert len(record['image_inputs'])==1
    directory=motion.folder(owner,cid,record['id'])
    restored=motion.load(directory)
    assert 'path' not in restored['image_inputs'][0]
    work=directory/'work';restore_inputs(directory,work,restored['image_inputs'])
    import shutil
    shutil.rmtree(work)
    restore_inputs(directory,work,restored['image_inputs'])
    assert (work/restored['image_inputs'][0]['asset']).is_file()


def test_medium_motion_attachment_ids_use_existing_owner_validation(monkeypatch):
    from app.agents.medium import tools
    calls=[]
    async def owned(ids,cid,user):
        calls.append((ids,cid,user))
        if ids==['foreign']:raise KeyError('attachment')
        return [{'id':v,'kind':'image'} for v in ids]
    monkeypatch.setattr(tools.repo,'get_attachments',owned)
    record={'conversation_id':'conversation','user_key':'owner','data':{'request':{'text':'compare images'}}}
    args=tools.validate(record,{'tool':'create_motion_graphic','arguments':{'request':'compare images','attachment_ids':['owned']}})
    assert args.attachment_ids==['owned'] and calls==[(['owned'],'conversation','owner')]
    with pytest.raises(KeyError):tools.validate(record,{'tool':'create_motion_graphic','arguments':{'request':'compare images','attachment_ids':['foreign']}})


def test_medium_execution_forwards_owned_images_without_replacing_original_brief(monkeypatch):
    from app.agents.medium import tools
    from app import studio_orchestrator as shared
    conversation={'state':{}}
    images=[{'id':'a'*32,'kind':'image','path':'server-owned-only'}]
    async def owned(ids,cid,user):
        assert ids==['a'*32] and (cid,user)==('conversation','owner')
        return images
    async def current(cid,user):return conversation
    calls=[]
    def start(cid,user,chat,brief,attachments,style):
        calls.append((brief,attachments));conversation['state']['motion']={'motion_id':'existing-job'}
    monkeypatch.setattr(tools.repo,'get_attachments',owned)
    monkeypatch.setattr(tools.repo,'get_conversation',current)
    monkeypatch.setattr(shared,'_start_motion_graphic',start)
    record={'conversation_id':'conversation','user_key':'owner','data':{'request':{'text':'Original approved source ordering'}}}
    result=tools.execute(record,{'tool':'create_motion_graphic','arguments':{'request':'Compare supplied states','attachment_ids':['a'*32]}})
    assert result['motion_id']=='existing-job'
    assert calls==[('Original approved source ordering\n\nCompare supplied states',images)]


def bind(value,frames=180):
    source=ROOT/'creative/shotcraft_data/demos/data/before-after-slider-scrub/BeforeAfterSliderScrub.tsx'
    script="""const fs=require('fs'),loader=require('./remotion/shotcraft-compare-loader.cjs');
    process.stdout.write(loader.call({getOptions:()=>({spec:JSON.parse(process.argv[1]),width:1920,height:1080,frames:Number(process.argv[2])})},fs.readFileSync(process.argv[3],'utf8')));"""
    return subprocess.run(['node','-e',script,json.dumps(value),str(frames),str(source)],cwd=ROOT,capture_output=True,text=True,timeout=20)


def test_exact_source_binds_two_images_without_fabricating_before():
    source=ROOT/'creative/shotcraft_data/demos/data/before-after-slider-scrub/BeforeAfterSliderScrub.tsx'
    before=hashlib.sha256(source.read_bytes()).hexdigest();result=bind(data());assert result.returncode==0,result.stderr
    for original in ['const T0 = 14','const FLING = 26','const SCRUB = 104','const squish = 1 + Math.min','clipPath: `inset(0 ${W - x}px 0 0)`']:
        assert original in result.stdout
    assert '<Picture index={0}' in result.stdout and '<Picture index={1}' in result.stdout
    assert '<FakeDashboard' not in result.stdout and 'G, FakeDashboard' not in result.stdout
    assert "filter: 'blur(1.6px)" not in result.stdout and 'rgba(196,194,188,0.38)' not in result.stdout
    assert '<Grain opacity=' not in result.stdout
    assert hashlib.sha256(source.read_bytes()).hexdigest()==before
    assert bind(data(),120).returncode!=0


def test_bound_comparison_tsx_transpiles():
    result=bind(data());assert result.returncode==0,result.stderr
    script="""const fs=require('fs'),ts=require('./web/node_modules/typescript');
    const d=ts.transpileModule(fs.readFileSync(0,'utf8'),{fileName:'Comparison.tsx',compilerOptions:{jsx:ts.JsxEmit.React},reportDiagnostics:true}).diagnostics||[];
    const e=d.filter(v=>v.category===ts.DiagnosticCategory.Error);if(e.length){console.error(e);process.exit(1)}"""
    compiled=subprocess.run(['node','-e',script],input=result.stdout,cwd=ROOT,capture_output=True,text=True,timeout=20)
    assert compiled.returncode==0,compiled.stderr


def test_native_cache_revalidates_owned_input_bytes_before_reuse(monkeypatch,tmp_path):
    from creative import shotcraft_native as native
    from engine import remotion_renderer
    root,first=owned_image(tmp_path,'a','blue');_,second=owned_image(tmp_path,'b','red')
    job=tmp_path/'job';job.mkdir();rows=stage_images(job,root,[first,second]);work=job/'work';restore_inputs(job,work,rows)
    value=data();value.update(before_asset=rows[0]['asset'],after_asset=rows[1]['asset']);spec=BeforeAfterNative.model_validate(value)
    calls=[]
    def mocked_render(config,path,**kwargs):calls.append(config);path.write_bytes(b'mocked test output, not actual video')
    monkeypatch.setattr(remotion_renderer,'render',mocked_render)
    monkeypatch.setattr(native,'source_fingerprint',lambda:'test-adapter')
    monkeypatch.setattr(native,'inspect_output',lambda *a:{'mocked':True})
    first=native.materialize(work,spec,'s1-shotcraft',6,'horizontal')
    assert first['input_sha256']==[row['sha256'] for row in rows]
    assert calls[0]['scenes'][0]['supporting_assets']==[row['asset'] for row in rows]
    assert native.materialize(work,spec,'s1-shotcraft',6,'horizontal')==first and len(calls)==1
    (work/spec.before_asset).write_bytes(image_bytes('green'))
    with pytest.raises(ValueError,match='integrity'):native.materialize(work,spec,'s1-shotcraft',6,'horizontal')
    assert len(calls)==1


def test_mismatched_input_geometry_is_rejected(tmp_path):
    root,first=owned_image(tmp_path,'a','blue');_,second=owned_image(tmp_path,'b','red')
    Path(second['path']).write_bytes(image_bytes('red',size=(3840,2160)))
    job=tmp_path/'job';job.mkdir();rows=stage_images(job,root,[first,second]);work=job/'work';restore_inputs(job,work,rows)
    value=data();value.update(before_asset=rows[0]['asset'],after_asset=rows[1]['asset'])
    with pytest.raises(ValueError,match='matching dimensions'):validate_assets(work,BeforeAfterNative.model_validate(value))
