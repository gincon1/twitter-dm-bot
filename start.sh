#!/bin/bash
set -e

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"

cleanup() {
  if [[ -n "$BACKEND_PID" ]]; then
    kill "$BACKEND_PID" 2>/dev/null || true
  fi
  if [[ -n "$FRONTEND_PID" ]]; then
    kill "$FRONTEND_PID" 2>/dev/null || true
  fi
  echo "系统已停止"
}

trap cleanup EXIT

echo "🚀 Twitter DM System 启动中..."

if ! command -v python3 >/dev/null 2>&1; then
  echo "❌ 未检测到 python3"
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "❌ 未检测到 npm"
  exit 1
fi

cd "$ROOT_DIR"
if [[ ! -d ".venv" ]]; then
  echo "📦 创建 Python 虚拟环境..."
  python3 -m venv .venv
fi

source .venv/bin/activate
pip install -q -r requirements.txt
playwright install chromium >/dev/null 2>&1 || true

echo "🔧 启动后端服务..."
cd "$BACKEND_DIR"
python3 main.py &
BACKEND_PID=$!

cd "$FRONTEND_DIR"
if [[ ! -d "node_modules" ]]; then
  echo "📦 安装前端依赖..."
  npm install >/dev/null
fi

echo "🔨 构建前端..."
npm run build >/dev/null

echo "🌐 启动前端预览..."
npm run preview -- --host 0.0.0.0 --port 3000 >/dev/null &
FRONTEND_PID=$!

sleep 2

echo "✅ 系统已启动"
echo "   控制台: http://localhost:3000"
echo "   API:    http://localhost:8000"
echo "按 Ctrl+C 停止"

wait
