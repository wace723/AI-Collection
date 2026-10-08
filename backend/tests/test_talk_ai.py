"""talk-002 AI 话术生成测试。

覆盖 docs/03 TC-TALK-05/07/08/09 + AI 配置 API + generate/feedback API + 权限。
不依赖真实 LLM：mock 走离线，openai_compatible 用不可达地址测降级。
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.models.ai_config import AIConfig
from app.models.order import Order, OrderFeature
from app.models.talk import AIConversation
from app.models.task import Task
from app.models.user import User
from app.services.risk_engine import seed_default_config
from app.services.risk_engine.config_service import get_current_config
from app.services.talk_engine import generate_talk
from app.services.talk_engine.ai_config_service import (
    get_effective_ai_config,
    mask_api_key,
)
from app.services.talk_engine.generator import is_compliant
from app.services.talk_engine.llm_provider import LLMProvider, MockLLMProvider
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


def _make_order(db, order_no, win_bid_date) -> Order:
    order = Order(
        supplier_no="S001",
        supplier_name=f"供应商{order_no}",
        biz_no="B001",
        service_fee_order_no=order_no,
        win_bid_date=win_bid_date,
        risk_tier="HIGH",
        pay_status=None,
    )
    db.add(order)
    db.flush()
    db.add(
        OrderFeature(
            order_id=order.id,
            is_member_at_win=True,
            history_fee_order_count=2,
            win_rate=0.3,
        )
    )
    db.flush()
    return order


def _make_task(db, order, *, assignee_id=None) -> Task:
    task = Task(
        order_id=order.id,
        service_fee_order_no=order.service_fee_order_no,
        risk_tier="HIGH",
        scene="ROUND_2",
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
    seed_default_talk_templates(db_session)


@pytest.fixture()
def ai_mock(db_session):
    """mock provider + 开启。"""
    db_session.add(
        AIConfig(id=1, provider="mock", enabled=True)
    )
    db_session.commit()


@pytest.fixture()
def ai_disabled(db_session):
    db_session.add(AIConfig(id=1, provider="mock", enabled=False))
    db_session.commit()


@pytest.fixture()
def ai_openai_bad(db_session):
    """openai_compatible 指向不可达地址，测降级。"""
    db_session.add(
        AIConfig(
            id=1,
            provider="openai_compatible",
            api_key="test-key",
            base_url="http://127.0.0.1:59999",
            model="test-model",
            enabled=True,
        )
    )
    db_session.commit()


# ── TC-TALK-05：mock 生成 ─────────────────────────────────────────


def test_mock_generate_writes_conversation(db_session, seed_talk, ai_mock):
    order = _make_order(db_session, "AI01", date(2026, 8, 29))
    task = _make_task(db_session, order)
    db_session.commit()

    result = generate_talk(db_session, task)

    assert result.enabled is True
    assert result.fallback is False
    assert result.content
    assert result.provider == "mock"
    assert result.conversation_id is not None

    convs = db_session.query(AIConversation).filter(AIConversation.task_id == task.id).all()
    assert len(convs) == 1
    assert convs[0].response == result.content
    assert convs[0].provider == "mock"


def test_mock_llm_provider_returns_non_empty():
    p = MockLLMProvider()
    out = p.generate("sys", "user")
    assert out and out.strip()


# ── TC-TALK-10：合规校验（纵深安全，不合规降级） ────────────────


def test_is_compliant_unit():
    assert is_compliant("请尽快缴纳平台使用费，避免影响投标资格。")
    assert not is_compliant("我们保证还款，必定追回欠款")
    assert not is_compliant("辱骂客户")
    assert not is_compliant("fuck off")


def test_non_compliant_llm_output_falls_back(db_session, seed_talk, ai_mock, monkeypatch):
    """LLM 返回违规内容 → 合规校验拦截 → 降级模板。"""
    # 用 monkeypatch 让 MockLLM 返回违规话术
    class ViolentLLM(LLMProvider):
        name = "mock"

        def generate(self, system_prompt, user_prompt):
            return "我们保证还款，必定追回欠款，否则威胁起诉！"

    monkeypatch.setattr(
        "app.services.talk_engine.generator.get_llm_provider",
        lambda eff: ViolentLLM(),
    )

    order = _make_order(db_session, "AI10", date(2026, 8, 29))
    task = _make_task(db_session, order)
    db_session.commit()

    result = generate_talk(db_session, task)

    assert result.enabled is True
    assert result.fallback is True
    assert result.fallback_reason and "合规" in result.fallback_reason
    # 降级到模板话术（不含违规词），不返回违规内容
    assert result.content and "保证还款" not in result.content
    # 原始违规输出仍记录到 AIConversation 供审计
    convs = db_session.query(AIConversation).filter(
        AIConversation.task_id == task.id
    ).all()
    assert len(convs) == 1
    assert "保证还款" in convs[0].response


# ── TC-TALK-07：开关关闭返回模板 ─────────────────────────────────


def test_disabled_returns_template(db_session, seed_talk, ai_disabled):
    order = _make_order(db_session, "AI02", date(2026, 8, 29))
    task = _make_task(db_session, order)
    db_session.commit()

    result = generate_talk(db_session, task)

    assert result.enabled is False
    assert result.fallback is True
    assert result.content  # 模板话术
    assert result.fallback_reason and "关闭" in result.fallback_reason


# ── TC-TALK-08：LLM 失败降级 ─────────────────────────────────────


def test_llm_failure_falls_back_to_template(db_session, seed_talk, ai_openai_bad):
    """openai_compatible 连不可达地址 → 降级模板，不抛错。"""
    order = _make_order(db_session, "AI03", date(2026, 8, 29))
    task = _make_task(db_session, order)
    db_session.commit()

    result = generate_talk(db_session, task)

    assert result.enabled is True
    assert result.fallback is True
    assert result.content  # 降级到模板
    assert result.fallback_reason and "失败" in result.fallback_reason
    # 仍记录一条 AIConversation（response 空）
    convs = db_session.query(AIConversation).filter(AIConversation.task_id == task.id).all()
    assert len(convs) == 1
    assert convs[0].provider == "openai_compatible"


# ── TC-TALK-09：话术反馈 ──────────────────────────────────────────


def test_feedback_useful(db_session, seed_talk, ai_mock):
    from app.services.talk_engine.generator import update_feedback

    order = _make_order(db_session, "AI04", date(2026, 8, 29))
    task = _make_task(db_session, order)
    db_session.commit()
    result = generate_talk(db_session, task)

    conv = update_feedback(db_session, result.conversation_id, "useful")
    assert conv.feedback == "useful"

    db_session.expire_all()
    assert (
        db_session.get(AIConversation, result.conversation_id).feedback == "useful"
    )


# ── 配置服务：DB 优先 / .env 回退 + 脱敏 ─────────────────────────


def test_effective_config_db_priority(db_session, ai_mock):
    eff = get_effective_ai_config(db_session)
    assert eff.from_db is True
    assert eff.provider == "mock"
    assert eff.enabled is True


def test_effective_config_env_fallback(db_session):
    """无 DB 行 → 回退 .env（settings）。"""
    eff = get_effective_ai_config(db_session)
    assert eff.from_db is False
    assert eff.provider == settings_provider()


def settings_provider() -> str:
    from app.core.config import settings

    return settings.LLM_PROVIDER


def test_mask_api_key():
    assert mask_api_key(None) is None
    assert mask_api_key("ab") == "***"
    assert mask_api_key("tqsk-abcdef123456") == "tqsk***3456"


# ── AI 配置 API ───────────────────────────────────────────────────


def test_get_ai_config_supervisor(client, db_session, seed_users, ai_mock):
    resp = client.get("/api/config/ai", headers=_headers(client, "supervisor"))
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["provider"] == "mock"
    assert data["from_db"] is True
    # api_key 为 None 时不泄露
    assert data["api_key_masked"] is None


def test_update_ai_config(client, db_session, seed_users):
    resp = client.put(
        "/api/config/ai",
        json={
            "provider": "openai_compatible",
            "api_key": "sk-newkey-1234567890",
            "base_url": "https://api.example.com/v1",
            "model": "gpt-4o",
            "enabled": True,
        },
        headers=_headers(client, "supervisor"),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["provider"] == "openai_compatible"
    assert data["enabled"] is True
    assert data["api_key_masked"] == "sk-n***7890"  # 脱敏，非明文
    assert data["model"] == "gpt-4o"

    # DB 确认存明文（MVP，生产应加密）
    row = db_session.get(AIConfig, 1)
    assert row.api_key == "sk-newkey-1234567890"


def test_update_ai_empty_key_keeps_old(client, db_session, seed_users, ai_mock):
    """api_key 传空 → 保留旧值（前端脱敏回填场景）。"""
    # 先设一个 key
    client.put(
        "/api/config/ai",
        json={
            "provider": "openai_compatible",
            "api_key": "sk-old-1234567890",
            "base_url": "https://x.example.com/v1",
            "model": "m",
            "enabled": True,
        },
        headers=_headers(client, "supervisor"),
    )
    # 再更新但 api_key 空
    client.put(
        "/api/config/ai",
        json={
            "provider": "openai_compatible",
            "api_key": "",
            "base_url": "https://y.example.com/v1",
            "model": "m2",
            "enabled": False,
        },
        headers=_headers(client, "supervisor"),
    )
    row = db_session.get(AIConfig, 1)
    assert row.api_key == "sk-old-1234567890"  # 保留旧
    assert row.model == "m2"
    assert row.enabled is False


def test_ai_config_collector_forbidden(client, seed_users, ai_mock):
    resp = client.get("/api/config/ai", headers=_headers(client, "collector1"))
    assert resp.status_code == 403


# ── generate / feedback API ───────────────────────────────────────


def test_generate_api_collector_own_task(
    client, db_session, seed_users, seed_risk_config, seed_talk, ai_mock
):
    cols = _collectors(db_session)
    today = date.today()
    order = _make_order(db_session, "G1", today - timedelta(days=10))
    task = _make_task(db_session, order, assignee_id=cols[0].id)
    db_session.commit()

    resp = client.post(
        f"/api/talk/generate?task_id={task.id}",
        headers=_headers(client, "collector1"),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["enabled"] is True
    assert data["content"]
    assert data["conversation_id"] is not None


def test_generate_api_other_task_403(
    client, db_session, seed_users, seed_risk_config, seed_talk, ai_mock
):
    cols = _collectors(db_session)
    today = date.today()
    order = _make_order(db_session, "G2", today - timedelta(days=10))
    task = _make_task(db_session, order, assignee_id=cols[1].id)
    db_session.commit()

    resp = client.post(
        f"/api/talk/generate?task_id={task.id}",
        headers=_headers(client, "collector1"),
    )
    assert resp.status_code == 403


def test_feedback_api(client, db_session, seed_users, seed_risk_config, seed_talk, ai_mock):
    cols = _collectors(db_session)
    today = date.today()
    order = _make_order(db_session, "G3", today - timedelta(days=10))
    task = _make_task(db_session, order, assignee_id=cols[0].id)
    db_session.commit()

    gen = client.post(
        f"/api/talk/generate?task_id={task.id}",
        headers=_headers(client, "collector1"),
    )
    conv_id = gen.json()["data"]["conversation_id"]

    resp = client.post(
        "/api/talk/feedback",
        json={"conversation_id": conv_id, "feedback": "useless"},
        headers=_headers(client, "collector1"),
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["feedback"] == "useless"


def test_feedback_not_found(client, seed_users):
    resp = client.post(
        "/api/talk/feedback",
        json={"conversation_id": 999999, "feedback": "useful"},
        headers=_headers(client, "admin"),
    )
    assert resp.status_code == 404
