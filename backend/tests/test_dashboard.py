"""dash-001 数据大盘测试。

覆盖 docs/03 TC-DASH-01/02/03：
- 日大盘指标与库统计一致
- 风险档分布合计=未支付总数
- 周大盘趋势返回 + 催收员绩效排名
+ 权限（COLLECTOR 403 / 未登录 401）+ 空库不除零边界。

测试日期全部用 date.today() 动态对齐，保证跨日运行稳定。
Task/TaskResult 的 created_at 创建后显式覆盖（CreatedAtMixin 允许，test_risk_config.py
对 risk_calc_time 有先例），使「当日」精确可控。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from app.models.order import Order
from app.models.task import Task, TaskResult
from app.models.user import User


# ── 辅助 ──────────────────────────────────────────────────────────


def _login_token(client, username, password="admin123") -> str:
    resp = client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["access_token"]


def _headers(client, username) -> dict[str, str]:
    return {"Authorization": f"Bearer {_login_token(client, username)}"}


def _make_order(
    db,
    order_no,
    *,
    win_bid_date=None,
    risk_tier="HIGH",
    pay_status=None,
) -> Order:
    """造未支付订单（pay_status 默认 None=未支付）。"""
    order = Order(
        supplier_no="S001",
        supplier_name=f"供应商{order_no}",
        biz_no="B001",
        service_fee_order_no=order_no,
        win_bid_date=win_bid_date or date(2026, 8, 15),
        risk_tier=risk_tier,
        pay_status=pay_status,
    )
    db.add(order)
    db.flush()
    return order


def _make_task(
    db,
    order: Order,
    *,
    risk_tier="HIGH",
    day_offset=7,
    status="PENDING_ASSIGN",
    assignee_id=None,
    created_at=None,
) -> Task:
    due = order.win_bid_date + timedelta(days=day_offset)
    task = Task(
        order_id=order.id,
        service_fee_order_no=order.service_fee_order_no,
        risk_tier=risk_tier,
        scene="FIRST",
        day_offset=day_offset,
        due_date=due,
        status=status,
        batch_id="2026-09-10",
        assignee_id=assignee_id,
    )
    db.add(task)
    db.flush()
    if created_at is not None:
        task.created_at = created_at
    db.flush()
    return task


def _make_task_result(
    db,
    task: Task,
    collector_id: int,
    *,
    result="PAID",
    created_at=None,
) -> TaskResult:
    tr = TaskResult(
        task_id=task.id,
        collector_id=collector_id,
        result=result,
    )
    db.add(tr)
    db.flush()
    if created_at is not None:
        tr.created_at = created_at
    db.flush()
    return tr


def _collectors(db) -> list[User]:
    return (
        db.query(User)
        .filter(User.role == "COLLECTOR")
        .order_by(User.id)
        .all()
    )


@pytest.fixture()
def seed_users(db_session):
    """覆盖 conftest：建 admin/supervisor + 3 名催收员。"""
    from app.core.security import hash_password

    users = [
        ("admin", "管理员", "ADMIN"),
        ("supervisor", "催收主管", "SUPERVISOR"),
        ("collector1", "催收员1", "COLLECTOR"),
        ("collector2", "催收员2", "COLLECTOR"),
        ("collector3", "催收员3", "COLLECTOR"),
    ]
    for username, display_name, role in users:
        db_session.add(
            User(
                username=username,
                password_hash=hash_password("admin123"),
                display_name=display_name,
                role=role,
                is_active=True,
            )
        )
    db_session.commit()
    return {u[0]: "admin123" for u in users}


def _utc_today() -> date:
    """与 API 层 _today_utc().date() 一致。"""
    return datetime.now(timezone.utc).date()


def _utc_dt(day: date) -> datetime:
    """当日中午时刻（避免边界），UTC。"""
    return datetime(day.year, day.month, day.day, 6, 0, tzinfo=timezone.utc)


# ── TC-DASH-01：日大盘指标正确 ─────────────────────────────────────


def test_daily_metrics_match_db(client, db_session, seed_users):
    """当日新增任务数、各档任务数、回款数、回款率与数据库统计一致。"""
    today = _utc_today()
    now = _utc_dt(today)
    cols = _collectors(db_session)
    assignee = cols[0].id

    # 当日新增 3 任务：H/M/L 各 1
    o_h = _make_order(db_session, "D01H", risk_tier="HIGH")
    o_m = _make_order(db_session, "D01M", risk_tier="MEDIUM")
    o_l = _make_order(db_session, "D01L", risk_tier="LOW")
    t_h = _make_task(db_session, o_h, risk_tier="HIGH", status="DONE",
                     assignee_id=assignee, created_at=now)
    t_m = _make_task(db_session, o_m, risk_tier="MEDIUM", status="IN_PROGRESS",
                     assignee_id=assignee, created_at=now)
    t_l = _make_task(db_session, o_l, risk_tier="LOW", status="PENDING",
                     assignee_id=assignee, created_at=now)

    # 当日回款 1（PAID）+ 当日处理非回款 1（DISPUTE）
    _make_task_result(db_session, t_h, assignee, result="PAID", created_at=now)
    _make_task_result(db_session, t_m, assignee, result="DISPUTE", created_at=now)
    db_session.commit()

    resp = client.get("/api/dashboard/daily", headers=_headers(client, "supervisor"))
    assert resp.status_code == 200, resp.text
    d = resp.json()["data"]

    assert d["date"] == today.isoformat()
    assert d["new_tasks"] == 3
    assert d["new_tasks_by_tier"] == {"HIGH": 1, "MEDIUM": 1, "LOW": 1, "NONE": 0}
    assert d["paid_count"] == 1
    assert d["processed_count"] == 2  # PAID + DISPUTE（distinct task）
    assert d["paid_rate"] == 0.5  # 1/2


# ── TC-DASH-02：风险档分布统计 ─────────────────────────────────────


def test_risk_distribution_sums_to_unpaid(client, db_session, seed_users):
    """当前未支付订单按 HIGH/MEDIUM/LOW/NONE 计数，合计=未支付总数。"""
    _make_order(db_session, "R01", risk_tier="HIGH", pay_status=None)
    _make_order(db_session, "R02", risk_tier="MEDIUM", pay_status=None)
    _make_order(db_session, "R03", risk_tier="LOW", pay_status=None)
    _make_order(db_session, "R04", risk_tier=None, pay_status=None)  # 无档→NONE
    _make_order(db_session, "R05", risk_tier="HIGH", pay_status="PAID")  # 已支付不计入
    db_session.commit()

    resp = client.get("/api/dashboard/daily", headers=_headers(client, "supervisor"))
    assert resp.status_code == 200, resp.text
    d = resp.json()["data"]

    assert d["unpaid_total"] == 4
    risk = d["risk_distribution"]
    assert risk["HIGH"] == 1
    assert risk["MEDIUM"] == 1
    assert risk["LOW"] == 1
    assert risk["NONE"] == 1
    assert sum(risk.values()) == d["unpaid_total"]


# ── TC-DASH-03：周大盘趋势 ─────────────────────────────────────────


def test_weekly_trend_and_ranking(client, db_session, seed_users):
    """返回本周每日趋势（7 点）+ 催收员绩效排名。"""
    today = _utc_today()
    cols = _collectors(db_session)
    assignee = cols[0].id

    # 造今天 + 昨天 2 天的回款数据（同一催收员）
    o1 = _make_order(db_session, "W01", risk_tier="HIGH")
    o2 = _make_order(db_session, "W02", risk_tier="HIGH")
    t1 = _make_task(db_session, o1, risk_tier="HIGH", status="DONE",
                    assignee_id=assignee)
    t2 = _make_task(db_session, o2, risk_tier="HIGH", status="DONE",
                    assignee_id=assignee)
    _make_task_result(db_session, t1, assignee, result="PAID",
                      created_at=_utc_dt(today))
    _make_task_result(db_session, t2, assignee, result="PAID",
                      created_at=_utc_dt(today - timedelta(days=1)))
    db_session.commit()

    resp = client.get("/api/dashboard/weekly", headers=_headers(client, "supervisor"))
    assert resp.status_code == 200, resp.text
    d = resp.json()["data"]

    # 7 个趋势点
    assert len(d["trend"]) == 7
    assert d["trend"][-1]["date"] == today.isoformat()  # 末点=今天
    today_point = d["trend"][-1]
    assert today_point["paid"] == 1  # 今天 1 笔回款
    assert today_point["processed"] == 1

    # 催收员绩效排名：collector1 回款 2
    assert len(d["collector_ranking"]) >= 1
    top = d["collector_ranking"][0]
    assert top["collector_id"] == assignee
    assert top["paid_count"] == 2


def test_weekly_ranking_sorted_desc(client, db_session, seed_users):
    """回款数降序，tie 取 collector_id 升序。"""
    today = _utc_today()
    cols = _collectors(db_session)
    now = _utc_dt(today)

    # collector1 回款 2，collector2 回款 1
    o1 = _make_order(db_session, "WS1", risk_tier="HIGH")
    o2 = _make_order(db_session, "WS2", risk_tier="HIGH")
    o3 = _make_order(db_session, "WS3", risk_tier="HIGH")
    t1 = _make_task(db_session, o1, risk_tier="HIGH", status="DONE",
                    assignee_id=cols[0].id)
    t2 = _make_task(db_session, o2, risk_tier="HIGH", status="DONE",
                    assignee_id=cols[0].id)
    t3 = _make_task(db_session, o3, risk_tier="HIGH", status="DONE",
                    assignee_id=cols[1].id)
    _make_task_result(db_session, t1, cols[0].id, result="PAID", created_at=now)
    _make_task_result(db_session, t2, cols[0].id, result="PAID", created_at=now)
    _make_task_result(db_session, t3, cols[1].id, result="PAID", created_at=now)
    db_session.commit()

    resp = client.get("/api/dashboard/weekly", headers=_headers(client, "supervisor"))
    ranking = resp.json()["data"]["collector_ranking"]
    assert ranking[0]["paid_count"] == 2
    assert ranking[1]["paid_count"] == 1
    assert ranking[0]["collector_id"] == cols[0].id


# ── 空库边界 ───────────────────────────────────────────────────────


def test_daily_empty_db(client, db_session, seed_users):
    """空库不除零，各项为 0，paid_rate=0.0。"""
    resp = client.get("/api/dashboard/daily", headers=_headers(client, "supervisor"))
    assert resp.status_code == 200, resp.text
    d = resp.json()["data"]
    assert d["new_tasks"] == 0
    assert d["paid_count"] == 0
    assert d["processed_count"] == 0
    assert d["paid_rate"] == 0.0
    assert d["unpaid_total"] == 0
    assert sum(d["risk_distribution"].values()) == 0


def test_paid_count_distinct_per_task(client, db_session, seed_users):
    """同一任务当日多条 PAID 明细，paid_count 按 distinct task 计（=1），
    回款率不超 100%（分子分母口径一致）。覆盖 H-1 边界。"""
    today = _utc_today()
    now = _utc_dt(today)
    cols = _collectors(db_session)
    assignee = cols[0].id

    o = _make_order(db_session, "PD1", risk_tier="HIGH")
    t = _make_task(db_session, o, risk_tier="HIGH", status="DONE",
                   assignee_id=assignee, created_at=now)
    # 同一任务两条 PAID 明细（模拟 PROMISE→PENDING→IN_PROGRESS→PAID 跨天再回款落同日）
    _make_task_result(db_session, t, assignee, result="PAID", created_at=now)
    _make_task_result(db_session, t, assignee, result="PAID", created_at=now)
    db_session.commit()

    resp = client.get("/api/dashboard/daily", headers=_headers(client, "supervisor"))
    d = resp.json()["data"]
    assert d["paid_count"] == 1  # distinct task，非 2
    assert d["processed_count"] == 1
    assert d["paid_rate"] == 1.0  # 不超 100%


def test_new_tasks_by_tier_includes_none_key(client, db_session, seed_users):
    """当日新增任务按风险档分组，输出含 NONE 键（稳定契约，值为 0 因 risk_tier NOT NULL）。"""
    today = _utc_today()
    now = _utc_dt(today)
    cols = _collectors(db_session)
    o = _make_order(db_session, "NT1", risk_tier="HIGH")
    _make_task(db_session, o, risk_tier="HIGH", status="PENDING",
               assignee_id=cols[0].id, created_at=now)
    db_session.commit()

    resp = client.get("/api/dashboard/daily", headers=_headers(client, "supervisor"))
    d = resp.json()["data"]
    # 输出固定含四档键（NONE 因 risk_tier NOT NULL 恒为 0）
    assert set(d["new_tasks_by_tier"].keys()) == {"HIGH", "MEDIUM", "LOW", "NONE"}
    assert d["new_tasks_by_tier"]["HIGH"] == 1
    assert d["new_tasks_by_tier"]["NONE"] == 0


# ── 月大盘冒烟 ─────────────────────────────────────────────────────


def test_monthly_smoke(client, db_session, seed_users):
    """月大盘返回结构正确，空库不报错。"""
    today = _utc_today()
    now = _utc_dt(today)
    cols = _collectors(db_session)

    # 造 1 笔回款 + 1 未支付订单
    o1 = _make_order(db_session, "M01", risk_tier="HIGH")
    t1 = _make_task(db_session, o1, risk_tier="HIGH", status="DONE",
                    assignee_id=cols[0].id)
    _make_task_result(db_session, t1, cols[0].id, result="PAID", created_at=now)
    _make_order(db_session, "M02", risk_tier="MEDIUM", pay_status=None)
    db_session.commit()

    resp = client.get("/api/dashboard/monthly", headers=_headers(client, "supervisor"))
    assert resp.status_code == 200, resp.text
    d = resp.json()["data"]
    assert d["month_start"] == today.replace(day=1).isoformat()
    assert d["month_end"] == today.isoformat()
    assert d["paid_count"] == 1
    assert d["processed_count"] == 1
    assert d["paid_rate"] == 1.0
    assert 0.0 <= d["unpaid_rate"] <= 1.0
    # 各档催收效果含 HIGH
    tiers = {te["risk_tier"] for te in d["tier_effects"]}
    assert "HIGH" in tiers


def test_monthly_tier_effects_fixed_keys(client, db_session, seed_users):
    """月大盘 tier_effects 固定输出四档（HIGH/MEDIUM/LOW/NONE），
    无数据档位补 0，不空缺。覆盖 S-1。"""
    today = _utc_today()
    now = _utc_dt(today)
    cols = _collectors(db_session)
    # 仅 HIGH 档有处理记录，其余档应补 0
    o = _make_order(db_session, "MF1", risk_tier="HIGH")
    t = _make_task(db_session, o, risk_tier="HIGH", status="DONE",
                   assignee_id=cols[0].id)
    _make_task_result(db_session, t, cols[0].id, result="PAID", created_at=now)
    db_session.commit()

    resp = client.get("/api/dashboard/monthly", headers=_headers(client, "supervisor"))
    d = resp.json()["data"]
    tiers = {te["risk_tier"]: te for te in d["tier_effects"]}
    assert set(tiers.keys()) == {"HIGH", "MEDIUM", "LOW", "NONE"}
    assert tiers["HIGH"]["paid"] == 1
    assert tiers["MEDIUM"]["paid"] == 0
    assert tiers["LOW"]["processed"] == 0
    assert tiers["NONE"]["paid_rate"] == 0.0


# ── 权限 ───────────────────────────────────────────────────────────


def test_collector_forbidden(client, db_session, seed_users):
    """COLLECTOR 无权看大盘 → 403。"""
    resp = client.get(
        "/api/dashboard/daily", headers=_headers(client, "collector1")
    )
    assert resp.status_code == 403


def test_unauthenticated_401(client):
    """未登录 → 401。"""
    resp = client.get("/api/dashboard/daily")
    assert resp.status_code == 401


def test_supervisor_can_access(client, db_session, seed_users):
    """SUPERVISOR 可访问三个端点。"""
    for endpoint in ("/daily", "/weekly", "/monthly"):
        resp = client.get(
            f"/api/dashboard{endpoint}", headers=_headers(client, "supervisor")
        )
        assert resp.status_code == 200, (endpoint, resp.text)
