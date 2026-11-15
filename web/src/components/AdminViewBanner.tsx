import React from "react";
import { useNavigate } from "react-router-dom";
import { getAdminViewAs, setAdminViewAs } from "../api";

/** Shown while an administrator reads a user's chat from the admin lists: it says whose chat this is, that nothing can be changed, and leads back. */
export function AdminViewBanner() {
  const navigate = useNavigate();
  const [viewing, setViewing] = React.useState(getAdminViewAs());
  React.useEffect(() => { const sync = () => setViewing(getAdminViewAs()); window.addEventListener("storage", sync); return () => window.removeEventListener("storage", sync); }, []);
  if (!viewing) return null;
  return <div className="admin-view-banner" role="status">
    <span>{`Admin view: you are reading the chat of user #${viewing} (read-only).`}</span>
    <button className="btn btn-sm btn-secondary" onClick={() => { setAdminViewAs(null); setViewing(""); navigate("/settings/users"); window.setTimeout(() => window.location.reload(), 50); }}>Back to admin</button>
  </div>;
}
