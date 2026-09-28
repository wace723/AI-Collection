# 会话交接

> 会话间快速交接用。详细进度见 `claude-progress.md`，功能状态见 `feature_list.json`。
> 本仓库由 Claude Code（`CLAUDE.md`）与 CodeBuddy（`CODEBUDDY.md`）共用一套 harness 工件开发。
> 遵守两套规范：harness-creator（状态追踪/会话连续/验证门槛）+ OpenSpec（变更提案/spec/任务）。

## 当前已验证

- **已规划待实施**：16 功能全 passing + talk-003 管理员话术配置后台（in_progress，OpenSpec change admin-talk-config 已规划 4/4 artifacts，待 /opsx:apply 实施）
- 最近进展（Session 025）：
  - 深度探索「话术配置后台会不会有问题」→ 列 9 项 P0/P1/P2 问题
  - 5 轮 AskUserQuestion 澄清，9 项核心决策全敲定（联动/存储/scene/匹配键/漂移/兜底/数据）
  - OpenSpec change `admin-talk-config` 4/4 artifacts 生成（proposal/design/specs/tasks）
  - feature_list.json 登记 talk-003（priority 17，in_progress，BREAKING）
  - 无代码改动，无验证（纯规划）

## 本轮改动总结（Session 025 talk-003 规划）

- **话术匹配键四维→二维**：[风险档×账龄段×场景×用户特征] → [风险档×轮次]，账龄段/用户特征降为话术变量
- **scene 改 ROUND_N**：固定枚举 FIRST/SECOND/THIRD → ROUND_N（seq 驱动，支持任意轮次）
- **两类模板一张表**：TalkTemplate 加 template_type（FIXED/AI_PROMPT），AI_PROMPT 存 system_prompt+user_prompt
- **占位符统一注册+校验**：纳入标的名称等新字段，保存校验非法占位符，防渲染残留
- **覆盖度矩阵+联动提示**：按 active risk_config 展开 [档×轮] 矩阵，缺口高亮可点击，风险档变更提示复核（不阻断）
- **合规基线不可绕过**：AI system prompt 追加合规基线，is_compliant 永不可关
- BREAKING：丢弃 6 条默认话术清空重配、不保留 ANY 兜底（未配显示空状态）

## 之前几轮（Session 022/023/024，已归档/收尾）

- Session 022：data-004 归档 + AI 话术超时修复（关闭 thinking，39s→2-8s）+ 自动分配按钮 + 启动自动分配 + 大文件导入超时修复
- Session 023：task-003 单活跃任务区间模型（一订单同时一任务，跨区间删旧生新），已归档
- Session 024：ReassignTab 筛选+服务端分页、任务统计改名+处理中卡片（纯前端小改）

## 仍损坏或未验证

- 已知缺陷：无（talk-003 仅规划，未动代码）
- 未验证路径：talk-003 实施后的二维匹配/覆盖度/AI 模板化（待 /opsx:apply 实施后验证）
- 风险/遗留：
  - talk-003 BREAKING：现有 6 条默认话术将清空重配；scene 值需迁移映射 FIRST→ROUND_1 等
  - task-003 BREAKING 已落地：现有 tasks 表需清空重建（dev.db 已清空，生产部署需清空）
  - 前端 axios 默认 10s 超时对耗时操作需逐个设长超时（已修 generateTalk/uploadPendingCsv/uploadPaidCsv）
  - 测试数据/待支付订单.xlsx 和 .csv 误提交进仓库，需确认是否移除

## 下一步可选方向（按价值/紧迫度）

**第一档 · 立即实施 talk-003**
1. `/opsx:apply` 实施 talk-003（按 tasks.md 9 组步骤：模型迁移→scene改造→占位符→匹配器→AI模板→覆盖度→API→前端→测试验证）

**第二档 · 收尾 + 让系统真正用起来**
2. 真实联调深化：待支付+已支付 CSV 订单号对齐，验证已支付回写终态停催全流程
3. 真实 LLM 调通体验优化（glm 响应 40s，可加流式 SSE）

**第三档 · 上生产前硬骨头**
4. 真实风险算法替换（需时间切割防数据泄漏）——当前风险概率从 CSV 来，算法由线下做
5. PostgreSQL 迁移 + 时区统一

