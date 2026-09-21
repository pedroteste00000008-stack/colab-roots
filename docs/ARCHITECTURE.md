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

#### Google Drive + rclone
- Workspace files synced to `~/colab-roots/workspace/`
- State files (excluding secrets) synced to `~/colab-roots/state/`
- Package list saved as `requirements.txt`
- Background sync every 10 minutes

#### State File
- Tracks installed packages
- Records system configuration
- Stores custom scripts
- Enables auto-restore on reconnect

### 8. Keep-Alive (Multi-Layer)

**Layer 1: Notebook Cell** (within Colab UI)
- Background thread executing lightweight operations
- Prevents 90-minute idle timeout

**Layer 2: Browser Tab** (JavaScript)
- Periodic DOM manipulation
- Simulates user activity

**Layer 3: Daemon Heartbeat**
- File-based heartbeat written every N seconds
- External monitoring possible

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
│   └── roots              # CLI script
├── logs/
│   ├── daemon.log
│   ├── code-server.log
│   └── ttyd.log
├── src/
│   └── daemon.py          # Daemon + CLI
├── state/
│   ├── password           # Session password (sensitive)
│   ├── tunnel_name        # VS Code tunnel name
│   ├── services.json      # Service state
│   ├── heartbeat          # Latest heartbeat timestamp
│   ├── version            # Installed version
│   └── code-server-pw     # code-server password file
└── notebook/
    └── colab_roots.ipynb
```
