"""talk-001 基础话术模板匹配测试。

覆盖 docs/03 TC-TALK-01~04 + 权限边界。
匹配/渲染核心逻辑直接调 service 注入 today；API 端到端用相对真实日期。
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.models.order import Order, OrderFeature
from app.models.task import Task
from app.models.talk import TalkTemplate
from app.models.user import User
from app.services.risk_engine import seed_default_config
from app.services.risk_engine.config_service import get_current_config
from app.services.talk_engine import map_age_bucket, recommend_talks
from app.services.talk_engine.matcher import derive_user_tag, match_templates
from app.services.talk_engine.renderer import render
from seed import seed_default_talk_templates


# ── 辅助 ──────────────────────────────────────────────────────────


def _login_token(client, username, password="admin123") -> str:
    resp = client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["access_token"]


def _headers(client, username) -> dict[str, str]:
    return {"Authorization": f"Bearer {_login_token(client, username)}"}


def _collectors(db) -> list[User]:
    return (
        db.query(User).filter(User.role == "COLLECTOR").order_by(User.id).all()
    )


def _make_order(
    db,
    order_no,
    *,
    win_bid_date,
    risk_tier="HIGH",
    is_member=True,
) -> Order:
    order = Order(
        supplier_no="S001",
        supplier_name=f"供应商{order_no}",
        biz_no="B001",
        service_fee_order_no=order_no,
        win_bid_date=win_bid_date,
        risk_tier=risk_tier,
        pay_status=None,
    )
    db.add(order)
    db.flush()
    db.add(
        OrderFeature(
            order_id=order.id,
            is_member_at_win=is_member,
            history_fee_order_count=2,
            avg_pay_duration_days=12.0,
            win_rate=0.3,
            active_90d=5,
            register_fund=1_000_000,
            supplier_categories="工程类",
        )
    )
    db.flush()
    return order


def _make_task(
    db,
    order,
    *,
    risk_tier="HIGH",
    scene="SECOND",
    assignee_id=None,
) -> Task:
    task = Task(
        order_id=order.id,
        service_fee_order_no=order.service_fee_order_no,
        risk_tier=risk_tier,
        scene=scene,
        day_offset=15,
        due_date=date(2026, 9, 7),
        status="PENDING",
        batch_id="2026-09-09",
        assignee_id=assignee_id,
    )
    db.add(task)
    db.flush()
    return task


@pytest.fixture()
def seed_users(db_session):
    from app.core.security import hash_password

    users = [
        ("admin", "管理员", "ADMIN"),
        ("supervisor", "催收主管", "SUPERVISOR"),
        ("collector1", "催收员1", "COLLECTOR"),
        ("collector2", "催收员2", "COLLECTOR"),
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


@pytest.fixture()
def seed_risk_config(db_session):
    seed_default_config(db_session)
    return get_current_config(db_session)


@pytest.fixture()
def seed_talk(db_session):
    """插入默认话术模板。"""
    seed_default_talk_templates(db_session)


# ── TC-TALK-01：精确命中 ──────────────────────────────────────────


def test_exact_match_high_8_15_second_member(db_session, seed_talk):
    """HIGH×8_15×SECOND×MEMBER 精确命中，变量已填充。"""
    order = _make_order(db_session, "T01", win_bid_date=date(2026, 8, 29))  # age=10
    task = _make_task(db_session, order, risk_tier="HIGH", scene="SECOND")
    db_session.commit()

    recs = recommend_talks(db_session, task, today=date(2026, 9, 8))

    assert len(recs) > 0
    top = recs[0]
    assert top.name == "HIGH×8_15×SECOND×MEMBER"
    assert top.score == 8  # 4 维各 2
    assert "供应商T01" in top.content
    assert "{供应商名称}" not in top.content


# ── TC-TALK-02：ANY 回退 ──────────────────────────────────────────


def test_any_fallback_when_no_exact(db_session, seed_talk):
    """删掉精确模板后回退到 HIGH×ANY×SECOND×ANY。"""
    order = _make_order(db_session, "T02", win_bid_date=date(2026, 8, 29))
    task = _make_task(db_session, order, risk_tier="HIGH", scene="SECOND")
    # 删除精确模板，强制回退
    db_session.query(TalkTemplate).filter(
        TalkTemplate.name == "HIGH×8_15×SECOND×MEMBER"
    ).delete()
    db_session.commit()

    recs = recommend_talks(db_session, task, today=date(2026, 9, 8))

    assert len(recs) > 0
    assert recs[0].name == "HIGH×ANY×SECOND×ANY"
    assert recs[0].score < 8  # 含 ANY 通配，分更低


# ── TC-TALK-03：变量占位符填充无残留 ─────────────────────────────


def test_render_no_residual_placeholders(db_session, seed_talk):
    """所有支持的占位符都被替换，渲染后无 { 残留。"""
    order = _make_order(db_session, "T03", win_bid_date=date(2026, 8, 29))
    task = _make_task(db_session, order, risk_tier="HIGH", scene="SECOND")
    db_session.commit()

    recs = recommend_talks(db_session, task, today=date(2026, 9, 8))
    for r in recs:
        assert "{" not in r.content
        assert "}" not in r.content
        assert "供应商T03" in r.content
        assert "T03" in r.content  # service_fee_order_no 含 T03


def test_render_direct():
    """直接测 render：中文+英文占位符都替换。"""
    order = Order(
        supplier_name="测试公司",
        service_fee_order_no="SFO123",
        win_bid_date=date(2026, 8, 29),
    )
    task = Task(
        service_fee_order_no="SFO123",
        risk_tier="HIGH",
        scene="SECOND",
        due_date=date(2026, 9, 7),
    )
    feature = OrderFeature(is_member_at_win=True)
    content = "尊敬的{供应商名称}，订单{service_fee_order_no}（{订单号}）{风险档}{场景}{应催日}{会员状态}"
    out = render(content, task=task, order=order, feature=feature)
    assert "{" not in out and "}" not in out
    assert "测试公司" in out
    assert "SFO123" in out
    assert "HIGH" in out and "SECOND" in out
    assert "2026-09-07" in out
    assert "会员" in out


# ── TC-TALK-04：账龄段映射 ───────────────────────────────────────


@pytest.mark.parametrize(
    "age,expected",
    [
        (0, "0_7"),
        (7, "0_7"),
        (8, "8_15"),
        (15, "8_15"),
        (16, "16_30"),
        (30, "16_30"),
        (31, "31_90"),
        (90, "31_90"),
        (91, "90_PLUS"),
        (200, "90_PLUS"),
    ],
)
def test_map_age_bucket(age, expected):
    assert map_age_bucket(age) == expected


def test_derive_user_tag():
    assert derive_user_tag(None) is None
    f = OrderFeature(is_member_at_win=True)
    assert derive_user_tag(f) == "MEMBER"
    f2 = OrderFeature(is_member_at_win=False)
    assert derive_user_tag(f2) is None


# ── 排序优先级 ─────────────────────────────────────────────────────


def test_priority_exact_before_any(db_session, seed_talk):
    """精确模板 score 高于 ANY 兜底，排在前面。"""
    order = _make_order(db_session, "T05", win_bid_date=date(2026, 8, 29))
    task = _make_task(db_session, order, risk_tier="HIGH", scene="SECOND")
    db_session.commit()

    recs = recommend_talks(db_session, task, today=date(2026, 9, 8))
    scores = [r.score for r in recs]
    assert scores == sorted(scores, reverse=True)  # 降序
    assert recs[0].score >= recs[-1].score


# ── API 端到端 ─────────────────────────────────────────────────────


def test_api_recommend_collector_own_task(client, db_session, seed_users, seed_risk_config, seed_talk):
    """collector1 查自己任务的话术 → 返回精确匹配且变量已渲染。"""
    cols = _collectors(db_session)
    today = date.today()
    order = _make_order(db_session, "API1", win_bid_date=today - timedelta(days=10))
    task = _make_task(db_session, order, assignee_id=cols[0].id)
    db_session.commit()

    resp = client.get(
        f"/api/talk/recommend?task_id={task.id}", headers=_headers(client, "collector1")
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["age_bucket"] == "8_15"
    assert data["user_tag"] == "MEMBER"
    templates = data["templates"]
    assert len(templates) > 0
    assert templates[0]["name"] == "HIGH×8_15×SECOND×MEMBER"
    assert "{" not in templates[0]["content"]
    assert "供应商API1" in templates[0]["content"]


def test_api_recommend_collector_other_task_403(client, db_session, seed_users, seed_risk_config, seed_talk):
    """COLLECTOR 查他人任务话术 → 403。"""
    cols = _collectors(db_session)
    today = date.today()
    order = _make_order(db_session, "API2", win_bid_date=today - timedelta(days=10))
    task = _make_task(db_session, order, assignee_id=cols[1].id)  # 分给 collector2
    db_session.commit()

    resp = client.get(
        f"/api/talk/recommend?task_id={task.id}", headers=_headers(client, "collector1")
    )
    assert resp.status_code == 403


def test_api_recommend_not_found_404(client, seed_users, seed_risk_config, seed_talk):
    resp = client.get(
        "/api/talk/recommend?task_id=999999", headers=_headers(client, "collector1")
    )
    assert resp.status_code == 404


def test_api_recommend_requires_auth(client, seed_users, seed_talk):
    resp = client.get("/api/talk/recommend?task_id=1")
    assert resp.status_code == 401


def test_api_recommend_supervisor_ok(client, db_session, seed_users, seed_risk_config, seed_talk):
    """SUPERVISOR 可查任意任务话术。"""
    cols = _collectors(db_session)
    today = date.today()
    order = _make_order(db_session, "API3", win_bid_date=today - timedelta(days=10))
    task = _make_task(db_session, order, assignee_id=cols[0].id)
    db_session.commit()

    resp = client.get(
        f"/api/talk/recommend?task_id={task.id}",
        headers=_headers(client, "supervisor"),
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["templates"][0]["name"] == "HIGH×8_15×SECOND×MEMBER"
