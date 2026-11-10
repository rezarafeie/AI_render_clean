import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const source = readFileSync(new URL('../src/Settings.tsx', import.meta.url), 'utf8');

test('settings are grouped into tabs, and nothing that existed was removed', () => {
  for (const part of ['<InstallationSettings/>', '<AgentSettings/>', '<DeviceSettings/>', '<IntegrationsSettings/>', 'id="set-appearance"', 'id="set-account"', 'id="set-admin"', '`set-g${index}`'])
    assert.ok(source.includes(part), `${part} must still be on the settings page`);
  for (const link of ['/new', '/content', '/talking', '/localize', '/my-effects', '/style-library', '/style-learner', '/library', '/hermes', '/settings/ai', '/settings/users', '/motion-library'])
    assert.ok(source.includes(`"${link}"`), `${link} must still be reachable`);
  for (const tab of ['general', 'assistant', 'connections', 'tools', 'admin']) assert.ok(source.includes(`id: "${tab}"`));
});

test('an old #editing link opens the assistant tab and the language can be chosen', () => {
  assert.match(source, /wanted === "editing" \? "assistant"/);
  assert.match(source, /setLang\("fa"\)/);
});

test('an old deep link to the connected services still opens the right tab', () => {
  assert.match(source, /wanted === "integrations" \? "connections"/);
});
