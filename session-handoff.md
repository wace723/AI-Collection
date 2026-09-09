# 会话交接

> 会话间快速交接用。详细进度见 `claude-progress.md`，功能状态见 `feature_list.json`。

## 当前已验证

- 现在明确可用的部分：infra-001 骨架、infra-002 鉴权、**data-001 CSV 上传与解析（37 列特征入库）**
- 这轮实际跑过的验证：
  - 后端 pytest 21 passed（3 health + 9 auth + 9 data）
  - 端到端真实联调：GBK 示例 CSV 上传 20 条入库、空值 NULL、重复去重、中文无乱码
  - 前端联调：经 vite proxy 5173 上传 20 条入库、列表 total=20
  - init.sh 退出码 0

## 本轮改动（data-001）

- 新增了哪些代码或行为：
  - 后端 services/data_ingestion/：columns.py（37 列映射常量）、encoding.py（GBK/UTF-8 自动探测）、parser.py（解析+去重入库）
  - 后端 schemas/data.py、api/data.py（POST /api/data/upload + GET /orders + GET /orders/{id}）、router 挂载 /data
  - 测试 tests/test_data_upload.py 9 用例（TC-DATA-01~07 + 权限 403/401）
  - 前端 types/api.ts 加 UploadSummary/Order/OrderList、api/data.ts、Config 页 CSV 拖拽上传 UI（ADMIN 校验）
- 基础设施或 harness 发生了哪些变化：
  - **修复 infra-001 遗留缺陷**：SQLite 下 BigInteger 主键/FK 不自增。orders/tasks/task_results/order_features 4 表的 BigInteger 改用 `BigInteger().with_variant(Integer, "sqlite")`（PostgreSQL 保持 BIGINT）。models/order.py、models/task.py、alembic/versions/0baedee4c6c7_init_schema.py 同步修正。

## 仍损坏或未验证

- 已知缺陷：无
- 未验证路径：risk-001 及之后功能均 not_started
- 下一轮会话需要注意的风险：
  - SQLite BigInteger 自增问题已彻底修复，勿重新引入裸 `BigInteger()` 作主键
  - 测试内存 SQLite 必须用 StaticPool（沿用 infra-002 记录）
  - vite 监听 IPv6，前端访问用 `localhost` 不是 `127.0.0.1`（沿用记录）
  - 后端默认端口 8000（与 vite proxy target 对齐），之前 session 用过 8123，新会话统一用 8000

## 下一步最佳动作

- 最高优先级未完成功能：`risk-001` Mock 风险概率计算 + RiskProvider 抽象
- 为什么它是下一步：data-001 已提供订单+特征数据，risk-001 在此基础上算欠费风险概率；risk-001 → task-001 是核心链路
- 什么结果才算 passing：
  - RiskProvider 抽象接口 + MockRiskProvider（基于历史缴费历时等加权），返回 0~100
  - 触发重算后每笔订单 risk_prob ∈ [0,100]，risk_tier 按 active 配置映射
  - Provider 接口可切换 mock→algorithm 不改调用方
  - 对应 TC-RISK-01/02 全过
- 这一步中哪些东西不要动：
  - docs/ 下需求架构（已是基线）
  - Order/OrderFeature 模型字段与 CSV 列映射（data-001 已落地）
  - CLAUDE.md 的设计约束（风险算法必须经 RiskProvider 抽象接口）

## risk-001 实现要点（给新会话的提示）

- 复用：`Order`/`OrderFeature` 模型、`APIResponse[T]`、`require_role("ADMIN")`、`get_db`
- 新建：`app/services/risk_engine/provider.py`（RiskProvider 抽象 + MockRiskProvider）、`app/api/risk.py`（触发重算端点）、`app/schemas/risk.py`
- RiskProvider 抽象接口：`calculate(order, feature) -> float`、`batch_calculate(...) -> ...`
- MockRiskProvider 加权维度参考 docs/02：历史缴费历时、历史平台使用费订单数、活跃度、中标率等（mock 应覆盖高/中/低三档分布便于测试）
- risk_tier 映射依赖 risk_configs active 配置（risk-002 才做配置 CRUD，risk-001 先用默认阈值或读 active 配置表）
- 参考 docs/02-技术架构设计.md §风险引擎、docs/03-测试用例.md TC-RISK-01/02

## 命令

- 启动命令：`./init.sh`（骨架就绪后 `RUN_START_COMMAND=1 ./init.sh`）
- 验证命令：后端 `cd backend && pytest -q`；前端 `cd frontend && npm run build`
- 种子数据：`cd backend && source .venv/Scripts/activate && python seed.py`
- 启动后端：`cd backend && uvicorn app.main:app --reload --port 8000`（用 localhost 访问）
- 启动前端：`cd frontend && npm run dev`（5173，用 localhost 访问）
- 默认账号：admin/supervisor/collector1-3，密码 admin123
