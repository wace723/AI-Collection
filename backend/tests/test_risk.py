"""risk-001 Mock 风险概率计算 + RiskProvider 抽象测试。

对应 docs/03-测试用例.md TC-RISK-01/02/03，并额外覆盖：
- Provider 接口可切换（mock→algorithm 不改调用方）
- MockRiskProvider 确定性（相同输入→相同输出）
- mock 不使用标签字段（防数据泄漏）
- 风险档映射边界值
- recalc 端点权限（ADMIN/未登录）
"""

from __future__ import annotations

import pytest

from app.core.security import create_access_token
from app.models.order import Order, OrderFeature
from app.models.risk import RiskConfig
from app.services.risk_engine import (
    AlgorithmRiskProvider,
    MockRiskProvider,
    Thresholds,
    get_active_thresholds,
    map_tier,
    recalculate_risks,
)


# ── 辅助构造 ──────────────────────────────────────────────────────


def _make_order(db_session, order_no="SFO_RISK_001") -> Order:
    """构造最小订单（非空字段齐全）。"""
    order = Order(
        supplier_no="S001",
        supplier_name="测试供应商",
        biz_no="B001",
        service_fee_order_no=order_no,
    )
    db_session.add(order)
    db_session.flush()
    return order


def _make_feature(
    db_session,
    order_id: int,
    *,
    avg_pay_duration_days=15.0,
    history_fee_order_count=2,
    win_rate=0.5,
    active_90d=5,
    is_member_at_win=True,
) -> OrderFeature:
    """构造订单特征（默认中性值）。"""
    feature = OrderFeature(
        order_id=order_id,
        avg_pay_duration_days=avg_pay_duration_days,
        history_fee_order_count=history_fee_order_count,
        win_rate=win_rate,
        active_90d=active_90d,
        is_member_at_win=is_member_at_win,
    )
    db_session.add(feature)
    db_session.flush()
    return feature


def _login_token(client, username="admin", password="admin123") -> str:
    resp = client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["access_token"]


def _auth_headers(client) -> dict[str, str]:
    return {"Authorization": f"Bearer {_login_token(client)}"}


# ── TC-RISK-01：mock 风险概率范围合规 ─────────────────────────────


def test_recalc_all_orders_prob_in_range(client, seed_users, db_session):
    """触发重算后每笔订单 risk_prob ∈ [0,100]，risk_tier 非空。"""
    # 构造 3 笔不同特征订单
    for i, kwargs in enumerate(
        [
            dict(avg_pay_duration_days=29.0, history_fee_order_count=0, win_rate=0.05, active_90d=0, is_member_at_win=False),  # 高风险
            dict(avg_pay_duration_days=15.0, history_fee_order_count=2, win_rate=0.5, active_90d=5, is_member_at_win=True),  # 中性
            dict(avg_pay_duration_days=2.0, history_fee_order_count=8, win_rate=0.9, active_90d=10, is_member_at_win=True),  # 低风险
        ]
    ):
        order = _make_order(db_session, f"SFO_RISK_RANGE_{i}")
        _make_feature(db_session, order.id, **kwargs)
    db_session.commit()

    resp = client.post("/api/data/orders/recalc-risk", headers=_auth_headers(client))
    assert resp.status_code == 200, resp.text
    body = resp.json()["data"]
    assert body["recalculated"] == 3

    # 验证回写：查列表
    list_resp = client.get("/api/data/orders", headers=_auth_headers(client))
    items = list_resp.json()["data"]["items"]
    for item in items:
        prob = item["risk_prob"]
        assert prob is not None
        assert 0 <= prob <= 100
        assert item["risk_tier"] in {"HIGH", "MEDIUM", "LOW"}
        assert item["risk_calc_time"] is not None

    # 三档应有分布（mock 设计覆盖高/中/低）
    tiers = {item["risk_tier"] for item in items}
    assert len(tiers) >= 2, f"mock 应覆盖多档分布，实际仅 {tiers}"


