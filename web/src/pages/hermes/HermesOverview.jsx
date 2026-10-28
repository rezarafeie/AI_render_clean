import { Link } from 'react-router-dom';
import hermesApi from '../../services/hermesApi';
import { array, number } from './hermesUtils';
import { useHermesData } from './hermesCache';
import { useHermes } from './HermesContext';

function Stat({ label, value, note }) {
  return <div className="hs-stat"><span className="hs-muted">{label}</span><strong>{value}</strong>{note && <small className="hs-muted">{note}</small>}</div>;
}

export default function HermesOverview() {
  const { agent, openAgent, runAgent } = useHermes();
  const posts = useHermesData('posts', () => hermesApi.getPosts());
  const list = array(posts.data);
  const upcoming = list.filter((p) => p.status === 'scheduled' && new Date(p.scheduled_at) > new Date()).sort((a, b) => new Date(a.scheduled_at) - new Date(b.scheduled_at)).slice(0, 5);
  const profile = agent?.profile;
  const analysis = agent?.analysis;
  const proposals = array(agent?.proposals);
  const waiting = proposals.filter((p) => p.status === 'proposed').length;
  const making = proposals.filter((p) => p.status === 'in_production').length;
  const media = array(agent?.media).slice(0, 6);
  return <div className="hs-page">
    <section className="hs-stats">
      <Stat label="Followers" value={profile?.followers != null ? number(profile.followers) : '—'} note={profile ? `@${profile.username}` : undefined} />
      <Stat label="Posts" value={profile?.media_count != null ? number(profile.media_count) : '—'} />
      <Stat label="Profile score" value={analysis?.profile?.score != null ? `${analysis.profile.score}/100` : '—'} note={analysis ? 'from the agent' : 'agent is reading your page'} />
      <Stat label="Ideas waiting" value={number(waiting)} note={making ? `${making} in production` : undefined} />
    </section>
    <section className="hs-grid">
      <div className="hs-card" dir="auto">
        <div className="hs-card-head"><strong>What the agent found</strong><button className="btn btn-ghost btn-sm" type="button" onClick={openAgent}>Open agent</button></div>
        {analysis ? <>
          {analysis.strategy && <p>{[analysis.strategy.niche, analysis.strategy.audience].filter(Boolean).join(' · ')}</p>}
          {array(analysis.content?.do_more).length > 0 && <p><strong>Do more:</strong> {array(analysis.content.do_more).slice(0, 3).join('، ')}</p>}
          {array(analysis.content?.stop).length > 0 && <p><strong>Stop:</strong> {array(analysis.content.stop).slice(0, 3).join('، ')}</p>}
          {array(analysis.data_gaps).length > 0 && <p className="hs-muted">{array(analysis.data_gaps).slice(0, 2).join('؛ ')}</p>}
        </> : <p className="hs-muted">The agent is reading your profile and recent posts. This takes a few minutes the first time.</p>}
        <div className="hs-row"><button className="btn btn-secondary btn-sm" type="button" onClick={() => runAgent()}>Run a new review</button></div>
      </div>
      <div className="hs-card">
        <div className="hs-card-head"><strong>Up next</strong><Link className="btn btn-ghost btn-sm" to="/hermes/content">Open content</Link></div>
        {upcoming.length ? <ul className="hs-plain">{upcoming.map((p) => <li key={p.id}><span dir="auto">{(p.caption || 'Untitled').slice(0, 60)}</span><small className="hs-muted">{new Date(p.scheduled_at).toLocaleString()}</small></li>)}</ul>
          : <p className="hs-muted">Nothing scheduled. Approve an idea from the agent, then make it in the editor.</p>}
      </div>
    </section>
    {media.length > 0 && <section className="hs-card">
      <div className="hs-card-head"><strong>Recent posts</strong></div>
      <ul className="hs-plain">{media.map((m) => <li key={m.id}><span dir="auto">{(m.caption || '(no caption)').slice(0, 90)}</span><small className="hs-muted">{m.likes ?? '?'} likes · {m.comments ?? '?'} comments</small></li>)}</ul>
    </section>}
  </div>;
}
