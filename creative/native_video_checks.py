"""Bounded blank-frame gates for the two fixed native Shotcraft designs.

Not a general quality/virality classifier. These designs deliberately have
foreground on every frame and a known light/dark background contract.
"""
import subprocess


def inspect_native_frames(source, *, dark_background=False, width=288, height=512, expected_frames=None, first_frame_only=False):
    from PIL import Image
    if width!=288 or height not in {162,288,512}:
        raise ValueError("Unsupported native frame-check dimensions")
    raw=subprocess.run(["ffmpeg","-v","error","-i",str(source),"-vf",f"scale={width}:{height}",
                        "-frames:v","1" if first_frame_only else "361","-pix_fmt","gray","-f","rawvideo","pipe:1"],
                       check=True,capture_output=True,timeout=30).stdout
    size=width*height
    if not raw or len(raw)%size or len(raw)//size>360:
        raise ValueError("Cannot inspect a bounded complete native sequence")
    if expected_frames is not None and len(raw)//size!=expected_frames:
        raise ValueError("Native encoded frame count does not match the approved timeline")
    counts=[]
    for offset in range(0,len(raw),size):
        histogram=Image.frombytes("L",(width,height),raw[offset:offset+size]).histogram()
        foreground=sum(histogram[180:]) if dark_background else sum(histogram[:140])
        background=sum(histogram[:140]) if dark_background else sum(histogram[180:])
        # Test foreground presence, not a minimum text area: a deliberately
        # short valid phrase must not be misclassified as an empty frame.
        if foreground<1 or background<size*.2:
            raise ValueError(f"Empty/light or black frame at index {offset//size}")
        counts.append(foreground)
    return {"validator_revision":2,"minimum_foreground_pixels":1,"decoded_frames":len(counts),"min_bright_pixels" if dark_background else "min_dark_pixels":min(counts),
            "method":f"{'first encoded frame' if first_frame_only else 'all encoded frames'}, {width}x{height} grayscale, {'dark' if dark_background else 'light'}-fixture foreground gate; not aesthetic certification"}
