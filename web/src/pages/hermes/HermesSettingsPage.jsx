import HermesConnect from './HermesConnect';
import HermesSettings from './HermesSettings';

// Accounts, connected apps and the advanced credentials live here, not in tabs of their own.
export default function HermesSettingsPage() {
  return <div className="hs-page">
    <section className="hs-section"><h2>Accounts</h2><HermesConnect /></section>
    <section className="hs-section"><h2>Connected apps</h2><HermesSettings /></section>
  </div>;
}
