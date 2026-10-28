import { Link } from 'react-router-dom';
import hermesApi from '../../services/hermesApi';
import { Icon } from '../../components/Icon';
import { array, number } from './hermesUtils';
import { useHermesData } from './hermesCache';
import { useHermes } from './HermesContext';
import AgentIdeas from './AgentIdeas';
import AgentInsights from './AgentInsights';

const ENGINE = { talking: 'صحبتی', explainer: 'اکسپلینر' };

const compact = (value) => (value == null ? '—' : new Intl.NumberFormat('en', { notation: 'compact', maximumFractionDigits: 1 }).format(value));

function Stat({ label, value, ring }) {
  return <div className="ov-stat"><span className="ov-sub">{label}</span><strong>{value}</strong>{ring != null ? <div className="ov-ring" style={{ '--v': ring }} aria-hidden="true"/> : null}</div>;
}

/** The home page's account summary: a compact profile line, three numbers and short lists, in the manner of an app, not a dashboard. */
export default function HermesOverview() {
  const { agent, runAgent } = useHermes();
  const posts = useHermesData('posts', () => hermesApi.getPosts());
  const list = array(posts.data);
  const upcoming = list.filter((p) => p.status === 'scheduled' && new Date(p.scheduled_at) > new Date()).sort((a, b) => new Date(a.scheduled_at) - new Date(b.scheduled_at)).slice(0, 3);
  const profile = agent?.profile;
  const analysis = agent?.analysis;
  const media = array(agent?.media).slice(0, 4);
  const score = analysis?.profile?.score;
  const running = agent?.run?.status === 'running';
  const found = analysis && (array(analysis.content?.do_more).length || array(analysis.content?.stop).length || analysis.strategy);
  return <div className="ov">
    <section className="ov-profile">
      <div className="ov-avatar" aria-hidden="true">{(profile?.username || '?').slice(0, 1).toUpperCase()}</div>
      <div className="ov-who">
        <strong dir="ltr">{profile ? `@${profile.username}` : 'Reading your page…'}</strong>
        <span className="ov-sub"><i className="ov-dot" aria-hidden="true"/>Connected · read-only</span>
      </div>
      <button className="icon-btn" type="button" onClick={() => runAgent()} disabled={running} aria-label={running ? 'Reviewing' : 'New review'} data-tip={running ? 'Reviewing…' : 'New review'} data-busy={running || undefined}><Icon name="refresh" size={19}/></button>
    </section>

    <section className="ov-stats" aria-label="Account">
      <Stat label="Followers" value={compact(profile?.followers)} />
      <Stat label="Posts" value={compact(profile?.media_count)} />
      <Stat label="Score" value={score != null ? score : '—'} ring={score} />
    </section>

    {found ? <section className="ov-block" dir="auto">
      <h3>What the agent found</h3>
      {analysis.strategy ? <p>{[analysis.strategy.niche, analysis.strategy.audience].filter(Boolean).join(' · ')}</p> : null}
      <div className="ov-chips">
        {array(analysis.content?.do_more).slice(0, 3).map((x) => <span key={x} className="ov-chip is-good">{x}</span>)}
        {array(analysis.content?.stop).slice(0, 3).map((x) => <span key={x} className="ov-chip is-bad">{x}</span>)}
      </div>
      <details><summary className="ov-sub">Full review</summary><AgentInsights embedded /></details>
    </section> : !analysis ? <p className="ov-note">{running ? 'The agent is reading your profile and recent posts. The first review takes a few minutes.' : 'No review yet. Tap refresh to start one.'}</p> : null}

    <section className="ov-block">
      <h3>Ideas for the editor</h3>
      <AgentIdeas limit={3} embedded />
    </section>

    {upcoming.length ? <section className="ov-block">
      <h3>Up next <Link to="/hermes/content">All</Link></h3>
      <ul className="ov-list">{upcoming.map((p) => <li key={p.id}><span dir="auto">{(p.caption || 'Untitled').slice(0, 56)}</span><small className="ov-sub">{new Date(p.scheduled_at).toLocaleDateString()}</small></li>)}</ul>
    </section> : null}

    {media.length ? <section className="ov-block">
      <h3>Recent posts</h3>
      <ul className="ov-list">{media.map((m) => <li key={m.id}><span dir="auto">{(m.caption || '(no caption)').slice(0, 56)}</span>{m.likes != null || m.comments != null ? <small className="ov-sub">{m.likes ?? '–'} ♥ · {m.comments ?? '–'} 💬</small> : null}</li>)}</ul>
    </section> : null}
  </div>;
}
