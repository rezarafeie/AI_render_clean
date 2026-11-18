import requests,sys
sys.path.insert(0,'.'); from key import key
r=requests.post('https://api.elevenlabs.io/v1/music?output_format=mp3_44100_128',headers={'xi-api-key':key()},
 json={'prompt':'Light, curious and optimistic instrumental for an educational whiteboard explainer video. Pizzicato strings, marimba, soft ukulele strums, light finger snaps and brushed percussion, 108 BPM, playful but focused, steady groove, gentle build in the second half, warm uplifting ending. No vocals, no lyrics.','music_length_ms':110000,'force_instrumental':True},timeout=175)
print(r.status_code, '' if r.ok else r.text[:300])
if r.ok: open('music.mp3','wb').write(r.content)
