import { useEffect, useRef, useState } from 'react';
import hermesApi from '../../services/hermesApi';
import { useHermes } from './HermesContext';
import HermesConnect from './HermesConnect';
import HermesSettings from './HermesSettings';

/** How the agent splits its ideas between the two kinds of content. Saved a moment after the slider stops. */
function IdeaMix() {
  const { agent, reloadAgent } = useHermes();
  const saved = agent?.prefs?.talking_share ?? 50;
  const [value, setValue] = useState(saved);
  const [state, setState] = useState('');
  const timer = useRef(0);
  useEffect(() => { setValue(saved); }, [saved]);
  const change = (next) => {
    setValue(next); setState('');
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(async () => {
      try { await hermesApi.setAgentPrefs(next); setState('Saved'); void reloadAgent(); } catch { setState('Could not save'); }
    }, 500);
  };
  return <section className="mix">
    <h3>Idea mix</h3>
    <p className="mix-note">How many of the agent’s ideas are talking reels you film yourself, and how many the editor produces from scratch.</p>
    <input className="mix-range" type="range" min="0" max="100" step="5" value={value} onChange={(e) => change(Number(e.target.value))} aria-label="Share of talking ideas" style={{ '--v': `${value}%` }}/>
    <div className="mix-legend"><span><b>{value}%</b> Talking<small>you film</small></span><span>Produced<small>the editor makes it</small><b>{100 - value}%</b></span></div>
    {state ? <small className="mix-state" role="status">{state}</small> : null}
  </section>;
}

// Accounts, connected apps and the advanced credentials live here, not in tabs of their own.
export default function HermesSettingsPage() {
  return <>
    <IdeaMix />
    <section><HermesConnect /></section>
    <section><HermesSettings /></section>
  </>;
}
