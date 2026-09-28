"""talk-003 覆盖度矩阵与联动校验提示测试（test_talk_coverage）。

覆盖 talk-config spec：
- compute_coverage：按 active risk_config 展开 [档×轮] 矩阵，每格 FIXED/AI_PROMPT 有无
- diff_coverage：3→4 轮提示新增 ROUND_4 缺话术；3→2 轮提示 ROUND_3 孤儿；仅改 day_offset 无轮次变更不提示
- API GET /api/talk/coverage
- API PUT /api/config/risk 响应附加 coverage_hint
"""

from __future__ import annotations

import pytest

from app.models.talk import TalkTemplate
from app.models.user import User
from app.schemas.config import RiskConfigUpdateIn, ScheduleIn
from app.services.risk_engine import seed_default_config
from app.services.risk_engine.config_service import (
    get_current_config,
    update_config,
)
from app.services.talk_engine.coverage import (
    CoverageHint,
    compute_coverage,
    diff_coverage,
    hint_to_dict,
)
from seed import seed_default_talk_templates


# ── 辅助 ──────────────────────────────────────────────────────────


def _login_token(client, username, password="admin123") -> str:
    resp = client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["access_token"]


def _admin_headers(client) -> dict[str, str]:
    return {"Authorization": f"Bearer {_login_token(client, 'admin')}"}


def _make_fixed_template(db, tier: str, scene: str, name: str | None = None) -> TalkTemplate:
    t = TalkTemplate(
        name=name or f"{tier}×{scene}×FIXED",
        risk_tier=tier,
        age_bucket="ANY",
        scene=scene,
        user_feature_tag=None,
        template_type="FIXED",
        content="{供应商名称}测试话术",
        is_active=True,
    )
    db.add(t)
    db.flush()
    return t


def _make_ai_template(db, tier: str, scene: str, name: str | None = None) -> TalkTemplate:
    t = TalkTemplate(
        name=name or f"{tier}×{scene}×AI",
        risk_tier=tier,
        age_bucket="ANY",
        scene=scene,
        user_feature_tag=None,
        template_type="AI_PROMPT",
        content="",
        system_prompt="语气正式。",
        user_prompt="为供应商生成话术。",
        is_active=True,
    )
    db.add(t)
    db.flush()
    return t


@pytest.fixture()
def seed_users_admin(db_session):
    from app.core.security import hash_password

    db_session.add(
        User(
            username="admin",
            password_hash=hash_password("admin123"),
            display_name="管理员",
            role="ADMIN",
            is_active=True,
        )
    )
    db_session.commit()


@pytest.fixture()
def base_config(db_session):
    """默认风险档配置（HIGH 3 轮 + MEDIUM 1 + LOW 1）。"""
    seed_default_config(db_session)
    return get_current_config(db_session)


# ── compute_coverage ──────────────────────────────────────────────


def test_compute_coverage_all_filled(db_session, base_config):
    """所有格子都配齐 FIXED → 无缺口。"""
    # 为所有 schedule 格配 FIXED
    for s in base_config.schedules:
        _make_fixed_template(db_session, s.risk_tier, s.scene)
    db_session.commit()

    matrix = compute_coverage(db_session, base_config)
    assert len(matrix.cells) == 5
    assert all(c.fixed_configured for c in matrix.cells)
    assert matrix.missing_cells == []


def test_compute_coverage_missing(db_session, base_config):
    """只配部分格子 → 缺口正确标记。"""
    _make_fixed_template(db_session, "HIGH", "ROUND_1")
    db_session.commit()

    matrix = compute_coverage(db_session, base_config)
    assert len(matrix.cells) == 5
    missing = matrix.missing_cells
    # ROUND_1 已配，其余 4 个缺口
    assert len(missing) == 4
    assert all(not c.fixed_configured for c in missing)


def test_compute_coverage_ai_prompt(db_session, base_config):
    """AI_PROMPT 配置状态正确标记。"""
    _make_ai_template(db_session, "HIGH", "ROUND_1")
    db_session.commit()

    matrix = compute_coverage(db_session, base_config)
    cell = next(c for c in matrix.cells if c.risk_tier == "HIGH" and c.scene == "ROUND_1")
    assert cell.ai_prompt_configured is True
    assert cell.fixed_configured is False


