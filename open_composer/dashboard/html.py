from __future__ import annotations

import re
from datetime import datetime
from html import escape
from pathlib import Path

from open_composer.config import ensure_dir, project_root
from open_composer.models.dashboard import DashboardCatalog


def write_dashboard_html(
    catalog: DashboardCatalog,
    root: Path | None = None,
    output_path: Path | None = None,
) -> Path:
    """Write a read-only static dashboard from the rebuildable dashboard catalog."""
    base = root or project_root()
    path = output_path or (base / "reports" / "dashboard" / "index.html")
    ensure_dir(path.parent)
    strategy_dir = path.parent / "strategies"
    ensure_dir(strategy_dir)
    for strategy in catalog.strategies:
        detail_path = strategy_dir / f"{_slug(strategy.strategy_id)}.html"
        detail_path.write_text(
            _render_strategy_html(catalog, strategy.strategy_id),
            encoding="utf-8",
        )
    path.write_text(_render_dashboard_html(catalog), encoding="utf-8")
    return path


def _render_dashboard_html(catalog: DashboardCatalog) -> str:
    summary = catalog.summary
    recent_runs = sorted(catalog.runs, key=lambda item: item.run_id, reverse=True)[:12]
    recent_signals = sorted(
        catalog.signals,
        key=lambda item: (item.timestamp, item.signal_id),
        reverse=True,
    )[:12]
    recent_audits = sorted(
        catalog.audits,
        key=lambda item: (item.created_at, item.id),
        reverse=True,
    )[:12]

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Open Composer Dashboard</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f6f7f9;
      --panel: #ffffff;
      --ink: #1d2433;
      --muted: #687386;
      --line: #d9dee8;
      --accent: #0f766e;
      --warn: #b45309;
      --bad: #b91c1c;
      --good: #047857;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system,
        BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.45;
    }}
    header {{
      border-bottom: 1px solid var(--line);
      background: var(--panel);
      padding: 20px clamp(16px, 4vw, 40px);
    }}
    main {{
      display: grid;
      gap: 18px;
      padding: 22px clamp(16px, 4vw, 40px) 42px;
    }}
    h1, h2, h3 {{ margin: 0; letter-spacing: 0; }}
    h1 {{ font-size: 26px; }}
    h2 {{ font-size: 17px; }}
    h3 {{ font-size: 14px; }}
    p {{ margin: 0; color: var(--muted); }}
    a {{ color: var(--accent); text-decoration: none; }}
    .meta {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px 18px;
      margin-top: 8px;
      color: var(--muted);
      font-size: 13px;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 12px;
    }}
    .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
      min-width: 0;
    }}
    .metric {{
      display: grid;
      gap: 4px;
      min-height: 78px;
    }}
    .metric strong {{ font-size: 27px; line-height: 1; }}
    .metric span {{ color: var(--muted); font-size: 13px; }}
    .section-head {{
      display: flex;
      justify-content: space-between;
      align-items: flex-end;
      gap: 12px;
      margin-bottom: 12px;
    }}
    .table-wrap {{ overflow-x: auto; }}
    table {{
      width: 100%;
      border-collapse: collapse;
      min-width: 820px;
      font-size: 13px;
    }}
    th, td {{
      border-bottom: 1px solid var(--line);
      padding: 9px 8px;
      text-align: left;
      vertical-align: top;
    }}
    th {{
      color: var(--muted);
      font-weight: 650;
      white-space: nowrap;
    }}
    td.mono, .mono {{
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 12px;
    }}
    .pill {{
      display: inline-flex;
      align-items: center;
      min-height: 22px;
      border-radius: 999px;
      padding: 2px 8px;
      background: #eef2f7;
      color: #263244;
      font-size: 12px;
      white-space: nowrap;
    }}
    .pill.good {{ background: #dcfce7; color: var(--good); }}
    .pill.warn {{ background: #fef3c7; color: var(--warn); }}
    .pill.bad {{ background: #fee2e2; color: var(--bad); }}
    .split {{
      display: grid;
      grid-template-columns: minmax(0, 1.35fr) minmax(280px, .65fr);
      gap: 18px;
    }}
    .stack {{ display: grid; gap: 12px; }}
    .list {{ display: grid; gap: 10px; }}
    .item {{
      border-bottom: 1px solid var(--line);
      padding-bottom: 10px;
    }}
    .item:last-child {{ border-bottom: 0; padding-bottom: 0; }}
    .small {{ font-size: 12px; color: var(--muted); }}
    @media (max-width: 860px) {{
      .split {{ grid-template-columns: 1fr; }}
      h1 {{ font-size: 23px; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>Open Composer Dashboard</h1>
    <div class="meta">
      <span>Generated: <span class="mono">{escape(catalog.generated_at.isoformat())}</span></span>
      <span>Source: <span class="mono">{escape(catalog.source_root)}</span></span>
      <span>Read model: <span class="mono">reports/dashboard/catalog.json</span></span>
    </div>
  </header>
  <main>
    <section class="grid">
      {_metric("Strategies", summary.strategy_count)}
      {_metric("Versions", summary.version_count)}
      {_metric("Runs", summary.run_count)}
      {_metric("Signals", summary.signal_count)}
      {_metric("Reviews", summary.review_count)}
      {_metric("Paper Orders", summary.order_count)}
      {_metric("Data Checks", summary.data_comparison_count)}
      {_metric("Feature Logs", summary.feature_packet_count)}
      {_metric("Active", summary.active_strategy_count)}
      {_metric("Paper Auto", summary.paper_auto_strategy_count)}
    </section>

    <section class="split">
      <div class="panel">
        <div class="section-head">
          <div>
            <h2>Strategy Library</h2>
            <p>Read-only view derived from StrategySpec snapshots and reports.</p>
          </div>
        </div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Strategy</th>
                <th>Lifecycle</th>
                <th>Role</th>
                <th>Risk</th>
                <th>Backend</th>
                <th>Status</th>
                <th>Data</th>
                <th>Versions</th>
                <th>Factors</th>
              </tr>
            </thead>
            <tbody>
              {_strategy_rows(catalog)}
            </tbody>
          </table>
        </div>
      </div>
      <aside class="stack">
        <div class="panel">
          <div class="section-head"><h2>Paper Safety</h2></div>
          <div class="list">
            {
        _kv(
            "Kill switch",
            "on" if summary.paper_kill_switch_enabled else "off",
            "bad" if summary.paper_kill_switch_enabled else "good",
        )
    }
            {_kv("Open orders", str(summary.paper_open_order_count))}
            {_kv("Account equity", _money(summary.paper_account_equity))}
            {_kv("Account snapshot", _dt(summary.paper_account_snapshot_at))}
            {_kv("Positions", str(summary.paper_position_count))}
            {_kv("Positions snapshot", _dt(summary.paper_positions_snapshot_at))}
            {_kv("Unrealized PnL", _money(summary.paper_total_unrealized_pl))}
            {
        _kv(
            "Reconciliation",
            (
                f"{summary.paper_reconciliation_status} / "
                f"{summary.paper_reconciliation_issue_count} issues"
            ),
            _status_class(summary.paper_reconciliation_status),
        )
    }
            {
        _kv(
            "Alerts",
            f"{summary.paper_alert_status} / {summary.paper_alert_count} alerts",
            _status_class(summary.paper_alert_status),
        )
    }
            {_kv("Order statuses", _dict_text(summary.paper_order_status_counts))}
          </div>
        </div>
        <div class="panel">
          <div class="section-head"><h2>Backend Mix</h2></div>
          <div class="list">
            {_dict_items(summary.strategy_backend_counts)}
          </div>
        </div>
        <div class="panel">
          <div class="section-head"><h2>Capability Readiness</h2></div>
          <div class="list">
            {_dict_items(summary.backend_status_counts)}
          </div>
        </div>
      </aside>
    </section>

    <section class="panel">
      <div class="section-head">
        <div>
          <h2>Deployment Readiness</h2>
          <p>
            Latest local deploy prepare and readiness reports indexed into the
            dashboard catalog.
          </p>
        </div>
      </div>
      <div class="grid">
        {_kv("Deployment", summary.deployment_status, _status_class(summary.deployment_status))}
        {_kv("Deployment ready", "yes" if summary.deployment_ready else "no")}
        {
        _kv(
            "Deployment warnings",
            str(summary.deployment_warning_count),
            "warn" if summary.deployment_warning_count else "good",
        )
    }
        {_kv("Readiness", summary.readiness_status, _status_class(summary.readiness_status))}
        {_kv("Readiness ready", "yes" if summary.readiness_ready else "no")}
        {
        _kv(
            "Readiness warnings",
            str(summary.readiness_warning_count),
            "warn" if summary.readiness_warning_count else "good",
        )
    }
      </div>
      <div class="split" style="margin-top: 14px;">
        <div class="list">
          <h3>Deploy prepare</h3>
          {_deployment_step_items(catalog)}
        </div>
        <div class="list">
          <h3>Readiness checks</h3>
          {_readiness_check_items(catalog)}
        </div>
      </div>
    </section>

    <section class="panel">
      <div class="section-head">
        <div>
          <h2>Data Quality</h2>
          <p>Latest source comparison reports used to check replay and research data quality.</p>
        </div>
      </div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Pair</th>
              <th>Feeds</th>
              <th>Coverage</th>
              <th>Close Diff bps</th>
              <th>Missing Left</th>
              <th>Missing Right</th>
              <th>Report</th>
            </tr>
          </thead>
          <tbody>
            {_data_comparison_rows(catalog.data_comparisons)}
          </tbody>
        </table>
      </div>
    </section>

    <section class="panel">
      <div class="section-head">
        <div>
          <h2>LLM Feature Replay</h2>
          <p>
            Feature packet logs used as point-in-time inputs for llm_feature and
            feature_packet factors.
          </p>
        </div>
      </div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Log</th>
              <th>Records</th>
              <th>Fields</th>
              <th>PIT</th>
              <th>First</th>
              <th>Last</th>
              <th>Warnings</th>
            </tr>
          </thead>
          <tbody>
            {_feature_packet_rows(catalog.feature_packets)}
          </tbody>
        </table>
      </div>
    </section>

    <section class="panel">
      <div class="section-head">
        <div>
          <h2>Recent Runs</h2>
          <p>Backtest and scan artifacts, including execution backend and report links.</p>
        </div>
      </div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Run</th>
              <th>Kind</th>
              <th>Strategy</th>
              <th>Backend</th>
              <th>Evidence</th>
              <th>Sanity</th>
              <th>Return</th>
              <th>Annualized</th>
              <th>Sharpe</th>
              <th>Signals</th>
              <th>Report</th>
            </tr>
          </thead>
          <tbody>
            {_run_rows(recent_runs)}
          </tbody>
        </table>
      </div>
    </section>

    <section class="split">
      <div class="panel">
        <div class="section-head"><h2>Recent Signals</h2></div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Signal</th>
                <th>Time</th>
                <th>Strategy</th>
                <th>Action</th>
                <th>Side</th>
                <th>Price</th>
                <th>Review</th>
              </tr>
            </thead>
            <tbody>
              {_signal_rows(recent_signals)}
            </tbody>
          </table>
        </div>
      </div>
      <div class="panel">
        <div class="section-head"><h2>Audit Trail</h2></div>
        <div class="list">
          {_audit_items(recent_audits)}
        </div>
      </div>
    </section>

    <section class="panel">
      <div class="section-head">
        <div>
          <h2>Dashboard Boundary</h2>
          <p>
            This page is read-only. Paper controls must go through the audited CLI
            or command service.
          </p>
        </div>
      </div>
      <div class="list">
        {_notes(summary.notes)}
      </div>
    </section>
  </main>
</body>
</html>
"""


def _metric(label: str, value: int | float | str) -> str:
    return (
        '<div class="panel metric">'
        f"<strong>{escape(str(value))}</strong>"
        f"<span>{escape(label)}</span>"
        "</div>"
    )


def _strategy_rows(catalog: DashboardCatalog) -> str:
    if not catalog.strategies:
        return '<tr><td colspan="9">No strategies indexed.</td></tr>'
    rows = []
    for strategy in catalog.strategies:
        detail_href = f"strategies/{_slug(strategy.strategy_id)}.html"
        rows.append(
            "<tr>"
            f'<td><a href="{escape(detail_href)}"><strong>'
            f"{escape(strategy.strategy_name)}</strong></a><br>"
            f'<span class="small mono">{escape(strategy.current_version_id or "")}</span></td>'
            f"<td>{_pill(strategy.lifecycle)}</td>"
            f"<td>{_pill(strategy.model_role)}</td>"
            f"<td>{_pill(strategy.risk_tier, _risk_class(strategy.risk_tier))}</td>"
            f'<td class="mono">{escape(strategy.backend)}</td>'
            f"<td>{_pill(strategy.backend_status, _status_class(strategy.backend_status))}</td>"
            f'<td class="mono">{escape(strategy.data_source)}</td>'
            f"<td>{strategy.version_count}</td>"
            f"<td>{escape(', '.join(strategy.factor_names[:6]))}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def _deployment_step_items(catalog: DashboardCatalog) -> str:
    report = catalog.deployment_report
    if report is None or not report.steps:
        return '<div class="item">No deployment report indexed.</div>'
    return "\n".join(
        _operational_item(step.name, step.status, step.message, step.suggested_actions)
        for step in report.steps
    )


def _readiness_check_items(catalog: DashboardCatalog) -> str:
    report = catalog.readiness_report
    if report is None or not report.checks:
        return '<div class="item">No readiness report indexed.</div>'
    return "\n".join(
        _operational_item(check.name, check.status, check.message, check.suggested_actions)
        for check in report.checks
    )


def _operational_item(
    name: str,
    status: str,
    message: str,
    suggested_actions: list[str],
) -> str:
    action = suggested_actions[0] if suggested_actions else ""
    action_html = (
        f'<div class="small mono">{escape(action)}</div>'
        if action
        else '<div class="small">No action required.</div>'
    )
    return (
        '<div class="item">'
        f"<h3>{escape(name)} {_pill(status, _status_class(status))}</h3>"
        f"<p>{escape(message)}</p>"
        f"{action_html}"
        "</div>"
    )


def _render_strategy_html(catalog: DashboardCatalog, strategy_id: str) -> str:
    strategy = next(item for item in catalog.strategies if item.strategy_id == strategy_id)
    versions = [item for item in catalog.versions if item.strategy_id == strategy_id]
    runs = [item for item in catalog.runs if item.strategy_id == strategy_id]
    signals = [item for item in catalog.signals if item.strategy_id == strategy_id]
    orders = [
        item
        for item in catalog.orders
        if item.strategy_id == strategy_id or item.strategy_name == strategy.strategy_name
    ]
    backend_plan_path = next(
        (item.backend_plan_path for item in runs if item.backend_plan_path), None
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(strategy.strategy_name)} | Open Composer Dashboard</title>
  <style>{_shared_css()}</style>
</head>
<body>
  <header>
    <h1>{escape(strategy.strategy_name)}</h1>
    <div class="meta">
      <span><a href="../index.html">Dashboard</a></span>
      <span>Version: <span class="mono">{escape(strategy.current_version_id or "")}</span></span>
      <span>Backend: <span class="mono">{escape(strategy.backend)}</span></span>
      <span>Data: <span class="mono">{escape(strategy.data_source)}</span></span>
      <span>Backend plan: <span class="mono">{escape(backend_plan_path or "n/a")}</span></span>
    </div>
  </header>
  <main>
    <section class="grid">
      {_metric("Versions", strategy.version_count)}
      {_metric("Runs", len(runs))}
      {_metric("Signals", len(signals))}
      {_metric("Paper Orders", len(orders))}
      {_metric("Factors", strategy.factor_count)}
      {_metric("Universe", strategy.universe_size)}
    </section>

    <section class="split">
      <div class="panel">
        <div class="section-head"><h2>Strategy Profile</h2></div>
        <div class="list">
          {_kv("Lifecycle", strategy.lifecycle)}
          {_kv("Model role", strategy.model_role)}
          {_kv("Risk tier", strategy.risk_tier, _risk_class(strategy.risk_tier))}
          {_kv("Execution mode", strategy.execution_mode)}
          {_kv("Broker", strategy.broker)}
          {_kv("Backend plan", backend_plan_path or "n/a")}
          {_kv("Required capabilities", ", ".join(strategy.required_capabilities) or "none")}
          {_kv("Factors", ", ".join(strategy.factor_names) or "none")}
          {_kv("LLM feature factors", ", ".join(strategy.llm_feature_factor_names) or "none")}
          {
        _kv(
            "Feature packet factors",
            ", ".join(getattr(strategy, "feature_packet_factor_names", [])) or "none",
        )
    }
        </div>
      </div>
      <div class="panel">
        <div class="section-head"><h2>Compatibility</h2></div>
        <div class="list">
          {_compatibility_items(strategy.compatibility, strategy.compatibility_reasons)}
        </div>
      </div>
    </section>

    <section class="panel">
      <div class="section-head"><h2>Versions</h2></div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Version</th>
              <th>Lifecycle</th>
              <th>Created</th>
              <th>Modified</th>
              <th>Source</th>
              <th>Hash</th>
            </tr>
          </thead>
          <tbody>{_version_rows(versions)}</tbody>
        </table>
      </div>
    </section>

    <section class="panel">
      <div class="section-head"><h2>Runs</h2></div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Run</th>
              <th>Kind</th>
              <th>Execution Backend</th>
              <th>Evidence</th>
              <th>Sanity</th>
              <th>Return</th>
              <th>Annualized</th>
              <th>Sharpe</th>
              <th>Fees</th>
              <th>Signals</th>
              <th>Assumptions</th>
              <th>Report</th>
            </tr>
          </thead>
          <tbody>{_strategy_run_rows(runs)}</tbody>
        </table>
      </div>
    </section>

    <section class="panel">
      <div class="section-head"><h2>Signals</h2></div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Signal</th>
              <th>Time</th>
              <th>Action</th>
              <th>Side</th>
              <th>Price</th>
              <th>Review</th>
              <th>Context</th>
            </tr>
          </thead>
          <tbody>{_strategy_signal_rows(signals[:80])}</tbody>
        </table>
      </div>
    </section>
  </main>
</body>
</html>
"""


def _run_rows(runs: list) -> str:
    if not runs:
        return '<tr><td colspan="11">No runs indexed.</td></tr>'
    rows = []
    for run in runs:
        report = _link(run.report_path) if run.report_path else ""
        rows.append(
            "<tr>"
            f'<td class="mono">{escape(run.run_id)}</td>'
            f"<td>{_pill(run.kind)}</td>"
            f"<td>{escape(run.strategy_name)}</td>"
            f'<td class="mono">{escape(run.execution_backend)}</td>'
            f"<td>{_evidence_cell(run)}</td>"
            f"<td>{_sanity_cell(run)}</td>"
            f"<td>{_pct(run.total_return_pct)}</td>"
            f"<td>{_pct(run.annualized_return_pct)}</td>"
            f"<td>{_ratio(run.sharpe_ratio)}</td>"
            f"<td>{run.signals}</td>"
            f"<td>{report}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def _data_comparison_rows(comparisons: list) -> str:
    if not comparisons:
        return '<tr><td colspan="7">No data comparison reports indexed.</td></tr>'
    rows = []
    for item in comparisons:
        rows.append(
            "<tr>"
            f"<td>{escape(item.symbol)} {escape(item.timeframe)} "
            f"{escape(item.left_source)} / {escape(item.right_source)}</td>"
            f"<td>{escape(item.left_feed or 'n/a')} / {escape(item.right_feed or 'n/a')}</td>"
            f"<td>{item.matched_coverage_pct:.2f}%</td>"
            f"<td>{item.max_abs_close_diff_bps:.2f}</td>"
            f"<td>{item.missing_left_rows}</td>"
            f"<td>{item.missing_right_rows}</td>"
            f"<td>{_artifact_link(item.report_markdown_path, '../../')}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def _feature_packet_rows(packets: list) -> str:
    if not packets:
        return '<tr><td colspan="7">No feature packet logs indexed.</td></tr>'
    rows = []
    for item in packets:
        status_class = "good" if item.point_in_time_status == "complete" else "warn"
        rows.append(
            "<tr>"
            f"<td>{_artifact_link(item.path, '../../')}</td>"
            f"<td>{item.record_count}</td>"
            f"<td>{escape(', '.join(item.field_names[:6]) or 'none')}</td>"
            f'<td><span class="badge {status_class}">'
            f"{escape(item.point_in_time_status)}</span></td>"
            f"<td>{escape(item.first_timestamp or 'n/a')}</td>"
            f"<td>{escape(item.last_timestamp or 'n/a')}</td>"
            f"<td>{escape('; '.join(item.replay_warnings[:3]) or 'none')}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def _signal_rows(signals: list) -> str:
    if not signals:
        return '<tr><td colspan="7">No signals indexed.</td></tr>'
    rows = []
    for signal in signals:
        review = _link(signal.review_path) if signal.review_path else ""
        rows.append(
            "<tr>"
            f'<td class="mono">{escape(signal.signal_id)}</td>'
            f'<td class="mono">{escape(signal.timestamp.isoformat())}</td>'
            f"<td>{escape(signal.strategy_name)}</td>"
            f"<td>{_pill(signal.action)}</td>"
            f"<td>{escape(signal.side)}</td>"
            f"<td>{signal.price:.2f}</td>"
            f"<td>{review}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def _version_rows(versions: list) -> str:
    if not versions:
        return '<tr><td colspan="6">No versions indexed.</td></tr>'
    rows = []
    for version in versions:
        rows.append(
            "<tr>"
            f'<td class="mono">{escape(version.version_id)}</td>'
            f"<td>{_pill(version.primary_lifecycle)}</td>"
            f'<td class="mono">{escape(version.created_at.isoformat())}</td>'
            f'<td class="mono">{escape(version.modified_at.isoformat())}</td>'
            f"<td>{_artifact_link(version.primary_path, '../../../')}</td>"
            f'<td class="mono">{escape(version.content_hash[:12])}</td>'
            "</tr>"
        )
    return "\n".join(rows)


def _strategy_run_rows(runs: list) -> str:
    if not runs:
        return '<tr><td colspan="12">No runs indexed for this strategy.</td></tr>'
    rows = []
    for run in runs:
        rows.append(
            "<tr>"
            f'<td class="mono">{escape(run.run_id)}</td>'
            f"<td>{_pill(run.kind)}</td>"
            f'<td class="mono">{escape(run.execution_backend)}</td>'
            f"<td>{_evidence_cell(run)}</td>"
            f"<td>{_sanity_cell(run)}</td>"
            f"<td>{_pct(run.total_return_pct)}</td>"
            f"<td>{_pct(run.annualized_return_pct)}</td>"
            f"<td>{_ratio(run.sharpe_ratio)}</td>"
            f"<td>{_money(run.total_fees)}</td>"
            f"<td>{run.signals}</td>"
            f"<td>{escape('; '.join(run.assumptions[:3]))}</td>"
            f"<td>{_artifact_link(run.report_path, '../../../')}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def _evidence_cell(run: object) -> str:
    evidence = getattr(run, "evidence_level", None) or "unknown"
    return _pill(evidence, "warn" if evidence.startswith("E0") else "")


def _sanity_cell(run: object) -> str:
    status = getattr(run, "data_sanity_status", None) or "unknown"
    warnings = getattr(run, "data_sanity_warnings", [])
    warning_count = len(warnings)
    detail = f"{warning_count} warnings" if warning_count else "no warnings"
    return f'{_pill(status, _status_class(status))}<br><span class="small">{escape(detail)}</span>'


def _strategy_signal_rows(signals: list) -> str:
    if not signals:
        return '<tr><td colspan="7">No signals indexed for this strategy.</td></tr>'
    rows = []
    for signal in sorted(signals, key=lambda item: item.timestamp, reverse=True):
        rows.append(
            "<tr>"
            f'<td class="mono">{escape(signal.signal_id)}</td>'
            f'<td class="mono">{escape(signal.timestamp.isoformat())}</td>'
            f"<td>{_pill(signal.action)}</td>"
            f"<td>{escape(signal.side)}</td>"
            f"<td>{signal.price:.2f}</td>"
            f"<td>{_artifact_link(signal.review_path, '../../../')}</td>"
            f"<td>{_artifact_link(signal.context_path, '../../../')}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def _compatibility_items(
    compatibility: dict[str, str],
    reasons: dict[str, list[str]],
) -> str:
    if not compatibility:
        return '<div class="small">No compatibility findings.</div>'
    items = []
    for capability, status in sorted(compatibility.items()):
        reason_text = "; ".join(reasons.get(capability, [])[:2])
        items.append(
            '<div class="item">'
            f"<h3>{escape(capability)} {_pill(status, _status_class(status))}</h3>"
            f'<div class="small">{escape(reason_text)}</div>'
            "</div>"
        )
    return "\n".join(items)


def _audit_items(audits: list) -> str:
    if not audits:
        return '<div class="small">No audit events indexed.</div>'
    items = []
    for audit in audits:
        items.append(
            '<div class="item">'
            f"<h3>{escape(audit.action)} {escape(audit.target)}</h3>"
            f'<div class="small mono">{escape(audit.created_at.isoformat())} | '
            f"{escape(audit.kind)} | {escape(audit.source_path)}</div>"
            "</div>"
        )
    return "\n".join(items)


def _notes(notes: list[str]) -> str:
    if not notes:
        return '<div class="small">No catalog notes.</div>'
    return "\n".join(f'<div class="item">{escape(note)}</div>' for note in notes)


def _kv(label: str, value: str, cls: str = "") -> str:
    return (
        '<div class="item">'
        f"<h3>{escape(label)}</h3>"
        f'<span class="pill {escape(cls)}">{escape(value or "-")}</span>'
        "</div>"
    )


def _dict_items(values: dict[str, int]) -> str:
    if not values:
        return '<div class="small">No records.</div>'
    return "\n".join(_kv(key, str(value)) for key, value in sorted(values.items()))


def _dict_text(values: dict[str, int]) -> str:
    if not values:
        return "none"
    return ", ".join(f"{key}: {value}" for key, value in sorted(values.items()))


def _pill(text: str, cls: str = "") -> str:
    return f'<span class="pill {escape(cls)}">{escape(text)}</span>'


def _risk_class(risk_tier: str) -> str:
    return {"stable": "good", "moderate": "warn", "high": "bad"}.get(risk_tier, "")


def _status_class(status: str) -> str:
    return {
        "ok": "good",
        "supported": "good",
        "warning": "warn",
        "partial": "warn",
        "error": "bad",
        "blocked": "bad",
    }.get(status, "")


def _pct(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.2f}%"


def _ratio(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.2f}"


def _money(value: float | None) -> str:
    if value is None:
        return ""
    return f"${value:.2f}"


def _dt(value: datetime | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _link(path: str | None) -> str:
    return _artifact_link(path, "../../")


def _artifact_link(path: str | None, prefix: str) -> str:
    if not path:
        return ""
    safe_path = escape(path)
    return f'<a href="{escape(prefix)}{safe_path}">{safe_path}</a>'


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_.-]+", "-", value.strip()).strip("-")
    return slug or "strategy"


def _shared_css() -> str:
    return """
    :root {
      color-scheme: light;
      --bg: #f6f7f9;
      --panel: #ffffff;
      --ink: #1d2433;
      --muted: #687386;
      --line: #d9dee8;
      --accent: #0f766e;
      --warn: #b45309;
      --bad: #b91c1c;
      --good: #047857;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system,
        BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.45;
    }
    header {
      border-bottom: 1px solid var(--line);
      background: var(--panel);
      padding: 20px clamp(16px, 4vw, 40px);
    }
    main {
      display: grid;
      gap: 18px;
      padding: 22px clamp(16px, 4vw, 40px) 42px;
    }
    h1, h2, h3 { margin: 0; letter-spacing: 0; }
    h1 { font-size: 26px; }
    h2 { font-size: 17px; }
    h3 { font-size: 14px; }
    p { margin: 0; color: var(--muted); }
    a { color: var(--accent); text-decoration: none; }
    .meta {
      display: flex;
      flex-wrap: wrap;
      gap: 8px 18px;
      margin-top: 8px;
      color: var(--muted);
      font-size: 13px;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 12px;
    }
    .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
      min-width: 0;
    }
    .metric {
      display: grid;
      gap: 4px;
      min-height: 78px;
    }
    .metric strong { font-size: 27px; line-height: 1; }
    .metric span { color: var(--muted); font-size: 13px; }
    .section-head {
      display: flex;
      justify-content: space-between;
      align-items: flex-end;
      gap: 12px;
      margin-bottom: 12px;
    }
    .table-wrap { overflow-x: auto; }
    table {
      width: 100%;
      border-collapse: collapse;
      min-width: 820px;
      font-size: 13px;
    }
    th, td {
      border-bottom: 1px solid var(--line);
      padding: 9px 8px;
      text-align: left;
      vertical-align: top;
    }
    th {
      color: var(--muted);
      font-weight: 650;
      white-space: nowrap;
    }
    td.mono, .mono {
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 12px;
    }
    .pill {
      display: inline-flex;
      align-items: center;
      min-height: 22px;
      border-radius: 999px;
      padding: 2px 8px;
      background: #eef2f7;
      color: #263244;
      font-size: 12px;
      white-space: nowrap;
    }
    .pill.good { background: #dcfce7; color: var(--good); }
    .pill.warn { background: #fef3c7; color: var(--warn); }
    .pill.bad { background: #fee2e2; color: var(--bad); }
    .split {
      display: grid;
      grid-template-columns: minmax(0, 1.35fr) minmax(280px, .65fr);
      gap: 18px;
    }
    .stack { display: grid; gap: 12px; }
    .list { display: grid; gap: 10px; }
    .item {
      border-bottom: 1px solid var(--line);
      padding-bottom: 10px;
    }
    .item:last-child { border-bottom: 0; padding-bottom: 0; }
    .small { font-size: 12px; color: var(--muted); }
    @media (max-width: 860px) {
      .split { grid-template-columns: 1fr; }
      h1 { font-size: 23px; }
    }
  """