**第四档 · 体验/功能补全**
6. 非功能测试（TC-NF-01/02 跑批性能 10000 笔≤5min、工作台列表≤2s）

## 本轮改动总结（data-002，已归档）

- 移除系统风险预测，风险概率从待支付 CSV「风险概率」列导入经阈值映射档位
- 拆分待支付/已支付两个导入入口（`/upload-pending` + `/upload-paid`）
- CSV 列映射重构（新表头：标的名称/概算金额/订单生成日期/中标品类/合同类型/注册省份）
- Order 新增字段、OrderFeature 移除标签列、actual_pay_duration_days 移到 Order
- 跑批默认 `recalc_risk=False`，风险由导入写入
- 工作台列表展示标的信息，详情改屏幕中间 Modal 左右两栏（左=特征分类，右=模板+AI话术）
- 归档：`openspec/changes/archive/2026-09-17-import-driven-risk-and-payment-sync/`
- 主 specs：`openspec/specs/`（import-payment-sync / data-ingestion / risk-engine）

## 仍损坏或未验证

- 已知缺陷：无
- 未验证路径：无（data-002 已完整收尾归档）
- 风险/遗留：
  - 真实 CSV 样本缺「风险概率」列，真实使用需线下算法跑好追加该列后再导入
  - calculator.recalculate_risks 保留函数但跑批不再调用（recalc_risk=False 默认）
  - TaskDetailModal 宽 1100px 在小屏可能偏挤（可后续响应式优化）

## 下一步可选方向（按价值/紧迫度）

**第一档 · 让系统真正用起来**
1. 真实 CSV（含风险概率列）灌入验证全流程：上传待支付→跑批→分配→催收→回填→已支付导入回写→大盘
2. 真实 LLM 调通体验优化（glm 响应 40s，可加流式 SSE）

**第二档 · 上生产前硬骨头**
3. 真实风险算法替换（需时间切割防数据泄漏）——当前风险概率从 CSV 来，算法由线下做
4. PostgreSQL 迁移 + 时区统一（dash-001 review 记录的 H-2）

**第三档 · 体验/功能补全**
5. 话术模板管理 UI（当前只有 seed 默认模板，后台不能增删改）
6. 主管手动改派已有（F-TASK-04），可补任务转派历史/审计
7. 非功能测试（TC-NF-01/02 跑批性能 10000 笔≤5min、工作台列表≤2s）

## 命令

- 快速启动（不测试）：`./start.sh`
- 标准验证：后端 `cd backend && .venv\Scripts\python.exe -m pytest -q`；前端 `cd frontend && npm run build`
- 种子：`cd backend && python seed.py`（用户 + 风险档配置 + 6 话术模板 + AI 配置）
- 启动后端：`uvicorn app.main:app --reload --port 8000`
- 启动前端：`npm run dev`（5173）
- 默认账号：admin/supervisor/collector1-3，密码 admin123
- 新增接口（data-002）：
  - 待支付导入：`POST /api/data/upload-pending`（ADMIN，含风险概率列）
  - 已支付导入：`POST /api/data/upload-paid`（ADMIN，回写支付状态）
  - 用户管理：`GET/POST /api/users`、`PUT/DELETE /api/users/{id}`
  - 绩效：`GET /api/supervisor/staff-performance`（SUPERVISOR/ADMIN）
  - 改派：`POST /api/tasks/{id}/reassign?assignee_id=`（SUPERVISOR/ADMIN）

## 状态文件位置

- `feature_list.json` — 16 功能 passing + talk-003 in_progress（priority 17）
- `claude-progress.md` — Session 025 记录
- `openspec/specs/` — 4 个 capability 主 specs（固化）
- `openspec/changes/admin-talk-config/` — 活动 change（4/4 artifacts，待 /opsx:apply）
- `openspec/changes/archive/` — data-002/003/004 + task-003 共 4 个已归档

## 给下一轮会话的重启路径

1. `pwd` 确认仓库根
2. 读 `claude-progress.md` 找 Session 025
3. 读 `feature_list.json` 确认 talk-003 in_progress
4. 检查 `openspec/changes/admin-talk-config/`（活动 change，4/4 artifacts ready）
5. `./start.sh` 启动验证基线
6. 运行 `/opsx:apply` 实施 talk-003（按 tasks.md 9 组步骤）
