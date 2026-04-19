#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "========================================="
echo " weibo CLI 一键安装"
echo "========================================="
echo ""

# --- 1. 检查 Python ---
PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        ver=$("$cmd" --version 2>&1 | grep -oE '[0-9]+\.[0-9]+')
        major=$(echo "$ver" | cut -d. -f1)
        minor=$(echo "$ver" | cut -d. -f2)
        if [ "$major" -ge 3 ] && [ "$minor" -ge 10 ]; then
            PYTHON="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo "❌ 需要 Python >= 3.10，请先安装。"
    exit 1
fi
echo "✅ Python: $($PYTHON --version)"

# --- 2. 检查 FFmpeg ---
if command -v ffmpeg &>/dev/null && command -v ffprobe &>/dev/null; then
    echo "✅ FFmpeg: $(ffmpeg -version 2>&1 | head -1)"
else
    echo "❌ 需要 FFmpeg（ffmpeg + ffprobe），请先安装。"
    echo "   macOS: brew install ffmpeg"
    echo "   Ubuntu: sudo apt install ffmpeg"
    exit 1
fi

# --- 3. 安装 weibo CLI ---
echo ""
echo "📦 正在安装 weibo CLI..."
cd "$PROJECT_DIR"

if [ -d ".venv" ]; then
    echo "   使用已有 .venv"
else
    "$PYTHON" -m venv .venv
    echo "   已创建 .venv"
fi

source .venv/bin/activate
pip install -e "./weibo" --quiet

if command -v weibo &>/dev/null; then
    echo "✅ weibo CLI 安装成功: $(which weibo)"
else
    echo "⚠️ weibo 未出现在 PATH 中，请运行: source .venv/bin/activate"
fi

# --- 4. 安装 skills ---
SKILLS_DIR="${HOME}/.agents/skills"
SKILL_NAMES=("h2v-skill" "style-transfer-skill" "character-swap-skill" "viral-replica-skill")
if [ -d "$PROJECT_DIR/skills" ]; then
    mkdir -p "$SKILLS_DIR"
    for SKILL_NAME in "${SKILL_NAMES[@]}"; do
        if [ -d "$PROJECT_DIR/skills/$SKILL_NAME" ]; then
            cp -r "$PROJECT_DIR/skills/$SKILL_NAME" "$SKILLS_DIR/$SKILL_NAME"
            echo "✅ Skill 已安装: $SKILL_NAME"
        fi
    done
fi

# --- 5. 检查配置 ---
echo ""
echo "========================================="
echo " 安装完成！"
echo "========================================="
echo ""

if [ -z "${WEIBO_ARK_API_KEY:-${CHANGDU_ARK_API_KEY:-${ARK_API_KEY:-}}}" ]; then
    echo "⚠️ 未检测到 API Key，请设置环境变量："
    echo ""
    echo '  export WEIBO_ARK_API_KEY="你的火山方舟API Key"'
    echo ""
else
    echo "✅ API Key 已配置"
fi

echo ""
echo "快速体验："
echo '  source .venv/bin/activate'
echo '  weibo run ./input.mp4 -o ./job --preset h2v --prompt "竖屏构图"'
echo ""
echo "可用预设: h2v / style_transfer / character_swap / viral_replica"
echo ""
