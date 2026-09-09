# 会话交接

> 会话间快速交接用。详细进度见 `claude-progress.md`，功能状态见 `feature_list.json`。

## 当前已验证

- 现在明确可用的部分：infra-001 骨架、infra-002 鉴权、data-001 CSV 上传与解析（37 列特征入库）、**risk-001 Mock 风险概率计算 + RiskProvider 抽象**
- 这轮实际跑过的验证：
  - 后端 pytest 37 passed（3 health + 9 auth + 9 data + 16 risk）
  - 端到端真实联调：示例 CSV 20 条入库 → POST /api/data/orders/recalc-risk → 20 笔全部回写 risk_prob/risk_tier，三档分布 HIGH=5/MEDIUM=12/LOW=3，0 NULL，概率范围 18.75~85.83
  - init.sh 退出码 0

## 本轮改动（risk-001）

- 新增了哪些代码或行为：
  - 后端 `services/risk_engine/provider.py`：RiskProvider 抽象 + MockRiskProvider（5 维确定性加权：历史缴费平均历时 0.35 + 历史平台使用费订单数 0.25 + 历史中标率 0.20 + 近90天活跃度 0.15 + 非会员 0.05）+ AlgorithmRiskProvider 占位
  - 后端 `services/risk_engine/tier_mapper.py`：Thresholds + get_active_thresholds（读 active 配置，无则回退默认 70/30）+ map_tier 纯函数（≥即归档）
  - 后端 `services/risk_engine/calculator.py`：recalculate_risks 编排器（拉订单+特征→算概率→映射→回写 Order.risk_prob/risk_tier/risk_calc_time）+ get_risk_provider 工厂（按 settings.RISK_PROVIDER 注入，可切 mock→algorithm）
  - 后端 `services/risk_engine/__init__.py`：稳定对外入口
  - 后端 `schemas/risk.py`：RecalcRiskSummary + RiskTierOut
  - 后端 `core/config.py`：加 `RISK_PROVIDER` 开关（mock | algorithm）
  - 后端 `api/data.py`：挂载 `POST /api/data/orders/recalc-risk`（ADMIN 权限）
  - 测试 `tests/test_risk.py` 16 用例
- 基础设施或 harness 发生了哪些变化：
  - 无表结构变更（Order 已有 risk_prob/risk_tier/risk_calc_time 字段，RiskConfig/CollectionSchedule 表 infra-001 已建好）
  - risk_configs 表尚无种子数据（tier_mapper 读不到 active 配置时回退默认 70/30）

## 仍损坏或未验证

- 已知缺陷：无
- 未验证路径：risk-002 及之后功能均 not_started
- 下一轮会话需要注意的风险：
  - SQLite BigInteger 自增问题已彻底修复，勿重新引入裸 `BigInteger()` 作主键（沿用记录）
  - 测试内存 SQLite 必须用 StaticPool（沿用记录）
  - vite 监听 IPv6，前端访问用 `localhost` 不是 `127.0.0.1`（沿用记录）
  - 后端默认端口 8000（与 vite proxy target 对齐）
  - AlgorithmRiskProvider 为占位，调用抛 NotImplementedError，上线真实算法时实现
  - mock 公式刻意不用 label_30/90/180/365 与 actual_pay_duration_days（防数据泄漏）

## 下一步最佳动作

- 最高优先级未完成功能：`risk-002` 风险档配置（阈值+催收时点，版本化）
- 为什么它是下一步：risk-001 已提供 MockRiskProvider + tier_mapper（读 active 配置回退默认阈值）；risk-002 补齐 risk_configs + collection_schedules 的 CRUD + 默认种子，为 task-001 跑批提供配置基础（催收时点表是任务生成的依据）
- 什么结果才算 passing：
  - 默认配置：HIGH=7/15/30天，MEDIUM=30天，LOW=90天（对应 TC-RISK-05）
  - 阈值边界值映射正确（对应 TC-RISK-03）
  - 改阈值重算生效（对应 TC-RISK-04）
  - 配置历史可查可回滚（对应 TC-RISK-06）
- 这一步中哪些东西不要动：
  - docs/ 下需求架构（已是基线）
  - RiskProvider 抽象 + MockRiskProvider 公式（risk-001 已落地，risk-002 只读配置不改算法）
  - Order/OrderFeature 模型字段（data-001 已落地）
  - CLAUDE.md 的设计约束

## risk-002 实现要点（给新会话的提示）

- 复用：`RiskConfig`/`CollectionSchedule` 模型（risk.py 已建好）、`Thresholds`/`get_active_thresholds`/`map_tier`（tier_mapper 已实现）、`APIResponse[T]`、`require_role("ADMIN")`、`get_db`
- 新建：
  - `app/api/config.py`（risk 配置 CRUD 路由，对应 docs/02 §5.3）
  - `app/schemas/config.py`（配置读写 schema）
  - `app/services/config/` 或直接在 risk_engine 下加 `config_service.py`（配置版本管理 + 默认种子）
  - 默认种子：risk_configs v1 (high=70, medium=30, is_active=True) + collection_schedules（HIGH 7/15/30 FIRST/SECOND/THIRD、MEDIUM 30 FIRST、LOW 90 FIRST）
  - 配置更新逻辑：生成新版本号 +1，旧版本 is_active=False，新版本 is_active=True（版本化回滚）
- 验证：改阈值 → recalc-risk 验证档位变化（risk-001 的 recalc 端点已可触发重算）
- 参考 docs/02 §3.2.3/§3.2.4、docs/03 TC-RISK-03~06

## 命令

- 启动命令：`./init.sh`（骨架就绪后 `RUN_START_COMMAND=1 ./init.sh`）
- 验证命令：后端 `cd backend && pytest -q`；前端 `cd frontend && npm run build`
- 种子数据：`cd backend && source .venv/Scripts/activate && python seed.py`（当前仅用户，risk-002 应在此加 risk_config 默认种子）
- 启动后端：`cd backend && uvicorn app.main:app --reload --port 8000`（用 localhost 访问）
- 启动前端：`cd frontend && npm run dev`（5173，用 localhost 访问）
- 默认账号：admin/supervisor/collector1-3，密码 admin123
- 重算风险：登录 admin 后 `POST /api/data/orders/recalc-risk`（需先上传 CSV）
