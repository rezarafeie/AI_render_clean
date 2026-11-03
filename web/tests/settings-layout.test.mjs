import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const source = readFileSync(new URL('../src/Settings.tsx', import.meta.url), 'utf8');

test('settings are grouped into tabs, and nothing that existed was removed', () => {
  for (const part of ['<InstallationSettings/>', '<AgentSettings/>', '<DeviceSettings/>', '<IntegrationsSettings/>', 'id="set-appearance"', 'id="set-account"', 'id="set-admin"', '`set-g${index}`'])
    assert.ok(source.includes(part), `${part} must still be on the settings page`);
  for (const link of ['/new', '/content', '/talking', '/localize', '/my-effects', '/style-library', '/style-learner', '/library', '/hermes', '/settings/ai'])
    assert.ok(source.includes(`"${link}"`), `${link} must still be reachable`);
  for (const tab of ['general', 'editing', 'connections', 'tools']) assert.ok(source.includes(`id: "${tab}"`));
});

test('an old deep link to the connected services still opens the right tab', () => {
  assert.match(source, /wanted === "integrations" \? "connections"/);
});
