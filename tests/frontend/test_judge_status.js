// Run with: node --test tests/frontend/test_judge_status.js
const { readFileSync } = require('node:fs');
const { resolve } = require('node:path');
const vm = require('node:vm');
const test = require('node:test');
const assert = require('node:assert/strict');
const context = vm.createContext({ escHtml: (value) => String(value ?? '').replaceAll('<', '&lt;').replaceAll('>', '&gt;') });
vm.runInContext(readFileSync(resolve(__dirname, '../../thesis-dm-frontend/judge-status.js'), 'utf8'), context);
const full = (valid = true) => ({ status: 'FULL', verdict: valid ? 'valid' : 'invalid', provider: 'codex', model: 'test', ok: { vocative: valid, register: true, gender: true } });

test('model colours distinguish valid, partial, invalid, error and not run', () => {
    assert.equal(context.uc01ModelStatus(full()), 'valid');
    assert.equal(context.uc01ModelStatus(full(false)), 'invalid');
    assert.equal(context.uc01ModelStatus({ ...full(), status: 'PARTIAL' }), 'partial');
    assert.equal(context.uc01ModelStatus({ status: 'MALFORMED' }), 'error');
    assert.equal(context.uc01ModelStatus(null), 'not-run');
});
test('pair requires matching booleans, not just matching final verdicts', () => {
    assert.equal(context.uc01PairStatus([full(), full()]), 'valid');
    assert.equal(context.uc01PairStatus([full(false), full(false)]), 'invalid');
    assert.equal(context.uc01PairStatus([full(), full(false)]), 'partial');
    assert.equal(context.uc01PairStatus([full()]), 'not-run');
});
test('each selected stage is visible, with arbiter and human routing preserved', () => {
    const judgment = { judges: [full(), { ...full(), status: 'PARTIAL' }], arbiter: full(false), final: 'HUMAN' };
    const html = context.uc01JudgeTrailHtml({ accepted: true }, judgment, { level: 3, judges: [] });
    for (const level of [0, 1, 2, 3]) assert.ok(html.includes(`Úroveň ${level}`));
    for (const status of ['valid', 'partial', 'invalid']) assert.ok(html.includes(`judge-status-${status}`));
    assert.ok(html.includes('rozhodne člověk'));
});
test('unnecessary escalation is not displayed as a performed judgment', () => {
    const html = context.uc01JudgeTrailHtml({ accepted: true }, { judges: [full(), full()], final: 'VALID' }, { level: 3 });
    assert.ok(html.includes('Nebylo potřeba'));
    assert.ok(html.includes('judge-status-not-run'));
});
test('rules only and rule rejection never manufacture model verdicts', () => {
    assert.ok(!context.uc01JudgeTrailHtml({ accepted: true }, null, null).includes('Úroveň 1'));
    const html = context.uc01JudgeTrailHtml({ accepted: false }, null, { level: 3 });
    assert.ok(html.includes('judge-status-invalid'));
    assert.ok(!html.includes('judge-status-valid'));
});
test('model identifiers are escaped and old picker settings remain readable', () => {
    const html = context.uc01JudgeTrailHtml(null, { judges: [{ ...full(), model: '<script>' }] }, { level: 1 });
    assert.ok(!html.includes('<script>'));
    assert.equal(context.uc01JudgeChoice({ provider: 'agy' }).level, 1);
});
