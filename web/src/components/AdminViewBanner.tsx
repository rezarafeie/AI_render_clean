import React from "react";
import { useNavigate } from "react-router-dom";
import { getAdminViewAs, setAdminViewAs } from "../api";

/** Shown while an administrator works in a user's chat from the admin lists: it says whose chat this is, that actions run as that user, and leads back. */
export function AdminViewBanner() {
  const navigate = useNavigate();
  const [viewing, setViewing] = React.useState(getAdminViewAs());
  React.useEffect(() => { const sync = () => setViewing(getAdminViewAs()); window.addEventListener("storage", sync); return () => window.removeEventListener("storage", sync); }, []);
  if (!viewing) return null;
  return <div className="admin-view-banner" role="status">
    <span>{`حالت مدیر: داخل چتِ کاربر #${viewing} هستید؛ هر کاری اینجا بکنید (ارسال، ویرایش، تأیید) به نام همین کاربر و با اعتبار او انجام می‌شود.`}</span>
    <button className="btn btn-sm btn-secondary" onClick={() => { setAdminViewAs(null); setViewing(""); navigate("/settings/users"); window.setTimeout(() => window.location.reload(), 50); }}>Back to admin</button>
  </div>;
}
