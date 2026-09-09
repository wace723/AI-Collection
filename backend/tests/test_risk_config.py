"""risk-002 风险档配置（阈值+催收时点，版本化）测试。

对应 docs/03-测试用例.md TC-RISK-03~06，并覆盖权限/校验/回滚边界。
回滚策略 = 方案 B（复制为新版本），测试断言按方案 B 调整为
"回滚后当前生效配置的阈值 = 目标旧版本的阈值"。
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.models.order import Order
from app.services.risk_engine import (
    MockRiskProvider,
    Thresholds,
    map_tier,
    recalculate_risks,
    seed_default_config,
)
from app.services.risk_engine.config_service import (
    AlreadyActiveError,
    ConfigNotFoundError,
    get_current_config,
    rollback_to_version,
    update_config,
)
from app.schemas.config import RiskConfigUpdateIn, ScheduleIn


# ── 辅助 ──────────────────────────────────────────────────────────


def _login_token(client, username="admin", password="admin123") -> str:
    resp = client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["access_token"]


def _auth_headers(client, username="admin") -> dict[str, str]:
    return {"Authorization": f"Bearer {_login_token(client, username)}"}


def _default_payload(high=70.0, medium=30.0) -> RiskConfigUpdateIn:
    """构造默认 schedules 的更新 payload。"""
    schedules = [
        ScheduleIn(risk_tier="HIGH", day_offset=7, scene="FIRST", seq=1),
        ScheduleIn(risk_tier="HIGH", day_offset=15, scene="SECOND", seq=2),
        ScheduleIn(risk_tier="HIGH", day_offset=30, scene="THIRD", seq=3),
        ScheduleIn(risk_tier="MEDIUM", day_offset=30, scene="FIRST", seq=1),
        ScheduleIn(risk_tier="LOW", day_offset=90, scene="FIRST", seq=1),
    ]
    return RiskConfigUpdateIn(
        high_threshold=high, medium_threshold=medium, schedules=schedules
    )


@pytest.fixture()
def seed_risk_config(db_session):
    """插入默认风险档配置，返回 ConfigSnapshot。"""
    seed_default_config(db_session)
    return get_current_config(db_session)


def _make_order(db_session, order_no, risk_prob=None) -> Order:
    """构造订单，可选直接写 risk_prob（用于边界测试）。"""
    order = Order(
        supplier_no="S001",
        supplier_name="测试供应商",
        biz_no="B001",
        service_fee_order_no=order_no,
    )
    if risk_prob is not None:
        order.risk_prob = risk_prob
        order.risk_calc_time = datetime.now(timezone.utc)
    db_session.add(order)
    db_session.flush()
    return order


# ── TC-RISK-05：催收时点配置默认值正确 ────────────────────────────


def test_default_config_values(client, seed_users, db_session):
    """seed 后 GET /current 返回默认配置：70/30 + 5 schedules。"""
    seed_default_config(db_session)

    resp = client.get("/api/config/risk/current", headers=_auth_headers(client))
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]

    assert data["version"] == 1
    assert data["is_active"] is True
    assert data["high_threshold"] == 70.0
    assert data["medium_threshold"] == 30.0

    # schedules 应为默认 5 条（顺序由服务层按 tier,seq 排序）
    sched = data["schedules"]
    # 按 (risk_tier, seq) 排序时，字符串序 LOW<MEDIUM，故用业务序映射后断言
    tier_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    sched_sorted = sorted(
        sched, key=lambda s: (tier_order.get(s["risk_tier"], 9), s["seq"])
    )
    assert [
        (s["risk_tier"], s["day_offset"], s["scene"], s["seq"])
        for s in sched_sorted
    ] == [
        ("HIGH", 7, "FIRST", 1),
        ("HIGH", 15, "SECOND", 2),
        ("HIGH", 30, "THIRD", 3),
        ("MEDIUM", 30, "FIRST", 1),
        ("LOW", 90, "FIRST", 1),
    ]


def test_seed_default_config_idempotent(db_session):
    """重复 seed 不重复插入。"""
    assert seed_default_config(db_session) is True
    assert seed_default_config(db_session) is False
    snap = get_current_config(db_session)
    assert snap is not None
    assert snap.config.version == 1


# ── TC-RISK-03：阈值边界值映射（配置生效后） ─────────────────────


def test_boundary_tier_mapping_with_config(
    client, seed_users, seed_risk_config, db_session
):
    """配置 70/30 生效后，recalc 时边界值映射正确。

    用 spy Provider 注入精确 prob，验证 70→HIGH, 69.99→MEDIUM,
    30→MEDIUM, 29.99→LOW, 0→LOW, 100→HIGH。
    """
    cases = [
        (70.00, "HIGH"),
        (69.99, "MEDIUM"),
        (30.00, "MEDIUM"),
        (29.99, "LOW"),
        (0.0, "LOW"),
        (100.0, "HIGH"),
    ]
    for i, (prob, _) in enumerate(cases):
        _make_order(db_session, f"SFO_BOUND_{i}")
    db_session.commit()

    # spy provider 按订单号顺序返回固定 prob
    probs = [c[0] for c in cases]

    class _Spy(MockRiskProvider):
        idx = 0

        def calculate(self, order, feature):
            p = probs[_Spy.idx % len(probs)]
            _Spy.idx += 1
            return p

    recalculate_risks(db_session, provider=_Spy())

    # 读回验证
    list_resp = client.get(
        "/api/data/orders?limit=100", headers=_auth_headers(client)
    )
    items = sorted(
        list_resp.json()["data"]["items"], key=lambda x: x["service_fee_order_no"]
    )
    for item, (_, expected_tier) in zip(items, cases, strict=True):
        assert item["risk_tier"] == expected_tier, (
            f"prob boundary: order={item['service_fee_order_no']} "
            f"prob={item['risk_prob']} expected={expected_tier} got={item['risk_tier']}"
        )


def test_map_tier_unit_with_default_thresholds():
    """纯函数单元：默认 Thresholds 边界值（risk-001 已覆盖，此处补 config 视角）。"""
    t = Thresholds()
    assert map_tier(70.0, t) == "HIGH"
    assert map_tier(69.99, t) == "MEDIUM"
    assert map_tier(30.0, t) == "MEDIUM"
    assert map_tier(29.99, t) == "LOW"


# ── TC-RISK-04：改阈值后重算生效 ──────────────────────────────────


def test_update_threshold_recalc_takes_effect(
    client, seed_users, seed_risk_config, db_session
):
    """v1(70/30) 下 prob=65→MEDIUM；PUT(60/30)→v2 active；recalc→65→HIGH。"""
    # 构造 prob=65 的订单（用 spy 直接给值）
    _make_order(db_session, "SFO_RECALC_001")
    db_session.commit()

    class _Fixed(MockRiskProvider):
        def calculate(self, order, feature):
            return 65.0

    # v1(70/30) 下重算 → 65 → MEDIUM
    recalculate_risks(db_session, provider=_Fixed())
    db_session.commit()
    snap = get_current_config(db_session)
    assert snap.config.version == 1

    # PUT 改阈值 high=60
    resp = client.put(
        "/api/config/risk",
        headers=_auth_headers(client),
        json=_default_payload(high=60.0, medium=30.0).model_dump(mode="json"),
    )
    assert resp.status_code == 200, resp.text
    new_cfg = resp.json()["data"]
    assert new_cfg["version"] == 2
    assert new_cfg["is_active"] is True
    assert new_cfg["high_threshold"] == 60.0

    # 旧 v1 is_active=False
    from app.models.risk import RiskConfig

    v1 = (
        db_session.query(RiskConfig)
        .filter(RiskConfig.version == 1)
        .first()
    )
    assert v1.is_active is False

    # 重算 → 65 ≥ 60 → HIGH
    recalculate_risks(db_session, provider=_Fixed())
    db_session.commit()

    list_resp = client.get(
        "/api/data/orders", headers=_auth_headers(client)
    )
    item = list_resp.json()["data"]["items"][0]
    assert item["risk_tier"] == "HIGH", (
        f"high=60 后 65 应为 HIGH，实际 {item['risk_tier']}"
    )

    # GET current 返回 v2
    cur = client.get("/api/config/risk/current", headers=_auth_headers(client))
    assert cur.json()["data"]["version"] == 2
    assert cur.json()["data"]["high_threshold"] == 60.0


# ── TC-RISK-06：配置历史可查且可回滚（方案 B） ────────────────────


def test_history_and_rollback(client, seed_users, seed_risk_config):
    """v1→PUT→v2→PUT→v3→history[3]；rollback/1→新 v4 值=v1 active。"""
    # v2
    r2 = client.put(
        "/api/config/risk",
        headers=_auth_headers(client),
        json=_default_payload(high=65.0, medium=25.0).model_dump(mode="json"),
    )
    assert r2.json()["data"]["version"] == 2
    # v3
    r3 = client.put(
        "/api/config/risk",
        headers=_auth_headers(client),
        json=_default_payload(high=80.0, medium=40.0).model_dump(mode="json"),
    )
    assert r3.json()["data"]["version"] == 3

    # history：3 版本，desc [3,2,1]，仅 v3 active
    hist = client.get(
        "/api/config/risk/history", headers=_auth_headers(client)
    )
    assert hist.status_code == 200
    versions = [h["version"] for h in hist.json()["data"]]
    assert versions == [3, 2, 1]
    active_flags = {h["version"]: h["is_active"] for h in hist.json()["data"]}
    assert active_flags[3] is True
    assert active_flags[2] is False
    assert active_flags[1] is False

    # 回滚到 v1（值 70/30）→ 新 v4
    rb = client.post(
        "/api/config/risk/rollback/1", headers=_auth_headers(client)
    )
    assert rb.status_code == 200, rb.text
    rb_data = rb.json()["data"]
    assert rb_data["version"] == 4
    assert rb_data["is_active"] is True
    assert rb_data["high_threshold"] == 70.0  # = v1 值
    assert rb_data["medium_threshold"] == 30.0

    # GET current = v4，阈值 = v1 阈值
    cur = client.get("/api/config/risk/current", headers=_auth_headers(client))
    assert cur.json()["data"]["version"] == 4
    assert cur.json()["data"]["high_threshold"] == 70.0

    # history 现在 4 版本，仅 v4 active；v1 行本身仍 inactive
    hist2 = client.get(
        "/api/config/risk/history", headers=_auth_headers(client)
    )
    versions2 = [h["version"] for h in hist2.json()["data"]]
    assert versions2 == [4, 3, 2, 1]
    active2 = {h["version"]: h["is_active"] for h in hist2.json()["data"]}
    assert active2[4] is True
    assert active2[1] is False  # 方案 B：v1 行本身未被改


def test_rollback_nonexistent_version_404(client, seed_users, seed_risk_config):
    """回滚不存在版本 → 404。"""
    resp = client.post(
        "/api/config/risk/rollback/999", headers=_auth_headers(client)
    )
    assert resp.status_code == 404


def test_rollback_current_active_400(client, seed_users, seed_risk_config):
    """回滚当前已激活版本 → 400。"""
    cur = client.get("/api/config/risk/current", headers=_auth_headers(client))
    active_version = cur.json()["data"]["version"]
    resp = client.post(
        f"/api/config/risk/rollback/{active_version}",
        headers=_auth_headers(client),
    )
    assert resp.status_code == 400


# ── 权限 ──────────────────────────────────────────────────────────


def test_update_requires_admin(client, seed_users, seed_risk_config):
    """COLLECTOR PUT → 403。"""
    headers = _auth_headers(client, username="collector1")
    resp = client.put(
        "/api/config/risk",
        headers=headers,
        json=_default_payload().model_dump(mode="json"),
    )
    assert resp.status_code == 403


def test_update_requires_auth(client, seed_users):
    """未登录 PUT → 401。"""
    resp = client.put(
        "/api/config/risk", json=_default_payload().model_dump(mode="json")
    )
    assert resp.status_code == 401


def test_history_requires_admin(client, seed_users, seed_risk_config):
    """COLLECTOR GET history → 403。"""
    headers = _auth_headers(client, username="collector1")
    resp = client.get("/api/config/risk/history", headers=headers)
    assert resp.status_code == 403


def test_current_requires_auth(client, seed_users):
    """未登录 GET current → 401。"""
    resp = client.get("/api/config/risk/current")
    assert resp.status_code == 401


def test_current_empty_returns_404(client, seed_users, db_session):
    """无配置时 GET current → 404。"""
    resp = client.get("/api/config/risk/current", headers=_auth_headers(client))
    assert resp.status_code == 404


# ── 输入校验 ──────────────────────────────────────────────────────


def _default_payload_dict(high=70.0, medium=30.0) -> dict:
    """构造默认 payload 的 dict（用于发送可能非法的值，绕过 Python 端校验）。"""
    return {
        "high_threshold": high,
        "medium_threshold": medium,
        "schedules": [
            {"risk_tier": "HIGH", "day_offset": 7, "scene": "FIRST", "seq": 1},
            {"risk_tier": "HIGH", "day_offset": 15, "scene": "SECOND", "seq": 2},
            {"risk_tier": "HIGH", "day_offset": 30, "scene": "THIRD", "seq": 3},
            {"risk_tier": "MEDIUM", "day_offset": 30, "scene": "FIRST", "seq": 1},
            {"risk_tier": "LOW", "day_offset": 90, "scene": "FIRST", "seq": 1},
        ],
    }


def test_update_high_le_medium_returns_422(client, seed_users, seed_risk_config):
    """high ≤ medium → 422（服务端 model_validator 拒绝）。"""
    resp = client.put(
        "/api/config/risk",
        headers=_auth_headers(client),
        json=_default_payload_dict(high=30.0, medium=70.0),
    )
    assert resp.status_code == 422


def test_update_invalid_day_offset_returns_422(client, seed_users, seed_risk_config):
    """day_offset=0 → 422。"""
    payload = _default_payload_dict()
    payload["schedules"][0]["day_offset"] = 0
    resp = client.put("/api/config/risk", headers=_auth_headers(client), json=payload)
    assert resp.status_code == 422


def test_update_invalid_scene_returns_422(client, seed_users, seed_risk_config):
    """scene=INVALID → 422。"""
    payload = _default_payload_dict()
    payload["schedules"][0]["scene"] = "INVALID"
    resp = client.put("/api/config/risk", headers=_auth_headers(client), json=payload)
    assert resp.status_code == 422


def test_update_empty_schedules_returns_422(client, seed_users, seed_risk_config):
    """空 schedules → 422。"""
    payload = _default_payload_dict()
    payload["schedules"] = []
    resp = client.put("/api/config/risk", headers=_auth_headers(client), json=payload)
    assert resp.status_code == 422