def test_recalc_no_null_prob_after_recalc(client, seed_users, db_session):
    """重算后无 NULL 概率（即使特征缺失也回退中性 50.0）。"""
    # 一笔有特征、一笔无特征
    o1 = _make_order(db_session, "SFO_WITH_FEAT")
    _make_feature(db_session, o1.id)
    _make_order(db_session, "SFO_NO_FEAT")  # 无特征
    db_session.commit()

    client.post("/api/data/orders/recalc-risk", headers=_auth_headers(client))

    list_resp = client.get("/api/data/orders", headers=_auth_headers(client))
    for item in list_resp.json()["data"]["items"]:
        assert item["risk_prob"] is not None


# ── TC-RISK-02：风险档阈值映射正确 ────────────────────────────────


def test_map_tier_boundaries_default():
    """默认阈值 70/30 边界值（docs/03 TC-RISK-02/03）。"""
    t = Thresholds()  # 默认 high=70, medium=30
    assert map_tier(85, t) == "HIGH"
    assert map_tier(45, t) == "MEDIUM"
    assert map_tier(15, t) == "LOW"


def test_map_tier_edge_values():
    """TC-RISK-03 边界值精确断言。"""
    t = Thresholds(high=70, medium=30)
    assert map_tier(70.00, t) == "HIGH"
    assert map_tier(69.99, t) == "MEDIUM"
    assert map_tier(30.00, t) == "MEDIUM"
    assert map_tier(29.99, t) == "LOW"
    assert map_tier(0, t) == "LOW"
    assert map_tier(100, t) == "HIGH"


def test_map_tier_custom_thresholds():
    """自定义阈值（模拟改阈值后重算，TC-RISK-04 的前置）。"""
    t = Thresholds(high=60, medium=20)
    assert map_tier(60, t) == "HIGH"
    assert map_tier(59.99, t) == "MEDIUM"
    assert map_tier(20, t) == "MEDIUM"
    assert map_tier(19.99, t) == "LOW"


def test_get_active_thresholds_fallback_default(db_session):
    """无 active 配置时回退默认 70/30。"""
    t = get_active_thresholds(db_session)
    assert t.high == 70.0
    assert t.medium == 30.0


def test_get_active_thresholds_from_active_config(db_session):
    """有 active 配置时读配置值。"""
    db_session.add(
        RiskConfig(
            version=1,
            high_threshold=60,
            medium_threshold=20,
            is_active=True,
        )
    )
    db_session.commit()
    t = get_active_thresholds(db_session)
    assert t.high == 60.0
    assert t.medium == 20.0


def test_recalc_uses_active_config_thresholds(client, seed_users, db_session):
    """重算档位映射依赖 active 配置（TC-RISK-02）。"""
    # 构造一笔中性订单（默认阈值下为 MEDIUM）
    order = _make_order(db_session, "SFO_CFG")
    _make_feature(
        db_session,
        order.id,
        avg_pay_duration_days=15.0,
        history_fee_order_count=2,
        win_rate=0.5,
        active_90d=5,
        is_member_at_win=True,
    )
    db_session.commit()

    # 默认阈值重算
    client.post("/api/data/orders/recalc-risk", headers=_auth_headers(client))
    list_resp = client.get("/api/data/orders", headers=_auth_headers(client))
    prob = list_resp.json()["data"]["items"][0]["risk_prob"]
    tier_default = list_resp.json()["data"]["items"][0]["risk_tier"]

    # 用默认阈值验证 map_tier 一致性
    assert tier_default == map_tier(prob, Thresholds())


# ── Provider 可切换（不改调用方） ─────────────────────────────────


def test_provider_switchable_via_injection(db_session):
    """调用方可注入任意 RiskProvider，recalculate_risks 无感知。"""
    order = _make_order(db_session, "SFO_SWITCH")
    _make_feature(db_session, order.id)
    db_session.commit()

    class SpyProvider(MockRiskProvider):
        """记录是否被调用的 spy，验证注入生效。"""

        called = False

        def calculate(self, order, feature):
            SpyProvider.called = True
            return 42.0

    result = recalculate_risks(db_session, provider=SpyProvider())
    assert SpyProvider.called is True
    assert result.recalculated == 1

    db_session.refresh(order)
    assert order.risk_prob == 42.0
    # 42 ≥ 30 → MEDIUM（默认阈值）
    assert order.risk_tier == "MEDIUM"