# ── diff_coverage：新增轮次 ───────────────────────────────────────


def test_diff_added_round_suggests_fill(db_session, base_config):
    """3→4 轮：提示新增 ROUND_4 缺话术。"""
    old = base_config
    # 新配置：HIGH 加第 4 轮
    new_schedules = [
        ScheduleIn(risk_tier="HIGH", day_offset=7, seq=1),
        ScheduleIn(risk_tier="HIGH", day_offset=15, seq=2),
        ScheduleIn(risk_tier="HIGH", day_offset=30, seq=3),
        ScheduleIn(risk_tier="HIGH", day_offset=45, seq=4),  # 新增
        ScheduleIn(risk_tier="MEDIUM", day_offset=30, seq=1),
        ScheduleIn(risk_tier="LOW", day_offset=90, seq=1),
    ]
    new_snap = update_config(
        db_session,
        RiskConfigUpdateIn(
            high_threshold=70, medium_threshold=30, schedules=new_schedules
        ),
        created_by=None,
    )

    hint = diff_coverage(db_session, old, new_snap)
    assert ("HIGH", "ROUND_4") in hint.added_rounds
    # 新增的 ROUND_4 是缺口（无话术）
    assert any(
        c.risk_tier == "HIGH" and c.scene == "ROUND_4" for c in hint.missing_cells
    )
    assert hint.has_hint


# ── diff_coverage：删除轮次 ───────────────────────────────────────


def test_diff_deleted_round_orphan(db_session, base_config):
    """3→2 轮：提示 ROUND_3 话术成孤儿。"""
    # 先为 ROUND_3 配话术
    _make_fixed_template(db_session, "HIGH", "ROUND_3")
    db_session.commit()
    old = get_current_config(db_session)

    new_schedules = [
        ScheduleIn(risk_tier="HIGH", day_offset=7, seq=1),
        ScheduleIn(risk_tier="HIGH", day_offset=15, seq=2),
        # 删除第 3 轮
        ScheduleIn(risk_tier="MEDIUM", day_offset=30, seq=1),
        ScheduleIn(risk_tier="LOW", day_offset=90, seq=1),
    ]
    new_snap = update_config(
        db_session,
        RiskConfigUpdateIn(
            high_threshold=70, medium_threshold=30, schedules=new_schedules
        ),
        created_by=None,
    )

    hint = diff_coverage(db_session, old, new_snap)
    assert ("HIGH", "ROUND_3") in hint.deleted_rounds
    assert hint.has_hint


# ── diff_coverage：仅改 day_offset 不提示 ─────────────────────────


def test_diff_day_offset_only_no_hint(db_session, base_config):
    """仅改 day_offset（轮次不变）→ added/deleted 为空。"""
    old = base_config
    new_schedules = [
        ScheduleIn(risk_tier="HIGH", day_offset=5, seq=1),  # 7→5
        ScheduleIn(risk_tier="HIGH", day_offset=15, seq=2),
        ScheduleIn(risk_tier="HIGH", day_offset=30, seq=3),
        ScheduleIn(risk_tier="MEDIUM", day_offset=30, seq=1),
        ScheduleIn(risk_tier="LOW", day_offset=90, seq=1),
    ]
    new_snap = update_config(
        db_session,
        RiskConfigUpdateIn(
            high_threshold=70, medium_threshold=30, schedules=new_schedules
        ),
        created_by=None,
    )

    hint = diff_coverage(db_session, old, new_snap)
    assert hint.added_rounds == []
    assert hint.deleted_rounds == []


# ── hint_to_dict ──────────────────────────────────────────────────


