/** Completion comes from an owned Studio artifact, never from a chat claim. */
export function proposalStatus(proposal, observedStatus) {
  return proposal.status === 'in_production' ? observedStatus || proposal.status : proposal.status;
}

export function productionStatus(conversation, motion) {
  if (conversation?.state?.motion?.motion_id) {
    if (motion?.status === 'completed' && motion.versions?.some(v => v.n === motion.current)) return 'produced';
    if (motion?.status === 'failed') return 'failed';
    return 'in_production';
  }
  const projects = conversation?.projects || [];
  const project = projects.find(p => p.id === conversation?.state?.current_project_id) || projects.at(-1);
  if (project?.status === 'done' && project.state?.last_observed?.output) return 'produced';
  if (project?.status === 'needs_review' || (project?.status !== 'running' && project?.state?.candidate_output)) return 'needs_review';
  if (project?.status === 'error') return 'failed';
  if (project?.status === 'awaiting_confirmation') return 'awaiting_confirmation';
  return 'in_production';
}
