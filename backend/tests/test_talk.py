"""talk-003 话术模板二维匹配 + 占位符校验测试。

覆盖 talk-config spec：二维 [风险档 × 轮次] 精确匹配、未配空状态、占位符校验、
渲染无残留、权限边界。匹配/渲染核心逻辑直接调 service 注入 today。
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
from app.services.talk_engine.placeholders import (
    available_placeholders,
    validate_placeholders,
)
from app.services.talk_engine.renderer import build_values, render
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


def _admin_headers(client) -> dict[str, str]:
    return _headers(client, "admin")


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
    subject_name="某标的",
) -> Order:
    order = Order(
        supplier_no="S001",
        supplier_name=f"供应商{order_no}",
        biz_no="B001",
        service_fee_order_no=order_no,
        win_bid_date=win_bid_date,
        risk_tier=risk_tier,
        pay_status=None,
        subject_name=subject_name,
        engineering_bureau="某工程局",
        subsidiary="某下属单位",
        register_province="北京",
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
    scene="ROUND_2",
    assignee_id=None,
) -> Task:
    task = Task(
        order_id=order.id,
        service_fee_order_no=order.service_fee_order_no,
        risk_tier=risk_tier,
        scene=scene,
        day_offset=15,
        due_date=date(2026, 9, 7),
        status="IN_PROGRESS",
        batch_id="2026-09-28",
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
    """插入默认话术模板（talk-003 ROUND_N 二维版本）。"""
    seed_default_talk_templates(db_session)


# ── 二维匹配：精确命中 ─────────────────────────────────────────────


def test_exact_match_high_round_2(db_session, seed_talk):
    """(HIGH, ROUND_2) 精确命中 FIXED 模板，变量已填充。"""
    order = _make_order(db_session, "T01", win_bid_date=date(2026, 8, 29))
    task = _make_task(db_session, order, risk_tier="HIGH", scene="ROUND_2")
    db_session.commit()

    recs = recommend_talks(db_session, task, today=date(2026, 9, 8))

    assert len(recs) >= 1
    top = recs[0]
    assert top.risk_tier == "HIGH"
    assert top.scene == "ROUND_2"
    assert top.template_type == "FIXED"
    assert "供应商T01" in top.content
    assert "{供应商名称}" not in top.content


def test_match_only_fixed_by_default(db_session, seed_talk):
    """默认 recommend_talks 只返回 FIXED 模板（AI_PROMPT 不混入）。"""
    order = _make_order(db_session, "T01b", win_bid_date=date(2026, 8, 29))
    task = _make_task(db_session, order, risk_tier="HIGH", scene="ROUND_1")
    db_session.commit()

    recs = recommend_talks(db_session, task, today=date(2026, 9, 8))
    assert all(r.template_type == "FIXED" for r in recs)


def test_match_ai_prompt_when_requested(db_session, seed_talk):
    """指定 template_type=AI_PROMPT 时返回 AI 提示词模板（content 为空）。"""
    order = _make_order(db_session, "T01c", win_bid_date=date(2026, 8, 29))
    task = _make_task(db_session, order, risk_tier="HIGH", scene="ROUND_1")
    db_session.commit()

    recs = recommend_talks(db_session, task, template_type="AI_PROMPT", today=date(2026, 9, 8))
    assert len(recs) == 1
    assert recs[0].template_type == "AI_PROMPT"
    assert recs[0].content == ""  # AI_PROMPT content 为空（由 generator 渲染 prompt）


# ── 未配话术返回空（无兜底） ───────────────────────────────────────


def test_no_match_returns_empty(db_session, seed_talk):
    """(MEDIUM, ROUND_3) 未配话术 → 返回空列表，不兜底。"""
    order = _make_order(db_session, "T02", win_bid_date=date(2026, 8, 29), risk_tier="MEDIUM")
    task = _make_task(db_session, order, risk_tier="MEDIUM", scene="ROUND_3")
    db_session.commit()

    recs = recommend_talks(db_session, task, today=date(2026, 9, 8))
    assert recs == []


# ── 账龄段/用户特征不参与匹配 ──────────────────────────────────────


def test_same_tier_scene_diff_age_matches_same_template(db_session, seed_talk):
    """同档同轮但账龄不同 → 命中同一条模板（账龄段不参与匹配）。"""
    order_a = _make_order(db_session, "T03a", win_bid_date=date(2026, 9, 1))  # age=7
    order_b = _make_order(db_session, "T03b", win_bid_date=date(2026, 6, 1))  # age=90+
    task_a = _make_task(db_session, order_a, scene="ROUND_2")
    task_b = _make_task(db_session, order_b, scene="ROUND_2")
    db_session.commit()

    recs_a = recommend_talks(db_session, task_a, today=date(2026, 9, 8))
    recs_b = recommend_talks(db_session, task_b, today=date(2026, 9, 8))

    assert len(recs_a) == len(recs_b) >= 1
    assert recs_a[0].template_id == recs_b[0].template_id  # 同一条模板


# ── 占位符校验 ─────────────────────────────────────────────────────


def test_validate_placeholders_valid():
    """合法占位符 → 返回空列表。"""
    assert validate_placeholders("{供应商名称}您好，标的{标的名称}") == []
    assert validate_placeholders("{订单号}{风险档}{场景}") == []
    assert validate_placeholders("") == []
    assert validate_placeholders(None) == []


def test_validate_placeholders_invalid():
    """非法占位符 → 返回未知列表。"""
    unknown = validate_placeholders("{标地名称}")  # 拼写错误
    assert unknown == ["标地名称"]

    unknown2 = validate_placeholders("{供应商名称} + {不存在的变量}")
    assert "不存在的变量" in unknown2
    assert "供应商名称" not in unknown2


def test_available_placeholders_complete():
    """可用占位符包含核心变量。"""
    keys = {p.key for p in available_placeholders()}
    assert "供应商名称" in keys
    assert "标的名称" in keys
    assert "概算金额" in keys
    assert "账龄段" in keys
    assert "轮次" in keys


# ── 渲染无残留 + 新占位符 ──────────────────────────────────────────


def test_render_no_residual_with_new_placeholders():
    """新占位符（标的名称/概算金额/账龄段/轮次等）渲染后无残留。"""
    order = Order(
        supplier_name="测试公司",
        service_fee_order_no="SFO123",
        win_bid_date=date(2026, 8, 29),
        subject_name="测试标的",
        subject_estimate_amount=1000000,
        engineering_bureau="某工程局",
        subsidiary="某下属",
        register_province="北京",
    )
    task = Task(
        service_fee_order_no="SFO123",
        risk_tier="HIGH",
        scene="ROUND_2",
        due_date=date(2026, 9, 7),
    )
    feature = OrderFeature(is_member_at_win=True, win_rate=0.3)
    content = (
        "{供应商名称} 订单{订单号} 标的{标的名称} 概算{概算金额} "
        "中标率{历史中标率} 账龄{账龄段}({账龄天数}天) 工程局{工程局单位} "
        "下属{下属单位} 省份{注册省份} {会员状态} {风险档} {场景} 第{轮次}轮 {应催日}"
    )
    out = render(content, task=task, order=order, feature=feature, today=date(2026, 9, 8))
    assert "{" not in out and "}" not in out
    assert "测试公司" in out
    assert "测试标的" in out
    assert "1000000" in out
    assert "某工程局" in out
    assert "ROUND_2" in out
    assert "第2轮" in out  # {轮次} 渲染为 2
    assert "会员" in out


def test_build_values_keys_complete():
    """build_values 覆盖所有注册占位符。"""
    order = Order(
        supplier_name="x", service_fee_order_no="o1", win_bid_date=date(2026, 9, 1),
        subject_name="s", subject_estimate_amount=100,
    )
    task = Task(service_fee_order_no="o1", risk_tier="HIGH", scene="ROUND_1", due_date=date(2026, 9, 8))
    values = build_values(task, order, None, today=date(2026, 9, 8))
    valid_keys = {p.key for p in available_placeholders()}
    assert valid_keys.issubset(set(values.keys()))


# ── map_age_bucket / derive_user_tag 保留（占位符取值用） ──────────


@pytest.mark.parametrize(
    "age,expected",
    [
        (0, "0_7"), (7, "0_7"), (8, "8_15"), (15, "8_15"),
        (16, "16_30"), (30, "16_30"), (31, "31_90"), (90, "31_90"),
        (91, "90_PLUS"), (200, "90_PLUS"),
    ],
)
def test_map_age_bucket(age, expected):
    assert map_age_bucket(age) == expected


def test_derive_user_tag():
    assert derive_user_tag(None) is None
    assert derive_user_tag(OrderFeature(is_member_at_win=True)) == "MEMBER"
    assert derive_user_tag(OrderFeature(is_member_at_win=False)) is None


# ── API 端到端 ─────────────────────────────────────────────────────


def test_api_recommend_has_talk_true(client, db_session, seed_users, seed_risk_config, seed_talk):
    """有匹配话术 → has_talk=true，templates 非空。"""
    cols = _collectors(db_session)
    today = date.today()
    order = _make_order(db_session, "API1", win_bid_date=today - timedelta(days=10))
    task = _make_task(db_session, order, scene="ROUND_2", assignee_id=cols[0].id)
    db_session.commit()

    resp = client.get(
        f"/api/talk/recommend?task_id={task.id}", headers=_headers(client, "collector1")
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["has_talk"] is True
    assert len(data["templates"]) >= 1
    assert "{" not in data["templates"][0]["content"]
    assert "供应商API1" in data["templates"][0]["content"]


def test_api_recommend_has_talk_false(client, db_session, seed_users, seed_risk_config, seed_talk):
    """未配话术 → has_talk=false，templates 空。"""
    cols = _collectors(db_session)
    today = date.today()
    order = _make_order(db_session, "API2", win_bid_date=today - timedelta(days=10), risk_tier="MEDIUM")
    task = _make_task(db_session, order, risk_tier="MEDIUM", scene="ROUND_3", assignee_id=cols[0].id)
    db_session.commit()

    resp = client.get(
        f"/api/talk/recommend?task_id={task.id}", headers=_headers(client, "collector1")
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["has_talk"] is False
    assert data["templates"] == []


def test_api_recommend_collector_other_task_403(client, db_session, seed_users, seed_risk_config, seed_talk):
    """COLLECTOR 查他人任务话术 → 403。"""
    cols = _collectors(db_session)
    today = date.today()
    order = _make_order(db_session, "API3", win_bid_date=today - timedelta(days=10))
    task = _make_task(db_session, order, assignee_id=cols[1].id)
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


def test_api_recommend_requires_auth(client, seed_talk):
    resp = client.get("/api/talk/recommend?task_id=1")
    assert resp.status_code == 401


def test_api_recommend_supervisor_ok(client, db_session, seed_users, seed_risk_config, seed_talk):
    """SUPERVISOR 可查任意任务话术。"""
    cols = _collectors(db_session)
    today = date.today()
    order = _make_order(db_session, "API4", win_bid_date=today - timedelta(days=10))
    task = _make_task(db_session, order, scene="ROUND_2", assignee_id=cols[0].id)
    db_session.commit()

    resp = client.get(
        f"/api/talk/recommend?task_id={task.id}",
        headers=_headers(client, "supervisor"),
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["has_talk"] is True


# ── 模板管理 CRUD + 占位符校验（API） ──────────────────────────────


def test_api_create_template_valid(client, db_session, seed_users, seed_risk_config):
    """ADMIN 创建合法 FIXED 模板 → 201。"""
    resp = client.post(
        "/api/talk/templates",
        headers=_admin_headers(client),
        json={
            "name": "MEDIUM×ROUND_2×FIXED",
            "risk_tier": "MEDIUM",
            "scene": "ROUND_2",
            "template_type": "FIXED",
            "content": "{供应商名称}，订单{订单号}请缴费。",
            "is_active": True,
        },
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    assert data["template_type"] == "FIXED"
    assert data["scene"] == "ROUND_2"


def test_api_create_template_invalid_placeholder_400(client, db_session, seed_users, seed_risk_config):
    """非法占位符 → 400。"""
    resp = client.post(
        "/api/talk/templates",
        headers=_admin_headers(client),
        json={
            "name": "bad",
            "risk_tier": "HIGH",
            "scene": "ROUND_1",
            "template_type": "FIXED",
            "content": "{标地名称}",
            "is_active": True,
        },
    )
    assert resp.status_code == 400
    assert "标地名称" in resp.text


def test_api_create_template_ai_prompt_valid(client, db_session, seed_users, seed_risk_config):
    """ADMIN 创建 AI_PROMPT 模板（system+user）→ 201。"""
    resp = client.post(
        "/api/talk/templates",
        headers=_admin_headers(client),
        json={
            "name": "HIGH×ROUND_2×AI",
            "risk_tier": "HIGH",
            "scene": "ROUND_2",
            "template_type": "AI_PROMPT",
            "system_prompt": "语气正式。",
            "user_prompt": "为供应商{供应商名称}生成话术。",
            "is_active": True,
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["data"]["template_type"] == "AI_PROMPT"


def test_api_create_template_collector_403(client, db_session, seed_users, seed_risk_config):
    """COLLECTOR 创建模板 → 403。"""
    resp = client.post(
        "/api/talk/templates",
        headers=_headers(client, "collector1"),
        json={
            "name": "x", "risk_tier": "HIGH", "scene": "ROUND_1",
            "template_type": "FIXED", "content": "x", "is_active": True,
        },
    )
    assert resp.status_code == 403


def test_api_list_placeholders(client, seed_users):
    """占位符列表 → 含核心变量。"""
    resp = client.get(
        "/api/talk/templates/placeholders", headers=_headers(client, "collector1")
    )
    assert resp.status_code == 200
    keys = {p["key"] for p in resp.json()["data"]}
    assert "供应商名称" in keys
    assert "标的名称" in keys


def test_api_coverage(client, db_session, seed_users, seed_risk_config, seed_talk):
    """覆盖度矩阵 → 含当前 schedules 对应的格子。"""
    resp = client.get("/api/talk/coverage", headers=_admin_headers(client))
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    cells = data["cells"]
    # 默认 5 个 schedule（HIGH 3 轮 + MEDIUM 1 + LOW 1）
    assert len(cells) == 5
    scenes = {(c["risk_tier"], c["scene"]) for c in cells}
    assert ("HIGH", "ROUND_1") in scenes
    assert ("HIGH", "ROUND_2") in scenes
    assert ("LOW", "ROUND_1") in scenes
    # seed 后 HIGH ROUND_1/2/3 + MEDIUM/LOW ROUND_1 有 FIXED，覆盖度非 0
    fixed_count = sum(1 for c in cells if c["fixed_configured"])
    assert fixed_count == 5
