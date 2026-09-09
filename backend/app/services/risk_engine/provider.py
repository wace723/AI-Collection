"""风险概率计算 Provider 抽象层。

设计约束（CLAUDE.md 关键设计约束 #1）：
风险算法必须经 ``RiskProvider`` 抽象接口，MVP 用 ``MockRiskProvider``，
后续替换为 ``AlgorithmRiskProvider`` 时调用方（任务调度）无感知。

每个 Provider 仅负责"概率计算"单一职责，不生成任务、不写库（见
docs/02 §7.4 工具设计）。写库与档位映射由 calculator 编排器统一处理。
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.models.order import Order, OrderFeature


class RiskProvider(ABC):
    """风险概率计算抽象接口。

    实现需保证 ``calculate`` 返回 [0, 100] 的浮点数。
    """

    name: str = "base"

    @abstractmethod
    def calculate(self, order: Order, feature: OrderFeature | None) -> float:
        """计算单笔订单的欠费风险概率。

        Args:
            order: 订单标识与状态
            feature: 订单特征（37 列），可能为 None（特征缺失）

        Returns:
            0~100 的风险概率
        """
        raise NotImplementedError


class MockRiskProvider(RiskProvider):
    """MVP mock 实现：基于历史缴费历时等维度的确定性加权。

    **确定性**：相同输入→相同输出，不引入随机数（便于测试与幂等跑批）。
    **防泄漏**：刻意不使用 label_30/90/180/365、actual_pay_duration_days
    等标签字段（这些是"事后结果"，中标时刻取数会泄漏未来信息，见
    docs/02 §3.2.2 数据泄漏提示）。仅用 A/B/C 类事前特征。

    加权维度（参考 docs/02 §4.1）：
    - 历史缴费平均历时越长 → 风险越高（缴费习惯差）
    - 历史平台使用费订单数越少 → 风险越高（新用户，无信用积累）
    - 历史中标率越低 → 风险越高（平台粘性弱）
    - 近 90 天活跃度越低 → 风险越高（可能失联）
    - 非会员 → 风险略高
    """

    name: str = "mock"

    # 权重总和 = 1.0，每维贡献 0~1 的子分，加权后映射到 [0,100]
    _W_PAY_DURATION = 0.35
    _W_FEE_ORDER_COUNT = 0.25
    _W_WIN_RATE = 0.20
    _W_ACTIVE_90D = 0.15
    _W_NON_MEMBER = 0.05

    # 归一化基准（经验值，mock 阶段用于把原始特征压到 0~1）
    _PAY_DURATION_REF = 30.0  # 历史平均缴费历时参考上限（天）
    _FEE_ORDER_COUNT_REF = 5.0  # 历史平台使用费订单数参考上限
    _ACTIVE_90D_REF = 10.0  # 近 90 天活跃度参考上限

    def calculate(self, order: Order, feature: OrderFeature | None) -> float:
        if feature is None:
            # 无特征：给中性偏高风险（信息不足视为风险偏高）
            return 50.0

        score = (
            self._pay_duration_score(feature) * self._W_PAY_DURATION
            + self._fee_order_count_score(feature) * self._W_FEE_ORDER_COUNT
            + self._win_rate_score(feature) * self._W_WIN_RATE
            + self._active_90d_score(feature) * self._W_ACTIVE_90D
            + self._non_member_score(feature) * self._W_NON_MEMBER
        )
        # score ∈ [0,1]，映射到 [0,100] 并钳制
        prob = round(max(0.0, min(1.0, score)) * 100.0, 2)
        return prob

    # ── 子分计算（各自返回 0~1，越大风险越高） ──────────────────────

    @staticmethod
    def _clamp01(x: float) -> float:
        return max(0.0, min(1.0, x))

    def _pay_duration_score(self, f: OrderFeature) -> float:
        """历史缴费平均历时越长，风险越高；None 给中性 0.5。"""
        v = f.avg_pay_duration_days
        if v is None:
            return 0.5
        # 历时 0 → 低风险；≥ 参考上限 → 高风险
        return self._clamp01(float(v) / self._PAY_DURATION_REF)

    def _fee_order_count_score(self, f: OrderFeature) -> float:
        """历史平台使用费订单数越多（信用积累足），风险越低。"""
        v = f.history_fee_order_count
        if v is None:
            return 0.5
        # 订单数 0 → 1.0（高风险）；≥ 参考上限 → 0.0
        return self._clamp01(1.0 - float(v) / self._FEE_ORDER_COUNT_REF)

    @staticmethod
    def _win_rate_score(f: OrderFeature) -> float:
        """历史中标率越低，风险越高。"""
        v = f.win_rate
        if v is None:
            return 0.5
        # 中标率 0 → 1.0；1 → 0.0
        return MockRiskProvider._clamp01(1.0 - float(v))

    def _active_90d_score(self, f: OrderFeature) -> float:
        """近 90 天活跃度越低，风险越高（可能失联）。"""
        v = f.active_90d
        if v is None:
            return 0.5
        return self._clamp01(1.0 - float(v) / self._ACTIVE_90D_REF)

    @staticmethod
    def _non_member_score(f: OrderFeature) -> float:
        """非会员风险略高。"""
        v = f.is_member_at_win
        if v is None:
            return 0.5
        return 0.3 if v else 0.8  # 会员 0.3，非会员 0.8


class AlgorithmRiskProvider(RiskProvider):
    """后续实现占位：调用训练好的模型服务。

    上线真实算法时实现此类，通过配置注入切换，调用方代码不变。
    当前未实现，调用时抛 NotImplementedError 以防误用。
    """

    name: str = "algorithm"

    def calculate(self, order: Order, feature: OrderFeature | None) -> float:
        raise NotImplementedError("AlgorithmRiskProvider 尚未实现，请使用 mock")


__all__ = ["RiskProvider", "MockRiskProvider", "AlgorithmRiskProvider"]
