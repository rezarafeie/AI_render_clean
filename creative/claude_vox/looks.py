"""The art directions («looks») of the Vox engine.

The kit's primitives are the same for every film; a look decides everything that makes two films feel different: the ground, the palette, the type pairing, how pictures
are treated, the accent shapes, how pages change, and the compositions that suit it. The story editor picks the look that fits the subject (and may bend it); the scene
writers receive its guide. Ten looks come from the studio's reference collection (paper collage, editorial pastel, cartographic documentary, black-and-white with paint,
data-minimal, photographic documentary, sepia with script, flat vector illustration, ink diorama, retro colour collage).
"""
from __future__ import annotations

# font key -> (file in kit/public/fonts, css weight range)
FONTS = {
    "Anton": ("Anton-Regular.ttf", "400"),
    "Bebas": ("BebasNeue-Regular.ttf", "400"),
    "Playfair": ("PlayfairDisplay.ttf", "400 900"),
    "Caveat": ("Caveat.ttf", "400 700"),
    "DMSerif": ("DMSerifDisplay-Regular.ttf", "400"),
    "Grotesk": ("SpaceGrotesk.ttf", "300 700"),
    "Elite": ("SpecialElite-Regular.ttf", "400"),
}

# treatment of the pictures: how the image route is asked and how the result is processed (assets.py)
PICTURE = {
    "halftone": "vintage black-and-white halftone newspaper photo cutouts, high contrast, grainy print texture, documentary collage style",
    "sepia": "vintage sepia-toned photo cutouts, warm brown monochrome, soft film grain, archival documentary style",
    "mono": "black-and-white documentary photographs, natural light, film grain, no cutout needed, filling their cell edge to edge",
    "engraving": "antique black ink engravings and line drawings with fine cross-hatching on white, 19th-century illustration style",
    "vector": "clean flat vector illustrations with a limited palette of rust red, navy and cream, simple shapes, slight paper texture, editorial style",
    "colorcut": "photo cutouts with natural colour slightly desaturated, clean edges, studio lighting, editorial collage style",
}

