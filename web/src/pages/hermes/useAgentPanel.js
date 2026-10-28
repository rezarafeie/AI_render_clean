import { useCallback, useRef, useState } from 'react';
import { usePanelWidth } from '../../components/Resizer';
import { useStudioLayout } from '../../components/hooks';
import { usePanelFullscreen } from '../../studio/Workspace';

const BOUNDS = { min: 340, max: 900 };
const lsGet = (key, fallback) => { try { return localStorage.getItem(key) ?? fallback; } catch { return fallback; } };
const lsSet = (key, value) => { try { localStorage.setItem(key, value); } catch { /* optional */ } };

/** The side panel of a Hermes page behaves like the Studio's preview panel: open/closed (remembered), resizable, full screen,
 *  an overlay on narrow screens and the whole screen on phones. */
export function useAgentPanel(storageKey) {
  const layout = useStudioLayout();                                        // desktop | tablet | mobile
  const [desktopOpen, setDesktopOpen] = useState(() => lsGet(`editorgpt.hermes.${storageKey}`, 'open') !== 'closed');
  const [overlay, setOverlay] = useState(false);
  const studioRef = useRef(null);
  const panelRef = useRef(null);
  const [saved, setSaved] = usePanelWidth('editorgpt.hermes.agent.width', BOUNDS);
  const [live, setLive] = useState(null);
  const [resizing, setResizing] = useState(false);
  const fullscreen = usePanelFullscreen();
  const setNode = useCallback((element) => { panelRef.current = element; fullscreen.node.current = element; }, [fullscreen.node]);
  const visible = layout === 'desktop' ? desktopOpen : overlay;
  const open = useCallback(() => { if (layout === 'desktop') { setDesktopOpen(true); lsSet(`editorgpt.hermes.${storageKey}`, 'open'); } else setOverlay(true); }, [layout, storageKey]);
  const close = useCallback(() => { if (layout === 'desktop') { setDesktopOpen(false); lsSet(`editorgpt.hermes.${storageKey}`, 'closed'); } else setOverlay(false); }, [layout, storageKey]);
  return { layout, visible, open, close, studioRef, panelRef, setNode, fullscreen, width: live ?? saved, setSaved, setLive, setResizing, resizing, bounds: BOUNDS, closeOverlay: () => setOverlay(false), overlay };
}
