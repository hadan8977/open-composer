// One finite pass from the existing research manager; no watcher or quota RPC.
import fs from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const CAPACITY = /^(?:\[System Error\]\s*)?Selected model is at capacity\. Please try a different model\.$/i;

export function recoveryDecision(snapshot, previous, config, authority, quota, now) {
  const policy = config.model_capacity_recovery;
  if (!policy?.enabled) return { action: 'skip', reason: 'disabled' };
  if (!authority.research_allowed || !authority.research_new_starts_allowed
      || authority.research_quota_pause_20261023 || authority.research_progress_checkpoint_pause) {
    return { action: 'skip', reason: 'research_hold' };
  }
  if (quota?.available && quota.used_percent >= config.soft_pause_at_used_percent) {
    return { action: 'skip', reason: 'saved_quota_at_cap' };
  }
  const scopes = (config.active_research_scope_keys ?? []).map(key => authority[key]);
  const scopeAllowed = scopes.some(scope => scope?.allowed === true
    && (scope.owner === snapshot.id || scope.independent_peer === snapshot.id
        || snapshot.id === policy.root_bridge_agent_id));
  if (!scopeAllowed) return { action: 'skip', reason: 'no_active_task_authority' };
  if (snapshot.status !== 'error' || snapshot.activeTurn || snapshot.archivedAt
      || snapshot.pendingPermissions?.length) return { action: 'skip', reason: 'not_terminal_error' };
  if (!CAPACITY.test(String(snapshot.lastError ?? '').trim())) {
    return { action: 'skip', reason: 'not_selected_model_capacity' };
  }
  const session = snapshot.persistence?.sessionId ?? snapshot.runtimeInfo?.sessionId;
  const failedAt = snapshot.lastUserMessageAt ?? snapshot.updatedAt;
  if (!session || !failedAt) return { action: 'skip', reason: 'missing_failure_identity' };
  const failure = createHash('sha256')
    .update(JSON.stringify([snapshot.id, session, failedAt, snapshot.lastError])).digest('hex');
  if (previous?.failure === failure) return { action: 'skip', reason: 'failure_already_attempted' };
  if (previous?.transport === 'unknown') return { action: 'skip', reason: 'delivery_unknown_needs_reception' };
  if (now < (previous?.not_before_ms ?? 0)) return { action: 'skip', reason: 'backoff' };
  const attempts = (previous?.attempts ?? 0) + 1;
  const delays = policy.backoff_minutes;
  const delay = delays[Math.min(attempts - 1, delays.length - 1)];
  return { action: 'retry', failure, attempts, session,
    not_before_ms: now + delay * 60_000,
    message_id: `capacity-resume-${snapshot.id}-${failure.slice(0, 20)}` };
}

