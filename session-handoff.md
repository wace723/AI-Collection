# 会话交接

> 会话间快速交接用。详细进度见 `claude-progress.md`，功能状态见 `feature_list.json`。

## 当前已验证

- 现在明确可用的部分：infra-001 骨架可运行、infra-002 鉴权可用（JWT 登录+角色权限+种子数据）
- 这轮实际跑过的验证：
  - 后端 pytest 12 passed（3 health + 9 auth）
  - curl 完整鉴权链路（登录 200+token、/me 200、无 token 401、admin-only admin 200/collector 403）
  - 前后端联调：vite proxy 登录成功、错误密码 401
  - 前端 npm run build 通过

## 本轮改动（infra-002）

- 新增了哪些代码或行为：
  - 后端 auth：security.py（bcrypt+jose）、deps.py（get_current_user/require_role）、schemas/auth.py、api/auth.py（login/me/admin-only/supervisor-or-admin）、seed.py 种子脚本
  - 测试：test_auth.py 9 用例 + conftest 加 seed_users fixture + StaticPool
  - 前端：auth.ts、RequireAuth 守卫、Login 接入、App.tsx、client 401 跳转
- 基础设施或 harness 发生了哪些变化：无（沿用 infra-001 的骨架）

## 仍损坏或未验证

- 已知缺陷：无
- 未验证路径：data-001 及之后功能均 not_started
- 下一轮会话需要注意的风险：
  - passlib 1.7.4 + bcrypt 5.0 不兼容已规避（改用 bcrypt 原生 API），新会话勿重新引入 passlib
  - 测试内存 SQLite 必须用 StaticPool，否则 TestClient 跨连接查不到表
  - alembic.ini 不能含中文（GBK 解码失败），已全英文
  - 用户管理 CRUD 尚未做（seed.py 够用），主管视图阶段再补

## 下一步最佳动作

- 最高优先级未完成功能：`data-001` CSV 上传与解析（37 列特征入库）
- 为什么它是下一步：催收任务的数据来源；data-001 → risk-001 → task-001 是主线核心链路
- 什么结果才算 passing：
  - CSV 上传（GBK/UTF-8 自动识别）解析入库到 orders + order_features
  - 上传需 ADMIN 权限（Depends(require_role("ADMIN"))）
  - 列校验、重复 service_fee_order_no 去重、空值存 NULL
  - 对应测试用例 TC-DATA-01~07 全过
- 这一步中哪些东西不要动：
  - docs/ 下需求架构（已是基线）
  - Order/OrderFeature 模型字段（已按 docs/02 落地，CSV 入库直接用）
  - CLAUDE.md 的设计约束

## data-001 实现要点（给新会话的提示）

- 复用：`Order`/`OrderFeature` 模型（backend/app/models/order.py，中文列名+英文属性）、`APIResponse[T]`、`require_role("ADMIN")`、`get_db`
- 新建：`app/api/data.py`（上传端点 POST /api/data/upload）、`app/services/data_ingestion/` 解析逻辑、`app/schemas/data.py`
- 编码识别：CSV 可能是 GBK（示例文件原编码）或 UTF-8，需自动探测（chardet 或试解码）
- 测试数据：仓库根 `平台使用费特征查询_2026_09_08.csv`（20 条，含 1 条欠费样本）
- 特征入库：orders 存标识+状态，order_features 存 37 列非标识字段（见模型）
- 参考 docs/02-技术架构设计.md §5.2 数据接入 API、docs/03-测试用例.md TC-DATA-01~07

## 命令

- 启动命令：`./init.sh`（骨架就绪后 `RUN_START_COMMAND=1 ./init.sh`）
- 验证命令：后端 `cd backend && pytest -q`；前端 `cd frontend && npm run build`
- 种子数据：`cd backend && source .venv/Scripts/activate && python seed.py`
- 启动后端：`cd backend && uvicorn app.main:app --reload`（注意用 localhost 访问，vite 监听 IPv6）
- 默认账号：admin/supervisor/collector1-3，密码 admin123
