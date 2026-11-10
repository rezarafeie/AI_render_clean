import { Link } from 'react-router-dom';
import { Icon } from '../../components/Icon';
import AgentSkills from './AgentSkills';

/** Skills of the Instagram agent as a page of the studio: competitors, benchmark table, and the thirteen skills. */
export default function HermesSkillsPage() {
  return <div className="studio-home hermes-home hs-page" data-hermes-main>
    <div className="home-inner" dir="rtl">
      <div className="hs-page-head"><Link to="/hermes" className="btn btn-sm btn-ghost"><Icon name="chevron" size={14}/>بازگشت</Link><h1>مهارت‌ها</h1></div>
      <AgentSkills />
    </div>
  </div>;
}
