#!/usr/bin/env bash
# Colab Roots — Restore script
# Use this to check status and restore state when reconnecting.
# Non-interactive: safe for notebook cells.

set -euo pipefail

ROOTS_HOME="${ROOTS_HOME:-$HOME/.colab-roots}"
ROOTS_STATE="$ROOTS_HOME/state"
ROOTS_LOGS="$ROOTS_HOME/logs"

echo "═══════════════════════════════════════════"
echo "  🌱 Colab Roots — Restore"
echo "═══════════════════════════════════════════"
echo ""

# ─── Check installation ─────────────────────────────────────────
if [ ! -f "$ROOTS_STATE/version" ]; then
    echo "❌ No Colab Roots installation found"
    echo "   Run the Bootstrap cell first."
    exit 1
fi

VERSION=$(cat "$ROOTS_STATE/version")
echo "✅ Colab Roots v${VERSION} detected"
echo ""

# ─── Check services ─────────────────────────────────────────────
echo "📊 Service Status:"
echo ""

# tmux
if command -v tmux &>/dev/null && tmux has-session -t roots 2>/dev/null; then
    echo "  ✅ tmux session 'roots': ACTIVE"
else
    echo "  ❌ tmux session 'roots': NOT FOUND"
fi

# code-server
if pgrep -x code-server >/dev/null 2>&1; then
    echo "  ✅ code-server: RUNNING (http://127.0.0.1:8080)"
else
    echo "  ❌ code-server: NOT RUNNING"
fi

# ttyd
if pgrep -x ttyd >/dev/null 2>&1; then
    echo "  ✅ ttyd: RUNNING (http://127.0.0.1:7681)"
else
    echo "  ❌ ttyd: NOT RUNNING"
fi

# cloudflared (if exposed)
if pgrep -x cloudflared >/dev/null 2>&1; then
    echo "  ✅ cloudflared: RUNNING"
else
    echo "  ⏭️  cloudflared: not running (normal if not exposed)"
fi

echo ""

# ─── Credentials ────────────────────────────────────────────────
if [ -f "$ROOTS_STATE/password" ]; then
    PASSWORD=$(cat "$ROOTS_STATE/password")
    echo "🔑 Password: ${PASSWORD:0:3}***${PASSWORD: -3}"
    echo "   Full: $PASSWORD"
fi

if [ -f "$ROOTS_STATE/tunnel_name" ]; then
    echo "🔧 Tunnel:   $(cat "$ROOTS_STATE/tunnel_name")"
fi

echo ""

# ─── System info ────────────────────────────────────────────────
echo "📊 System:"
echo "  CPU: $(nproc) cores"

# RAM
FREE_OUTPUT=$(free -h | awk '/^Mem:/{print $2, $3}')
echo "  RAM: $FREE_OUTPUT (total, used)"

# Disk
DISK_FREE=$(df -h /content 2>/dev/null | awk 'NR==2{print $4}')
echo "  Disk: ${DISK_FREE:-unknown} free"

# GPU
GPU=$(python3 -c "import torch; print(torch.cuda.get_device_name(0)) if torch.cuda.is_available() else print('None')" 2>/dev/null || echo "None")
echo "  GPU: $GPU"

echo ""

# ─── Restore from Drive (non-interactive) ──────────────────────
# Prefere a pasta registrada pelo notebook; default "colab-roots"
if [ -f "$ROOTS_STATE/drive_path" ]; then
    DRIVE_PATH=$(cat "$ROOTS_STATE/drive_path")
else
    DRIVE_PATH="/content/drive/MyDrive/colab-roots"
fi
if [ -d "$DRIVE_PATH" ]; then
    echo "☁️  Found Drive backup at $DRIVE_PATH"
    
    # Restore state files
    if [ -d "$DRIVE_PATH/state" ]; then
        for f in "$DRIVE_PATH/state/"*; do
            [ -f "$f" ] || continue
            basename=$(basename "$f")
            # Don't overwrite passwords
            case "$basename" in
                password|code-server-pw) continue ;;
            esac
            cp "$f" "$ROOTS_STATE/$basename" 2>/dev/null || true
        done
        echo "   ✅ State files restored"
    fi
    
    # Restore packages
    if [ -f "$DRIVE_PATH/requirements.txt" ]; then
        echo "   📦 Found saved packages (run 'pip install -r $DRIVE_PATH/requirements.txt' to restore)"
    fi

    # Restore workspace — safe semantics: ONLY when the local one is empty
    if [ -d "$DRIVE_PATH/workspace" ] && [ -n "$(find "$DRIVE_PATH/workspace" -mindepth 1 -maxdepth 1 2>/dev/null | head -1)" ]; then
        if [ ! -d /content/workspace ] || [ -z "$(find /content/workspace -mindepth 1 -maxdepth 1 2>/dev/null | head -1)" ]; then
            echo "   📥 Workspace local vazio — restaurando do backup…"
            mkdir -p /content/workspace
            rsync -a --exclude=.git --exclude=node_modules --exclude=__pycache__ --exclude='*.log' --exclude=.env \
                "$DRIVE_PATH/workspace/" /content/workspace/
            echo "   ✅ Workspace restaurado"
        else
            echo "   ⏭️  Workspace local já tem conteúdo — mantendo (não sobrescreve)"
        fi
    fi
else
    echo "☁️  No Drive backup found"
fi

echo ""
echo "✅ Restore complete"
echo "   roots status    — check services"
echo "   roots restart X — restart a service"
