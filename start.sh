#!/usr/bin/env bash
# 快速启动脚本 — 只启动前后端，不跑测试。
# 用法：./start.sh
# 停止：Ctrl+C（会同时停掉前后端）

set -euo pipefail

# 中文路径 + GBK 终端防 UnicodeEncodeError
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8
# 关闭 SQL echo，启动日志干净（DEBUG=true 时 alembic/seed 会刷大量 SQL）
export DEBUG=false

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"

echo "==> 快速启动（不跑测试）"
echo "    仓库：$ROOT_DIR"

# ── 后端 ──────────────────────────────────────────────
if [ ! -d "$BACKEND_DIR" ]; then
  echo "[错误] backend/ 目录不存在" >&2
  exit 1
fi

echo "==> 后端：激活 venv 并迁移数据库"
if [ ! -d "$BACKEND_DIR/.venv" ]; then
  echo "    创建虚拟环境 .venv"
  if command -v python >/dev/null 2>&1; then PY=python
  elif command -v python3 >/dev/null 2>&1; then PY=python3
  else echo "[错误] 未找到 python" >&2; exit 1; fi
  "$PY" -m venv "$BACKEND_DIR/.venv"
fi

if [ -f "$BACKEND_DIR/.venv/Scripts/activate" ]; then
  # shellcheck disable=SC1091
  source "$BACKEND_DIR/.venv/Scripts/activate"
elif [ -f "$BACKEND_DIR/.venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  source "$BACKEND_DIR/.venv/bin/activate"
else
  echo "[错误] venv 激活脚本未找到" >&2; exit 1
fi

# 依赖缺失则安装（首次或换机器）
if ! python -c "import fastapi, sqlalchemy, uvicorn" 2>/dev/null; then
  echo "==> 后端：安装依赖"
  pip install -q -r "$BACKEND_DIR/requirements.txt"
fi

echo "==> 后端：数据库迁移 (alembic upgrade head)"
(cd "$BACKEND_DIR" && alembic upgrade head)

# 首次无用户则种子（用户 + 风险档配置 + 话术模板 + AI 配置）
echo "==> 后端：种子数据（如缺失）"
(cd "$BACKEND_DIR" && python seed.py) || echo "    [警告] seed.py 执行失败（可能已种子过，可忽略）"

# ── 前端 ──────────────────────────────────────────────
if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
  echo "==> 前端：安装依赖 (npm install)"
  (cd "$FRONTEND_DIR" && npm install --silent)
fi

# ── 启动 ──────────────────────────────────────────────
BACK_PID=""
FRONT_PID=""
cleanup() {
  echo ""
  echo "==> 停止前后端进程"
  [ -n "$BACK_PID" ]  && kill "$BACK_PID"  2>/dev/null || true
  [ -n "$FRONT_PID" ] && kill "$FRONT_PID" 2>/dev/null || true
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo ""
echo "==> 启动后端 (8000)..."
(cd "$BACKEND_DIR" && uvicorn app.main:app --reload --host 127.0.0.1 --port 8000) &
BACK_PID=$!

echo "==> 启动前端 (5173)..."
(cd "$FRONTEND_DIR" && npm run dev) &
FRONT_PID=$!

echo ""
echo "============================================================"
echo "  前端页面： http://localhost:5173"
echo "  后端 API： http://127.0.0.1:8000   (文档 /docs)"
echo "  默认账号： admin / supervisor / collector1-3  密码 admin123"
echo "  停止：Ctrl+C"
echo "============================================================"
echo ""
echo "    （日志在下方实时输出，后端 --reload 改代码自动重载）"

wait
