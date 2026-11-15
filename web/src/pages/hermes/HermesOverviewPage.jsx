import { Link } from 'react-router-dom';
import { Icon } from '../../components/Icon';
import HermesOverview from './HermesOverview';

/** The page itself: profile, numbers, the agent's findings, ideas for the editor. */
export default function HermesOverviewPage() {
  return <div className="studio-home hermes-home hs-page" data-hermes-main>
    <div className="home-inner">
      <div className="hs-page-head"><Link to="/insta" className="btn btn-sm btn-ghost"><Icon name="chevron" size={14}/>بازگشت</Link><h1>پیج من</h1></div>
      <div className="hs-home-overview"><HermesOverview /></div>
    </div>
  </div>;
}
