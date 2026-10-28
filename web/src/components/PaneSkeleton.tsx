/** What the content area shows while a page's code arrives: the shell stays, only this pane is a placeholder. */
export default function PaneSkeleton() {
  return <div className="pane-skeleton" role="status" aria-label="Loading"><span/><span/><span/><span/></div>;
}
