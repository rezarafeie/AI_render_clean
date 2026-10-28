import HermesConnect from './HermesConnect';
import HermesSettings from './HermesSettings';

// Accounts, connected apps and the advanced credentials live here, not in tabs of their own.
export default function HermesSettingsPage() {
  return <>
    <section><HermesConnect /></section>
    <section><HermesSettings /></section>
  </>;
}
