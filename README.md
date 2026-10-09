# 平台使用费 AI 辅助催收系统

从真实业务平台获取中标订单及特征 → 线下算法跑好风险概率随 CSV 导入 → 经阈值映射风险档 → 按催收时点生成任务并分配给催收员 → 催收员工作台直接处理回填（无需领取）→ 话术辅助（模板+AI）→ 数据大盘。

MVP 已完成（17 个功能全 passing，222 个测试通过）。详细设计文档见 [docs/](./docs/)。

## 技术栈

- 后端：Python 3.13 / FastAPI / SQLAlchemy 2.0 / Alembic / APScheduler
- 前端：React 19 / TypeScript / Vite 8 / Ant Design 5 / @ant-design/charts
- 数据库：PostgreSQL 15（开发期 SQLite）
- LLM：OpenAI 兼容 SDK（glm-5.2 / DeepSeek / 通义等，可开关 + 降级模板）
- 变更管理：OpenSpec（proposal/design/specs/tasks）

## 功能模块

| 模块 | 说明 |
|---|---|
| 数据接入 | 待支付/已支付 CSV 双入口导入；GBK/UTF-8 自动识别；40 列特征入库 |
| 风险引擎 | 风险概率从 CSV「风险概率」列导入经阈值映射 HIGH/MEDIUM/LOW；阈值+催收时点可配置，版本化回滚 |
| 任务引擎 | 单活跃任务区间模型跑批；按风险档+账龄生成催收任务；高风险优先+负载均衡分配给 3 名催收员 |
| 催收工作台 | 待办列表（风险/账龄排序）、任务详情、用户特征画像、处理结果回填（已接通/未接通两分类）|
| 话术引擎 | 二维匹配（风险档×轮次）；固定模板 + AI 提示词模板；44 个占位符变量；覆盖度矩阵；AI 生成失败降级模板 |
| 数据大盘 | 日/周/月核心指标；风险档/账龄分布；催收员绩效排名；趋势图 |
| 监督员视图 | 催收员管理、任务改派、团队处理中任务统计、当天完成进度 |

## 快速开始（本地开发）

### 一、后端

```bash
cd backend
python -m venv .venv
source .venv/Scripts/activate    # Git Bash / Windows
# source .venv/bin/activate      # Unix
pip install -r requirements.txt

# 数据库迁移（开发期 SQLite，dev.db 落在 backend/ 下）
alembic upgrade head

# 种子数据（5 个用户 + 默认风险档配置 + 话术模板 + AI 配置）
python seed.py

# 启动
uvicorn app.main:app --reload
# 健康检查：curl http://localhost:8000/health
# API 文档：http://localhost:8000/docs
```

启动时系统自动跑批（推进催收状态机 + 生成任务）+ 分配任务给催收员。

### 二、前端

```bash
cd frontend
npm install
npm run dev
# 浏览器打开 http://localhost:5173
```

### 三、一键脚本

```bash
./init.sh                           # 装依赖 + 迁移 + pytest + npm build
RUN_START_COMMAND=1 ./init.sh        # 同上并启动前后端
./start.sh                          # 快速启动（不跑测试）
```

## 默认账号

种子数据 `python seed.py` 创建，密码统一为 `admin123`：

| 角色 | 账号 | 权限 |
|---|---|---|
| 管理员 | admin | 全部权限（数据导入、配置、跑批）|
| 催收主管 | supervisor | 大盘、监督员视图、改派 |
| 催收员1 | collector1 | 工作台（仅看自己任务）|
| 催收员2 | collector2 | 同上 |
| 催收员3 | collector3 | 同上 |

## 演示数据一键生成

```bash
cd backend
python demo_setup.py
```

脚本功能：
1. 清库（删业务数据，保留用户/配置/话术）
2. 生成 3 个演示 CSV 到 `演示数据/`：
   - `01_待支付_T时_300条.csv` — T 时存量待支付（HIGH:MEDIUM:LOW = 1:3:6）
   - `02_待支付_T+1新增_30条.csv` — T+1 新增订单（全部未到首轮）
   - `03_已支付_T+1_30条.csv` — T+1 已支付回写
3. 预置 14 天历史数据（30 条已支付订单 + 30 个已完成任务，驱动大盘趋势）
4. 生成 `演示数据/演示操作手册.md`（11 步分阶段操作文档）

详细演示流程见 [演示数据/演示操作手册.md](./演示数据/演示操作手册.md)。

## 环境变量

复制 `backend/.env.example` 为 `backend/.env` 后按需修改：

