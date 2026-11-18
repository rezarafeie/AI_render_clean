import requests,sys,time
sys.path.insert(0,'.'); from key import key
M={'reel':('High-energy modern motion design showreel track, punchy electronic funk with tight drums, syncopated bass stabs, glitchy percussion fills and bold hits, 128 BPM, starts immediately with a three-count pulse then drops hard, confident and playful, ends with a clean final hit. Instrumental, no vocals.',19000),
'story':('Light, witty, minimalist instrumental for a charming typographic product story. Soft felt piano motif, pizzicato strings, gentle upright bass, brushed percussion, small celesta sparkles, 96 BPM. Starts very sparse and quiet for the first four seconds, then warms up and gently grows, ends on a sweet resolved note. No vocals.',52000),
'talk':('Sleek confident modern underscore for a premium tech product film with a presenter. Warm analog synth bass pulse, soft sidechained pads, crisp minimal drums, subtle plucks, 100 BPM, cinematic but friendly, leaves room for voice-over, clean ending. Instrumental, no vocals.',36000),
'film':('Slow cinematic ambient score for a quiet 3D film of a desk at dusk and night. Warm felt piano notes, soft evolving analog pads, gentle tape hiss, distant airy strings, 70 BPM, intimate and hopeful, slowly builds through the night to a gentle luminous sunrise resolution. Instrumental, no vocals.',60000)}
for k in sys.argv[1:]:
    p,ms=M[k]
    for a in range(3):
        r=requests.post('https://api.elevenlabs.io/v1/music?output_format=mp3_44100_128',headers={'xi-api-key':key()},json={'prompt':p,'music_length_ms':ms,'force_instrumental':True},timeout=170)
        print(k,r.status_code,'' if r.ok else r.text[:160])
        if r.ok: open(f'music_{k}.mp3','wb').write(r.content); break
        time.sleep(6)
