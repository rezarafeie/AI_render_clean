import { Link } from 'react-router-dom';
import { Icon } from '../../components/Icon';
import AgentInsights from './AgentInsights';

/** What the agent understood about the page, its open questions and the saved answers, as a page of the studio. */
export default function HermesInsightsPage() {
  return <div className="studio-home hermes-home hs-page" data-hermes-main>
    <div className="home-inner" dir="rtl">
      <div className="hs-page-head"><Link to="/insta" className="btn btn-sm btn-ghost"><Icon name="chevron" size={14}/>بازگشت</Link><h1>بینش‌ها</h1></div>
      <AgentInsights embedded />
    </div>
  </div>;
}
