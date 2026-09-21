# Colab Roots 🌱 v2 (hardened)

> **The most stable ephemeral VM experience on Google Colab.**

> **Security:** ver `docs/SECURITY.md`. Testes adversariais em `tests/test_daemon_hardening.py` (`python3 tests/test_daemon_hardening.py`).

Colab Roots transforms a disposable Colab runtime into a persistent, reconnectable development environment with a full IDE, terminal, service daemon, and automatic data persistence.

## Why Colab Roots?

Google Colab VMs are ephemeral by design — they disappear when you disconnect or go idle. Colab Roots fights back:

| Feature | Colab Nomad | Colab SSH | **Colab Roots** |
|---------|-------------|-----------|-----------------|
| Official ToS compliance | ✅ | ❌ (SSH banned) | ✅ (VS Code Tunnels + Cloudflare) |
| Browser IDE (code-server) | ❌ | ❌ | ✅ |
| Browser terminal (ttyd) | ✅ | ❌ | ✅ |
| VS Code Remote Tunnels | ❌ | ❌ | ✅ |
| tmux session persistence | ✅ | ❌ | ✅ |
| Service daemon (process mgmt) | Go binary | ❌ | ✅ Python daemon |
| Auto-restore on reconnect | Partial | ❌ | ✅ |
| Google Drive persistence | ❌ | ❌ | ✅ (rclone sync) |
| Keep-alive (idle prevention) | ❌ | ❌ | ✅ (multi-layer) |
| Health monitoring + self-heal | Basic | ❌ | ✅ |
| SSH fallback (cloudflared) | N/A | ✅ | ✅ (optional) |
| OpenCode support | ✅ | ❌ | ✅ |
| One-click setup | ✅ | ✅ | ✅ |

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   Colab VM                          │
│                                                     │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────┐  │
│  │ tmux     │  │ ttyd     │  │ code-server      │  │
│  │ (sessions)│  │ (terminal)│  │ (IDE in browser) │  │
│  └────┬─────┘  └────┬─────┘  └───────┬──────────┘  │
│       │              │                │              │
│  ┌────┴──────────────┴────────────────┴──────────┐  │
│  │            colab-roots daemon                  │  │
│  │  • Process supervision                        │  │
│  │  • Auto-restart on crash                      │  │
│  │  • Health checks                              │  │
│  │  • Keep-alive heartbeat                       │  │
│  │  • Drive sync (rclone)                        │  │
│  └────┬──────────────┬────────────────┬──────────┘  │
│       │              │                │              │
│  ┌────┴─────┐  ┌─────┴────┐  ┌───────┴──────────┐  │
│  │ Cloudflare│  │ VS Code  │  │ Google Drive     │  │
│  │ Tunnel    │  │ Tunnel   │  │ (via rclone)     │  │
│  └──────────┘  └──────────┘  └──────────────────┘  │
└─────────────────────────────────────────────────────┘
```

## Quick Start

### 1. Open in Colab

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/your-user/colab-roots/blob/main/notebook/colab_roots.ipynb)

### 2. Set your preferences (optional)

In the first cell, configure:
```python
WORKSPACE_REPO = ""          # Git repo to clone (optional)
WORKSPACE_BRANCH = "main"    # Branch/tag/ref
ENABLE_VSCODE_TUNNEL = True  # VS Code Remote Tunnel
ENABLE_CODE_SERVER = True    # Browser IDE
ENABLE_TTYD = True           # Browser terminal
ENABLE_SSH = False           # SSH via Cloudflare (optional)
PERSIST_TO_DRIVE = True      # Auto-sync to Google Drive
DRIVE_FOLDER = "colab-roots" # Folder in Google Drive
```

### 3. Run all cells

The notebook will:
1. Mount Google Drive (if persistence enabled)
2. Install all dependencies
3. Start services and tunnels
4. Print access URLs and credentials

### 4. Connect

- **Browser IDE**: Click the code-server URL → full VS Code in browser
- **VS Code Desktop**: Use Remote Tunnels extension → select your tunnel
- **Terminal**: Click the ttyd URL → browser-based terminal
- **SSH** (optional): Connect via the Cloudflare tunnel

## Services

| Service | Port | Purpose | URL Pattern |
|---------|------|---------|-------------|
| code-server | 8080 | Full VS Code IDE in browser | `https://<tunnel>/code-server/` |
| ttyd | 7681 | Browser terminal | `https://<tunnel>/ttyd/` |
| VS Code Tunnel | - | Official VS Code Remote | Via VS Code extension |
| SSH | 22 | Cloudflare tunnel SSH | `ssh root@<tunnel>` |

## Persistence Strategy

Colab Roots uses a multi-layer persistence strategy:

1. **tmux sessions**: Survive terminal disconnects within a session
2. **Google Drive sync**: Automatic background sync via rclone
3. **State file**: Tracks installed packages, config, customizations
4. **Auto-restore**: On reconnect, restores previous environment state
5. **Keep-alive**: Prevents idle timeouts via periodic activity

### What gets persisted:
- Installed pip packages (state file)
- Git repositories (cloned to Drive)
- Configuration files (.bashrc, .gitconfig, etc.)
- Custom scripts and tools
- tmux session names (for quick restore)

### What doesn't persist (inherent Colab limitation):
- GPU/CPU state (ephemeral VM)
- Running processes (must restart after VM death)
- System-level package installs (apt)

## Daemon Commands

Once running, manage services via the daemon:

```bash
# Add to PATH first
export PATH="$HOME/.colab-roots/bin:$PATH"

# Check all services
roots status

# Restart specific service
roots restart code-server
roots restart ttyd
roots restart daemon

# View logs
roots logs daemon
roots logs code-server
roots logs ttyd

# Trigger manual Drive sync
roots sync

# Run health check
roots doctor

# Graceful shutdown
roots down
```

## Keep-Alive

Colab Roots implements 3 layers of keep-alive:

1. **Notebook cell**: Periodic execution within the Colab notebook
2. **Browser tab**: JavaScript-based tab activity simulation  
3. **Daemon heartbeat**: Background process that maintains activity

⚠️ **Note**: Keep-alive works against idle timeouts but not against 12-hour maximum session limits or resource reclamation. For guaranteed uptime, use GCP Marketplace VMs.

## Security

- Services bind to `127.0.0.1` by default
- Public access only through authenticated tunnels
- Credentials auto-generated per session (random passwords)
- Token/credential redaction in logs
- **Never** paste credentials into public channels

## Troubleshooting

### Service won't start
```bash
roots doctor          # Check what's wrong
roots logs <service>  # View service logs
roots restart <service>
```

### Lost connection
1. Check if Colab VM is still running (look at the notebook)
2. If VM is alive, re-run the last notebook cell to get new URLs
3. If VM is dead, re-run the notebook from the beginning

### Drive sync failing
```bash
roots sync --force     # Force full sync
roots logs sync        # Check sync logs
```

## License

MIT
