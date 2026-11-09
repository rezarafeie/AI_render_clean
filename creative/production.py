"""Compile the chosen concept into existing engine inputs, not another prompt.

No network calls, file paths supplied by a model, arbitrary tools, or media
generation here. Invalid direction stops before paid production.
"""
from __future__ import annotations

import math

from . import speech
from .schemas import CreativePlan, CreativeUnavailable


def storyboard_from_plan(plan: CreativePlan, *, prompt: str, language: str, style: str,
                         duration: float, asset_indices: set[int], brief: dict | None = None,
                         catalog: list[dict] | None = None):
    from brain.storyboard import Scene, Storyboard
    beats = plan.chosen.beats
    if not 3 <= len(beats) <= 10 or not 10 <= duration <= 90:
        raise CreativeUnavailable('برنامهٔ خلاقانه هنوز صحنه‌های اجرایی کافی یا مدت معتبر ندارد.')
    # Time follows the real length of the spoken line: a scene is never shorter than its narration, and the total speech
    # must fit the video (estimated from Persian letters and pauses, not from a word count). An approved script that is
    # longer than the requested length makes the video longer (up to the 90 s limit) instead of failing the build.
    needs = [speech.speech_seconds(b.narration)*speech.MARGIN if b.narration else 0.0 for b in beats]
    if sum(needs) > duration:
        duration = float(math.ceil(sum(needs) + 1))
        if duration > 90:
            raise CreativeUnavailable(f'نریشن حدود {sum(needs):.1f} ثانیه طول می‌کشد و در بیشینهٔ ۹۰ ثانیه جا نمی‌شود؛ پیش از تولید باید کوتاه شود.')
    frames = round(duration*30)
    weights = [b.duration_weight for b in beats]
    seconds_each = _allocate(duration, weights, [max(n, .5) for n in needs])
    lengths = [round(sec*30) for sec in seconds_each[:-1]]
    lengths.append(frames-sum(lengths))
    _assign_missing_assets(beats, asset_indices)
    spread_assets(beats, asset_indices, catalog or [])
    scenes = []
    for index, (beat, length) in enumerate(zip(beats, lengths)):
        seconds = length/30
        if seconds < .5 or not beat.title or not beat.visual or len(beat.title)>80:
            raise CreativeUnavailable(f'صحنهٔ {index+1} عنوان، طراحی یا زمان اجرایی معتبر ندارد.')
        if asset_indices and beat.source_asset_index not in asset_indices:
            raise CreativeUnavailable(f'صحنهٔ {index+1} باید تصویر تأییدشدهٔ مرتبط انتخاب کند.')
        if beat.motion_engine=='motion_so':
            from brain.motion_so import configured
            if not configured():
                raise CreativeUnavailable('کلیپ موشن هوشمند در این سرور فعال نیست؛ برنامه به موتور غیرقابل‌اجرا ارجاع داده است.')
        scenes.append(Scene(index=index,description=f'{beat.role}: {beat.visual}',duration_s=seconds,
            text_overlay=beat.title,narration_text=beat.narration,
            media_method='upload' if asset_indices else 'generate',media_prompt=beat.visual,
            source_asset_index=beat.source_asset_index,estimated_cost=0,
            narrative_role=beat.role,visual_type=beat.visual_type,motion_style=beat.motion,
            motion_engine=beat.motion_engine,script_line=beat.line_id,why_visual=beat.why_visual,emotion=beat.emotion,
            focus=beat.focus,link_prev=beat.link_prev,reference_trait=beat.reference_trait,items=list(getattr(beat, 'items', None) or [])[:4]))
    return Storyboard(prompt=prompt,content_type='reel',language=language,style=style,
        creative_brief=brief or {}, scenes=scenes,total_duration_s=frames/30,
        # Zero is not a price estimate. Studio separately reports unknown cost
        # for generation providers; actual provider cost remains authoritative.
        estimated_total_cost=0, usage={'model':','.join(plan.models),'source':'creative_plan_v2'})


def _assign_missing_assets(beats, asset_indices: set[int]) -> None:
    """The approved script may leave a scene (a kinetic-type or a plain motion scene) without a picture while the verified product images are
    the material of the video: each such scene takes the picture used least so far (the first one, the product itself, for the opening), rather than the
    whole production being refused over a choice the script did not need to make."""
    if not asset_indices:
        return
    order = sorted(asset_indices)
    uses = {index: 0 for index in order}
    for beat in beats:
        if beat.source_asset_index in uses:
            uses[beat.source_asset_index] += 1
    for position, beat in enumerate(beats):
        if beat.source_asset_index in uses:
            continue
        choice = order[0] if position == 0 else min(order, key=lambda index: (uses[index], index))
        beat.source_asset_index = choice
        uses[choice] += 1


