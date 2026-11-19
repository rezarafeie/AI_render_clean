import React from "react";
import { Icon } from "../components/Icon";
import { useAuthenticatedMediaUrl } from "../AuthenticatedMedia";

const clock = (seconds: number) => {
  if (!Number.isFinite(seconds) || seconds < 0) return "0:00";
  const s = Math.floor(seconds);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
};

/** One audio file in the chat (a narration take, a voice, music): a rounded card with a round play button, its name, the time and a seek bar,
 *  and a download button. `authenticated` sources are fetched with the person's session first (the server's media routes need it). */
export default function AudioPlayer({ src, title = "صدا", authenticated = true, filename }: { src: string; title?: string; authenticated?: boolean; filename?: string }) {
  const fetched = useAuthenticatedMediaUrl(authenticated ? src : null);
  const url = authenticated ? fetched : src;
  const audio = React.useRef<HTMLAudioElement>(null);
  const [playing, setPlaying] = React.useState(false);
  const [time, setTime] = React.useState(0);
  const [duration, setDuration] = React.useState(0);
  const toggle = () => {
    const el = audio.current;
    if (!el) return;
    if (el.paused) void el.play().catch(() => setPlaying(false)); else el.pause();
  };
  const seek = (value: number) => { if (audio.current && duration) { audio.current.currentTime = value; setTime(value); } };
  const percent = duration ? Math.min(100, (time / duration) * 100) : 0;
  return <div className="audio-card" dir="ltr">
    {url ? <audio ref={audio} src={url} preload="metadata" onPlay={() => setPlaying(true)} onPause={() => setPlaying(false)} onEnded={() => setPlaying(false)}
      onTimeUpdate={e => setTime(e.currentTarget.currentTime)} onLoadedMetadata={e => setDuration(e.currentTarget.duration)} onDurationChange={e => setDuration(e.currentTarget.duration)}/> : null}
    <button type="button" className="audio-play" onClick={toggle} disabled={!url} aria-label={playing ? "توقف" : "پخش"}>
      <Icon name={playing ? "pause" : "play"} size={20}/>
    </button>
    <div className="audio-main">
      <div className="audio-title" dir="auto">{title}</div>
      <div className="audio-line">
        <span className="audio-time">{clock(time)} / {clock(duration)}</span>
        <input type="range" className="audio-seek" min={0} max={duration || 0} step={0.05} value={time} disabled={!duration}
          onChange={e => seek(Number(e.target.value))} aria-label="جابه‌جایی در صدا" style={{ ["--pct" as string]: `${percent}%` }}/>
      </div>
    </div>
    {url ? <a className="audio-action" href={url} download={filename || `${title}.mp3`} aria-label="دانلود"><Icon name="download" size={18}/></a> : null}
  </div>;
}
