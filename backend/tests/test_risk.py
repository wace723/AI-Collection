"""risk-002 风险档阈值映射测试（重写）。

data-002 改造后：
- 风险概率由 CSV 导入写入，跑批不再调 MockRiskProvider 重算
- 旧 `/api/data/orders/recalc-risk` 已删除（调 MockRiskProvider 预测的测试整体移除）

保留覆盖：
- tier_mapper 纯函数边界值（map_tier）
- get_active_thresholds 默认回退 + active 配置读取
- 导入时风险概率→档位映射（经 tier_mapper，依赖 seed_default_config）

MockRiskProvider 的确定性/单调性/防泄漏测试与 data-002 无关，且 Provider
抽象仍由 run_batch(recalc_risk=True) 复用（见 test_task_generation），此处不再
重复覆盖。recalc-risk API 已删，权限/空库端点测试整体移除。
"""

from __future__ import annotations

from app.models.order import Order
from app.models.risk import RiskConfig
from app.services.data_ingestion.parser import ingest_pending_rows
from app.services.risk_engine import (
    Thresholds,
    get_active_thresholds,
    map_tier,
    seed_default_config,
)
from app.services.risk_engine.config_service import get_current_config


# ── TC-RISK-02/03：风险档阈值映射边界值（纯函数） ──────────────────


def test_map_tier_boundaries_default():
    """默认阈值 70/30 边界值（docs/03 TC-RISK-02/03）。"""
    t = Thresholds()  # 默认 high=70, medium=30
    assert map_tier(85, t) == "HIGH"
    assert map_tier(45, t) == "MEDIUM"
    assert map_tier(15, t) == "LOW"


def test_map_tier_edge_values():
    """TC-RISK-03 边界值精确断言：≥ 即归入该档。"""
    t = Thresholds(high=70, medium=30)
    assert map_tier(70.00, t) == "HIGH"
    assert map_tier(69.99, t) == "MEDIUM"
    assert map_tier(30.00, t) == "MEDIUM"
    assert map_tier(29.99, t) == "LOW"
    assert map_tier(0, t) == "LOW"
    assert map_tier(100, t) == "HIGH"


def test_map_tier_custom_thresholds():
    """自定义阈值（模拟改阈值后重映射，TC-RISK-04 的前置）。"""
    t = Thresholds(high=60, medium=20)
    assert map_tier(60, t) == "HIGH"
    assert map_tier(59.99, t) == "MEDIUM"
    assert map_tier(20, t) == "MEDIUM"
    assert map_tier(19.99, t) == "LOW"


# ── get_active_thresholds：默认回退 + active 配置 ────────────────────


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


def test_seed_default_config_activates_70_30(db_session):
    """seed_default_config 插入 active 配置 v1（70/30 + 5 schedules），幂等。"""
    assert seed_default_config(db_session) is True  # 新建
    assert seed_default_config(db_session) is False  # 已存在 active，跳过

    snapshot = get_current_config(db_session)
    assert snapshot is not None
    assert snapshot.config.is_active is True
    assert float(snapshot.config.high_threshold) == 70.0
    assert float(snapshot.config.medium_threshold) == 30.0
    # 5 条默认催收时点
    assert len(snapshot.schedules) == 5

    t = get_active_thresholds(db_session)
    assert t.high == 70.0
    assert t.medium == 30.0


# ── 导入时风险概率→档位映射（经 tier_mapper） ─────────────────────


