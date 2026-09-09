# 进度日志

## 当前已验证状态

- 仓库根目录：`e:/my-projects/平台使用费ai辅助催收系统`
- 标准启动路径：`./init.sh`
- 标准验证路径：后端 `pytest` + 前端 `npm run build`（骨架就绪后）
- 当前最高优先级未完成功能：`wb-001` 催收工作台（任务列表/详情/结果回填 UI）
- 当前 blocker：无（task-002 已 passing，跑批生成+分配+状态机可用；前端工作台待做）
- 双工具：本仓库现由 Claude Code（路由层 `CLAUDE.md`）与 CodeBuddy（路由层 `CODEBUDDY.md`）共用同一套 docs/ 与状态文件开发

## 已完成的基础工件

- [x] docs/01-产品需求文档.md（PRD：6 大功能模块 + MVP 范围 + 验收标准）
- [x] docs/02-技术架构设计.md（技术栈 + 架构图 + 9 张数据表 + API 设计 + AI 架构）
- [x] docs/03-测试用例.md（50+ 用例覆盖 7 模块 + 3 E2E）
- [x] docs/00-文档索引.md
- [x] CLAUDE.md（harness 路由层）
- [x] feature_list.json（12 个功能，按 PRD 拆解）
- [x] init.sh、session-handoff.md、clean-state-checklist.md

## 关键决策记录（ADR 速记）

- 风险概率 MVP mock，RiskProvider 抽象可替换，后续接算法无感知
- 话术双层：模板为主 + LLM 增强（可开关），LLM 失败降级模板
- 任务幂等：batch_id + order_id + day_offset 三元组唯一
- 风险档全可配置：阈值 + 催收时点 + 场景
- C 类标签表特征无时间维度，上线真实算法前需时间切割（防泄漏）
- 平台阻断不在本系统，"阻断"语义=催收节点强提醒+人工介入

## 会话记录

### Session 001

- 日期：2026-09-08
- 本轮目标：理解需求 → 落地需求/架构/测试文档 → 搭建 harness 五子系统
- 已完成：
  - 澄清系统定位、风险档语义、MVP 范围（2 轮 AskUserQuestion）
  - 用 agent-app-builder 方法论产出 PRD/架构/测试三份文档
  - 用 harness-creator 五子系统框架搭建：CLAUDE.md + feature_list.json + init.sh + 交接/检查清单
