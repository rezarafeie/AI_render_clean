import { Link } from 'react-router-dom';
import hermesApi from '../../services/hermesApi';
import { Icon } from '../../components/Icon';
import { array, number } from './hermesUtils';
import { useHermesData } from './hermesCache';
import { useHermes } from './HermesContext';
import AgentIdeas from './AgentIdeas';
import AgentInsights from './AgentInsights';

const ENGINE = { talking: 'صحبتی', explainer: 'اکسپلینر' };

function Stat({ icon, label, children, note }) {
  return <div className="ov-stat"><div className="ov-stat-top"><span>{label}</span><Icon name={icon} size={16}/></div>{children}{note ? <small className="ov-sub">{note}</small> : null}</div>;
}

export default function HermesOverview() {
  const { agent, runAgent } = useHermes();
  const posts = useHermesData('posts', () => hermesApi.getPosts());
  const list = array(posts.data);
  const upcoming = list.filter((p) => p.status === 'scheduled' && new Date(p.scheduled_at) > new Date()).sort((a, b) => new Date(a.scheduled_at) - new Date(b.scheduled_at)).slice(0, 5);
  const profile = agent?.profile;
  const analysis = agent?.analysis;
  const proposals = array(agent?.proposals);
  const ideas = proposals.filter((p) => p.status === 'proposed');
  const making = proposals.filter((p) => p.status === 'in_production').length;
  const media = array(agent?.media).slice(0, 5);
  const score = analysis?.profile?.score;
  const running = agent?.run?.status === 'running';
  return <>
    <section className="ov-hero">
      <div className="ov-avatar" aria-hidden="true">{(profile?.username || '?').slice(0, 1).toUpperCase()}</div>
      <div className="ov-who">
        <strong dir="ltr">{profile ? `@${profile.username}` : 'Reading your page…'}</strong>
        <span className="ov-sub">{profile ? [profile.followers != null && `${number(profile.followers)} followers`, profile.follows != null && `${number(profile.follows)} following`, profile.media_count != null && `${number(profile.media_count)} posts`].filter(Boolean).join(' · ') : 'The agent is connecting to your account'}</span>
        <span className="ov-pill">Connected · read-only</span>
      </div>
      <div className="hs-seg-row">
        <button className="btn btn-secondary btn-sm" type="button" onClick={() => runAgent()} disabled={running}><Icon name="refresh" size={15}/>{running ? 'Reviewing…' : 'New review'}</button>
        <Link className="btn btn-sm" to="/hermes/post/new"><Icon name="plus" size={15}/>New post</Link>
      </div>
    </section>

    <section className="ov-stats">
      <Stat icon="user" label="Followers"><strong>{profile?.followers != null ? number(profile.followers) : '—'}</strong></Stat>
      <Stat icon="film" label="Posts"><strong>{profile?.media_count != null ? number(profile.media_count) : '—'}</strong></Stat>
      <Stat icon="spark" label="Profile score" note={analysis ? 'from the agent’s review' : 'review in progress'}>
        <div className="hs-seg-row"><strong>{score != null ? `${score}` : '—'}</strong>{score != null ? <div className="ov-ring" style={{ '--v': score }}><span>{score}</span></div> : null}</div></Stat>
      <Stat icon="wand" label="Ideas waiting" note={making ? `${making} in production` : undefined}><strong>{number(ideas.length)}</strong></Stat>
    </section>

    <section className="ov-card" dir="auto">
      <h3>What the agent found</h3>
      {analysis ? <>
        {analysis.strategy ? <p>{[analysis.strategy.niche, analysis.strategy.audience].filter(Boolean).join(' · ')}</p> : null}
        {array(analysis.content?.do_more).length ? <div><span className="ov-sub">Do more</span><div className="ov-chips">{array(analysis.content.do_more).slice(0, 4).map((x) => <span key={x} className="ov-chip is-good">{x}</span>)}</div></div> : null}
        {array(analysis.content?.stop).length ? <div><span className="ov-sub">Stop</span><div className="ov-chips">{array(analysis.content.stop).slice(0, 4).map((x) => <span key={x} className="ov-chip is-bad">{x}</span>)}</div></div> : null}
        <details><summary className="ov-sub">Full review and questions</summary><AgentInsights embedded /></details>
      </> : <p className="ov-sub">The agent is reading your profile and recent posts. The first review takes a few minutes.</p>}
    </section>

    <section className="ov-card">
      <h3>Ideas for the editor</h3>
      <AgentIdeas limit={3} embedded />
    </section>

    <section className="ov-grid">
      <div className="ov-card">
        <h3>Up next <Link className="btn btn-ghost btn-sm" to="/hermes/content">Open content</Link></h3>
        {upcoming.length ? <ul className="ov-list">{upcoming.map((p) => <li key={p.id}><span dir="auto">{(p.caption || 'Untitled').slice(0, 56)}</span><small className="ov-sub">{new Date(p.scheduled_at).toLocaleDateString()}</small></li>)}</ul>
          : <p className="ov-sub">Nothing scheduled yet.</p>}
      </div>
      <div className="ov-card">
        <h3>Recent posts</h3>
        {media.length ? <ul className="ov-list">{media.map((m) => <li key={m.id}><span dir="auto">{(m.caption || '(no caption)').slice(0, 56)}</span><small className="ov-sub">{m.likes ?? '?'} ♥ · {m.comments ?? '?'} 💬</small></li>)}</ul>
          : <p className="ov-sub">Posts appear after the first review.</p>}
      </div>
    </section>
  </>;
}
