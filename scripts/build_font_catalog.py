"""Builds assets/fonts_pro from a folder of Persian font packages.

    python scripts/build_font_catalog.py "/path/to/fonts" [--specimens]

It copies the files the designers use (variable fonts wherever a package has one), reads their real metadata (weights, axes, glyph coverage) with fontTools and writes
assets/fonts_pro/catalog.json: for every family what it looks like and what it is for. With --specimens it also renders specimen images (Chrome headless) and contact
sheets, which the vision step looks at when it chooses fonts. The catalog is the one list the planner, the scene designers, the vision step and the Edit tab read
(creative/font_catalog.py). The packages are proprietary software of their vendors: each project that ships them needs the vendor's licence."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "fonts_pro"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
KAHROBA = "180-Kahroba-v1.0-Pro/180-Kahroba-v1.0-Pro/Variable/ttf(desktop)"

# id, package files (relative to the packages folder; first is the main face), curated character. Separate designs that share one weight (Hasti, Typokar, Kaghaz) each get
# their own CSS family.
CURATED: list[dict] = [
    {"id": "doran", "label": "دوران", "vendor": "فونت‌ایران", "designer": "فرشته ایران‌شاهی، رضا بختیاری‌فرد", "category": "editorial",
     "files": [("Doran Pro/Doran Variable/Doran-VF.ttf", "Doran")],
     "mood": ["شیک", "ادبی", "گرم", "کتابی"], "best_for": ["روایت و داستان", "برند لوکس", "مستند", "عنوان‌های بلند", "نقل‌قول"],
     "avoid_for": ["هوک تند و فریادی"], "pairs_with": ["aramesh", "mahoor"],
     "note": "سنس‌سریف ادبی با کنتراست ملایم و لاتین کتابی؛ برای وقتی که فیلم باید باوقار و خوش‌خوان باشد. وزن ۱۰۰ تا ۹۰۰."},
    {"id": "quarantine", "label": "قرنطینه", "vendor": "فونت‌ایران", "designer": "محمدرضا چیت‌ساز", "category": "display-elegant",
     "files": [("Quarantine Pro [@FontiranIR]/01 Font Family/variable-ttf/Quarantine-VF.ttf", "Quarantine")],
     "mood": ["مد و استایل", "ظریف", "مجله‌ای", "هنری"], "best_for": ["مد و زیبایی", "سبک زندگی", "عنوان بزرگ", "کاور و تیتر مجله‌ای"],
     "avoid_for": ["متن کوچک و پرحجم"], "pairs_with": ["aramesh", "paykan"],
     "note": "دیسپلی ظریف با اندازهٔ نوری؛ در وزن‌های بالا تیتر شیک و در وزن‌های پایین ظریف است. وزن ۱۰۰ تا ۹۵۰."},
    {"id": "rokh", "label": "رخ", "vendor": "فونت‌ایران", "designer": "کامیاب جعفری", "category": "tech-sans",
     "files": [("Rokh_Pro/VariableFonts/RokhVFGX.ttf", "Rokh")],
     "mood": ["فنی", "هندسی", "مدرن", "پرانرژی"], "best_for": ["استارتاپ و فناوری", "مالی و آمار", "گیم", "عدد و نمودار", "عنوان‌های سنگین"],
     "avoid_for": ["متن ادبی و احساسی"], "pairs_with": ["aramesh", "doran"],
     "note": "سنس هندسی با گوشه‌های گرد؛ از بسیار نازک تا بسیار ضخیم (۵۰ تا ۹۰۰). برای هر چیز دیجیتالی و عددی."},
    {"id": "paykan", "label": "پیکان", "vendor": "رضا بختیاری‌فرد", "designer": "رضا بختیاری‌فرد", "category": "sans",
     "files": [("Peykan Pro @editollogist/Paykan Variable/Paykan-VF.ttf", "Paykan")],
     "mood": ["خنثی", "دوستانه", "تمیز", "همه‌منظوره"], "best_for": ["متن بدنه", "توضیحات", "فروش و محصول", "هر موضوعی که فونت خاصی نمی‌خواهد"],
     "avoid_for": ["حس خاص و هنری"], "pairs_with": ["quarantine", "morabba"],
     "note": "سنس خنثی و خوانا با وزن ۰ تا ۹۵۰؛ انتخاب امن وقتی طراحی باید از متن جلو نزند."},
    {"id": "mahoor", "label": "ماهور", "vendor": "فونت‌امین", "designer": "امیر عابدی", "category": "humanist-sans",
     "files": [("Mahoor-v1.0/Variable/Mahoor[CNTR,wght].ttf", "Mahoor")],
     "mood": ["روشن", "خبری", "آموزشی", "قابل‌اعتماد"], "best_for": ["اکسپلینر", "خبر و تحلیل", "آموزش", "متن بدنه و تیتر"],
     "avoid_for": ["حس شیطنت و هیجان"], "pairs_with": ["morabba", "doran"],
     "note": "سنس انسانی با محور کنتراست (CNTR) برای کنترل ضخامت‌های ظریف؛ وزن ۴۰۰ تا ۸۰۰."},
    {"id": "aramesh", "label": "آرامش", "vendor": "صابر راستی‌کردار", "designer": "صابر راستی‌کردار", "category": "humanist-sans",
     "files": [("Aramesh @editollogist/w_Aramesh Regular.ttf", "Aramesh"), ("Aramesh @editollogist/w_Aramesh Bold.otf", "Aramesh"),
               ("Aramesh @editollogist/w_Aramesh Extra Bold.otf", "Aramesh"), ("Aramesh @editollogist/w_Aramesh  Black.ttf", "Aramesh")],
     "mood": ["آرام", "خوانا", "ساده"], "best_for": ["متن بدنه", "زیرنویس و توضیح", "فهرست و مراحل", "برچسب‌های کوچک"],
     "avoid_for": ["عنوان‌های بسیار بزرگ و پرشور"], "pairs_with": ["doran", "rokh", "hasti"],
     "note": "سنس آرام و بسیار خوانا در چهار وزن؛ بهترین جفت برای فونت‌های دیسپلی."},
    {"id": "kahroba", "label": "کهربا", "vendor": "فونت‌ایران", "designer": "امین عابدی", "category": "display-sans",
     "files": [(KAHROBA + "/weight axis only/Kahroba-VF-wght[wght,100,50].ttf", "Kahroba")],
     "mood": ["جدی", "مجله‌ای", "قدرتمند", "خبری"], "best_for": ["تیتر خبری", "تحلیل و دیدگاه", "عدد و آمار بزرگ", "مستند"],
     "avoid_for": ["حس بازیگوش"], "pairs_with": ["aramesh", "mahoor"],
     "note": "فارسی سنس قوی و خوانا با لاتین سریف؛ تیترهایی با وزن و اعتبار مجله. وزن ۱۰۰ تا ۹۰۰."},
    {"id": "kahroba-pro", "label": "کهربا پرو (متغیر)", "vendor": "فونت‌ایران", "designer": "امین عابدی", "category": "display-sans",
     "files": [(KAHROBA + "/Kahroba-VF[wght,wdth,CNTR].ttf", "Kahroba Pro")],
     "mood": ["جدی", "پویا", "قدرتمند", "تایپوگرافی متحرک"], "best_for": ["تایپوگرافی متحرک", "تیتر با تغییر ضخامت و عرض", "هوک"],
     "avoid_for": ["متن کوچک"], "pairs_with": ["aramesh"],
     "note": "همان کهربا با سه محور: وزن، عرض (wdth ۸۷ تا ۱۲۵) و کنتراست (CNTR ۰ تا ۱۰۰). برای انیمیشنِ تغییر شکل حروف با font-variation-settings."},
    {"id": "morabba", "label": "مربع", "vendor": "فونت‌ایران", "designer": "حسن منظوری", "category": "square-display",
     "files": [("Morabba @editollogist/VF/MorabbaVF.ttf", "Morabba")],
     "mood": ["قوی", "هندسی", "تبلیغاتی", "ورزشی"], "best_for": ["هوک و تیتر تبلیغاتی", "ورزش و انگیزشی", "حراج و تخفیف", "تیتر کشیده با کشیده (kash)"],
     "avoid_for": ["متن ادبی", "متن پرحجم"], "pairs_with": ["paykan", "mahoor"],
     "note": "کوفی مربع با وزن ۲۵۰ تا ۹۰۰ و محور کشیده (kash ۰ تا ۱۰۰) برای کشیدن حروف."},
    {"id": "manshoor", "label": "منشور", "vendor": "فونت‌امین", "designer": "امین عابدی", "category": "heavy-display",
     "files": [("Manshoor @editollogist/Variable/Manshoor-VF[wght].ttf", "Manshoor")],
     "mood": ["سنگین", "فشرده", "شوک", "جسور"], "best_for": ["هوک ثانیهٔ اول", "تیتر یک‌کلمه‌ای", "حراج", "اعداد بزرگ"],
     "avoid_for": ["متن چندخطی", "هر متنی که حروف لاتین دارد (این فونت لاتین ندارد)"], "pairs_with": ["aramesh", "paykan"],
     "note": "دیسپلی فشردهٔ بسیار سنگین (۵۰۰ تا ۹۰۰). فقط حروف فارسی و ارقام؛ لاتین ندارد."},
    {"id": "gofteh", "label": "گفته", "vendor": "فونت‌ایران", "designer": "علیرضا نعمت‌اللهی", "category": "heavy-display",
     "files": [("Gofteh [@fontiranir]/01-Standard/TTF/Gofteh-Heavy.ttf", "Gofteh")],
     "mood": ["شوخ", "پرصدا", "جوان", "محاوره‌ای"], "best_for": ["هوک جوان‌پسند", "میم و طنز", "نقل‌قول محاوره‌ای", "تیتر کوتاه"],
     "avoid_for": ["حس رسمی و لوکس"], "pairs_with": ["aramesh", "paykan"],
     "note": "دیسپلی بسیار ضخیم و خودمانی با شخصیت «گفتگو» (یک وزن، ۹۰۰)."},
    {"id": "kaghaz", "label": "کاغذ", "vendor": "مرتضی آخوندپور", "designer": "مرتضی آخوندپور", "category": "poster-display",
     "files": [("Kaghaz @editollogist/KaghazAlef-Bold.ttf", "Kaghaz Alef"), ("Kaghaz @editollogist/Kaghaz.ttf", "Kaghaz")],
     "mood": ["پوستری", "چاپی", "جسور", "مستقیم"], "best_for": ["پوستر و بنر", "جملهٔ قصار", "تیتر کوتاه و بزرگ"],
     "avoid_for": ["متن بلند"], "pairs_with": ["aramesh"],
     "note": "دیسپلی سنگین با حس برش کاغذ و پوستر چاپی؛ دو شکل: «Kaghaz Alef» و «Kaghaz»."},
    {"id": "hasti", "label": "هستی", "vendor": "فونت‌ایران", "designer": "مسلم ابراهیمی", "category": "brush-display",
     "files": [("Hasti v2/ttf/Hasti-HeavyR.ttf", "Hasti R"), ("Hasti v2/ttf/Hasti-HeavyRRD.ttf", "Hasti RRD"), ("Hasti v2/ttf/Hasti-HeavyS.ttf", "Hasti S"),
               ("Hasti v2/ttf/Hasti-HeavySRD.ttf", "Hasti SRD")],
     "mood": ["پرانرژی", "مورب", "تبلیغاتی", "قلم‌گیری"], "best_for": ["فروش و تخفیف", "ریل پرهیجان", "تیتر مورب", "هشتگ و برچسب"],
     "avoid_for": ["متن آرام و رسمی"], "pairs_with": ["aramesh", "paykan"],
     "note": "دیسپلی مورب سنگین با حس قلم؛ چهار شکل: R (گرد)، RRD (گرد با تزیین)، S (تیز)، SRD (تیز با تزیین)."},
    {"id": "typokar", "label": "تایپوکار", "vendor": "رایگان‌فونت", "designer": "علی درستکار", "category": "script-display",
     "files": [(f"Typokar @editollogist/typokar-{n} [ fontrayegan ].ttf", f"Typokar {n}") for n in (1, 2, 3, 4)],
     "mood": ["دست‌نویس", "خودمانی", "خلاق", "امضایی"], "best_for": ["برند شخصی", "امضا و اسم", "تیتر خلاق", "جملهٔ تأکیدی"],
     "avoid_for": ["متن بدنه"], "pairs_with": ["aramesh", "paykan"],
     "note": "چهار شکل قلمی مورب با حس دست‌نویس سریع: Typokar 1 تا 4."},
    {"id": "leila", "label": "لیلا", "vendor": "مریم‌سافت", "designer": "مریم‌سافت", "category": "calligraphic",
     "files": [(f"Leila @editollogist/Leila-{w}[@fontrayegan].ttf", "Leila") for w in ("Light", "Regular", "Bold", "ExtraBold", "Black")],
     "mood": ["عاشقانه", "شاعرانه", "نستعلیق‌گونه", "نرم"], "best_for": ["شعر و نقل‌قول", "عاشقانه و احساسی", "امضا", "تیتر ظریف"],
     "avoid_for": ["اعداد و اطلاعات", "متن کوچک"], "pairs_with": ["aramesh", "doran"],
     "note": "دست‌نویس نستعلیق‌گونه در پنج وزن؛ فقط برای کلمات کم و بزرگ."},
    {"id": "daftar", "label": "دفتر", "vendor": "استودیو دفتر", "designer": "Studio Daftar", "category": "handwriting",
     "files": [("Daftar @editollogist/SD-Daftar-Regular.ttf", "Daftar")],
     "mood": ["دفترچه‌ای", "خودمانی", "ساده", "آموزشی"], "best_for": ["یادداشت و دفترچه", "مراحل دست‌نویس", "حس مدرسه و آموزش", "برچسب‌های خودمانی"],
     "avoid_for": ["تیتر رسمی"], "pairs_with": ["morabba", "aramesh"],
     "note": "دست‌نویس تک‌خطی نازک با حس نوشتن در دفتر (یک وزن)."},
]

# the fonts the studio already used before this catalog: kept in the list so the designers see one set
BUILTIN: list[dict] = [
    {"id": "ray", "label": "ری", "family": "Ray", "vendor": "رایگان‌فونت", "designer": "", "category": "sans", "builtin": True,
     "mood": ["مدرن", "پرقدرت", "تمیز"], "best_for": ["تیتر عمومی", "شبکه‌های اجتماعی", "فناوری"], "avoid_for": [], "pairs_with": ["aramesh"],
     "note": "فونت پیش‌فرض استودیو؛ سنس مدرن در وزن‌های ۳۰۰ تا ۹۰۰.", "weights": [300, 400, 500, 700, 800, 900], "css_families": ["Ray"], "latin": True, "faces": [],
     "axes": {}, "persian_digits": True, "license": "", "specimen": "specimens/ray.jpg"},
    {"id": "vazir", "label": "وزیرمتن", "family": "Vazir", "vendor": "صابر راستی‌کردار", "designer": "صابر راستی‌کردار", "category": "sans", "builtin": True,
     "mood": ["خنثی", "خوانا"], "best_for": ["متن بدنه"], "avoid_for": [], "pairs_with": ["ray"], "note": "سنس خنثی برای متن (وزن معمولی).",
     "weights": [400], "css_families": ["Vazir"], "latin": True, "faces": [], "axes": {}, "persian_digits": True, "license": "", "specimen": "specimens/vazir.jpg"},
    {"id": "kharazmi", "label": "خوارزمی", "family": "Kharazmi", "vendor": "ایران", "designer": "", "category": "traditional", "builtin": True,
     "mood": ["سنتی", "ادبی", "رسمی"], "best_for": ["شعر", "تاریخ", "مذهبی", "حس کلاسیک"], "avoid_for": ["فناوری"], "pairs_with": ["vazir"],
     "note": "نسخ سنتی و کلاسیک (وزن معمولی).", "weights": [400], "css_families": ["Kharazmi"], "latin": False, "faces": [], "axes": {}, "persian_digits": True, "license": "",
     "specimen": "specimens/kharazmi.jpg"},
]


def _slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", name).strip("-").lower()


def _read(path: Path) -> dict:
    font = TTFont(path, lazy=True)
    cmap = font.getBestCmap() or {}
    axes = {a.axisTag: [a.minValue, a.maxValue] for a in font["fvar"].axes} if "fvar" in font else {}
    weight = font["OS/2"].usWeightClass if "OS/2" in font else 400
    return {"weight": weight, "axes": axes, "latin": sum(1 for c in cmap if 0x41 <= c <= 0x5A) > 20, "persian_digits": all(c in cmap for c in range(0x6F0, 0x6FA))}


def build(packages: Path, specimens: bool) -> None:
    shutil.rmtree(OUT / "files", ignore_errors=True)
    (OUT / "files").mkdir(parents=True, exist_ok=True)
    catalog = []
    for spec in CURATED:
        faces, weights, axes, latin, digits = [], set(), {}, True, True
        for rel, css_family in spec["files"]:
            source = packages / rel
            if not source.is_file():
                raise SystemExit(f"missing: {rel}")
            info = _read(source)
            name = _slug(css_family) + "-" + _slug(Path(rel).stem)[:40] + source.suffix.lower()
            target = OUT / "files" / spec["id"] / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            wght = info["axes"].get("wght")
            faces.append({"css_family": css_family, "file": f"files/{spec['id']}/{name}", "weight": f"{int(wght[0])} {int(wght[1])}" if wght else str(info["weight"]), "variable": bool(info["axes"]),
                          "axes": {k: [int(v[0]), int(v[1])] for k, v in info["axes"].items()}})
            if wght:
                weights.update(w for w in range(100, 1000, 100) if wght[0] <= w <= wght[1])
            else:
                weights.add(info["weight"])
            axes.update({k: [int(v[0]), int(v[1])] for k, v in info["axes"].items()})
            latin = latin and info["latin"]
            digits = digits and info["persian_digits"]
        families = list(dict.fromkeys(f["css_family"] for f in faces))
        catalog.append({k: spec[k] for k in ("id", "label", "vendor", "designer", "category", "mood", "best_for", "avoid_for", "pairs_with", "note")} |
                       {"family": families[0], "css_families": families, "faces": faces, "weights": sorted(weights), "axes": axes, "latin": latin, "persian_digits": digits,
                        "builtin": False, "license": "نرم‌افزار مالکیتی فروشنده؛ برای هر پروژه‌ای که همراه محصول عرضه می‌شود، مجوز فروشنده لازم است.",
                        "specimen": f"specimens/{spec['id']}.jpg"})
    catalog = BUILTIN + catalog
    flat = ROOT / "presets" / "fonts" / "pro"                   # the caption renderer (libass) reads fonts from presets/fonts
    shutil.rmtree(flat, ignore_errors=True)
    flat.mkdir(parents=True)
    for source in (OUT / "files").rglob("*"):
        if source.is_file():
            shutil.copy2(source, flat / source.name)
    (OUT / "catalog.json").write_text(json.dumps({"version": 1, "fonts": catalog}, ensure_ascii=False, indent=1), encoding="utf-8")
    size = sum(p.stat().st_size for p in (OUT / "files").rglob("*") if p.is_file()) / 1e6
    print(f"{len(catalog)} fonts; {sum(1 for p in (OUT / 'files').rglob('*') if p.is_file())} files; {size:.1f} MB")
    if specimens:
        render_specimens(catalog)


SAMPLE_FA = "ثبت شرکت جهانی بدون مهاجرت"
SAMPLE_NUM = "۱۴ سال تجربه · ۲۵٬۰۰۰ تومان"
SAMPLE_EN = "Fast Reels 2026"


def render_specimens(catalog: list[dict]) -> None:
    from PIL import Image
    work = OUT / "_work"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    (OUT / "specimens").mkdir(exist_ok=True)
    (OUT / "sheets").mkdir(exist_ok=True)
    kit = ROOT / "presets" / "fonts"
    builtin_files = {"ray": [("Ray", "RAY-LIGHT.TTF", 300), ("Ray", "RAY.TTF", 400), ("Ray", "RAY-BOLD.TTF", 700), ("Ray", "RAY-BLACK.TTF", 900)],
                     "vazir": [("Vazir", "Vazirmatn-Regular.ttf", 400)], "kharazmi": [("Kharazmi", "IRAN_Kharazmi/IRAN Kharazmi.ttf", 400)]}
    images = []
    for font in catalog:
        faces = []
        if font["builtin"]:
            for family, rel, weight in builtin_files[font["id"]]:
                shutil.copy2(kit / rel, work / Path(rel).name)
                faces.append((family, Path(rel).name, str(weight)))
        else:
            for face in font["faces"]:
                shutil.copy2(OUT / face["file"], work / Path(face["file"]).name)
                faces.append((face["css_family"], Path(face["file"]).name, face["weight"]))
        css = "".join(f'@font-face{{font-family:"{fam}";src:url("{file}");font-weight:{w if " " in w else w + " " + w}}}' for fam, file, w in faces)
        rows = []
        variable = [f for f in faces if " " in f[2]]
        if variable:
            fam = variable[0][0]
            low, high = (int(x) for x in variable[0][2].split())
            rows = [(fam, w) for w in sorted({max(low, 300), min(high, 500), min(high, 700), high})]
        else:
            seen = set()
            for fam, _file, w in faces:
                if (fam, w) not in seen:
                    seen.add((fam, w))
                    rows.append((fam, int(w)))
        rows = rows[:5]
        body = "".join(f'<div class="r"><span class="t" style="font-family:\'{fam}\';font-weight:{w}">{SAMPLE_FA}</span><span class="m">{fam} {w}</span></div>' for fam, w in rows)
        last_fam, last_w = rows[-1]
        extra = f'<div class="n" style="font-family:\'{last_fam}\';font-weight:{last_w}">{SAMPLE_NUM}</div>'
        if font.get("latin"):
            extra += f'<div class="n en" style="font-family:\'{last_fam}\';font-weight:{last_w}">{SAMPLE_EN}</div>'
        html = (f'<meta charset="utf-8"><style>{css}body{{margin:0;background:#fff;color:#111;width:1000px}}.h{{padding:14px 28px 4px;font:600 15px sans-serif;color:#666;direction:ltr}}'
                f'.r{{padding:6px 28px;direction:rtl;display:flex;justify-content:space-between;align-items:baseline;gap:16px}}.t{{font-size:50px;line-height:1.5}}.m{{font:12px monospace;color:#999;direction:ltr}}'
                f'.n{{padding:2px 28px 12px;direction:rtl;font-size:34px;line-height:1.5}}.en{{direction:ltr;text-align:left}}</style>'
                f'<div class="h">{font["id"]} · {font["family"]} · {font["label"]}</div>{body}{extra}')
        page = work / f"{font['id']}.html"
        page.write_text(html, encoding="utf-8")
        png = work / f"{font['id']}.png"
        height = 80 + 84 * len(rows) + 56 + (52 if font.get("latin") else 0) + 20
        subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--window-size=1000,{height}", f"--screenshot={png}", f"file://{page}"],
                       capture_output=True, timeout=90, check=True)
        image = Image.open(png).convert("RGB")
        image.save(OUT / "specimens" / f"{font['id']}.jpg", quality=84, optimize=True)
        images.append((font["id"], image))
    for number, start in enumerate(range(0, len(images), 4)):          # contact sheets for the vision step: four specimens each, ids written on them
        group = images[start:start + 4]
        sheet = Image.new("RGB", (1000, sum(img.height for _, img in group)), "white")
        top = 0
        for _, img in group:
            sheet.paste(img, (0, top))
            top += img.height
        sheet.save(OUT / "sheets" / f"sheet-{number + 1}.jpg", quality=82, optimize=True)
    shutil.rmtree(work, ignore_errors=True)
    print(f"{len(images)} specimens, {len(list((OUT / 'sheets').glob('*.jpg')))} sheets")


if __name__ == "__main__":
    packages = Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else None
    if not packages or not packages.is_dir():
        raise SystemExit(__doc__)
    build(packages, "--specimens" in sys.argv)
