# Architecture

## Overview

Colab Roots is designed to transform an ephemeral Google Colab VM into a persistent, reconnectable development environment. It works within Google Colab's Terms of Service by using official APIs (VS Code Remote Tunnels) and standard tools (tmux, ttyd, code-server).

## Design Principles

1. **Compliance First**: All tunnel/proxy methods must comply with Google Colab's ToS
2. **Layered Persistence**: Multiple mechanisms to survive disconnections
3. **Self-Healing**: Services automatically restart on crash
4. **Zero Config**: Works out of the box with sensible defaults
5. **Modular**: Each component can be enabled/disabled independently

## Components

### 1. tmux (Session Persistence)

```
tmux new-session -d -s roots
```

tmux provides the foundation for session persistence. All terminal sessions run inside tmux, which survives SSH disconnections and browser tab closures. The `roots` session is the primary session.

**Why tmux?**
- Survives terminal disconnects
- Allows multiple windows/panes
- ttyd attaches to this session for browser access
- User can reattach from any terminal

### 2. ttyd (Browser Terminal)

ttyd is a terminal emulator that serves a web-based terminal via HTTP. It's lightweight, fast, and requires no account.

```
ttyd -p 7681 -W -c user:pass tmux attach -t roots
```

**Port**: 7681 (configurable)

### 3. code-server (Browser IDE)

code-server is a self-hosted VS Code that runs in the browser. It provides a full IDE experience without installing anything locally.

```
code-server --bind-addr 127.0.0.1:8080 --auth password
```

**Port**: 8080 (configurable)

### 4. VS Code Remote Tunnels (Official Integration)

The official VS Code Remote Tunnels extension provides the most stable way to connect desktop VS Code to Colab.

```
code-tunnel tunnel --accept-server-license-terms --name colab-roots-XXXX
```

**Pros**: Official, stable, supports all VS Code features
**Cons**: Requires GitHub authentication, connection through Microsoft servers

### 5. Cloudflare Tunnels (Optional)

Cloudflare's quick tunnels provide temporary public URLs without an account:

```
cloudflared tunnel --url http://127.0.0.1:8080 --no-autoupdate
```

**Pros**: No account needed, instant public URLs
**Cons**: Temporary (stops when process dies), URLs change each time

### 5b. Colab Proxy (primary browser access)

The *most important* access path. `google.colab.kernel.proxyPort(PORT)` asks Colab
for a public URL that proxies into the VM's `127.0.0.1:PORT`:

```
https://xxx-8080.colab.googleusercontent.com/  →  127.0.0.1:8080 (code-server)
```

**Pros**: Works out of the box in the browser; automatic Google auth (no extra
password to manage); HTTPS; no external account needed.
**Cons**: The URL works while the runtime is alive; proxy is browser/account-bound.

The START cell prints these URLs; the 🔄 RE-LINK cell regenerates them later.
Services stay bound to `127.0.0.1` — only Colab's proxy can reach them.

### 6. Daemon (Process Manager)

The daemon is a Python process that:
- Monitors all services via health checks
- Restarts crashed services (up to 5 times)
- Manages keep-alive heartbeats
- Handles Drive sync in background
- Provides a Unix socket API for the CLI

**Architecture**:
```
┌─────────────────────────────────────────┐
│            Daemon Process               │
│                                         │
│  ┌─────────────┐  ┌──────────────────┐  │
│  │ Health       │  │ Keep-alive       │  │
│  │ Checker      │  │ Heartbeat        │  │
│  │ (15s interval)│  │ (configurable)   │  │
│  └─────────────┘  └──────────────────┘  │
│                                         │
│  ┌─────────────┐  ┌──────────────────┐  │
│  │ Drive Sync   │  │ Socket Server    │  │
│  │ (10min)      │  │ (CLI API)        │  │
│  └─────────────┘  └──────────────────┘  │
└─────────────────────────────────────────┘
```

### 7. Persistence Layer

#### Google Drive (mount + rsync)
- Workspace files synced to `MyDrive/colab-roots/workspace/` via rsync
- Package snapshot saved as `requirements.txt`
- Non-secret state files (tunnel name, heartbeat, service state) synced to `MyDrive/colab-roots/state/`
- Background sync every 10 minutes (daemon loop); secrets (`password`, `code-server-pw`) never leave the VM

#### State File (`~/.colab-roots/state/`)
- `services.json` — service status (no secrets, no PIDs)
- `heartbeat` — latest keep-alive timestamp
- `password` / `code-server-pw` — session credentials (0600)
- `drive_path`, `tunnel_name`, `version`

### 8. Keep-Alive (2 layers — what Colab idle detection actually watches)

Colab disconnects an idle runtime after ~90 min of inactivity (free tier).
Idle = no kernel execution. So the critical keep-alive is a *blocking loop*:

**Layer 1: START cell loop** (primary)
- The notebook's START cell enters an infinite loop after printing the links
- It writes a heartbeat file + does a tiny CPU tick each interval
- The kernel stays *executing* — Colab sees activity and keeps the VM alive
- The user can close the browser tab; the loop keeps running on the VM
- Interrupting the cell (■) stops this layer — services keep running

**Layer 2: Daemon heartbeat** (redundant backup)
- Background process writing heartbeat + CPU ticks every interval
- Costs nothing, keeps heartbeat file fresh even without the notebook open

**Limitation**: Cannot prevent 12-hour maximum session limit or resource reclamation.

## Data Flow

```
User's Browser
    │
    ├──▶ code-server (8080) ──▶ Colab VM filesystem
    │
    ├──▶ ttyd (7681) ──▶ tmux session ──▶ Shell
    │
    ├──▶ VS Code Desktop ──▶ VS Code Tunnel ──▶ Colab VM
    │
    └──▶ Cloudflare Tunnel ──▶ Colab VM (exposed services)
    
Colab VM
    │
    ├──▶ Daemon ──▶ Health checks ──▶ Auto-restart
    │
    ├──▶ Daemon ──▶ Keep-alive ──▶ Prevent idle timeout
    │
    └──▶ Daemon ──▶ Drive sync ──▶ Google Drive
```

## Security Model

1. **Local binding**: All services bind to 127.0.0.1 by default
2. **Authentication**: Random passwords generated per session
3. **Tunnel-only access**: Public access only through authenticated tunnels
4. **No SSH**: Avoids prohibited SSH tunnels on free tier
5. **Credential isolation**: Passwords stored in files, not environment variables

## File Structure

```
~/.colab-roots/
├── bin/
│   └── roots              # CLI script (installed by the notebook)
├── logs/
│   ├── daemon.log
│   ├── code-server.log
│   └── ttyd.log
├── src/
│   ├── daemon.py          # Daemon + CLI
│   └── start_daemon.py    # Launcher written by the START cell
├── state/
│   ├── password           # Session password (sensitive, 0600)
│   ├── code-server-pw     # code-server password file (sensitive, 0600)
│   ├── services.json      # Service state (no secrets/PIDs)
│   ├── heartbeat          # Latest heartbeat timestamp
│   ├── tunnel_name        # VS Code tunnel name
│   ├── drive_path         # Registered Drive backup folder
│   └── version            # Installed version
└── notebook/
    └── colab_roots.ipynb
```
