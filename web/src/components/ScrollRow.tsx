import React from "react";
import { Icon } from "./Icon";

/**
 * A row that scrolls sideways and says so: a fade on the side where more is hidden and a small arrow that moves on by most of a screen.
 * Both disappear on their own when the row is fully visible or the end is reached.
 */
export function ScrollRow({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  const ref = React.useRef<HTMLDivElement>(null);
  const [more, setMore] = React.useState({ start: false, end: false });
  const update = React.useCallback(() => {
    const el = ref.current;
    if (!el) return;
    const room = el.scrollWidth - el.clientWidth, at = Math.abs(el.scrollLeft);
    setMore(previous => previous.start === (at > 4) && previous.end === (at < room - 4) ? previous : { start: at > 4, end: at < room - 4 });
  }, []);
  React.useLayoutEffect(update, [update, children]);
  React.useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const watcher = typeof ResizeObserver === "function" ? new ResizeObserver(update) : null;
    watcher?.observe(el);
    window.addEventListener("resize", update);
    return () => { watcher?.disconnect(); window.removeEventListener("resize", update); };
  }, [update]);
  return <div className="scroll-row" data-start={more.start || undefined} data-end={more.end || undefined}>
    <div ref={ref} className={`chip-row home-chips ${className}`.trim()} onScroll={update}>{children}</div>
    {more.end ? <button type="button" className="scroll-row-next" aria-label="Show more" onClick={() => ref.current?.scrollBy({ left: Math.max(160, ref.current.clientWidth * 0.7), behavior: "smooth" })}><Icon name="chevron" size={16}/></button> : null}
  </div>;
}
