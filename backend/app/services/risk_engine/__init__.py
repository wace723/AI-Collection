"""风险计算模块：Provider 抽象 + Mock 实现 + 档位映射 + 重算编排。

对外暴露稳定的入口，调用方（API/任务调度）只需依赖 calculator.recalculate_risks，
切换 mock→algorithm 通过配置或注入，调用方代码不变。
"""

from app.services.risk_engine.calculator import (
    RecalcResult,
    get_risk_provider,
    recalculate_risks,
)
from app.services.risk_engine.provider import (
    AlgorithmRiskProvider,
    MockRiskProvider,
    RiskProvider,
)
from app.services.risk_engine.config_service import (
    DEFAULT_SCHEDULES,
    AlreadyActiveError,
    ConfigNotFoundError,
    ConfigSnapshot,
    get_config_history,
    get_current_config,
    rollback_to_version,
    seed_default_config,
    update_config,
)
from app.services.risk_engine.tier_mapper import (
    HIGH,
    LOW,
    MEDIUM,
    Thresholds,
    get_active_thresholds,
    map_tier,
)

__all__ = [
    "RiskProvider",
    "MockRiskProvider",
    "AlgorithmRiskProvider",
    "RecalcResult",
    "get_risk_provider",
    "recalculate_risks",
    "Thresholds",
    "get_active_thresholds",
    "map_tier",
    "HIGH",
    "MEDIUM",
    "LOW",
    "DEFAULT_SCHEDULES",
    "ConfigSnapshot",
    "ConfigNotFoundError",
    "AlreadyActiveError",
    "get_current_config",
    "get_config_history",
    "update_config",
    "rollback_to_version",
    "seed_default_config",
]