- 运行过的验证：无代码，仅文档工件
- 已记录证据：文档已创建（见上"已完成基础工件"）
- 提交记录：无（仓库尚未 git init）
- 更新过的文件或工件：docs/*、CLAUDE.md、feature_list.json、init.sh、session-handoff.md、clean-state-checklist.md
- 已知风险或未解决问题：
  - 仓库尚未 git init，建议首步即初始化
  - 技术栈（Python FastAPI + React）待用户最终确认
  - 数据大盘具体指标细节待补
  - 逾期滚动跟进逻辑（v2.2）待定
- 下一步最佳动作：确认技术栈 → 初始化 git → 执行 `infra-001` 搭建前后端骨架

### Session 002

- 日期：2026-09-08
- 本轮目标：完成 `infra-001` 项目骨架与运行环境
- 已完成：
  - git init + 基线提交（harness 文件）
  - 后端骨架：FastAPI + SQLAlchemy 2.0 + Alembic，9 张表 ORM 模型，/health 端点，pytest 2 passed
  - 前端骨架：Vite + React 18 + TS + Ant Design 5，4 个占位页 + 登录页 + 布局 + 路由 + axios 客户端
  - docker-compose.yml + Dockerfile + nginx.conf + README.md（交付不验证，本地无 Docker）
  - init.sh 去降级兜底 + PYTHONUTF8=1，./init.sh 全流程退出码 0
  - feature_list.json infra-001 → passing + evidence
- 运行过的验证：
  - `python -c "import app.models"` → 9 张表
  - `alembic revision --autogenerate` → 检测到 9 张表
  - `alembic upgrade head` → 9 业务表建表成功
  - `pytest -q` → 2 passed
  - `uvicorn app.main:app` + `curl /health` → 200 {"status":"ok"}
  - `npm run build` → ✓ built
  - `npm run dev` → Vite ready, HTTP 200
  - `./init.sh` → 退出码 0
- 已记录证据：见 feature_list.json infra-001.evidence
- 提交记录：`chore: bootstrap harness`、即将 `feat: scaffold backend+frontend`
- 更新过的文件或工件：backend/（app/*、alembic/*、tests/*、requirements.txt、alembic.ini、Dockerfile）、frontend/（src/*、vite.config.ts、Dockerfile、nginx.conf）、docker-compose.yml、init.sh、README.md、.gitignore、feature_list.json、claude-progress.md
- 已知风险或未解决问题：
  - Vite 实装 v8.2.2（非预期 v5），功能正常，后续若需固定版本可锁
  - alembic.ini 含中文注释会致 GBK 解码错误，已全改英文（坑点记录）
  - 迁移脚本 autogenerate 生成 `postgresql.JSONB(astext_type=Text())` 缺 Text 导入，已手动修正为 sa.Text()
  - dev.db 生成在 backend/ 下（已被 .gitignore 覆盖）
  - chunk 超 500kB 警告（antd 整包），后续按需 code-split
- 下一步最佳动作：开始 `infra-002` 认证授权（JWT 登录、角色权限、3 名催收员+主管+管理员种子数据）

### Session 003

- 日期：2026-09-09
- 本轮目标：完成 `infra-002` 认证授权（JWT + 角色权限 + 种子数据）
- 已完成：
  - 后端：security.py 4 函数实现（bcrypt 原生 API + jose JWT）、deps.py 加 get_current_user/require_role、schemas/auth.py、api/auth.py（login/me/admin-only/supervisor-or-admin）、router.py 挂载、seed.py 种子脚本
  - 测试：test_auth.py 9 个用例 + conftest 加 seed_users fixture，pytest 12 passed
  - 前端：types 加 User/LoginData、auth.ts 实现、RequireAuth 路由守卫、Login 表单接入、App.tsx 包裹守卫、client 401 跳转
- 运行过的验证：
  - `pytest -q` → 12 passed
  - `python seed.py` → 5 个用户入库
  - curl：登录 200+token、/me 带 token 200、无 token 401、admin-only admin 200/collector 403、错误密码 401
  - `npm run build` → ✓ built
  - 前后端联调：vite proxy POST /api/auth/login → 登录成功，错误密码 401
- 已记录证据：见 feature_list.json infra-002.evidence
- 已知风险或未解决问题：
  - passlib 1.7.4 + bcrypt 5.0 不兼容（读不到 bcrypt 版本号误判密码长度），已弃用 passlib 改用 bcrypt 原生 API
  - 测试内存 SQLite 需 StaticPool 共享连接，否则 TestClient 跨连接 no such table
  - bcrypt 哈希有 DeprecationWarning（utcnow），无害
- 下一步最佳动作：开始 `data-001` CSV 上传与解析（37 列特征入库），这是催收任务数据来源

### Session 004

- 日期：2026-09-09
- 本轮目标：完成 `data-001` CSV 上传与解析（37 列特征入库）
- 已完成：
  - 后端：services/data_ingestion/（columns.py 37 列映射常量 + encoding.py GBK/UTF-8 自动探测 + parser.py 解析入库去重）、schemas/data.py、api/data.py（POST /api/data/upload + GET /orders + GET /orders/{id}）、router 挂载
  - 测试：test_data_upload.py 9 用例（TC-DATA-01~07 + 权限 403/401），pytest 21 passed
  - 前端：types 加 UploadSummary/Order/OrderList、api/data.ts、Config 页 CSV 拖拽上传 UI（ADMIN 权限校验），npm run build 通过
- 运行过的验证：
  - `pytest -q` → 21 passed（3 health + 9 auth + 9 data）
  - 端到端真实联调（/e/tmp/verify_data_e2e.py）：GBK 示例 CSV 上传 20 条入库、河南曼之达空值=NULL、重复上传 0/20 去重、中文无乱码
  - 前端联调：经 vite proxy 5173 上传 20 条入库、列表 total=20
  - `./init.sh` → 退出码 0
- 已记录证据：见 feature_list.json data-001.evidence
- 已知风险或未解决问题：
  - **修复 infra-001 遗留缺陷**：SQLite 下 BigInteger 主键/FK 不自增（只有 INTEGER PRIMARY KEY 是 rowid 别名），orders/tasks/task_results/order_features 4 表受影响。改用 `BigInteger().with_variant(Integer, "sqlite")`，模型 + init 迁移脚本同步修正。PostgreSQL 保持 BIGINT 不受影响。data-001 入库因此前直接 NOT NULL 失败，已彻底修复。
  - verify_data_e2e.py 中文字面量相等断言受 bash GBK 终端影响（`==` False 但 `in` True），改用 `in` 子串断言；API 返回的 UTF-8 数据本身正确。
  - 真实 CSV 河南曼之达：实际支付时长=空(NULL)、历史缴费平均历时=90、历史平台使用费订单数=1（与测试构造数据 CSV_ROW_OVERDUE 不同，均符合逻辑）。
  - 前端 chunk 超 500kB 警告（antd 整包），沿用 infra-001 记录，后续按需 code-split。
- 下一步最佳动作：开始 `risk-001` Mock 风险概率计算 + RiskProvider 抽象（依赖 data-001 已就绪）

### Session 005

- 日期：2026-09-09
- 本轮目标：完成 `risk-001` Mock 风险概率计算 + RiskProvider 抽象
- 已完成：
  - `services/risk_engine/provider.py`：RiskProvider 抽象 + MockRiskProvider（5 维确定性加权）+ AlgorithmRiskProvider 占位
  - `services/risk_engine/tier_mapper.py`：Thresholds + get_active_thresholds（读 active 配置，无则回退 70/30）+ map_tier 纯函数
  - `services/risk_engine/calculator.py`：recalculate_risks 编排器（拉订单+特征→算概率→映射→回写）+ get_risk_provider 工厂（按 settings.RISK_PROVIDER 注入）
  - `services/risk_engine/__init__.py`：稳定对外入口
  - `schemas/risk.py`：RecalcRiskSummary + RiskTierOut
  - `core/config.py`：加 RISK_PROVIDER 开关（mock | algorithm）
  - `api/data.py`：挂载 POST /api/data/orders/recalc-risk（ADMIN），恢复误删的 get_order 函数体
  - 测试 `tests/test_risk.py` 16 用例（TC-RISK-01/02/03 + Provider 可切换 + 确定性 + 防泄漏 + 权限）
- 运行过的验证：
  - `pytest tests/test_risk.py -q` → 16 passed
  - `./init.sh` → 退出码 0：pytest 37 passed（3 health + 9 auth + 9 data + 16 risk）+ npm run build ✓
  - 端到端真实联调：示例 CSV 20 条入库 → POST /api/data/orders/recalc-risk → recalculated=20，三档分布 HIGH=5/MEDIUM=12/LOW=3，0 NULL，概率范围 18.75~85.83 全 ∈[0,100]
- 已记录证据：见 feature_list.json risk-001.evidence
- 已知风险或未解决问题：
  - `del skipped` 在 calculator.py 中是占位（当前无跳过逻辑），保留字段供后续扩展，无害
  - AlgorithmRiskProvider 为占位（调用抛 NotImplementedError），上线真实算法时实现
  - mock 公式刻意不用 label_30/90/180/365 与 actual_pay_duration_days（防数据泄漏），上线真实算法前需做时间切割（沿用 docs/02 记录）
  - risk_configs 表尚无种子数据（tier_mapper 读不到 active 配置时回退默认 70/30），risk-002 做配置 CRUD + 默认种子
- 下一步最佳动作：开始 `risk-002` 风险档配置（阈值+催收时点，版本化），为 task-001 跑批提供配置基础

### Session 006

- 日期：2026-09-09
- 本轮目标：完成 `risk-002` 风险档配置（阈值+催收时点，版本化）
- 已完成：
  - `schemas/config.py`：RiskTierEnum/SceneEnum + ScheduleOut/RiskConfigOut + ScheduleIn/RiskConfigUpdateIn（model_validator 校验 high>medium、day_offset 正整数、枚举）
  - `services/risk_engine/config_service.py`：ConfigSnapshot(frozen) + DEFAULT_SCHEDULES + get_current_config/get_config_history/update_config/rollback_to_version/seed_default_config
  - `api/config.py`：GET /risk/current（登录可见）、PUT /risk（ADMIN）、GET /risk/history（ADMIN）、POST /risk/rollback/{version}（ADMIN）
  - `api/router.py`：挂载 config 路由 /config
  - `services/risk_engine/__init__.py`：导出 config_service 公共函数
  - `seed.py`：加 seed_default_config 幂等种子（v1 70/30 + 5 schedules）
  - 前端 `types/api.ts`：追加 RiskTier/Scene/CollectionSchedule/RiskConfig/RiskConfigUpdate/RecalcRiskSummary
  - 前端 `api/config.ts`：getRiskConfig/updateRiskConfig/getRiskHistory/rollbackRisk
  - 前端 `pages/Config/RiskConfigPanel.tsx`：当前配置展示+编辑表单（阈值+可增删催收时点）+历史回滚
  - 前端 `pages/Config/index.tsx`：引入 RiskConfigPanel
  - 测试 `tests/test_risk_config.py` 17 用例（TC-RISK-03~06 + 权限/校验/回滚边界）
- 运行过的验证：
  - `pytest tests/test_risk_config.py -q` → 17 passed
  - `./init.sh` → 退出码 0：pytest 54 passed + npm run build ✓
  - 端到端真实联调：seed v1(70/30)+5 schedules→上传CSV 20条→recalc HIGH=5/MEDIUM=12/LOW=3→PUT(60/30)→v2→recalc HIGH=8/MEDIUM=9/LOW=3→rollback/1→v3(=70/30)active→history=[v3 active, v2/v1 inactive]
- 已记录证据：见 feature_list.json risk-002.evidence
- 已知风险或未解决问题：
  - 并发同 version 冲突：MVP 单 ADMIN 不处理（生产可加 UniqueConstraint(version)+IntegrityError 重试）
  - is_active 唯一性靠单事务顺序+expire_all，无行锁（SQLite/PG 单线程 MVP 足够）
  - 回滚=方案B（复制为新版本），历史表会增长（符合审计设计）
  - `_deactivate_all` 后必须 `db.expire_all()`，否则 identity map 缓存旧 is_active（坑点，已记录）
  - 前端 chunk 超 500kB 警告（antd 整包），沿用记录，后续按需 code-split
- 下一步最佳动作：开始 `task-001` 催收任务生成（跑批核心逻辑），依赖 risk-002 的催收时点配置

### Session 007（CodeBuddy）

- 日期：2026-09-09
- 本轮目标：完成 `task-001` 催收任务生成（跑批核心逻辑）
- 工具：CodeBuddy（新增 `CODEBUDDY.md` 路由层，与 `CLAUDE.md` 并行；两工具共享同一套 docs/feature_list/claude-progress，不建平行状态文件）
- 已完成：
  - `models/task.py`：加 `uq_tasks_batch_order_day` 复合唯一约束（`__table_args__`）+ alembic 迁移 `c4a2b9d1e0f1`（SQLite batch 重建表，无历史数据安全）
  - `services/task_engine/batch.py`（新）：`BatchResult`(frozen) + `generate_tasks`（扫描未支付(含 pay_status NULL)→命中 win_bid_date+day_offset<=today→幂等生成）+ `run_batch`(recalc_risk 编排) + `BatchNotReadyError`
  - `services/task_engine/__init__.py`：导出稳定入口
  - `scheduler/`（新包）：`jobs.py`（run_daily_batch_job + build_scheduler，cron `0 0 * * *`，coalesce/max_instances=1/misfire_grace_time）；`main.py` 改用 lifespan 启动/关闭调度器（TestClient 非 ctx 不触发）
  - `api/tasks.py`（新）：POST `/api/tasks/batch/run`（ADMIN，`?recalc=true`）+ GET `/api/tasks/batch/status/{batch_id}`（登录）；router 挂载 /tasks
  - `schemas/task.py`（新）：BatchRunOut / BatchStatusOut
  - `core/config.py`：加 `BATCH_RUN_CRON`
  - `requirements.txt`：加 APScheduler==3.10.4（Python 3.13 下 import 验证通过）
  - 测试 `tests/test_task_generation.py` 20 用例
- 运行过的验证：
  - `pytest tests/test_task_generation.py -q` → 20 passed
  - `pytest -q` 全量 → 74 passed（54 旧 + 20 新，无回归）
  - `alembic upgrade head` → 新迁移成功；PRAGMA index_list(tasks) → sqlite_autoindex unique=1 确认约束
  - 端到端真实数据：dev.db 20 条未支付订单模拟每日跑批（run_batch recalc_risk=True）→ 30 任务 PENDING_ASSIGN（HIGH 15/MEDIUM 12/LOW 3）batch=2026-09-09；同日再次跑批 → generated=0 idempotent_skipped=30
  - `npm run build` → ✓（无前端改动，回归确认）
- 已记录证据：见 feature_list.json task-001.evidence
- 提交记录：`feat: task-001 collection task generation (batch run + idempotency + scheduler)`（含新增 CODEBUDDY.md）
- 更新过的文件或工件：CODEBUDDY.md（新）、requirements.txt、models/task.py、alembic/versions/c4a2b9d1e0f1_add_tasks_unique_constraint.py（新）、services/task_engine/*、scheduler/*（新）、api/tasks.py（新）、api/router.py、schemas/task.py（新）、core/config.py、main.py、tests/test_task_generation.py（新）、feature_list.json、claude-progress.md、session-handoff.md
- 已知风险或未解决问题：
  - APScheduler 后台线程经 lifespan 启动；本地已验证手动触发路径，真实 0 点触发行为留待长期运行观察
  - scheduler job 内 logger.exception 后抛出（由 APScheduler 捕获），保证失败可观察
  - run_batch recalc 对无特征订单 mock=50 → MEDIUM（确定性可预期）
  - dev.db 现含 30 条本地演示任务（2026-09-09 batch），属本地数据，不影响仓库
- 下一步最佳动作：开始 `task-002` 任务分配（PENDING_ASSIGN → 规则/轮询分给 3 名催收员），依赖 task-001 已 passing

### Session 008（CodeBuddy）

- 日期：2026-09-09
- 本轮目标：完成 `task-002` 任务分配（高风险优先 + 负载均衡）+ 状态机
- 已完成：
  - `services/task_engine/assignment.py`（新）：`assign_pending_tasks`（风险档排序 HIGH>MEDIUM>LOW + 账龄倒序 + 当前最低负载者轮询，tie 取最小 id）+ `AssignmentResult`
  - `services/task_engine/state.py`（新）：`claim_task`（PENDING→IN_PROGRESS）+ `submit_result`（IN_PROGRESS→DONE 终态 / PROMISE→PENDING 改期）+ 写 `TaskResult` 明细 + 终态保护 + 权限校验（COLLECTOR 仅自己的）
  - `services/task_engine/__init__.py`：导出 assign/claim/submit_result 等
  - `api/tasks.py`：追加 POST `/api/tasks/assign/run`（ADMIN）、POST `/api/tasks/{id}/claim`、POST `/api/tasks/{id}/result`
  - `schemas/task.py`：追加 `AssignmentRunOut`/`TaskOut`/`TaskResultIn`
  - `scheduler/jobs.py`：每日 job 改为 generate + assign 完整跑批（docs §4.2.1 第 2~5 步）
  - 测试 `tests/test_task_assignment.py` 13 用例（覆盖 seed_users 覆盖 fixture 建 3 名催收员）
- 运行过的验证：
  - `pytest tests/test_task_assignment.py -q` → 13 passed
  - `pytest -q` 全量 → 87 passed（74 旧 + 13 新，无回归）
  - 端到端真实数据：dev.db 30 条 PENDING_ASSIGN → 分给 collector1/2/3 各 10 个，负载均衡差=0
  - `npm run build` → ✓
- 已记录证据：见 feature_list.json task-002.evidence
- 提交记录：`feat: task-002 task assignment + state machine (load balance + claim/result)`
- 更新过的文件或工件：services/task_engine/assignment.py（新）、state.py（新）、__init__.py、api/tasks.py、schemas/task.py、scheduler/jobs.py、tests/test_task_assignment.py（新）、feature_list.json、claude-progress.md、session-handoff.md
- 已知风险或未解决问题：
  - 分配负载只统计 PENDING+IN_PROGRESS（不含 PROMISE 改期后回 PENDING 的任务，它们也算待处理——已计入 PENDING，OK）
  - 状态机 result 的 talk_used 仅写入 TaskResult 明细，Task 本身无 talk_used 字段（符合模型）
  - 主管手动改派（F-TASK-04 P1）尚未实现，task-002 只做系统自动分配
  - 前端工作台 UI（wb-001）尚未做，claim/result 当前只能 API 调用
- 下一步最佳动作：开始 `wb-001` 催收工作台（任务列表/详情/领取/回填前端 UI），依赖 task-002 后端已 passing