export async function recoverOnce({ client, loadContext, state, persist, now = Date.now }) {
  const initial = await loadContext();
  const policy = initial.config.model_capacity_recovery;
  if (!policy?.enabled) return [];
  const targets = [...new Set([...initial.config.active_research_owners,
    ...(initial.config.active_research_peers ?? []), policy.root_bridge_agent_id])]
    .filter(id => id && id !== initial.config.owner_agent_id);
  const results = [];
  state.agents ??= {};
  for (const id of targets) {
    try {
      const received = await client.fetchAgent({ agentId: id, timeout: 10_000 });
      if (!received?.agent) { results.push({ agent_id: id, action: 'skip', reason: 'not_found' }); continue; }
      let snapshot = received.agent;
      // A successful completed turn ends the incident; an accepted/running turn does not.
      if (snapshot.status === 'idle' && !snapshot.lastError && state.agents[id]) {
        delete state.agents[id];
        await persist(state);
      }
      let context = await loadContext();
      let decision = recoveryDecision(snapshot, state.agents[id], context.config,
        context.authority, context.quota, now());
      if (decision.action === 'retry') {
        // Recheck immediately before sending: a user may have resumed it meanwhile.
        snapshot = (await client.fetchAgent({ agentId: id, timeout: 10_000 }))?.agent;
        context = await loadContext();
        decision = snapshot ? recoveryDecision(snapshot, state.agents[id], context.config,
          context.authority, context.quota, now()) : { action: 'skip', reason: 'not_found' };
      }
      if (decision.action !== 'retry') { results.push({ agent_id: id, ...decision }); continue; }
      const record = { ...decision, at_utc: new Date(now()).toISOString(), transport: 'unknown' };
      state.agents[id] = record;
      // Save intent before transport. A crash/unknown send is not permission for a duplicate.
      await persist(state);
      const message = 'Automatic same-session continuation after the confirmed terminal error '
        + '"Selected model is at capacity. Please try a different model." The owner authorized '
        + 'retry and continuation. Keep this session/model/effort and the existing assignment. '
        + 'Read current authority and saved state; receive any existing job/output before starting '
        + 'anything. Do not rerun an already-started fit/account/source job, reset a ledger, '
        + 'change the frozen science, clear a hold or switch models. Resume only the interrupted '
        + 'LLM work. Existing quota progress/cap and paper boundaries remain. If this is Root, '
        + 'handle only the interrupted task or an actual native-child capacity fault through '
        + 'its same collaboration task; no new task, periodic standby or completed-task wake. '
        + 'Transport is not proof of execution. notifyOnFinish=false; no finish subscription.';
      await client.sendAgentMessage(id, message,
        { activeTurnBehavior: 'steer', messageId: decision.message_id });
      record.transport = 'accepted';
      await persist(state);
      results.push({ agent_id: id, action: 'retry_sent', message_id: decision.message_id,
        attempts: decision.attempts, execution_verified: false });
    } catch (error) {
      results.push({ agent_id: id, action: 'unverified', error_name: error?.name ?? 'Error' });
    }
  }
  return results;
}

async function main() {
  const root = fileURLToPath(new URL('..', import.meta.url));
  const directory = path.join(root, 'reports/research/program/research-quota-manager-20261023');
  if (!process.argv.includes('--locked')) {
    const run = spawnSync('flock', ['-n', '-E', '75', path.join(directory, 'capacity-recovery.lock'),
      process.execPath, fileURLToPath(import.meta.url), '--locked'], { stdio: 'inherit' });
    if (run.status === 75) {
      console.log(JSON.stringify({ action: 'skip', reason: 'recovery_already_running', quota_RPC: 0 }));
      return;
    }
    process.exitCode = run.status ?? 1;
    return;
  }
  const read = async name => JSON.parse(await fs.readFile(path.join(root, name), 'utf8'));
  const loadContext = async () => {
    const config = await read('config/research-quota-manager.json');
    return { config, authority: await read('reports/research/control/owner-compute-hold.json'),
      quota: await read(config.current_reading) };
  };
  const statePath = path.join(directory, 'capacity-recovery-state.json');
  let state;
  try { state = JSON.parse(await fs.readFile(statePath, 'utf8')); }
  catch (error) { if (error.code !== 'ENOENT') throw error; state = { schema_version: 1, agents: {} }; }
  const persist = async value => {
    const temporary = `${statePath}.tmp`;
    await fs.writeFile(temporary, JSON.stringify(value, null, 2) + '\n');
    await fs.rename(temporary, statePath);
  };
  const { connectToDaemon } = await import('/root/.hermes/node/lib/node_modules/@getpaseo/cli/dist/utils/client.js');
  const { selectDaemonTarget } = await import('/root/.hermes/node/lib/node_modules/@getpaseo/cli/dist/utils/daemon-target.js');
  const client = await connectToDaemon({ target: selectDaemonTarget({}), timeout: 10_000 });
  try {
    const results = await recoverOnce({ client, loadContext, state, persist });
    const receipt = { at_utc: new Date().toISOString(), results, quota_RPC: 0,
      new_timer_or_agent: false, model_changes: 0, no_finish_subscription: true };
    await fs.writeFile(path.join(directory, 'capacity-recovery-latest.json'), JSON.stringify(receipt, null, 2) + '\n');
    console.log(JSON.stringify(receipt));
  } finally { await client.close(); }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  await main();
}
