"""Notify the current conversation once when a finite research series exits.

Used by systemd ExecStopPost, not a poller or a research permission source.
Owner pauses suppress the notification's model invocation.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--series', required=True)
    parser.add_argument('--root-agent', required=True)
    parser.add_argument('--preview', action='store_true')
    args = parser.parse_args()
    series = (ROOT / args.series).resolve()
    if not series.is_relative_to(ROOT / 'research') or not series.is_file():
        raise ValueError('Expected an existing project research series')
    control = json.loads((ROOT / 'control.json').read_text())
    hold = json.loads((ROOT / 'reports/research/control/owner-compute-hold.json').read_text())
    enabled = control.get('research') is True and not hold.get('research_paused') and all(
        hold.get(k) is not False for k in ('research_allowed', 'research_new_starts_allowed')
    )
    state = json.loads(series.read_text())
    prompt = (
        '同一研究任务的自动终态通知，不是新的授权或新建研究会话。\n'
        f'原生研究链已退出：{args.series}\n'
        f'记录状态：{state.get("status")}；systemd结果：{os.getenv("SERVICE_RESULT", "unknown")}。\n'
        '先读该series及其最后run、既有检查点和真实作业；核对当前owner指令。'
        '若研究仍获授权，接收实际结果并继续有具体科学依据的原工作；'
        '真实暂停/额度/认证/资源故障必须保留，不盲目重启或复制计算。'
        '该次接续在当前会话汇报真实进展，不把等待或准备说成完成。'
    )
    if args.preview:
        print(json.dumps({'research_enabled': enabled, 'series_status': state.get('status'),
                          'target_agent': args.root_agent, 'prompt': prompt}, ensure_ascii=False))
        return 0
    invocation = os.getenv('INVOCATION_ID', 'manual')
    record = series.with_name(series.stem + '-terminal-' + invocation + '.json')
    try:
        output = record.open('x')
    except FileExistsError:
        return 0
    receipt = {'at_utc': datetime.now(timezone.utc).isoformat(), 'series': args.series,
               'series_status': state.get('status'), 'service_result': os.getenv('SERVICE_RESULT'),
               'exit_code': os.getenv('EXIT_CODE'), 'exit_status': os.getenv('EXIT_STATUS'),
               'notification': 'suppressed_owner_pause' if not enabled else 'dispatching'}
    with output:
        json.dump(receipt, output, ensure_ascii=False, indent=2)
    if not enabled:
        return 0
    prompt_file = record.with_suffix('.txt')
    prompt_file.write_text(prompt)
    try:
        result = subprocess.run(
            ['/root/.hermes/node/bin/paseo', 'send', args.root_agent, '--prompt-file',
             str(prompt_file), '--behavior', 'steer', '--no-wait', '--json',
             '--home', '/root/.paseo'], capture_output=True, text=True, timeout=60,
        )
        receipt.update(notification='queued' if result.returncode == 0 else 'failed',
                       command_exit_code=result.returncode,
                       response=result.stdout[-2000:], error=result.stderr[-1000:])
    except (OSError, subprocess.TimeoutExpired) as exc:
        receipt.update(notification='failed', error=type(exc).__name__)
    record.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    return 0 if receipt['notification'] == 'queued' else 1


if __name__ == '__main__':
    raise SystemExit(main())
