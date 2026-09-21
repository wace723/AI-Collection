## Why

当前系统导入 CSV 后不会立即产生任务——任务只靠每日凌晨定时跑批或手动 POST /batch/run 触发，业务方每次导入后必须等到第二天或手动调用 API 才看到任务，体验割裂。同时真实业务 CSV 新增「工程局单位」「下属单位」两列特征字段（待支付/已支付 CSV 均从 38/39 列变为 40 列），现有列映射不支持，导入会因表头不符失败。前端导入后只有 message.success 简单提示，看不到 inserted/updated/skipped/errors 明细，也无法判断是否产生了任务。

## What Changes

- **Order 新增「工程局单位」「下属单位」两字段**：`engineering_bureau`、`subsidiary`（String，订单级标识字段），Alembic 迁移加列；columns.py 两套 CSV 表头加这两列（待支付 40 列 / 已支付 40 列），ORDER_FIELD_MAP 加映射 **BREAKING**（旧 38/39 列 CSV 不兼容）
- **待支付导入后自动跑批**：`POST /api/data/upload-pending` 导入成功后自动触发跑批（推进状态机 + 生成任务），导入响应扩展返回跑批结果（generated/finalized/by_tier）
- **系统启动时自动跑批**：`main.py` lifespan 启动调度器后跑一次跑批，确保启动即同步任务状态
- **已支付导入后不自动跑批**（已支付导入只回写支付状态+终态停催，不生成新任务）
- **前端导入结果展示 Modal**：Config 页导入后弹 Modal 展示 inserted/updated/skipped/errors 明细 + 跑批结果，用户点「关闭」完成
- **前端 Config 页**：待支付/已支付 Dragger 上传后展示结果 Modal，含错误明细列表与跑批统计

## Capabilities

### New Capabilities
（无新 capability，全部基于现有 capability 改）

### Modified Capabilities
- `data-ingestion`: 待支付/已支付 CSV 列映射加「工程局单位」「下属单位」两列（40 列）；待支付导入后自动触发跑批并返回跑批结果
- `task-engine`: 系统启动时自动跑批（lifespan 触发）；跑批入口复用现有 generate_tasks
- `import-payment-sync`: 已支付 CSV 列映射加两列（40 列，含支付日期+实际支付时长，与待支付共享新列）

## Impact

- **后端模型**：Order 新增 engineering_bureau/subsidiary 字段 + Alembic 迁移
- **后端服务**：columns.py 两套表头加两列 + ORDER_FIELD_MAP；api/data.py upload-pending 端点导入后自动跑批 + 响应扩展；main.py lifespan 加启动跑批
- **后端 schema**：UploadSummary/OrderOut 加跑批结果与新字段
- **前端**：Config 页导入结果 Modal（展示明细 + 跑批统计）；types/api.ts Order/UploadSummary 加新字段与跑批结果类型
- **测试**：test_data_upload 适配 40 列 CSV + 自动跑批；新增启动跑批测试
- **BREAKING**：旧 38/39 列 CSV 不兼容（表头缺「工程局单位」「下属单位」会 400）
