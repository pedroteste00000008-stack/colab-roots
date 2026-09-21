# Quick Start

## Method 1: One click (Recommended)

1. Open the notebook in Colab with the badge below:

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/pedroteste00000008-stack/colab-roots/blob/main/notebook/colab_roots.ipynb)

2. Press **Runtime ▸ Run all**
3. Wait 2–4 minutes while the VM is prepared
4. Copy the **IDE link** and **Terminal link** printed at the end
5. Close the tab — the VM keeps running (keep-alive loop)

The START cell is fully self-contained: it installs everything, starts services,
mounts Drive (and keeps working even if you skip the auth), and prints working
Colab proxy URLs. No manual URLs like `127.0.0.1` — those don't work in Colab.

## Method 3: Manual Setup

If you prefer manual control:

### Step 1: Install dependencies

```python
!apt-get update -qq && apt-get install -y -qq curl wget git tmux jq
!curl -fsSL https://code-server.dev/install.sh | sh
!wget -q https://github.com/tsl0922/ttyd/releases/latest/download/ttyd.x86_64 -O /usr/local/bin/ttyd && chmod +x /usr/local/bin/ttyd
```

### Step 2: Mount Google Drive (for persistence)

```python
from google.colab import drive
drive.mount('/content/drive')
```

### Step 3: Start services

```bash
# Start tmux
tmux new-session -d -s roots

# Start code-server
nohup code-server --bind-addr 127.0.0.1:8080 --auth password --disable-telemetry &

# Start ttyd
nohup ttyd -p 7681 -W -c roots:YOUR_PASSWORD tmux attach -t roots &
```

### Step 4: Access

> ⚠️ **`127.0.0.1` não abre no seu navegador.** Esses links só funcionam *dentro* da VM.
> No Colab, use **View ▸ Ports** (adição manual de 8080 e 7681) ou as URLs
> Colab proxy geradas pelo notebook (célula ▶️ INICIAR TUDO). Este método manual
> é para quem quer entender o mecanismo — o notebook one-click já faz tudo.

## First Time Setup

### VS Code Remote Tunnel

1. Install [Remote Tunnels extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode.remote-server) in desktop VS Code
2. Sign in with GitHub
3. The notebook will generate a tunnel name
4. Use Command Palette → "Remote Tunnels: Connect to Tunnel..."
5. Select your tunnel name

### Cloudflare Tunnel (Temporary)

For quick public access:

```bash
# Install cloudflared
!wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -O /usr/local/bin/cloudflared
!chmod +x /usr/local/bin/cloudflared

# Create tunnel
!cloudflared tunnel --url http://127.0.0.1:8080
```

## Reconnecting

If you lose connection but the Colab VM is still running:

1. Go back to the Colab notebook
2. Run the 🔄 **RE-LINK** cell (regenerates proxy links — no reinstall)
3. Use the displayed URLs and credentials
4. 📊 **STATUS** cell shows what's running and the heartbeat age

## Troubleshooting

### "Address already in use"

```bash
# Kill existing processes
!pkill -f code-server
!pkill -f ttyd
```

### "Permission denied"

```bash
!chmod +x /usr/local/bin/ttyd
```

### Services not accessible

Make sure you're using the correct URLs. Services bind to 127.0.0.1 (localhost), not 0.0.0.0.

### Google Drive not mounting

```python
from google.colab import drive
drive.mount('/content/drive', force_remount=True)
```