# What each kind of picture shows, in the words a scene uses for it (Persian) and the words an image description uses (English).
_TOPICS = (
    (("میکروفون", "صحبت", "گفت‌وگو", "گفتگو", "هم‌تیمی"), ("microphone", "boom", "mic", "pickup", "diagram")),
    (("بالشتک", "نرم", "راحت", "گوش", "ارگونومیک"), ("cushion", "earcup", "ear cup", "padded", "close-up")),
    (("نور", "ال‌ای‌دی", "چراغ", "درخشان", "رنگ"), ("led", "glow", "light", "lighting", "rgb")),
    (("سیم", "اتصال", "جک", "یو‌اس‌بی", "usb"), ("jack", "usb", "plug", "connector", "cable")),
)


def spread_assets(beats, asset_indices: set[int], catalog: list[dict]) -> None:
    """One picture for four scenes reads as a slideshow. A picture may serve at most ceil(scenes / pictures) scenes: a scene beyond that moves to the picture
    that best matches what the scene is about (its title, line and visual against each picture's description), else the picture used least."""
    order = sorted(asset_indices)
    if len(order) < 2 or len(beats) < 4:
        return
    subjects = {row["index"]: str(row.get("subject") or "").lower() for row in catalog if isinstance(row, dict) and "index" in row}
    cap = math.ceil(len(beats) / len(order))
    uses = {index: 0 for index in order}

    def fit(beat, index: int) -> int:
        text = f"{beat.title} {beat.narration} {beat.visual}".lower()
        subject = subjects.get(index, "")
        return sum(1 for words, tags in _TOPICS if any(w in text for w in words) and any(t in subject for t in tags))

    for position, beat in enumerate(beats):
        keep = beat.source_asset_index if beat.source_asset_index in uses else None
        if keep is not None and uses[keep] < cap and (position == 0 or fit(beat, keep) > 0 or uses[keep] == 0):
            uses[keep] += 1
            continue
        pool = [i for i in order if uses[i] < cap] or order
        choice = max(pool, key=lambda i: (fit(beat, i), -uses[i], -i))
        beat.source_asset_index = choice
        uses[choice] += 1


def _allocate(total: float, weights: list[float], minimum: list[float]) -> list[float]:
    """Split ``total`` seconds in proportion to ``weights`` without letting any scene fall below its minimum."""
    fixed: dict[int, float] = {}
    for _ in range(len(weights)):
        free = [i for i in range(len(weights)) if i not in fixed]
        room = total - sum(fixed.values())
        share = sum(weights[i] for i in free) or 1.0
        trial = {i: room*weights[i]/share for i in free}
        short = [i for i in free if trial[i] < minimum[i]]
        if not short:
            return [fixed.get(i, trial.get(i, 0.0)) for i in range(len(weights))]
        for i in short:
            fixed[i] = minimum[i]
    return [fixed[i] for i in range(len(weights))]


def bind_talking(plan: CreativePlan, decisions: dict, sentences: list[dict]) -> dict:
    """The director's anchored beats override the second writer's graphic choices.

    Cuts/captions retain their existing engine authority. Explicit style stays
    unchanged. Unsupported or dropped sentence references fail before rendering.
    """
    import copy
    result = copy.deepcopy(decisions)
    if plan.style not in {'talking_2','talking_3'}:
        return result
    board = []
    for beat_index, beat in enumerate(plan.chosen.beats):
        i = beat.sentence
        if i is None or not 0 <= i < len(sentences):
            raise CreativeUnavailable('صحنهٔ خلاقانه به جملهٔ واقعی ویدیو متصل نیست.')
        if i in result.get('drop',[]):
            raise CreativeUnavailable('برنامهٔ کات، جملهٔ موردنیاز صحنه را حذف کرده است؛ نیاز به بازبینی دارد.')
        if not beat.title:
            raise CreativeUnavailable('صحنهٔ خلاقانه عنوان نهایی ندارد.')
        if beat.visual_type == 'stat' and not any(c.isdigit() for c in sentences[i]['text']):
            raise CreativeUnavailable('نمایش آمار بدون عدد واقعی در گفتار مجاز نیست.')
        board.append({'i':i,'title':beat.title,'visual_type':beat.visual_type,
            'narrative_role':beat.role,'motion_style':beat.motion,'items':beat.items,'why':beat.intent})
        choice = next((c for c in plan.resource_choices if c.get('beat_index') == beat_index), None)
        if choice and choice.get('resource_id'):
            from .resources.planning import resolve_talking_recipe
            resolve_talking_recipe(choice['resource_id'], beat.visual_type)
            board[-1]['resource_id'] = choice['resource_id']
    if board:
        result['storyboard']=board
        # B-roll slots are derived from meaningful beats, not inserted to meet a
        # quota. Asset generation remains the engine's existing approved path.
        prior = {b['i']:b for b in result.get('broll',[])}
        result['broll']=[{**prior.get(row['i'],{}),'i':row['i'],
            'visual_type':row['visual_type'],'visual':beat.visual,'label':row['title'],
            'items':row['items'],'media':prior.get(row['i'],{}).get('media','')}
            for row,beat in zip(board,plan.chosen.beats)]
    return result