| 变量 | 默认 | 说明 |
|------|------|------|
| DATABASE_URL | sqlite:///./dev.db | 开发期 SQLite，生产用 postgresql+psycopg:// |
| JWT_SECRET | change-me-in-prod | JWT 签名密钥 |
| JWT_EXPIRE_MINUTES | 1440 | token 有效期（分钟）|
| LLM_PROVIDER | mock | mock / openai_compatible |
| LLM_API_KEY | （空） | LLM API Key，留空用 mock |
| LLM_BASE_URL | （空） | OpenAI 兼容接口地址 |
| LLM_MODEL | （空） | 模型名（如 glm-5.2）|
| LLM_TIMEOUT | 30.0 | LLM 调用超时（秒）|
| AI_TALK_ENABLED | false | AI 话术总开关（有 key 首次启动自动开启）|
| RISK_PROVIDER | mock | 风险计算 Provider（data-002 后已废弃，正常流程不触发）|
| BATCH_RUN_CRON | 0 0 * * * | 每日跑批 cron（默认凌晨 0 点）|
| CORS_ORIGINS | ["http://localhost:5173"] | 允许的前端来源 |

LLM 配置：.env 值仅作首次启动兜底，主管可在前端「配置后台」运行时修改，存 DB（DB 优先）。

## Docker（可选生产自检）

本地未安装 Docker 时可跳过，开发用 SQLite + uvicorn 即可。

```bash
docker compose --profile pg up --build   # 启动 postgres + backend + frontend
```

## 数据库表（10 张业务表）

| 表 | 说明 |
|---|---|
| orders | 订单（标识+状态+风险+支付+催收状态机）|
| order_features | 订单特征（1:1 关联 orders，37 列特征字段）|
| risk_configs | 风险档配置（版本化，阈值+催收时点）|
| collection_schedules | 催收时点（HIGH 7/15/30 天，MEDIUM 30 天，LOW 90 天）|
| tasks | 催收任务（单活跃任务区间模型，batch_id+order_id+day_offset 唯一）|
| task_results | 回填结果明细（已接通/未接通两分类）|
| users | 用户（COLLECTOR/SUPERVISOR/ADMIN）|
| talk_templates | 话术模板（固定模板+AI 提示词模板，二维匹配）|
| ai_config | AI 话术配置（单行表，DB 优先）|
| ai_conversations | AI 话术审计记录 |

## 项目结构

```
docs/                  需求/架构/测试文档（事实来源）
openspec/              OpenSpec 变更管理（变更方案事实来源）
backend/               FastAPI 后端
  app/
    core/              config, security, database
    models/            ORM 模型（10 张表）
    schemas/          Pydantic 模型
    api/              路由（auth/data/tasks/talk/config/dashboard/supervisor）
    services/         业务逻辑（按模块组织）
      data_ingestion/  CSV 解析导入
      risk_engine/      风险概率映射 + 配置版本化
      task_engine/      跑批 + 分配 + 状态机
      talk_engine/      话术匹配 + 渲染 + AI 生成
      dashboard/      大盘指标聚合
    scheduler/          APScheduler 每日跑批
    alembic/            迁移
    tests/             pytest（222 passed）
frontend/              React 前端
  src/
    pages/            Workbench/Supervisor/Config/Dashboard
    components/       Charts/Layout
    api/               axios 客户端
feature_list.json       功能状态追踪（harness）
claude-progress.md      会话进度日志（harness）
init.sh / start.sh      标准启动与验证脚本
demo_setup.py          演示数据一键生成脚本
演示数据/             演示 CSV + 操作手册
```

## 关键设计约束

1. **风险概率来源**：从待支付 CSV「风险概率」列导入（线下算法跑好），系统不再预测；经阈值映射 HIGH/MEDIUM/LOW
2. **LLM 可降级**：AI 话术失败必须回退模板话术，不阻断催收
3. **单活跃任务**：一个订单同一时间只有一个活跃任务（当前催收区间的），跨区间删旧生新
4. **催收触发**：到达催收时点且届时仍未支付才生成任务
5. **状态机简化**：分配后直接 IN_PROGRESS（无领取步骤）；已接通推进该轮已催收
6. **风险预测已废弃**：`recalculate_risks` + `MockRiskProvider` 是 data-002 前旧路径，正常流程不触发

## 验证

- [x] `./init.sh` 全流程退出码 0（pytest 222 passed + npm build）
- [x] `curl http://localhost:8000/health` → 200
- [x] `cd frontend && npm run dev` → Vite 启动
- [x] `alembic upgrade head` → 10 张业务表建表成功
- [x] 演示数据脚本端到端验证通过（T 时导入 300 条 → 159 任务 → 分配各 53 → T+1 演进 45 新任务）
