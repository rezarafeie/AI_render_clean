import test from 'node:test';
import assert from 'node:assert/strict';
import {productionStatus, proposalStatus} from '../src/pages/hermes/ideaProduction.js';

test('observed production status never overrides explicit publishing or rejection decisions', () => {
  for (const status of ['rejected', 'queued', 'proposed', 'produced']) {
    assert.equal(proposalStatus({status}, 'in_production'), status);
    assert.equal(proposalStatus({status}, 'produced'), status);
  }
  assert.equal(proposalStatus({status:'in_production'}, 'produced'), 'produced');
  assert.equal(proposalStatus({status:'in_production'}, undefined), 'in_production');
});

test('ready requires the current real motion artifact, not an assistant promise', () => {
  const c={state:{motion:{motion_id:'owned'}}};
  assert.equal(productionStatus(c,{status:'completed',current:2,versions:[{n:1}]}),'in_production');
  assert.equal(productionStatus(c,{status:'completed',current:2,versions:[{n:2}]}),'produced');
  assert.equal(productionStatus(c,{status:'rendering',current:1,versions:[{n:1}]}),'in_production');
  assert.equal(productionStatus(c,{status:'failed'}),'failed');
});

test('current project approval, failure and missing output never claim ready', () => {
  const c={state:{current_project_id:'p'},projects:[{id:'old',status:'done',state:{last_observed:{output:'/old'}}},{id:'p',status:'awaiting_confirmation',state:{}}]};
  assert.equal(productionStatus(c),'awaiting_confirmation');
  c.projects[1].status='done';
  assert.equal(productionStatus(c),'in_production');
  c.projects[1].state.last_observed={output:'/ready'};
  assert.equal(productionStatus(c),'produced');
  c.projects[1].status='error';
  assert.equal(productionStatus(c),'failed');
});
