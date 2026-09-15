# 会话交接

> 会话间快速交接用。详细进度见 `claude-progress.md`，功能状态见 `feature_list.json`。
> 本仓库由 Claude Code（`CLAUDE.md`）与 CodeBuddy（`CODEBUDDY.md`）共用一套 harness 工件开发。

## 当前已验证

- MVP 12 功能全 passing + supervisor 增强 4 项已完成
- 这轮实际跑过的验证（Session 014）：
  - 后端 pytest 全量 **185 passed**（152 旧 + 33 新：17 users + 11 reassign + 5 supervisor）
  - 前端 `npm run build` 通过（主 chunk 降到 619KB，Supervisor 三 Tab lazy 独立 chunk）
  - 真实联调：用户 CRUD / 改派 / 绩效 / 工作台 supplier_name 全通

## 本轮改动（supervisor 增强 4 项）

后端新建：
- `app/api/users.py`（GET/POST/PUT/DELETE 用户管理，SUPERVISOR 查/ADMIN 改）
- `app/api/supervisor.py`（GET /staff-performance 绩效）
- `app/schemas/user.py`、`app/schemas/supervisor.py`
- `app/services/supervisor_service.py`（get_staff_performance 聚合）
- `app/services/task_engine/reassign.py`（reassign_task，终态不可改派）
- `tests/test_users.py`、`tests/test_reassign.py`、`tests/test_supervisor.py`

后端修改：
- `app/api/tasks.py`（加 POST /{id}/reassign + 列表 join supplier_name）
- `app/api/router.py`（挂载 users/supervisor）
- `app/schemas/task.py`（TaskOut 加 supplier_name）
- `app/services/task_engine/__init__.py`（导出 reassign_task）
- `tests/test_workbench.py`（加 supplier_name 断言）

前端新建：
- `src/api/users.ts`、`src/api/supervisor.ts`
- `src/pages/Supervisor/UsersTab.tsx`、`StaffTab.tsx`、`ReassignTab.tsx`

前端修改：
- `src/components/Layout/index.tsx`（Header 用户名+登出 Dropdown）
- `src/pages/Supervisor/index.tsx`（重写为三 Tab，lazy 加载）
- `src/pages/Workbench/index.tsx`（加供应商名称列）
- `src/types/api.ts`（Task 加 supplier_name + UserCreate/UserUpdate/StaffPerformance）
- `src/api/tasks.ts`（加 reassignTask）

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