LOOKS: dict[str, dict] = {
    "paper_collage": {
        "name": "Paper collage (Vox classic)",
        "when": "explainers about business, money, companies, technology and history; the safe, recognisable Vox look",
        "ground": "paper", "bg": "#EEE5D9", "ink": "#1C1B19", "text": "#1C1B19",
        "palette": ["#D9432F", "#F2B33D", "#2A9D8F"], "picture": "halftone",
        "display": "Anton", "serif": "Playfair", "script": "Caveat", "sans": "Grotesk", "transition": "mix",
        "guide": "Crumpled cream paper (tex 'paper') and graph paper ('grid'); coloured paper by Paper tint (mustard, red, teal, dark for quotes); halftone cut-outs with white borders and "
                 "printed photos with tape; big flat discs behind pictures; red marker marks; Persian headlines heavy, years/numbers typed (Special Elite) or Anton; stamps, torn paper, "
                 "counters. The reference film is exactly this look.",
    },
    "editorial_pastel": {
        "name": "Editorial pastel collage",
        "when": "finance, investing, real estate, SaaS, personal growth, anything calm and trustworthy that needs a modern editorial feel",
        "ground": "white", "bg": "#F1F1EF", "ink": "#111111", "text": "#111111",
        "palette": ["#F2A592", "#A8D8A0", "#8A9A3C"], "picture": "halftone",
        "display": "Grotesk", "serif": "Playfair", "script": "Caveat", "sans": "Grotesk", "transition": "zoom",
        "guide": "A clean white-grey paper ground with a faint grid (tex 'white' or 'grid'); GIANT soft pastel discs and half-discs (salmon, mint) behind grayscale cut-outs; olive-green "
                 "tape strips at angles; tiny sparkle stars; a single object may keep a strong accent colour (a red house, a red balloon) while everything else is grayscale. Headlines: "
                 "bold black grotesk, left-aligned, two stacked lines, size 120-170, with a blinking underscore cursor after the last word; one oversized object as the hero (magnifier, "
                 "house, balloon, check, handshake), scale and rotate it; checks and cheques drawn with black redaction bars; cut-outs of people with the face replaced by an object are "
                 "allowed. Pages change with a quick zoom-fade, not a slide.",
    },
    "cartographic": {
        "name": "Cartographic documentary",
        "when": "geography, trade, international money flows, geopolitics, empires, migration, supply chains, 'how X spread across the world'",
        "ground": "blueprint", "bg": "#0F1C3F", "ink": "#1B1B1B", "text": "#F4EBD8",
        "palette": ["#C8372D", "#E9D8B4", "#4F7CAC"], "picture": "engraving",
        "display": "Playfair", "serif": "Playfair", "script": "Caveat", "sans": "Grotesk", "transition": "zoom",
        "guide": "A deep navy ground with a thin graph grid (tex 'blueprint'); the WORLD MAP (WorldMap) in cream with the story's countries filled red, routes drawn across it with Route "
                 "(dashed, animated, glowing end), city dots and small-caps place labels; engraving-style pictures shown on cream cards with a soft vignette; archival newspaper clippings; "
                 "title cards in serif caps with wide letter-spacing (Latin only) and a red vertical band; people appear as small circular portraits with a red ring and a name line. "
                 "Camera moves matter here: slow push over the map between countries. Text on navy is cream (TXT); on cream cards it is dark.",
    },
    "bw_paint": {
        "name": "Black-and-white collage with paint",
        "when": "creators, marketing, media, agencies, brand and growth stories; loud, confident, poster-like",
        "ground": "white", "bg": "#F2F1EC", "ink": "#101010", "text": "#101010",
        "palette": ["#9CC9E6", "#101010", "#C9D6DF"], "picture": "halftone",
        "display": "Bebas", "serif": "Playfair", "script": "Caveat", "sans": "Grotesk", "transition": "zoom",
        "guide": "Off-white paper (tex 'white', or 'grid' for a graph-paper moment); piles of grayscale cut-outs stacked into towers and bursts (people, cameras, laptops, charts, megaphones) that GROW on the narration; light-blue "
                 "brush-stroke and paint-splash shapes (Splash) behind and over them; huge black condensed titles at the bottom (size 220-300) that crop at the frame edge; thick blue "
                 "brush checkmarks and circles; a glowing logo-like mark may sit in the centre of a radial burst of film strips. Scenes feel like a poster that assembles itself; "
                 "transitions are fast zooms with blur.",
    },
    "data_minimal": {
        "name": "Data-minimal",
        "when": "economics, statistics, comparisons, 'the numbers behind…', salary, inflation, productivity, anything where a chart IS the story",
        "ground": "flat", "bg": "#FBF6EA", "ink": "#1A1A1A", "text": "#1A1A1A",
        "palette": ["#2F7D5B", "#D64545", "#E9C46A"], "picture": "colorcut",
        "display": "Grotesk", "serif": "Playfair", "script": "Caveat", "sans": "Grotesk", "transition": "slide",
        "guide": "A flat warm-cream ground (Paper tex 'flat'), lots of empty space, thin lines; deep green and soft red as the only colours; charts are the hero (LineChart, Bars, Pie) "
                 "with tiny typed axis labels, a highlighted region (soft red wedge under a line) and a typed definition box beside it; a title in plain bold grotesk (size 80-110) "
                 "above, a one-line caption below; one scene may flip to a DARK ground (Paper tex 'flat' with tint DARK) for the contrast chart. Cut-out people stand small with a soft "
                 "ground shadow beside a labelled fact card. Calm, precise, no stamps unless the number is the news.",
    },
    "documentary_photo": {
        "name": "Photographic documentary",
        "when": "biographies, history, brands with real photographs, interviews, 'the man who…' stories",
        "ground": "flat", "bg": "#0C0C0C", "ink": "#0C0C0C", "text": "#F4F1EA",
        "palette": ["#F2D12E", "#C8372D", "#F4F1EA"], "picture": "mono",
        "display": "Grotesk", "serif": "Playfair", "script": "Caveat", "sans": "Grotesk", "transition": "zoom",
        "guide": "Black ground; FULL-BLEED black-and-white photographs (printed photos scaled to fill, slow push) alternating with rounded-corner photo cards side by side on black; "
                 "yellow typed captions over the photo (small, centred or left) and giant bold white words that appear one at a time over a darkened photo; red or yellow label boxes "
                 "pointing at a thing with a thin leader line; a title card is plain bold sans on light grey. Real photographs are the point: use the supplied pictures big.",
    },
    "sepia_script": {
        "name": "Sepia with script type",
        "when": "personalities, entrepreneurs, motivation, 'who is…' profiles, success stories",
        "ground": "kraft", "bg": "#B9AE98", "ink": "#3A2F22", "text": "#3A2F22",
        "palette": ["#E8C53A", "#3A2F22", "#8C7B5E"], "picture": "sepia",
        "display": "Playfair", "serif": "Playfair", "script": "Caveat", "sans": "Grotesk", "transition": "zoom",
        "guide": "Khaki/kraft textured ground (tex 'kraft'); sepia-toned portraits cut out and set against a dark slate rectangle, or full-bleed sepia with white text; MIXED TYPE: a heavy "
                 "serif word next to a flowing script word that overlaps it (size 100-150 serif + 90 script), a tiny sans caption under it; a social-profile card (rounded white "
                 "rows) with yellow highlighter over the follower numbers; bills and objects floating in; the number being the hero, big. Warm, personal, a bit cinematic.",
    },
    "vector_flat": {
        "name": "Flat vector illustration with torn paper",
        "when": "how-to, money-making methods, categories and lists (ways to earn, types of X), friendly educational explainers",
        "ground": "paper", "bg": "#F1E9DA", "ink": "#25304D", "text": "#25304D",
        "palette": ["#C8502A", "#25304D", "#E9B44C"], "picture": "vector",
        "display": "Bebas", "serif": "DMSerif", "script": "Caveat", "sans": "Grotesk", "transition": "slide",
        "guide": "Cream paper ground; flat vector illustrations (rust, navy, mustard) as cut-outs; a starburst of rays (Starburst) with coins or confetti behind the key icon; uppercase "
                 "condensed titles (size 110-160) with a red underline, set on torn paper strips at the top; list items appear as torn tags (MERCH., MEMBERSHIPS) one by one, "
                 "each with its icon; a character at a desk is the opening hero. Friendly, tidy, quick; pages slide over like paper.",
    },
    "ink_diorama": {
        "name": "Ink diorama",
        "when": "history, biographies of an era, nostalgic stories, songs and culture, anything told as 'a world that moves past the camera'",
        "ground": "white", "bg": "#F4F4F2", "ink": "#151515", "text": "#151515",
        "palette": ["#59C3C3", "#B5472B", "#151515"], "picture": "engraving",
        "display": "Bebas", "serif": "Playfair", "script": "Caveat", "sans": "Grotesk", "transition": "slide",
        "guide": "A near-white ground fading into soft cloud-gray at the top; pictures are black ink drawings or old photo cut-outs (a train, a diner, a truck) standing on a road/ground "
                 "strip at the bottom that SLIDES sideways like a diorama: the scene changes by the whole set scrolling past (use a long horizontal row and translate it), with one "
                 "object keeping a warm colour (a rust-red truck); names in small teal bold caps with a thin underline and the song/work title below in italic serif. Calm, "
                 "nostalgic, lots of air, small elements.",
    },
    "retro_collage": {
        "name": "Retro colour collage",
        "when": "science, discoveries, inventions, 20th-century history, 'accidents that changed the world'",
        "ground": "flat", "bg": "#D8DE6C", "ink": "#1B1B1B", "text": "#1B1B1B",
        "palette": ["#B3261E", "#58B6A6", "#F3D13B"], "picture": "colorcut",
        "display": "Grotesk", "serif": "DMSerif", "script": "Caveat", "sans": "Grotesk", "transition": "slide",
        "guide": "Flat lime-yellow ground (tex 'flat' with this bg) that changes colour between scenes (deep red, cream, teal); cut-outs of vintage skylines, hands, lab glassware and "
                 "portraits in muted colour with big half-discs (mint, red) behind them; bold sans titles in black where the SECOND word takes an accent colour; small yellow tag "
                 "labels with thin leader lines that annotate a detail of the picture (Tag); a vignette plate (petri dish, microscope view) filling the frame for the big reveal; "
                 "a year appears huge in Anton-like caps on a skyline. Warm, 1940s science-poster feeling.",
    },
}

