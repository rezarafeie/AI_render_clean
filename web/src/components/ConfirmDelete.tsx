import React from "react";
import { Sheet } from "./Sheet";
import { Icon } from "./Icon";
import { friendlyError } from "../ui";

export interface DeleteTarget { title: string; what: string; detail?: string; run: () => Promise<unknown> }

/** The one confirmation for every deletion (a chat, a project, a file, an idea): says what goes, asks once, shows why it failed (for example "still working"). */
export function ConfirmDelete({ target, onClose, onDone }: { target: DeleteTarget | null; onClose: () => void; onDone?: () => void }) {
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");
  React.useEffect(() => { setError(""); setBusy(false); }, [target]);
  async function confirm() {
    if (!target) return;
    setBusy(true); setError("");
    try { await target.run(); onClose(); onDone?.(); }
    catch (e) { setError(friendlyError(e, "delete this")); setBusy(false); }
  }
  return <Sheet open={target !== null} onClose={() => { if (!busy) onClose(); }} label={target?.title || "Delete"}>
    {target ? <div className="confirm-delete" dir="auto">
      <span className="confirm-delete-icon" aria-hidden="true"><Icon name="trash" size={22}/></span>
      <h2>{target.title}</h2>
      <p className="confirm-delete-what" dir="auto">{target.what}</p>
      {target.detail ? <p className="field-hint">{target.detail}</p> : null}
      {error ? <p className="notice" data-tone="error" role="alert">{error}</p> : null}
      <div className="confirm-delete-actions">
        <button type="button" className="btn btn-secondary" onClick={onClose} disabled={busy}>Cancel</button>
        <button type="button" className="btn btn-danger" onClick={() => void confirm()} disabled={busy} autoFocus>{busy ? "Deleting…" : "Delete"}</button>
      </div>
    </div> : null}
  </Sheet>;
}