def test_hint_to_dict_serializable(db_session, base_config):
    """hint_to_dict 输出可 JSON 序列化结构。"""
    old = base_config
    new_schedules = [
        ScheduleIn(risk_tier="HIGH", day_offset=7, seq=1),
        ScheduleIn(risk_tier="HIGH", day_offset=15, seq=2),
        ScheduleIn(risk_tier="HIGH", day_offset=30, seq=3),
        ScheduleIn(risk_tier="HIGH", day_offset=45, seq=4),
        ScheduleIn(risk_tier="MEDIUM", day_offset=30, seq=1),
        ScheduleIn(risk_tier="LOW", day_offset=90, seq=1),
    ]
    new_snap = update_config(
        db_session,
        RiskConfigUpdateIn(
            high_threshold=70, medium_threshold=30, schedules=new_schedules
        ),
        created_by=None,
    )
    hint = diff_coverage(db_session, old, new_snap)
    d = hint_to_dict(hint)
    assert "added_rounds" in d
    assert "deleted_rounds" in d
    assert "missing_cells" in d
    assert isinstance(d["added_rounds"], list)
    assert all("risk_tier" in r and "scene" in r for r in d["added_rounds"])


# ── API GET /api/talk/coverage ────────────────────────────────────


def test_api_coverage_admin(client, db_session, seed_users_admin, base_config):
    """ADMIN 查覆盖度矩阵 → 200，含 5 格。"""
    resp = client.get("/api/talk/coverage", headers=_admin_headers(client))
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert len(data["cells"]) == 5
    assert data["missing_count"] == 5  # 无话术，全是缺口


def test_api_coverage_collector_403(client, db_session, seed_users_admin, base_config):
    """COLLECTOR 查覆盖度 → 403。"""
    from app.core.security import hash_password

    db_session.add(
        User(
            username="collector1",
            password_hash=hash_password("admin123"),
            display_name="催收员",
            role="COLLECTOR",
            is_active=True,
        )
    )
    db_session.commit()
    headers = {"Authorization": f"Bearer {_login_token(client, 'collector1')}"}
    resp = client.get("/api/talk/coverage", headers=headers)
    assert resp.status_code == 403


def test_api_coverage_no_config_404(client, db_session, seed_users_admin):
    """无生效风险档配置 → 404。"""
    resp = client.get("/api/talk/coverage", headers=_admin_headers(client))
    assert resp.status_code == 404


# ── API PUT /api/config/risk 附加 coverage_hint ────────────────────


def test_api_update_risk_coverage_hint_added(client, db_session, seed_users_admin, base_config):
    """风险档配置新增轮次 → 响应含 coverage_hint，提示新增轮次缺话术。"""
    new_schedules = [
        ScheduleIn(risk_tier="HIGH", day_offset=7, seq=1),
        ScheduleIn(risk_tier="HIGH", day_offset=15, seq=2),
        ScheduleIn(risk_tier="HIGH", day_offset=30, seq=3),
        ScheduleIn(risk_tier="HIGH", day_offset=45, seq=4),  # 新增
        ScheduleIn(risk_tier="MEDIUM", day_offset=30, seq=1),
        ScheduleIn(risk_tier="LOW", day_offset=90, seq=1),
    ]
    resp = client.put(
        "/api/config/risk",
        headers=_admin_headers(client),
        json={
            "high_threshold": 70,
            "medium_threshold": 30,
            "schedules": [
                {"risk_tier": s.risk_tier, "day_offset": s.day_offset, "seq": s.seq}
                for s in new_schedules
            ],
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    hint = data.get("coverage_hint")
    assert hint is not None
    assert any(r["scene"] == "ROUND_4" for r in hint["added_rounds"])


def test_api_update_risk_no_hint_when_day_offset_only(
    client, db_session, seed_users_admin, base_config
):
    """仅改 day_offset（轮次不变）→ coverage_hint 为 null。"""
    new_schedules = [
        ScheduleIn(risk_tier="HIGH", day_offset=5, seq=1),  # 7→5
        ScheduleIn(risk_tier="HIGH", day_offset=15, seq=2),
        ScheduleIn(risk_tier="HIGH", day_offset=30, seq=3),
        ScheduleIn(risk_tier="MEDIUM", day_offset=30, seq=1),
        ScheduleIn(risk_tier="LOW", day_offset=90, seq=1),
    ]
    resp = client.put(
        "/api/config/risk",
        headers=_admin_headers(client),
        json={
            "high_threshold": 70,
            "medium_threshold": 30,
            "schedules": [
                {"risk_tier": s.risk_tier, "day_offset": s.day_offset, "seq": s.seq}
                for s in new_schedules
            ],
        },
    )
    assert resp.status_code == 200
    assert resp.json()["data"].get("coverage_hint") is None
