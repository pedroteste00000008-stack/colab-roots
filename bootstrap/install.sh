#!/usr/bin/env bash
# Colab Roots — Bootstrap installer
# Installs Colab Roots into a Colab VM.
# Usage: bash install.sh

set -euo pipefail

VERSION="2.0.0"
ROOTS_HOME="${ROOTS_HOME:-$HOME/.colab-roots}"
ROOTS_BIN="$ROOTS_HOME/bin"
ROOTS_LOGS="$ROOTS_HOME/logs"
ROOTS_STATE="$ROOTS_HOME/state"

echo "═══════════════════════════════════════════"
echo "  🌱 Colab Roots — Installer v${VERSION}"
echo "═══════════════════════════════════════════"
echo ""

# ─── Create directories ──────────────────────────────────────────
for dir in "$ROOTS_BIN" "$ROOTS_LOGS" "$ROOTS_STATE"; do
    mkdir -p "$dir"
done

# ─── Resolve script directory ────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# ─── Install CLI ─────────────────────────────────────────────────
echo "📦 Installing CLI..."
if [ -f "$PROJECT_DIR/scripts/roots" ]; then
    cp "$PROJECT_DIR/scripts/roots" "$ROOTS_BIN/roots"
    chmod +x "$ROOTS_BIN/roots"
    echo "   ✅ CLI installed to $ROOTS_BIN/roots"
else
    echo "   ❌ Source not found: $PROJECT_DIR/scripts/roots"
    echo "   Install manually or run from project directory"
fi

# ─── Install Python modules ──────────────────────────────────────
echo "📦 Installing Python modules..."
mkdir -p "$ROOTS_HOME/src"
if [ -f "$PROJECT_DIR/src/daemon.py" ]; then
    cp "$PROJECT_DIR/src/daemon.py" "$ROOTS_HOME/src/daemon.py"
    echo "   ✅ daemon.py installed"
else
    echo "   ❌ Source not found: $PROJECT_DIR/src/daemon.py"
fi

# ─── Install notebook ────────────────────────────────────────────
echo "📦 Installing notebook..."
mkdir -p "$ROOTS_HOME/notebook"
if ls "$PROJECT_DIR/notebook/"*.ipynb 2>/dev/null; then
    cp "$PROJECT_DIR/notebook/"*.ipynb "$ROOTS_HOME/notebook/"
    echo "   ✅ Notebook installed"
else
    echo "   ⚠️  No notebook files found"
fi

# ─── Write version file ──────────────────────────────────────────
echo "$VERSION" > "$ROOTS_STATE/version"

# ─── Verify installation ─────────────────────────────────────────
echo ""
echo "─── Verification ───"

OK=true
for f in "$ROOTS_BIN/roots" "$ROOTS_HOME/src/daemon.py"; do
    if [ -f "$f" ]; then
        echo "  ✅ $f"
    else
        echo "  ❌ $f"
        OK=false
    fi
done

echo ""
if [ "$OK" = true ]; then
    echo "✅ Colab Roots v${VERSION} installed successfully"
    echo ""
    echo "Next steps:"
    echo "  1. Add to PATH:  export PATH=\"$ROOTS_BIN:\$PATH\""
    echo "  2. Use CLI:       roots status"
    echo "  3. Or run the notebook for full bootstrap"
else
    echo "⚠️  Installation incomplete. Check errors above."
    exit 1
fi
