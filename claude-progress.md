# 进度日志

## 当前已验证状态

- 仓库根目录：`e:/my-projects/平台使用费ai辅助催收系统`
- 标准启动路径：`./init.sh`
- 标准验证路径：后端 `pytest` + 前端 `npm run build`（骨架就绪后）
- 当前最高优先级未完成功能：`risk-001` Mock 风险概率计算 + RiskProvider 抽象（data-001 已 passing）
- 当前 blocker：无（data-001 已 passing，CSV 上传解析可用）

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
