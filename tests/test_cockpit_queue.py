from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from open_composer.cockpit.app import create_app
from open_composer.cockpit.data.queue import load_queue_glance, normalize_status, parse_queue

SAMPLE = """# 自主研究队列

## 任务

### T-20260930-14 纳领 C2a'：样本外核对
- status: done（待主审）
- priority: 1
- notes:
  - 2026-09-30 16:07 UTC 执行轮开始。
  - 2026-09-30 16:40 UTC 执行轮完成：gate_a true，gate_b false。

### T-20260930-17 模型族扫描
- status: partial
- notes:
  - 2026-09-30 13:52 UTC 主审写 brief。

### T-20260929-61 期权 IV 截面信号
- status: blocked（等数据）
- notes:
  - 2026-09-30 18:41 UTC 机主决定不买付费期权数据。

### T-20260927-03 新规则下第一次月度调仓核对
- status: ready
- notes:

### T-20260929-30 旧任务
- status: superseded
- notes:
  - 2026-09-30 13:40 UTC 被 T-17 取代。

## 附录

- status: ready
"""


def test_statuses_fold_into_the_tile_states() -> None:
    assert normalize_status("done（待主审）") == "review"
    assert normalize_status("partial") == "running"
    assert normalize_status("blocked（等数据）") == "blocked"
    assert normalize_status("ready") == "ready"
    assert normalize_status("superseded") == "closed"
    assert normalize_status("") == "closed"


def test_parse_queue_reads_status_and_newest_note() -> None:
    items = {item.task_id: item for item in parse_queue(SAMPLE)}
    assert list(items) == [
        "T-20260930-14",
        "T-20260930-17",
        "T-20260929-61",
        "T-20260927-03",
        "T-20260929-30",
    ]  # the appendix's status line belongs to no task
    review = items["T-20260930-14"]
    assert review.status == "review" and review.dot == "warn"
    assert review.updated_at == datetime(2026, 9, 30, 16, 40, tzinfo=UTC)
    assert review.last_note is not None and review.last_note.startswith("执行轮完成")
    assert items["T-20260927-03"].updated_at is None


def test_glance_counts_open_states_and_orders_them(tmp_path: Path) -> None:
    path = tmp_path / "reports" / "research" / "control" / "autonomous-queue.md"
    path.parent.mkdir(parents=True)
    path.write_text(SAMPLE, encoding="utf-8")
    glance = load_queue_glance(tmp_path)
    assert glance.available and glance.total == 5
    assert glance.counts == {"running": 1, "review": 1, "ready": 1, "blocked": 1}
    assert [item.task_id for item in glance.open] == [
        "T-20260930-17",
        "T-20260930-14",
        "T-20260927-03",
        "T-20260929-61",
    ]
    assert glance.recent[0].task_id == "T-20260929-61"  # newest note, any state


def test_missing_queue_is_unavailable_not_an_error(tmp_path: Path) -> None:
    glance = load_queue_glance(tmp_path)
    assert not glance.available and glance.total == 0


def test_research_screen_leads_with_the_task_queue() -> None:
    text = TestClient(create_app(warm=False)).get("/hypotheses").text
    assert 'id="queue"' in text and "Task queue" in text
    assert text.index("Task queue") < text.index("Hypothesis cards")
