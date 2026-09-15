# 会话交接

> 会话间快速交接用。详细进度见 `claude-progress.md`，功能状态见 `feature_list.json`。
> 本仓库由 Claude Code（`CLAUDE.md`）与 CodeBuddy（`CODEBUDDY.md`）共用一套 harness 工件开发。

## 当前已验证

- MVP 12 功能全 passing + supervisor 增强 + 业务流程简化（去领取/导入更新支付状态）已完成
- 这轮实际跑过的验证（Session 015）：
  - 后端 pytest 全量 **182 passed**（无回归；删除 3 个 claim 专属测试）
  - 前端 `npm run build` 通过
  - 真实联调：导入未支付→跑批→分配 IN_PROGRESS→重复导入更新 pay_status=PAID ✓

## 本轮改动（业务流程简化）

后端：
- `services/data_ingestion/parser.py`：重复订单更新支付状态（非跳过）；actual_pay_duration_days 有值→pay_status='PAID'；UploadResult 加 updated
- `services/task_engine/assignment.py`：分配后直接 IN_PROGRESS（去掉 PENDING）
- `services/task_engine/state.py`：PROMISE 改期回 IN_PROGRESS（保留 assignee）
- `services/task_engine/reassign.py`：改派后保持 IN_PROGRESS
- `api/tasks.py`：删 /claim 端点
- `schemas/data.py`：UploadSummary 加 updated

前端：
- `pages/Workbench/index.tsx`：去领取按钮/onClaim，PENDING/IN_PROGRESS 都显示回填
- `api/tasks.ts`：删 claimTask

状态机最终：
```
PENDING_ASSIGN ──分配──▶ IN_PROGRESS ──回填──▶ DONE(终态)
                              │
                              └─ PROMISE → 改期 → IN_PROGRESS(保留 assignee)
```

## 仍损坏或未验证

- 已知缺陷：无
- 未验证路径：无（本轮 4 项全完成并验证）
- 风险：删除用户「不可删自己」会先于「最后 ADMIN」触发；改派 IN_PROGRESS 退回 PENDING；绩效 paid_count 含主管代理回填

## 下一步

- 可继续完善：话术模板管理 UI、真实算法替换（需时间切割）、PG 迁移、非功能测试（性能）
- 或真实业务 CSV 数据灌入验证全流程

## 命令

- 快速启动（不测试）：`./start.sh`
- 标准验证：后端 `cd backend && .venv\Scripts\python.exe -m pytest -q`；前端 `cd frontend && npm run build`
- 种子：`cd backend && python seed.py`
- 启动后端：`uvicorn app.main:app --reload --port 8000`
- 启动前端：`npm run dev`（5173）
- 默认账号：admin/supervisor/collector1-3，密码 admin123
- 新增接口：
  - 用户管理：`GET/POST /api/users`、`PUT/DELETE /api/users/{id}`
  - 绩效：`GET /api/supervisor/staff-performance`（SUPERVISOR/ADMIN）
  - 改派：`POST /api/tasks/{id}/reassign?assignee_id=`（SUPERVISOR/ADMIN）
