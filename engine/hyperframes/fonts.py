"""Local fonts for maintained HyperFrames templates."""

def fonts_css() -> str:
    """@font-face for the local Persian-capable families used by maintained templates (copied locally)."""
    faces = [("Ray", 300, "ray-light.ttf"), ("Ray", 400, "ray.ttf"), ("Ray", 500, "ray-medium.ttf"), ("Ray", 700, "ray-bold.ttf"),
             ("Ray", 800, "ray-extrabold.ttf"), ("Ray", 900, "ray-black.ttf"), ("Kharazmi", 400, "kharazmi.ttf"), ("Vazir", 400, "vazirmatn.ttf")]
    return "".join(f"@font-face{{font-family:{family};font-weight:{weight};src:url('./assets/fonts/{file}')}}" for family, weight, file in faces)


FONT_FILES = {
    "ray-light.ttf": "RAY-LIGHT.TTF", "ray.ttf": "RAY.TTF", "ray-medium.ttf": "RAY-MEDIUM.TTF", "ray-bold.ttf": "RAY-BOLD.TTF",
    "ray-extrabold.ttf": "RAY-EXTRABOLD.TTF", "ray-black.ttf": "RAY-BLACK.TTF",
    "kharazmi.ttf": "IRAN_Kharazmi/IRAN Kharazmi.ttf", "vazirmatn.ttf": "Vazirmatn-Regular.ttf",
}