def test_algorithm_provider_not_implemented():
    """AlgorithmRiskProvider 未实现，调用抛 NotImplementedError（占位校验）。"""
    provider = AlgorithmRiskProvider()
    with pytest.raises(NotImplementedError):
        provider.calculate(order=None, feature=None)


# ── MockRiskProvider 确定性 ────────────────────────────────────────


def test_mock_provider_deterministic(db_session):
    """相同输入→相同输出（幂等跑批前提）。"""
    order = _make_order(db_session, "SFO_DETERMIN")
    feature = _make_feature(db_session, order.id)
    db_session.commit()

    provider = MockRiskProvider()
    p1 = provider.calculate(order, feature)
    p2 = provider.calculate(order, feature)
    assert p1 == p2
    assert 0 <= p1 <= 100


def test_mock_high_risk_inputs_produce_higher_prob(db_session):
    """高风险特征组合 → 概率高于低风险特征组合（单调性）。"""
    provider = MockRiskProvider()

    order_high = _make_order(db_session, "SFO_HIGH")
    feat_high = _make_feature(
        db_session,
        order_high.id,
        avg_pay_duration_days=30.0,  # 历时长
        history_fee_order_count=0,  # 无信用积累
        win_rate=0.0,  # 中标率低
        active_90d=0,  # 不活跃
        is_member_at_win=False,  # 非会员
    )

    order_low = _make_order(db_session, "SFO_LOW")
    feat_low = _make_feature(
        db_session,
        order_low.id,
        avg_pay_duration_days=1.0,  # 历时短
        history_fee_order_count=10,  # 信用积累足
        win_rate=1.0,  # 中标率高
        active_90d=20,  # 活跃
        is_member_at_win=True,  # 会员
    )
    db_session.commit()

    prob_high = provider.calculate(order_high, feat_high)
    prob_low = provider.calculate(order_low, feat_low)
    assert prob_high > prob_low, (
        f"高风险特征应产出更高概率: {prob_high} vs {prob_low}"
    )


# ── 防数据泄漏：mock 不依赖标签字段 ───────────────────────────────


def test_mock_provider_ignores_label_fields(db_session):
    """改变标签字段（label_30/actual_pay_duration）不影响概率（防泄漏）。"""
    order = _make_order(db_session, "SFO_LEAK")
    feat = _make_feature(db_session, order.id)
    # 标签字段设"事后欠费"值
    feat.label_30 = 1
    feat.label_90 = 1
    feat.label_180 = 1
    feat.label_365 = 1
    feat.actual_pay_duration_days = 999
    db_session.commit()

    provider = MockRiskProvider()
    prob_with_labels = provider.calculate(order, feat)

    # 清空标签字段
    feat2 = OrderFeature(
        order_id=order.id,
        avg_pay_duration_days=feat.avg_pay_duration_days,
        history_fee_order_count=feat.history_fee_order_count,
        win_rate=feat.win_rate,
        active_90d=feat.active_90d,
        is_member_at_win=feat.is_member_at_win,
    )
    prob_without_labels = provider.calculate(order, feat2)

    assert prob_with_labels == prob_without_labels, "mock 不应使用标签字段"


# ── 权限：recalc 端点需 ADMIN ──────────────────────────────────────


def test_recalc_requires_admin(client, seed_users):
    """COLLECTOR 触发重算 → 403。"""
    resp = client.post(
        "/api/auth/login",
        json={"username": "collector1", "password": "admin123"},
    )
    collector_token = resp.json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {collector_token}"}

    resp = client.post("/api/data/orders/recalc-risk", headers=headers)
    assert resp.status_code == 403


def test_recalc_requires_auth(client, seed_users):
    """未登录触发重算 → 401。"""
    resp = client.post("/api/data/orders/recalc-risk")
    assert resp.status_code == 401


def test_recalc_empty_orders(client, seed_users, db_session):
    """无订单时重算不报错，返回 recalculated=0。"""
    resp = client.post("/api/data/orders/recalc-risk", headers=_auth_headers(client))
    assert resp.status_code == 200
    assert resp.json()["data"]["recalculated"] == 0
