import assert from 'node:assert/strict';
import { test } from 'node:test';
import { recoverOnce, recoveryDecision } from '../scripts/research_capacity_recovery.mjs';

const snapshot = { id: 'owner', status: 'error', activeTurn: null,
  lastError: 'Selected model is at capacity. Please try a different model.',
  persistence: { sessionId: 'same-session' }, lastUserMessageAt: '2026-10-26T07:00:00Z' };
const config = { owner_agent_id: 'manager', active_research_owners: ['owner'],
  active_research_peers: [], active_research_scope_keys: ['task'], soft_pause_at_used_percent: 70,
  model_capacity_recovery: { enabled: true, root_bridge_agent_id: 'root', backoff_minutes: [30, 60, 120] } };
const authority = { research_allowed: true, research_new_starts_allowed: true,
  task: { allowed: true, owner: 'owner' } };
const quota = { available: true, used_percent: 2 };
const decide = (s = snapshot, a = authority, previous = null, q = quota, now = 0) =>
  recoveryDecision(s, previous, config, a, q, now);

test('only the exact terminal capacity fault is recoverable', () => {
  assert.equal(decide().action, 'retry');
  for (const s of [{ ...snapshot, status: 'running', activeTurn: {} },
    { ...snapshot, status: 'idle' }, { ...snapshot, status: 'canceled' },
    { ...snapshot, pendingPermissions: [{}] }, { ...snapshot, archivedAt: 'today' },
    { ...snapshot, lastError: 'insufficient_quota' },
    { ...snapshot, lastError: 'Permission denied' },
    { ...snapshot, lastError: '429 rate limit exceeded' }]) assert.equal(decide(s).action, 'skip');
});

test('research, progress, task and total quota holds take precedence', () => {
  for (const a of [{ ...authority, research_allowed: false },
    { ...authority, research_new_starts_allowed: false },
    { ...authority, research_quota_pause_20261023: {} },
    { ...authority, research_progress_checkpoint_pause: {} },
    { ...authority, task: { ...authority.task, allowed: false } }]) {
    assert.equal(decide(snapshot, a).action, 'skip');
  }
  assert.equal(decide(snapshot, authority, null, { available: true, used_percent: 70 }).action, 'skip');
});

test('deduplication and exponential backoff survive new capacity failures', () => {
  const first = decide();
  assert.equal(first.not_before_ms, 30 * 60_000);
  assert.equal(decide(snapshot, authority, first, quota, 9999999).reason, 'failure_already_attempted');
  const next = { ...snapshot, lastUserMessageAt: '2026-10-26T07:01:00Z' };
  assert.equal(decide(next, authority, first, quota, 1).reason, 'backoff');
  const second = decide(next, authority, first, quota, first.not_before_ms);
  assert.equal(second.not_before_ms, 90 * 60_000);
  assert.equal(decide(next, authority, { ...first, transport: 'unknown' }, quota, 9999999).reason,
    'delivery_unknown_needs_reception');
});

function mockRun({ snapshots = [snapshot], context = { config, authority, quota }, fail = false } = {}) {
  let index = 0;
  const sent = [], saved = [], state = {};
  const client = { fetchAgent: async ({ agentId }) => {
    if (agentId !== 'owner') return { agent: { id: agentId, status: 'running', activeTurn: {} } };
    return { agent: snapshots[Math.min(index++, snapshots.length - 1)] };
  }, sendAgentMessage: async (...args) => {
    sent.push(args);
    if (fail) throw new Error('unknown delivery');
  } };
  const options = { client, loadContext: async () => context, state,
    persist: async value => saved.push(structuredClone(value)), now: () => 0 };
  return { options, sent, saved, state };
}

test('one actual same-session steer, with intent saved before transport', async () => {
  const m = mockRun();
  await recoverOnce(m.options);
  assert.equal(m.sent.length, 1);
  assert.equal(m.sent[0][0], 'owner');
  assert.equal(m.sent[0][2].activeTurnBehavior, 'steer');
  assert.match(m.sent[0][1], /Do not rerun an already-started/);
  assert.equal(m.saved[0].agents.owner.transport, 'unknown');
  assert.equal(m.saved.at(-1).agents.owner.transport, 'accepted');
  await recoverOnce(m.options);
  assert.equal(m.sent.length, 1);
});

test('a user-resumed turn is never interrupted by stale capacity evidence', async () => {
  const m = mockRun({ snapshots: [snapshot, { ...snapshot, status: 'running', activeTurn: { id: 'live' } }] });
  await recoverOnce(m.options);
  assert.equal(m.sent.length, 0);
});

test('a new hold received between inspection and send prevents continuation', async () => {
  const m = mockRun();
  let calls = 0;
  m.options.loadContext = async () => ({ config, quota, authority: ++calls < 3
    ? authority : { ...authority, research_new_starts_allowed: false } });
  await recoverOnce(m.options);
  assert.equal(m.sent.length, 0);
});

test('an unrelated or closed task cannot be resumed by a matching error string', () => {
  assert.equal(decide({ ...snapshot, id: 'closed-owner' }).reason, 'no_active_task_authority');
});

test('unknown transport is retained without a blind duplicate', async () => {
  const m = mockRun({ fail: true });
  await recoverOnce(m.options);
  m.options.now = () => 999999999;
  await recoverOnce(m.options);
  assert.equal(m.sent.length, 1);
  assert.equal(m.state.agents.owner.transport, 'unknown');
});

test('successful completion ends the incident without waking a completed owner', async () => {
  const m = mockRun({ snapshots: [{ ...snapshot, status: 'idle', lastError: null }] });
  m.state.agents = { owner: { attempts: 3 } };
  await recoverOnce(m.options);
  assert.equal(m.sent.length, 0);
  assert.equal(m.state.agents.owner, undefined);
});