def _pending_row(order_no: str, risk_prob: str) -> dict[str, str]:
    """构造一行待支付 CSV 行 dict（只含解析需要的列，其余留空）。"""
    row = {col: "" for col in (
        "供应商编号", "供应商名称", "招标编号", "服务费订单号",
        "标的名称", "招标类型", "采购类型", "中标品类", "合同类型",
        "标的概算金额", "中标日期", "订单生成日期",
        "历史平台使用费订单数", "上次缴费历时_天", "历史缴费平均历时_天",
        "服务市场历史支付金额", "历史报名次数", "历史投标次数", "历史中标次数",
        "历史中标率", "近90天投标活跃度", "首次中标距本次间隔_天",
        "中标时是否会员", "中标前购买会员次数", "注册资金", "注册地区", "注册省份",
        "注册时间距中标间隔_天", "平台入驻时间距中标间隔_天",
        "最早入库时间距中标间隔_天", "标签表历史中标率", "股份优质评级次数",
        "合作单位数量", "累计履约项目数", "中标月份", "是否月末", "是否季末",
        "风险概率",
    )}
    row["供应商编号"] = "S001"
    row["供应商名称"] = "测试公司"
    row["招标编号"] = "B001"
    row["服务费订单号"] = order_no
    row["风险概率"] = risk_prob
    return row


def test_import_maps_risk_prob_to_tier(db_session):
    """导入时风险概率经 tier_mapper 映射档位（seed_default_config 后）。"""
    seed_default_config(db_session)

    rows = [
        _pending_row("SFO_IMP_HIGH", "75"),    # 75 ≥ 70 → HIGH
        _pending_row("SFO_IMP_MED", "50"),     # 50 ≥ 30 → MEDIUM
        _pending_row("SFO_IMP_LOW", "15"),     # 15 < 30 → LOW
    ]
    result = ingest_pending_rows(db_session, rows)
    assert result.inserted == 3

    orders = (
        db_session.query(Order)
        .order_by(Order.service_fee_order_no)
        .all()
    )
    tiers = {o.service_fee_order_no: o.risk_tier for o in orders}
    assert tiers["SFO_IMP_HIGH"] == "HIGH"
    assert tiers["SFO_IMP_MED"] == "MEDIUM"
    assert tiers["SFO_IMP_LOW"] == "LOW"
    # 风险概率与档位一致：map_tier 纯函数复核
    t = Thresholds()
    for o in orders:
        assert o.risk_tier == map_tier(float(o.risk_prob), t)


def test_import_null_risk_prob_yields_null_tier(db_session):
    """风险概率为空 → risk_tier=None（不入档）。"""
    seed_default_config(db_session)
    row = _pending_row("SFO_NULL_RISK", "")
    result = ingest_pending_rows(db_session, [row])
    assert result.inserted == 1

    order = (
        db_session.query(Order)
        .filter(Order.service_fee_order_no == "SFO_NULL_RISK")
        .first()
    )
    assert order.risk_prob is None
    assert order.risk_tier is None
    assert order.risk_import_time is None  # 无风险概率不写导入时间


def test_import_custom_thresholds_affect_mapping(db_session):
    """自定义 active 阈值后，导入按新阈值映射档位。"""
    # 自定义阈值 high=60, medium=20
    db_session.add(
        RiskConfig(
            version=1,
            high_threshold=60,
            medium_threshold=20,
            is_active=True,
        )
    )
    db_session.commit()

    # 风险概率=50：默认 70/30 → MEDIUM；自定义 60/20 → 50≥20 → 仍 MEDIUM
    # 风险概率=55：默认 70/30 → MEDIUM；自定义 60/20 → 55<60 且 ≥20 → MEDIUM
    # 风险概率=62：默认 70/30 → MEDIUM；自定义 60/20 → 62≥60 → HIGH（差异点）
    rows = [
        _pending_row("SFO_CUST_50", "50"),
        _pending_row("SFO_CUST_62", "62"),
    ]
    ingest_pending_rows(db_session, rows)

    orders = {
        o.service_fee_order_no: o.risk_tier
        for o in db_session.query(Order).all()
    }
    assert orders["SFO_CUST_50"] == "MEDIUM"
    assert orders["SFO_CUST_62"] == "HIGH"  # 自定义阈值下 62 → HIGH

    # 用默认阈值复核：62 应为 MEDIUM（证明自定义阈值生效）
    assert map_tier(62.0, Thresholds()) == "MEDIUM"
