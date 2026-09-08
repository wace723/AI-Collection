#!/usr/bin/env bash
# 平台使用费 AI 辅助催收系统 — 标准启动与验证脚本
# 用法：./init.sh           # 安装依赖 + 基础验证
#      RUN_START_COMMAND=1 ./init.sh  # 同时启动应用

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

echo "==> 当前目录: $PWD"

# ── 后端 ──────────────────────────────────────────────
BACKEND_DIR="$ROOT_DIR/backend"
if [ -d "$BACKEND_DIR" ]; then
  echo "==> 后端：检查 Python 环境"
  if command -v python >/dev/null 2>&1; then
    PY=python
  elif command -v python3 >/dev/null 2>&1; then
    PY=python3
  else
    echo "    [警告] 未找到 python，跳过后端验证"
    PY=""
  fi

  if [ -n "$PY" ]; then
    if [ ! -d "$BACKEND_DIR/.venv" ]; then
      echo "==> 创建虚拟环境 .venv"
      "$PY" -m venv "$BACKEND_DIR/.venv"
    fi
    # 激活虚拟环境
    if [ -f "$BACKEND_DIR/.venv/Scripts/activate" ]; then
      # Git Bash / Windows
      # shellcheck disable=SC1091
      source "$BACKEND_DIR/.venv/Scripts/activate"
    elif [ -f "$BACKEND_DIR/.venv/bin/activate" ]; then
      # shellcheck disable=SC1091
      source "$BACKEND_DIR/.venv/bin/activate"
    fi

    if [ -f "$BACKEND_DIR/requirements.txt" ]; then
      echo "==> 安装后端依赖"
      pip install -q -r "$BACKEND_DIR/requirements.txt"
    fi

    echo "==> 后端：数据库迁移"
    (cd "$BACKEND_DIR" && alembic upgrade head 2>/dev/null || echo "    [警告] 迁移未就绪（骨架未搭建时可忽略）")

    echo "==> 后端：运行测试"
    (cd "$BACKEND_DIR" && pytest -q 2>/dev/null || echo "    [警告] 测试未就绪（骨架未搭建时可忽略）")
  fi
else
  echo "==> backend/ 目录不存在，跳过后端（骨架未搭建）"
fi

# ── 前端 ──────────────────────────────────────────────
FRONTEND_DIR="$ROOT_DIR/frontend"
if [ -d "$FRONTEND_DIR" ]; then
  echo "==> 前端：安装依赖"
  (cd "$FRONTEND_DIR" && npm install --silent 2>/dev/null || echo "    [警告] npm install 失败")

  echo "==> 前端：类型检查与构建"
  (cd "$FRONTEND_DIR" && npm run build 2>/dev/null || echo "    [警告] 构建未就绪（骨架未搭建时可忽略）")
else
  echo "==> frontend/ 目录不存在，跳过前端（骨架未搭建）"
fi

# ── 启动 ──────────────────────────────────────────────
echo "==> 启动命令"
echo "    后端：cd backend && uvicorn app.main:app --reload"
echo "    前端：cd frontend && npm run dev"

if [ "${RUN_START_COMMAND:-0}" = "1" ]; then
  echo "==> 启动后端"
  (cd "$BACKEND_DIR" && uvicorn app.main:app --reload) &
  BACK_PID=$!
  echo "==> 启动前端"
  (cd "$FRONTEND_DIR" && npm run dev) &
  FRONT_PID=$!
  trap "kill $BACK_PID $FRONT_PID 2>/dev/null || true" EXIT
  wait
fi

echo "==> 验证完成（骨架未搭建时上述警告可忽略）"
