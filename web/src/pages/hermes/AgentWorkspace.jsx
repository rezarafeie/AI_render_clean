import { Icon } from '../../components/Icon';
import { Resizer } from '../../components/Resizer';

const MIN_CONTENT = 520;

/** The right-hand panel: the Studio's own workspace chrome (same classes, resizer, full screen, hide) around the given tabs. */
export default function AgentWorkspace({ panel, label, tabs, tab, onTab, actions, children }) {
  const { layout, fullscreen, studioRef, panelRef, width, bounds, setLive, setSaved, setResizing, visible, close } = panel;
  return <section className="workspace" ref={panel.setNode} data-max={fullscreen.active || undefined} aria-label={label}>
    {layout === 'desktop' && visible ? <Resizer panel={panelRef} edge="start" label="عرض پنل ایجنت" width={width}
      bounds={() => ({ min: bounds.min, max: Math.min(bounds.max, (studioRef.current?.clientWidth ?? 1400) - MIN_CONTENT) })}
      onResize={setLive} onDragState={setResizing} onCommit={(next) => { setSaved(next); setLive(null); }}/> : null}
    <header className="ws-head hs-ws-head">
      <div className="tabs-bar hs-ws-tabs" role="tablist" aria-label={label}>
        {tabs.map(([id, text, icon, badge]) => <button key={id} role="tab" aria-selected={tab === id} className="tab" onClick={() => onTab(id)} title={text}>
          <Icon name={icon} size={15}/><span className="hs-tab-text">{text}</span>{badge ? <span className="hs-badge">{badge}</span> : null}</button>)}
      </div>
      <span className="grow"/>
      {actions}
      <button className="icon-btn" onClick={() => void fullscreen.toggle()} aria-pressed={fullscreen.active} aria-label={fullscreen.active ? 'Exit full screen' : 'Full screen'}
        data-tip={fullscreen.active ? 'Exit full screen' : 'Full screen'}><Icon name={fullscreen.active ? 'fullscreenExit' : 'fullscreen'} size={19}/></button>
      <button className="icon-btn" onClick={close} aria-label="Hide agent" data-tip="Hide agent"><Icon name={layout === 'desktop' ? 'panelRight' : 'close'} size={19}/></button>
    </header>
    <div className="ws-body hs-agent-body">{children}</div>
  </section>;
}
