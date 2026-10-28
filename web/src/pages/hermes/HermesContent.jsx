import { useState } from 'react';
import HermesScheduler from './HermesScheduler';
import HermesContentPlan from './HermesContentPlan';

// One tab for what gets published: the calendar/queue and the plan that fills it.
export default function HermesContent() {
  const [view, setView] = useState(() => { try { return localStorage.getItem('hermes:content') || 'calendar'; } catch { return 'calendar'; } });
  const pick = (next) => { setView(next); try { localStorage.setItem('hermes:content', next); } catch { /* optional */ } };
  return <>
    <div className="hs-seg-row">
      <div className="tabs-bar" role="tablist">
        <button type="button" role="tab" aria-selected={view === 'calendar'} className="tab" onClick={() => pick('calendar')}>Calendar & queue</button>
        <button type="button" role="tab" aria-selected={view === 'plan'} className="tab" onClick={() => pick('plan')}>Content plan</button>
      </div>
    </div>
    {view === 'calendar' ? <HermesScheduler /> : <HermesContentPlan />}
  </>;
}