DEFAULT = "paper_collage"


def get(look: str | None) -> dict:
    return LOOKS.get(look or "", LOOKS[DEFAULT])


def catalog() -> str:
    return "\n".join(f"- {key}: {value['name']} — {value['when']}" for key, value in LOOKS.items())


def theme(look_id: str, overrides: dict | None = None) -> dict:
    """The THEME object the kit reads (colours, ground, fonts) for a look; `overrides` may change palette/bg/text of this film only."""
    look = get(look_id)
    a, b, c = look["palette"]
    data = {"look": look_id if look_id in LOOKS else DEFAULT, "red": a, "must": b, "teal": c, "bg": look["bg"], "ink": look["ink"], "text": look["text"], "ground": look["ground"],
            "display": look["display"], "serif": look["serif"], "script": look["script"], "sans": look["sans"], "transition": look["transition"]}
    for key in ("red", "must", "teal", "bg", "ink", "text"):
        value = (overrides or {}).get(key)
        if isinstance(value, str) and len(value) == 7 and value.startswith("#"):
            data[key] = value
    return data


def font_faces(theme_data: dict) -> list[dict]:
    keys = []
    for k in ("display", "serif", "script", "sans"):
        if theme_data[k] not in keys:
            keys.append(theme_data[k])
    if "Elite" not in keys:
        keys.append("Elite")
    return [{"family": k, "file": FONTS[k][0], "weight": FONTS[k][1]} for k in keys if k in FONTS]
