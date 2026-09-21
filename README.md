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
| Google Drive persistence | ❌ | ❌ | ✅ (Drive mount + rsync) |
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
│  │  • Drive sync (rsync)                        │  │
│  └────┬──────────────┬────────────────┬──────────┘  │
│       │              │                │              │
│  ┌────┴─────┐  ┌─────┴────┐  ┌───────┴──────────┐  │
│  │ Cloudflare│  │ VS Code  │  │ Google Drive     │  │
│  │ Tunnel    │  │ Tunnel   │  │ (Drive mount) │  │
│  └──────────┘  └──────────┘  └──────────────────┘  │
└─────────────────────────────────────────────────────┘
```

## Quick Start — one-click 🎬

### 1. Open in Colab

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/pedroteste00000008-stack/colab-roots/blob/main/notebook/colab_roots.ipynb)

### 2. Press play

**Runtime ▸ Run all. Wait 2–4 minutes. Done.**

The notebook does everything by itself:

1. Installs all dependencies
2. Mounts Google Drive (optional — it *keeps working* if you skip the auth)
3. Starts the services + daemon
4. Prints your **IDE link** and **Terminal link** — real Colab proxy URLs that
   work in your browser (no useless `127.0.0.1` links)
5. Keeps your VM **alive** (blocking keep-alive loop — close the tab anytime)

### 3. Connect

- **Browser IDE**: click the IDE link → enter the printed password
- **Terminal**: click the Terminal link → user `roots` + printed password
- Re-open links later with the 🔄 **RE-LINK** cell
- Optional 🌐 **Cloudflare** cell gives public URLs that work from any device
  without a Google login

### 4. Stop (when you're done)

Interrupt the START cell (■), then run the 🛑 **PARAR** cell — or just
`Runtime ▸ Disconnect & delete runtime`.

## Advanced Configuration (optional)

In the first cell, configure:
```python
WORKSPACE_REPO = ""          # Git repo to clone (optional)
WORKSPACE_BRANCH = "main"    # Branch/tag/ref
ENABLE_CODE_SERVER = True    # Browser IDE
ENABLE_TTYD = True           # Browser terminal
ENABLE_VSCODE_TUNNEL = False # VS Code Remote Tunnel (needs MS/GitHub login)
PERSIST_TO_DRIVE = True      # Auto-sync to Google Drive
DRIVE_FOLDER = "colab-roots" # Folder in Google Drive
```

## Services

| Service | Port | Purpose | URL Pattern |
|---------|------|---------|-------------|
| code-server | 8080 | Full VS Code IDE in browser | Colab proxy link printed by notebook |
| ttyd | 7681 | Browser terminal | Colab proxy link printed by notebook |
| VS Code Tunnel | - | Official VS Code Remote | Via VS Code extension (optional) |
| Cloudflare | - | Public URLs, any device | `https://<sub>.trycloudflare.com` (optional cell) |

## Persistence Strategy

Colab Roots uses a multi-layer persistence strategy:

1. **tmux sessions**: Survive terminal disconnects within a session
2. **Google Drive sync**: Background sync via rsync to the mounted Drive
   folder (daemon runs it every 10 minutes)
3. **State file**: Service state + heartbeat (`~/.colab-roots/state`)
4. **Auto-restore**: On a fresh VM, the START cell restores your workspace from
   Drive (only when local is empty — never overwrites) and reinstalls saved
   packages
5. **Keep-alive**: Prevents idle timeouts (START cell loop + daemon heartbeat)

### What gets persisted:
- Workspace files (`/content/workspace` → Drive, excluding `.git`, `node_modules`, `__pycache__`, logs, `.env`)
- Installed pip packages (snapshot in `requirements.txt` on Drive)
- Git repositories (cloned into the workspace, synced to Drive)
- Non-secret state files (tunnel name, heartbeat, service state)

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
roots restart vscode-tunnel   # only if VS Code tunnel enabled

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

Colab Roots keeps your VM awake with 2 independent layers:

1. **START cell loop**: the notebook cell blocks with periodic heartbeat +
   CPU activity — this is what Colab's idle detection actually watches.
   You can close the tab; the loop keeps executing on the VM.
2. **Daemon heartbeat**: background process writing heartbeat + CPU ticks
   (redundant backup layer).

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
2. If VM is alive, run the 🔄 **RE-LINK** cell to get fresh proxy links
3. If VM is dead, run ▶️ **INICIAR TUDO** again — Drive restores your environment

### Drive sync failing
```bash
roots doctor       # Diagnose the issue
roots logs daemon  # Check daemon logs (sync runs inside the daemon)
```

## License

MIT
