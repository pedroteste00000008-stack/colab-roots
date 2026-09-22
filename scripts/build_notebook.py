#!/usr/bin/env python3
"""Build the one-click Colab Roots notebook.

Usage: python3 scripts/build_notebook.py
Output: notebook/colab_roots.ipynb

Design goals (average user = zero setup):
- "Give it play, get your link, close the tab."
- The START cell does EVERYTHING and ends in a blocking keep-alive loop,
  which keeps the Colab kernel busy -> no idle disconnect.
- External access links use Cloudflare Quick Tunnels; Colab's runtime proxy is
  used only through the supported in-notebook iframe helper.
- Re-running cells is idempotent (no duplicate daemons/services/passwords).
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "notebook" / "colab_roots.ipynb"


# ─────────────────────────────────────────────────────────────────────
# helpers
# ─────────────────────────────────────────────────────────────────────
def src(text: str):
    """Turn a single (already newline-separated) string into ipynb source list."""
    out = []
    lines = text.replace("\r\n", "\n").split("\n")
    for i, line in enumerate(lines):
        if i < len(lines) - 1:
            out.append(line + "\n")
        elif line:
            out.append(line)
    return out


def markdown(text: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": src(text)}


def code(text: str) -> dict:
    return {"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [], "source": src(text)}


# ─────────────────────────────────────────────────────────────────────
# CELL 0 — Title / how to use
# ─────────────────────────────────────────────────────────────────────
C0 = r"""# 🌱 Colab Roots — One-Click Edition 🌳

**Transforma seu Google Colab numa máquina de desenvolvimento estável — como uma árvore com raízes.**

- 🖥️ **VS Code completo no navegador** (code-server)
- 💻 **Terminal no navegador** com sessão tmux persistente (ttyd)
- 🤖 **OpenCode Web** pronto para codar com agentes no mesmo workspace
- 💾 **Backup automático no Google Drive** — seu trabalho sobrevive a reconexões
- ❤️ **Keep-alive** — a VM não "dorme" nem desconecta por inatividade
- 🔗 **Links externos de verdade** via Cloudflare Quick Tunnel (com senha) + fallback embutido do Colab

---

## 🎬 Como usar (30 segundos, sem configuração)

1. **Runtime ▸ Run all** (ou clique no ▶ da célula "▶️ INICIAR TUDO" abaixo)
2. Espere 2–4 minutos (a VM está instalando tudo — acompanhe o progresso)
3. **Copie o link do IDE e do Terminal** que aparecem no final
4. **Feche a aba.** A VM continua rodando. Reabra os links quando quiser.

> ⚠️ Uso educacional/de desenvolvimento. Respeite os Termos de Serviço do Google Colab.
> ⚠️ VMs gratuitas são recicladas após ~12h ou longa inatividade. A célula de START fica rodando justamente para evitar isso.
"""

# ─────────────────────────────────────────────────────────────────────
# CELL 1 — Config intro
# ─────────────────────────────────────────────────────────────────────
C1 = r"""## ⚙️ Configuração (opcional — normalmente não mexa)

Os padrões já estão ajustados para **zero fricção**. Toque no formulário abaixo
só se quiser:

- Clonar um repositório Git automaticamente para `/content/workspace`
- Mudar a pasta de backup no Google Drive
- Desligar o IDE ou o terminal do navegador
- Habilitar o *VS Code Remote Tunnel* para conectar o VS Code do seu computador (pede login)

**Se você não quer configurar nada: pule esta célula e vá direto para ▶️ INICIAR TUDO.**
"""

# ─────────────────────────────────────────────────────────────────────
# CELL 2 — Config form
# ─────────────────────────────────────────────────────────────────────
C2 = r"""#@title ⚙️ Configuração (leve jeito — rode antes do START se for mexer){display-mode:"form"}
# ── Workspace ─────────────────────────────────────────────────
WORKSPACE_REPO    = ""        #@param {type:"string"}  Git repo para clonar em /content/workspace (vazio = não clonar)
WORKSPACE_BRANCH  = "main"    #@param {type:"string"}

# ── Serviços ─────────────────────────────────────────────────
ENABLE_CODE_SERVER   = True   #@param {type:"boolean"}  IDE VS Code no navegador (porta 8080)
ENABLE_TTYD          = True   #@param {type:"boolean"}  Terminal no navegador (porta 7681)
ENABLE_OPENCODE       = True   #@param {type:"boolean"}  OpenCode Web (porta 4096)
ENABLE_VSCODE_TUNNEL = False  #@param {type:"boolean"}  VS Code Remote Tunnel (pede login MS/GitHub)

# ── Persistência ─────────────────────────────────────────────
PERSIST_TO_DRIVE = True       #@param {type:"boolean"}  Backup automático no Google Drive
DRIVE_FOLDER     = "colab-roots"  #@param {type:"string"}

# ── Keep-alive ───────────────────────────────────────────────
KEEP_ALIVE_INTERVAL = 240     #@param {type:"integer"}  Batimentos por segundo (mínimo 60)

# ── Avançado (quase nunca mexa) ──────────────────────────────
DAEMON_URL = "https://raw.githubusercontent.com/pedroteste00000008-stack/colab-roots/main/src/daemon.py"  #@param {type:"string"}

import os, secrets, string
from pathlib import Path

ROOTS_HOME  = Path(os.path.expanduser("~/.colab-roots"))
ROOTS_BIN   = ROOTS_HOME / "bin"
ROOTS_LOGS  = ROOTS_HOME / "logs"
ROOTS_STATE = ROOTS_HOME / "state"
for d in (ROOTS_HOME, ROOTS_BIN, ROOTS_LOGS, ROOTS_STATE):
    d.mkdir(parents=True, exist_ok=True)

# Uma única senha para toda a sessão, salva em disco (idempotente)
pw_file = ROOTS_STATE / "password"
if pw_file.exists():
    PASSWORD = pw_file.read_text().strip()
else:
    PASSWORD = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(16))
    pw_file.write_text(PASSWORD)
    pw_file.chmod(0o600)

USERNAME = "roots"
OPENCODE_USERNAME = "opencode"
tn_file = ROOTS_STATE / "tunnel_name"
if tn_file.exists():
    TUNNEL_NAME = tn_file.read_text().strip()
else:
    TUNNEL_NAME = f"colab-roots-{secrets.token_hex(4)}"
    tn_file.write_text(TUNNEL_NAME)

os.environ.update({
    "ROOTS_HOME": str(ROOTS_HOME),
    "ROOTS_BIN": str(ROOTS_BIN),
    "ROOTS_LOGS": str(ROOTS_LOGS),
    "ROOTS_STATE": str(ROOTS_STATE),
    "ROOTS_WORKSPACE": "/content/workspace",
    "ROOTS_PASSWORD": PASSWORD,
    "ROOTS_USERNAME": USERNAME,
    "ROOTS_TUNNEL": TUNNEL_NAME,
    "ROOTS_DRIVE_FOLDER": DRIVE_FOLDER,
    "ROOTS_DAEMON_URL": DAEMON_URL,
    "ROOTS_KEEP_ALIVE_INTERVAL": str(KEEP_ALIVE_INTERVAL),
    "ROOTS_WORKSPACE_REPO": WORKSPACE_REPO,
    "ROOTS_WORKSPACE_BRANCH": WORKSPACE_BRANCH,
    "ROOTS_ENABLE_CODE_SERVER": str(ENABLE_CODE_SERVER),
    "ROOTS_ENABLE_TTYD": str(ENABLE_TTYD),
    "ROOTS_ENABLE_OPENCODE": str(ENABLE_OPENCODE),
    "ROOTS_OPENCODE_USERNAME": OPENCODE_USERNAME,
    "ROOTS_ENABLE_VSCODE_TUNNEL": str(ENABLE_VSCODE_TUNNEL),
    "ROOTS_PERSIST_TO_DRIVE": str(PERSIST_TO_DRIVE),
})

print("✅ Configuração carregada")
print(f"   Senha: {PASSWORD[:3]}…{PASSWORD[-2:]} (completa salva em {pw_file})")
"""

# ─────────────────────────────────────────────────────────────────────
# CELL 3 — START intro
# ─────────────────────────────────────────────────────────────────────
C3 = r"""## ▶️ INICIAR TUDO — um clique e pronto

**Rode a célula abaixo.** Ela vai:

1. Instalar tudo (2–4 min, siga o progresso)
2. Montar o Google Drive e **restaurar seu workspace + pacotes salvos** (aceite a autorização — dá para rodar **sem** o Drive também)
3. Subir os serviços + daemon de backup
4. Imprimir seus **links do IDE, Terminal e OpenCode** (funcionam de verdade no navegador)
5. **Manter a VM viva** (fica piscando 💓 — é normal, deixe quieto)

✅ **Depois que imprimir os links você pode fechar a aba.** A VM continua de pé.
"""

# ─────────────────────────────────────────────────────────────────────
# CELL 4 — START (the big one)
# ─────────────────────────────────────────────────────────────────────
C4 = r"""print("🌱 Colab Roots — ▶️ INICIAR TUDO 🚀")
import os, sys, time, socket, subprocess, secrets, string
from pathlib import Path

ROOTS_HOME    = Path(os.environ.get("ROOTS_HOME", str(Path.home() / ".colab-roots")))
ROOTS_BIN     = ROOTS_HOME / "bin"
ROOTS_LOGS    = ROOTS_HOME / "logs"
ROOTS_STATE   = ROOTS_HOME / "state"
ROOTS_WORKSPACE = Path(os.environ.get("ROOTS_WORKSPACE", "/content/workspace"))
USERNAME      = os.environ.get("ROOTS_USERNAME", "roots")
TUNNEL_NAME   = os.environ.get("ROOTS_TUNNEL", "colab-roots")

ENABLE_CODE_SERVER   = os.environ.get("ROOTS_ENABLE_CODE_SERVER", "True") == "True"
ENABLE_TTYD          = os.environ.get("ROOTS_ENABLE_TTYD", "True") == "True"
ENABLE_OPENCODE       = os.environ.get("ROOTS_ENABLE_OPENCODE", "True") == "True"
OPENCODE_USERNAME    = os.environ.get("ROOTS_OPENCODE_USERNAME", "opencode")
ENABLE_VSCODE_TUNNEL = os.environ.get("ROOTS_ENABLE_VSCODE_TUNNEL", "False") == "True"
PERSIST_TO_DRIVE     = os.environ.get("ROOTS_PERSIST_TO_DRIVE", "True") == "True"
DRIVE_FOLDER         = os.environ.get("ROOTS_DRIVE_FOLDER", "colab-roots")
KEEP_ALIVE_INTERVAL  = max(int(os.environ.get("ROOTS_KEEP_ALIVE_INTERVAL", "240")), 60)

for d in (ROOTS_HOME, ROOTS_BIN, ROOTS_LOGS, ROOTS_STATE, ROOTS_WORKSPACE):
    d.mkdir(parents=True, exist_ok=True)

# Senha única por sessão (já foi criada na célula de config, se rodou)
pw_file = ROOTS_STATE / "password"
if pw_file.exists():
    PASSWORD = pw_file.read_text().strip()
else:
    PASSWORD = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(16))
    pw_file.write_text(PASSWORD)
    pw_file.chmod(0o600)
(ROOTS_STATE / "code-server-pw").write_text(PASSWORD)
(ROOTS_STATE / "code-server-pw").chmod(0o600)

def sh(cmd, check=False, capture=True, timeout=None):
    r = subprocess.run(cmd, shell=isinstance(cmd, str), capture_output=capture, text=True, timeout=timeout)
    if check and r.returncode != 0:
        print(f"   ⚠️ falhou: {cmd}\n      {(r.stderr or '')[:300]}")
    return r

def listening(port):
    try:
        s = socket.create_connection(("127.0.0.1", port), 0.5); s.close(); return True
    except OSError:
        return False

def wait_port(port, timeout=90):
    end = time.time() + timeout
    while time.time() < end:
        if listening(port):
            return True
        time.sleep(1)
    return False

# ━━━ 1/9 Pacotes do sistema ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
print("📦 [1/9] Pacotes do sistema…")
sh("apt-get update -qq")
sh("apt-get install -y -qq curl wget git tmux jq rsync openssh-client")
print("   ✅ ok")

# ━━━ 2/9 code-server (IDE VS Code no navegador) ━━━━━━━━━━
if ENABLE_CODE_SERVER:
    print("📦 [2/9] code-server…")
    if sh("command -v code-server").returncode != 0:
        sh("curl -fsSL https://code-server.dev/install.sh | sh")
    print("   ✅ ok")

# ━━━ 3/9 ttyd (terminal no navegador) ━━━━━━━━━━━━━━━━━━━━
if ENABLE_TTYD:
    print("📦 [3/9] ttyd…")
    if sh("command -v ttyd").returncode != 0:
        if sh("wget -q https://github.com/tsl0922/ttyd/releases/latest/download/ttyd.x86_64 -O /usr/local/bin/ttyd").returncode != 0:
            sh("apt-get install -y -qq ttyd")
        sh("chmod +x /usr/local/bin/ttyd", check=False)
    print("   ✅ ok")

# ━━━ 4/9 OpenCode Web ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OPENCODE_BIN_DIR = Path.home() / ".opencode" / "bin"
os.environ["PATH"] = f"{OPENCODE_BIN_DIR}:{os.environ.get('PATH', '')}"
OPENCODE_READY = False
if ENABLE_OPENCODE:
    print("📦 [4/9] OpenCode…")
    if sh("command -v opencode").returncode != 0:
        install = sh("curl -fsSL https://opencode.ai/v2/install | bash")
        if install.returncode != 0:
            print(f"   ⚠️ instalação do OpenCode falhou: {(install.stderr or '')[:300]}")
    os.environ["PATH"] = f"{OPENCODE_BIN_DIR}:{os.environ.get('PATH', '')}"
    OPENCODE_READY = sh("command -v opencode").returncode == 0
    print("   ✅ ok" if OPENCODE_READY else "   ❌ OpenCode não instalado — seguindo sem ele")

# ━━━ 5/9 VS Code Remote Tunnel (opcional) ━━━━━━━━━━━━━━━━
if ENABLE_VSCODE_TUNNEL:
    print("🔧 [5/9] VS Code Remote Tunnel…")
    if sh("command -v code-tunnel").returncode != 0:
        sh("wget -q 'https://code.visualstudio.com/sha/download?build=stable&os=cli-alpine-x64' -O /tmp/vscode-cli.tar.gz")
        sh("mkdir -p /tmp/vscode-cli-extract")
        sh("tar -xzf /tmp/vscode-cli.tar.gz -C /tmp/vscode-cli-extract")
        sh("cp /tmp/vscode-cli-extract/code /usr/local/bin/code-tunnel && chmod +x /usr/local/bin/code-tunnel", check=False)
        sh("rm -rf /tmp/vscode-cli-extract /tmp/vscode-cli.tar.gz", check=False)
    ok = sh("command -v code-tunnel").returncode == 0
    print("   ✅ ok" if ok else "   ⚠️ pulado (opcional)")

# ━━━ 6/9 Google Drive (backup) ━━━━━━━━━━━━━━━━━━━━━━━━━━━
DRIVE_PATH = ""
if PERSIST_TO_DRIVE:
    print("☁️  [6/9] Google Drive…")
    if not Path("/content/drive/MyDrive").exists():
        try:
            from google.colab import drive
            drive.mount("/content/drive")   # autorização única do Google
        except Exception as e:
            print(f"   ⚠️ Drive não autorizado — seguindo SEM backup: {e}")
    if Path("/content/drive/MyDrive").exists():
        DRIVE_PATH = str(Path("/content/drive/MyDrive") / DRIVE_FOLDER)
        Path(DRIVE_PATH, "workspace").mkdir(parents=True, exist_ok=True)
        (ROOTS_STATE / "drive_path").write_text(DRIVE_PATH)
        req = Path(DRIVE_PATH) / "requirements.txt"
        if req.exists():
            print("   📦 Restaurando pacotes salvos…")
            sh(f"pip install -q -r '{req}'")
        print(f"   ✅ Drive pronto: {DRIVE_PATH}")
    else:
        print("   ⚠️ Sem Drive — rodando sem persistência")

# ━━━ 7/9 Workspace (repo opcional ou restauração do Drive) ━
WORKSPACE_REPO = os.environ.get("ROOTS_WORKSPACE_REPO", "").strip()
if WORKSPACE_REPO:
    print("📥 [7/9] Clonando workspace…")
    if (ROOTS_WORKSPACE / ".git").exists():
        sh(f"cd {ROOTS_WORKSPACE} && git pull --ff-only", check=False)
    else:
        import shutil
        if ROOTS_WORKSPACE.exists():
            shutil.rmtree(ROOTS_WORKSPACE)
        branch = os.environ.get("ROOTS_WORKSPACE_BRANCH", "main")
        if sh(f"git clone --branch {branch} {WORKSPACE_REPO} {ROOTS_WORKSPACE}", check=False).returncode != 0:
            sh(f"git clone {WORKSPACE_REPO} {ROOTS_WORKSPACE}", check=False)
    print("   ✅ workspace pronto (repo)")
elif DRIVE_PATH and not any(ROOTS_WORKSPACE.iterdir()):
    # Restauração com semântica segura: SÓ quando o local está vazio
    ws_backup = Path(DRIVE_PATH) / "workspace"
    if ws_backup.exists() and any(ws_backup.iterdir()):
        print("📥 [7/9] Restaurando workspace do Drive…")
        r = sh(f"rsync -a --exclude=.git --exclude=node_modules --exclude=__pycache__ --exclude='*.log' --exclude=.env '{ws_backup}/' '{ROOTS_WORKSPACE}/'")
        if r.returncode == 0:
            print("   ✅ workspace restaurado do Drive")
        else:
            print("   ⚠️  restore do workspace FALHOU — os arquivos locais ficaram como estão")
    else:
        print("   ℹ️  [7/9] Workspace vazio e sem backup no Drive — começando do zero")
else:
    print("   ℹ️  [7/9] Workspace já tem conteúdo — mantendo (nunca sobrescreve)")

# ━━━ 8/9 Daemon + serviços ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
print("🤖 [8/9] Daemon + serviços…")

def obtain_daemon():
    for c in (Path(os.getcwd()) / "src" / "daemon.py",
              Path(os.getcwd()) / "daemon.py",
              ROOTS_HOME / "src" / "daemon.py"):
        if c.exists():
            return c.read_text()
    url = os.environ.get("ROOTS_DAEMON_URL", "")
    if url:
        try:
            import urllib.request
            print("   📥 baixando daemon…")
            return urllib.request.urlopen(url, timeout=30).read().decode()
        except Exception as e:
            print(f"   ⚠️ download do daemon falhou: {e}")
    return None

daemon_src = obtain_daemon()
DAEMON_AVAILABLE = bool(daemon_src)
if DAEMON_AVAILABLE:
    dst = ROOTS_HOME / "src" / "daemon.py"
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(daemon_src)

# CLI "roots"
cli = ROOTS_BIN / "roots"
cli.write_text(
    "#!/usr/bin/env bash\n"
    'SOURCE="${BASH_SOURCE[0]}"\n'
    'ROOTS_HOME="' + str(ROOTS_HOME) + '"\n'
    'exec python3 "$ROOTS_HOME/src/daemon.py" "$@"\n'
)
cli.chmod(0o755)
print(f"   ✅ CLI: {cli}")

# Sessão tmux nova
sh("tmux kill-session -t roots 2>/dev/null || true")
sh("tmux new-session -d -s roots -x 220 -y 50")

if DAEMON_AVAILABLE:
    start_script = ROOTS_HOME / "start_daemon.py"
    start_script.write_text(
        "import os, sys\n"
        "sys.path.insert(0, os.path.expanduser('~/.colab-roots/src'))\n"
        "from daemon import ColabRootsDaemon\n"
        "config = {\n"
        " 'roots_home': os.environ['ROOTS_HOME'],\n"
        " 'enable_code_server': os.environ.get('ROOTS_ENABLE_CODE_SERVER', 'True') == 'True',\n"
        " 'enable_ttyd': os.environ.get('ROOTS_ENABLE_TTYD', 'True') == 'True',\n"
        " 'enable_opencode': os.environ.get('ROOTS_ENABLE_OPENCODE', 'True') == 'True',\n"
        " 'opencode_username': os.environ.get('ROOTS_OPENCODE_USERNAME', 'opencode'),\n"
        " 'enable_vscode_tunnel': os.environ.get('ROOTS_ENABLE_VSCODE_TUNNEL', 'False') == 'True',\n"
        " 'persist_to_drive': os.environ.get('ROOTS_PERSIST_TO_DRIVE', 'False') == 'True',\n"
        " 'drive_path': os.environ.get('ROOTS_DRIVE_PATH', ''),\n"
        " 'keep_alive': True,\n"
        " 'keep_alive_interval': int(os.environ.get('ROOTS_KEEP_ALIVE_INTERVAL', '240')),\n"
        " 'username': os.environ.get('ROOTS_USERNAME', 'roots'),\n"
        " 'password': os.environ.get('ROOTS_PASSWORD', ''),\n"
        " 'tunnel_name': os.environ.get('ROOTS_TUNNEL', 'colab-roots'),\n"
        "}\n"
        "d = ColabRootsDaemon(config)\n"
        "ok = d.start_background()\n"
        "sys.exit(0 if ok else 1)\n"
    )
    # Limpeza para o daemon ser dono das portas (idempotente)
    sh("pkill -f '[c]ode-server' 2>/dev/null || true")
    sh("pkill -x ttyd 2>/dev/null || true")
    sh("pkill -f '[o]pencode serve --hostname 127.0.0.1 --port 4096' 2>/dev/null || true")
    log = open(ROOTS_LOGS / "daemon.log", "ab")
    env = dict(os.environ, **{
        "ROOTS_HOME": str(ROOTS_HOME),
        "ROOTS_LOGS": str(ROOTS_LOGS),
        "ROOTS_STATE": str(ROOTS_STATE),
        "ROOTS_PASSWORD": PASSWORD,
        "ROOTS_USERNAME": USERNAME,
        "ROOTS_TUNNEL": TUNNEL_NAME,
        "ROOTS_DRIVE_PATH": DRIVE_PATH,
        "ROOTS_ENABLE_CODE_SERVER": str(ENABLE_CODE_SERVER),
        "ROOTS_ENABLE_TTYD": str(ENABLE_TTYD),
        "ROOTS_ENABLE_OPENCODE": str(ENABLE_OPENCODE and OPENCODE_READY),
        "ROOTS_OPENCODE_USERNAME": OPENCODE_USERNAME,
        "ROOTS_ENABLE_VSCODE_TUNNEL": str(ENABLE_VSCODE_TUNNEL),
        "ROOTS_PERSIST_TO_DRIVE": str(PERSIST_TO_DRIVE),
        "ROOTS_KEEP_ALIVE_INTERVAL": str(KEEP_ALIVE_INTERVAL),
    })
    try:
        subprocess.Popen(["python3", str(start_script)], env=env,
                         stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        time.sleep(3)
    except Exception as e:
        print(f"   ⚠️ daemon não subiu: {e}")
else:
    print("   ⚠️ daemon indisponível — subindo serviços direto (sem auto-restart)")
    if ENABLE_CODE_SERVER and not listening(8080):
        sh(f"nohup code-server --bind-addr 127.0.0.1:8080 --auth password --password-file '{ROOTS_STATE/'code-server-pw'}' --disable-telemetry --disable-update-check {ROOTS_WORKSPACE} > {ROOTS_LOGS}/code-server.log 2>&1 & echo $! > {ROOTS_STATE}/code-server.pid")
    if ENABLE_TTYD and not listening(7681):
        sh(f"nohup ttyd -p 7681 -W -c '{USERNAME}:{PASSWORD}' tmux attach -t roots > {ROOTS_LOGS}/ttyd.log 2>&1 & echo $! > {ROOTS_STATE}/ttyd.pid")
    if ENABLE_OPENCODE and OPENCODE_READY and not listening(4096):
        opencode_env = os.environ.copy()
        opencode_env.update({
            "OPENCODE_SERVER_USERNAME": OPENCODE_USERNAME,
            "OPENCODE_SERVER_PASSWORD": PASSWORD,
        })
        opencode_log = open(ROOTS_LOGS / "opencode.log", "ab")
        try:
            opencode_cmd = "opencode serve --hostname 127.0.0.1 --port 4096".split()
            opencode_proc = subprocess.Popen(
                opencode_cmd,
                cwd=str(ROOTS_WORKSPACE),
                env=opencode_env,
                stdout=opencode_log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            (ROOTS_STATE / "opencode.pid").write_text(str(opencode_proc.pid))
        finally:
            opencode_log.close()

print("   ⏳ esperando serviços subirem…")
if ENABLE_CODE_SERVER:
    print("   " + ("✅ code-server :8080" if wait_port(8080, 90) else "❌ code-server falhou"))
if ENABLE_TTYD:
    print("   " + ("✅ ttyd :7681" if wait_port(7681, 90) else "❌ ttyd falhou"))
if ENABLE_OPENCODE and OPENCODE_READY:
    print("   " + ("✅ OpenCode :4096" if wait_port(4096, 90) else "❌ OpenCode falhou"))
elif ENABLE_OPENCODE:
    print("   ⏭️  OpenCode indisponível porque a instalação falhou")

# ━━━ 9/9 Acesso (Cloudflare para IDE/terminal + SSE tunnel para OpenCode) ━━━━━━
print("\n⏳ criando links externos de acesso…")
import re, shutil, signal, base64, json, urllib.request, urllib.error

def ensure_cloudflared():
    if shutil.which("cloudflared"):
        return True
    print("   📦 instalando cloudflared…")
    r = subprocess.run(
        "wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 "
        "-O /usr/local/bin/cloudflared && chmod +x /usr/local/bin/cloudflared",
        shell=True, capture_output=True, text=True,
    )
    if r.returncode != 0:
        print(f"   ⚠️ cloudflared não instalou: {(r.stderr or '')[:300]}")
        return False
    return shutil.which("cloudflared") is not None

def pid_alive(path):
    try:
        os.kill(int(path.read_text().strip()), 0)
        return True
    except (OSError, ValueError):
        return False

def stop_pid_file(path):
    try:
        pid = int(path.read_text().strip())
    except (OSError, ValueError):
        path.unlink(missing_ok=True)
        return
    try:
        os.killpg(os.getpgid(pid), signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        pass
    path.unlink(missing_ok=True)

def start_quick_tunnel(port, label):
    log_path = ROOTS_LOGS / f"cloudflared-{label}.log"
    pid_path = ROOTS_STATE / f"cloudflare-{label}.pid"
    url_path = ROOTS_STATE / f"cloudflare-{label}.url"
    url_path.unlink(missing_ok=True)
    log_fh = open(log_path, "w")
    try:
        proc = subprocess.Popen(
            ["cloudflared", "tunnel", "--protocol", "http2", "--url", f"http://127.0.0.1:{port}", "--no-autoupdate"],
            stdout=log_fh, stderr=subprocess.STDOUT, text=True, start_new_session=True,
        )
    finally:
        log_fh.close()
    pid_path.write_text(str(proc.pid))
    pattern = re.compile(r"(https://[a-zA-Z0-9-]+\.trycloudflare\.com)")
    for _ in range(60):
        if proc.poll() is not None:
            break
        time.sleep(0.5)
        try:
            m = pattern.search(log_path.read_text(errors="replace"))
        except OSError:
            m = None
        if m:
            url = m.group(1).rstrip("/")
            url_path.write_text(url)
            return url
    tail = ""
    try:
        tail = "\n".join(log_path.read_text(errors="replace").splitlines()[-8:])
    except OSError:
        pass
    print(f"   ⚠️ tunnel {label} não gerou URL" + (f":\n{tail}" if tail else ""))
    return None

def start_opencode_tunnel(port=4096):
    """localhost.run is used because OpenCode depends on SSE (/api/event)."""
    log_path = ROOTS_LOGS / "opencode-tunnel.log"
    pid_path = ROOTS_STATE / "opencode-tunnel.pid"
    url_path = ROOTS_STATE / "opencode-tunnel.url"
    known_hosts = ROOTS_STATE / "localhostrun_known_hosts"
    stop_pid_file(pid_path)
    url_path.unlink(missing_ok=True)

    log_fh = open(log_path, "w")
    try:
        proc = subprocess.Popen(
            [
                "ssh", "-T",
                "-o", "ExitOnForwardFailure=yes",
                "-o", "ServerAliveInterval=30",
                "-o", "ServerAliveCountMax=3",
                "-o", "StrictHostKeyChecking=accept-new",
                "-o", f"UserKnownHostsFile={known_hosts}",
                "-R", f"80:127.0.0.1:{port}",
                "nokey@localhost.run",
            ],
            stdout=log_fh, stderr=subprocess.STDOUT, text=True, start_new_session=True,
        )
    finally:
        log_fh.close()
    pid_path.write_text(str(proc.pid))

    pattern = re.compile(r"(https://[A-Za-z0-9-]+\.lhr\.life(?:[^\s\x1b]*)?)")
    for _ in range(80):
        if proc.poll() is not None:
            break
        time.sleep(0.5)
        try:
            m = pattern.search(log_path.read_text(errors="replace"))
        except OSError:
            m = None
        if m:
            url = m.group(1).rstrip("/.,);]")
            url_path.write_text(url)
            return url
    tail = ""
    try:
        tail = "\n".join(log_path.read_text(errors="replace").splitlines()[-12:])
    except OSError:
        pass
    print("   ⚠️ tunnel SSE do OpenCode não gerou URL" + (f":\n{tail}" if tail else ""))
    stop_pid_file(pid_path)
    return None

def opencode_headers(accept="application/json"):
    token = base64.b64encode(f"{OPENCODE_USERNAME}:{PASSWORD}".encode()).decode()
    return {
        "Authorization": f"Basic {token}",
        "x-opencode-directory": str(ROOTS_WORKSPACE),
        "Accept": accept,
    }

def data_list(payload):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        value = payload.get("data")
        if isinstance(value, list):
            return value
    return []

def probe_opencode_api(base_url, timeout=15):
    counts = {}
    for endpoint, must_have_items in (
        ("/api/agent", True),
        ("/api/provider", True),
        ("/api/model", True),
        ("/api/session", False),
    ):
        try:
            req = urllib.request.Request(base_url.rstrip("/") + endpoint, headers=opencode_headers())
            with urllib.request.urlopen(req, timeout=timeout) as response:
                raw = response.read()
                if response.status != 200:
                    return False, counts, f"{endpoint} HTTP {response.status}"
                payload = json.loads(raw.decode() or "{}")
                items = data_list(payload)
                counts[endpoint] = len(items)
                if must_have_items and not items:
                    return False, counts, f"{endpoint} respondeu vazio"
        except Exception as exc:
            return False, counts, f"{endpoint}: {exc}"
    return True, counts, None

def probe_opencode_sse(base_url, timeout=12):
    try:
        req = urllib.request.Request(
            base_url.rstrip("/") + "/api/event",
            headers=opencode_headers("text/event-stream"),
        )
        with urllib.request.urlopen(req, timeout=timeout) as response:
            ctype = (response.headers.get("Content-Type") or "").lower()
            if response.status != 200 or not ctype.startswith("text/event-stream"):
                return False, f"/api/event HTTP {response.status} content-type={ctype!r}"
            for _ in range(80):
                line = response.readline().decode(errors="replace").strip()
                if line.startswith("data:") or line.startswith("event:"):
                    return True, None
            return False, "/api/event encerrou/ficou sem frame SSE"
    except Exception as exc:
        return False, str(exc)

def show_colab_iframe(port, label, height, path="/"):
    try:
        from google.colab import output
        print(f"   ↪ {label}: usando acesso embutido suportado pelo Colab")
        output.serve_kernel_port_as_iframe(port, path=path, height=height)
        return True
    except Exception as e:
        print(f"   ⚠️ fallback embutido {label} indisponível: {e}")
        return False

# Cloudflare continua para IDE/terminal; OpenCode usa túnel SSE-capable separado.
sh("pkill -f '[c]loudflared' 2>/dev/null || true")
for stale in ROOTS_STATE.glob("cloudflare-*.url"):
    stale.unlink(missing_ok=True)
for stale in ROOTS_STATE.glob("cloudflare-*.pid"):
    stale.unlink(missing_ok=True)

IDE_URL = TTYD_URL = None
if ensure_cloudflared():
    if ENABLE_CODE_SERVER and listening(8080):
        IDE_URL = start_quick_tunnel(8080, "code-server")
    if ENABLE_TTYD and listening(7681):
        TTYD_URL = start_quick_tunnel(7681, "ttyd")

OPENCODE_BASE_URL = OPENCODE_PROJECT_URL = None
OPENCODE_PROJECT_SLUG = base64.urlsafe_b64encode(str(ROOTS_WORKSPACE).encode()).decode().rstrip("=")
OPENCODE_PROBE_COUNTS = {}
if ENABLE_OPENCODE and OPENCODE_READY and listening(4096):
    local_ok, local_counts, local_error = probe_opencode_api("http://127.0.0.1:4096")
    if local_ok:
        print(
            "   ✅ OpenCode API local:"
            f" agents={local_counts.get('/api/agent', 0)}"
            f" providers={local_counts.get('/api/provider', 0)}"
            f" models={local_counts.get('/api/model', 0)}"
            f" sessions={local_counts.get('/api/session', 0)}"
        )
        OPENCODE_BASE_URL = start_opencode_tunnel(4096)
        if OPENCODE_BASE_URL:
            public_ok, public_counts, public_error = probe_opencode_api(OPENCODE_BASE_URL)
            sse_ok, sse_error = probe_opencode_sse(OPENCODE_BASE_URL)
            if public_ok and sse_ok:
                OPENCODE_PROBE_COUNTS = public_counts
                OPENCODE_PROJECT_URL = f"{OPENCODE_BASE_URL}/{OPENCODE_PROJECT_SLUG}"
                (ROOTS_STATE / "opencode-project.url").write_text(OPENCODE_PROJECT_URL)
                print("   ✅ OpenCode público: API de projeto + SSE validados")
            else:
                print(
                    "   ⚠️ OpenCode público reprovou probe:"
                    f" API={public_error or 'ok'}; SSE={sse_error or 'ok'}"
                )
                stop_pid_file(ROOTS_STATE / "opencode-tunnel.pid")
                OPENCODE_BASE_URL = None
    else:
        print(f"   ⚠️ OpenCode local não está pronto no contexto do workspace: {local_error}")

print()
print("=" * 62)
print("  🌳 COLAB ROOTS ESTÁ NO AR — acesso")
print("=" * 62)
if IDE_URL:
    print(f"  🖥️  IDE (VS Code):\n      {IDE_URL}\n      senha: {PASSWORD}")
elif ENABLE_CODE_SERVER and listening(8080):
    print("  🖥️  IDE: sem link externo; abrindo fallback dentro do notebook abaixo")
    show_colab_iframe(8080, "IDE", "720")
if TTYD_URL:
    print(f"  💻  Terminal:\n      {TTYD_URL}\n      usuário: {USERNAME}   senha: {PASSWORD}")
elif ENABLE_TTYD and listening(7681):
    print("  💻  Terminal: sem link externo; abrindo fallback dentro do notebook abaixo")
    show_colab_iframe(7681, "Terminal", "360")
if OPENCODE_PROJECT_URL:
    print(
        f"  🤖 OpenCode:\n      {OPENCODE_PROJECT_URL}"
        f"\n      usuário: {OPENCODE_USERNAME}   senha: {PASSWORD}"
        f"\n      workspace: {ROOTS_WORKSPACE}"
    )
elif ENABLE_OPENCODE and listening(4096):
    print("  🤖 OpenCode: link externo SSE indisponível; abrindo o projeto dentro do notebook")
    show_colab_iframe(4096, "OpenCode", "720", "/" + OPENCODE_PROJECT_SLUG)
if not (IDE_URL or TTYD_URL or OPENCODE_PROJECT_URL):
    print("  ⚠️  Nenhum link externo foi criado para um ou mais serviços. Use os fallbacks acima ou rode 🔄 RE-LINK.")
print(f"  🔑  Senha também salva em: {ROOTS_STATE / 'password'}")
print(f"  🛠️  Gerenciar com:          {ROOTS_BIN}/roots status")
if DRIVE_PATH:
    print(f"  ☁️  Backup no Drive:        {DRIVE_PATH}")
print("  🔒  IDE/terminal usam Cloudflare; OpenCode usa localhost.run porque precisa de SSE.")
print("      Reabra/renove depois com a célula 🔄 RE-LINK.")
print("=" * 62)

# ━━━ 💓 Keep-alive (bloqueia de propósito) ━━━━━━━━━━━━━━━
print(f"\n💓 Mantendo sua VM acordada (batimento a cada {KEEP_ALIVE_INTERVAL}s).")
print("   PODE FECHAR ESTA ABA AGORA — a VM continua trabalhando.")
print("   Para parar depois: reabra, aperte ■ neste celula, e rode a celula 🛑 PARAR.")

beat = 0
last_report = time.time()
try:
    while True:
        beat += 1
        try:
            (ROOTS_STATE / "heartbeat").write_text(time.strftime("%Y-%m-%dT%H:%M:%S"))
            _ = sum(i * i for i in range(8000))  # atividade leve de CPU
            now = time.time()
            if beat == 1 or now - last_report >= 1200:
                last_report = now
                print(f"   [{time.strftime('%H:%M:%S')}] 💓 vivo — batimento #{beat} · links acima continuam válidos", flush=True)
        except Exception:
            pass
        time.sleep(KEEP_ALIVE_INTERVAL)
except KeyboardInterrupt:
    print("\n🛑 Keep-alive parado (você interrompeu a célula).")
    print("   Os serviços continuam no ar. Rode 🛑 PARAR para desligar tudo, ou saia do runtime.")
"""

# ─────────────────────────────────────────────────────────────────────
# CELL 5 — Links / FAQ markdown
# ─────────────────────────────────────────────────────────────────────
C5 = r"""## 🔗 Seus links & como funciona

### Links externos
O START cria URLs temporárias para IDE e Terminal via Cloudflare. O OpenCode usa
um túnel SSH via localhost.run, porque sua UI depende de SSE em `/api/event`.
O link do OpenCode já aponta para a rota codificada de `/content/workspace`,
para que modelos, agents e sessões carreguem no contexto correto.

- **IDE** → senha mostrada pelo START
- **Terminal** → usuário `roots` + a mesma senha
- **OpenCode** → usuário `opencode` + a mesma senha; link já abre `/content/workspace`
- Os links são públicos na Internet, mas os serviços continuam protegidos pela senha.

### Por que não usamos mais o URL `*.prod.colab.dev`?
`google.colab.kernel.proxyPort()` é um proxy interno do frontend do Colab.
Abrir o origin retornado como uma URL externa comum pode resultar em 404 e o
helper oficial para nova janela está deprecated. Quando o túnel externo falha,
o notebook usa `serve_kernel_port_as_iframe()`, que é o caminho suportado
para acesso dentro do próprio Colab.

### O que acontece quando você fecha a aba?
Os serviços e os túneis rodam na VM. A célula START continua executando o
keep-alive.

### Perdi o link / fechei a aba / reconectou
Se a VM ainda está viva, rode:
- 🔄 **RE-LINK** — reutiliza ou recria os Quick Tunnels sem reinstalar tudo
- 📊 **STATUS** — mostra serviços e heartbeat

### Como parar de vez?
1. Aperte ■ na célula START
2. Rode 🛑 **PARAR**
3. Ou use **Runtime ▸ Disconnect & delete runtime**
"""

# ─────────────────────────────────────────────────────────────────────
# CELL 6 — Re-link
# ─────────────────────────────────────────────────────────────────────
C6 = r"""#@title 🔄 RE-LINK (reutilizar/recriar links externos){display-mode:"form"}
import os, time, socket, subprocess, re, shutil, signal, base64, json, urllib.request
from pathlib import Path

ROOTS_HOME  = Path(os.environ.get("ROOTS_HOME", str(Path.home() / ".colab-roots")))
ROOTS_LOGS  = ROOTS_HOME / "logs"
ROOTS_STATE = ROOTS_HOME / "state"
ROOTS_WORKSPACE = Path(os.environ.get("ROOTS_WORKSPACE", "/content/workspace"))
PASSWORD = (ROOTS_STATE / "password").read_text().strip() if (ROOTS_STATE / "password").exists() else ""
USERNAME = os.environ.get("ROOTS_USERNAME", "roots")
OPENCODE_USERNAME = os.environ.get("ROOTS_OPENCODE_USERNAME", "opencode")

def listening(port):
    try:
        s = socket.create_connection(("127.0.0.1", port), 0.5); s.close(); return True
    except OSError:
        return False

def pid_alive(path):
    try:
        os.kill(int(path.read_text().strip()), 0)
        return True
    except (OSError, ValueError):
        return False

def stop_pid_file(path):
    try:
        pid = int(path.read_text().strip())
    except (OSError, ValueError):
        path.unlink(missing_ok=True)
        return
    try:
        os.killpg(os.getpgid(pid), signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        pass
    path.unlink(missing_ok=True)

def saved_tunnel(label):
    pid_path = ROOTS_STATE / f"cloudflare-{label}.pid"
    url_path = ROOTS_STATE / f"cloudflare-{label}.url"
    if pid_path.exists() and url_path.exists() and pid_alive(pid_path):
        url = url_path.read_text().strip()
        if url.startswith("https://") and ".trycloudflare.com" in url:
            return url
    return None

def saved_opencode_tunnel():
    pid_path = ROOTS_STATE / "opencode-tunnel.pid"
    url_path = ROOTS_STATE / "opencode-tunnel.url"
    if pid_path.exists() and url_path.exists() and pid_alive(pid_path):
        url = url_path.read_text().strip()
        if url.startswith("https://") and ".lhr.life" in url:
            return url
    return None

def ensure_cloudflared():
    if shutil.which("cloudflared"):
        return True
    r = subprocess.run(
        "wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 "
        "-O /usr/local/bin/cloudflared && chmod +x /usr/local/bin/cloudflared",
        shell=True, capture_output=True, text=True,
    )
    return r.returncode == 0 and shutil.which("cloudflared") is not None

def start_quick_tunnel(port, label):
    log_path = ROOTS_LOGS / f"cloudflared-{label}.log"
    pid_path = ROOTS_STATE / f"cloudflare-{label}.pid"
    url_path = ROOTS_STATE / f"cloudflare-{label}.url"
    log_fh = open(log_path, "w")
    try:
        proc = subprocess.Popen(
            ["cloudflared", "tunnel", "--protocol", "http2", "--url", f"http://127.0.0.1:{port}", "--no-autoupdate"],
            stdout=log_fh, stderr=subprocess.STDOUT, text=True, start_new_session=True,
        )
    finally:
        log_fh.close()
    pid_path.write_text(str(proc.pid))
    pattern = re.compile(r"(https://[a-zA-Z0-9-]+\.trycloudflare\.com)")
    for _ in range(60):
        if proc.poll() is not None:
            break
        time.sleep(0.5)
        try:
            m = pattern.search(log_path.read_text(errors="replace"))
        except OSError:
            m = None
        if m:
            url = m.group(1).rstrip("/")
            url_path.write_text(url)
            return url
    return None

def start_opencode_tunnel(port=4096):
    log_path = ROOTS_LOGS / "opencode-tunnel.log"
    pid_path = ROOTS_STATE / "opencode-tunnel.pid"
    url_path = ROOTS_STATE / "opencode-tunnel.url"
    known_hosts = ROOTS_STATE / "localhostrun_known_hosts"
    stop_pid_file(pid_path)
    url_path.unlink(missing_ok=True)
    log_fh = open(log_path, "w")
    try:
        proc = subprocess.Popen(
            [
                "ssh", "-T",
                "-o", "ExitOnForwardFailure=yes",
                "-o", "ServerAliveInterval=30",
                "-o", "ServerAliveCountMax=3",
                "-o", "StrictHostKeyChecking=accept-new",
                "-o", f"UserKnownHostsFile={known_hosts}",
                "-R", f"80:127.0.0.1:{port}",
                "nokey@localhost.run",
            ],
            stdout=log_fh, stderr=subprocess.STDOUT, text=True, start_new_session=True,
        )
    finally:
        log_fh.close()
    pid_path.write_text(str(proc.pid))
    pattern = re.compile(r"(https://[A-Za-z0-9-]+\.lhr\.life(?:[^\s\x1b]*)?)")
    for _ in range(80):
        if proc.poll() is not None:
            break
        time.sleep(0.5)
        try:
            m = pattern.search(log_path.read_text(errors="replace"))
        except OSError:
            m = None
        if m:
            url = m.group(1).rstrip("/.,);]")
            url_path.write_text(url)
            return url
    stop_pid_file(pid_path)
    return None

def opencode_headers(accept="application/json"):
    token = base64.b64encode(f"{OPENCODE_USERNAME}:{PASSWORD}".encode()).decode()
    return {
        "Authorization": f"Basic {token}",
        "x-opencode-directory": str(ROOTS_WORKSPACE),
        "Accept": accept,
    }

def data_list(payload):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("data"), list):
        return payload["data"]
    return []

def probe_opencode_api(base_url, timeout=15):
    for endpoint, must_have_items in (
        ("/api/agent", True),
        ("/api/provider", True),
        ("/api/model", True),
        ("/api/session", False),
    ):
        try:
            req = urllib.request.Request(base_url.rstrip("/") + endpoint, headers=opencode_headers())
            with urllib.request.urlopen(req, timeout=timeout) as response:
                payload = json.loads(response.read().decode() or "{}")
                if response.status != 200:
                    return False, f"{endpoint} HTTP {response.status}"
                if must_have_items and not data_list(payload):
                    return False, f"{endpoint} vazio"
        except Exception as exc:
            return False, f"{endpoint}: {exc}"
    return True, None

def probe_opencode_sse(base_url, timeout=12):
    try:
        req = urllib.request.Request(
            base_url.rstrip("/") + "/api/event",
            headers=opencode_headers("text/event-stream"),
        )
        with urllib.request.urlopen(req, timeout=timeout) as response:
            ctype = (response.headers.get("Content-Type") or "").lower()
            if response.status != 200 or not ctype.startswith("text/event-stream"):
                return False, f"HTTP {response.status} content-type={ctype!r}"
            for _ in range(80):
                line = response.readline().decode(errors="replace").strip()
                if line.startswith("data:") or line.startswith("event:"):
                    return True, None
            return False, "sem primeiro frame SSE"
    except Exception as exc:
        return False, str(exc)

def show_iframe(port, label, height, path="/"):
    try:
        from google.colab import output
        print(f"  ↪ {label}: fallback embutido")
        output.serve_kernel_port_as_iframe(port, path=path, height=height)
    except Exception as e:
        print(f"  ⚠️ {label}: fallback indisponível: {e}")

print("🔄 Verificando links externos…")
IDE_URL = saved_tunnel("code-server") if listening(8080) else None
TTYD_URL = saved_tunnel("ttyd") if listening(7681) else None

if ((listening(8080) and not IDE_URL) or (listening(7681) and not TTYD_URL)) and ensure_cloudflared():
    if listening(8080) and not IDE_URL:
        IDE_URL = start_quick_tunnel(8080, "code-server")
    if listening(7681) and not TTYD_URL:
        TTYD_URL = start_quick_tunnel(7681, "ttyd")

OPENCODE_PROJECT_SLUG = base64.urlsafe_b64encode(str(ROOTS_WORKSPACE).encode()).decode().rstrip("=")
OPENCODE_BASE_URL = saved_opencode_tunnel() if listening(4096) else None
OPENCODE_PROJECT_URL = None
if listening(4096):
    if not OPENCODE_BASE_URL:
        OPENCODE_BASE_URL = start_opencode_tunnel(4096)
    if OPENCODE_BASE_URL:
        api_ok, api_error = probe_opencode_api(OPENCODE_BASE_URL)
        sse_ok, sse_error = probe_opencode_sse(OPENCODE_BASE_URL)
        if api_ok and sse_ok:
            OPENCODE_PROJECT_URL = f"{OPENCODE_BASE_URL}/{OPENCODE_PROJECT_SLUG}"
            (ROOTS_STATE / "opencode-project.url").write_text(OPENCODE_PROJECT_URL)
        else:
            print(f"  ⚠️ OpenCode tunnel inválido: API={api_error or 'ok'}; SSE={sse_error or 'ok'}")
            stop_pid_file(ROOTS_STATE / "opencode-tunnel.pid")
            OPENCODE_BASE_URL = None

print("=" * 62)
print("  🌳 Seus links atuais")
print("=" * 62)
if IDE_URL:
    print(f"  🖥️  IDE:\n      {IDE_URL}\n      senha: {PASSWORD}")
elif listening(8080):
    print("  🖥️  IDE: link externo indisponível")
    show_iframe(8080, "IDE", "720")
if TTYD_URL:
    print(f"  💻  Terminal:\n      {TTYD_URL}\n      usuário: {USERNAME}  senha: {PASSWORD}")
elif listening(7681):
    print("  💻  Terminal: link externo indisponível")
    show_iframe(7681, "Terminal", "360")
if OPENCODE_PROJECT_URL:
    print(f"  🤖 OpenCode:\n      {OPENCODE_PROJECT_URL}\n      usuário: {OPENCODE_USERNAME}  senha: {PASSWORD}")
elif listening(4096):
    print("  🤖 OpenCode: link externo SSE indisponível")
    show_iframe(4096, "OpenCode", "720", "/" + OPENCODE_PROJECT_SLUG)
if not any((IDE_URL, TTYD_URL, OPENCODE_PROJECT_URL, listening(8080), listening(7681), listening(4096))):
    print("  ⚠️  Os serviços não estão no ar. Se a VM foi reciclada, rode ▶️ INICIAR TUDO.")
print(f"\n  🔑 Senha: {ROOTS_STATE / 'password'}")
"""

# ─────────────────────────────────────────────────────────────────────
# CELL 7 — Status
# ─────────────────────────────────────────────────────────────────────
C7 = r"""#@title 📊 STATUS (serviços + daemon + heartbeat){display-mode:"form"}
import os, time, subprocess, socket
from pathlib import Path

ROOTS_HOME  = Path(os.environ.get("ROOTS_HOME", str(Path.home() / ".colab-roots")))
ROOTS_STATE = ROOTS_HOME / "state"

def listening(port):
    try:
        s = socket.create_connection(("127.0.0.1", port), 0.5); s.close(); return True
    except OSError:
        return False

print("═" * 34)
print("  🌳 Colab Roots — Status")
print("═" * 34)
for name, port in (("code-server (IDE)", 8080), ("ttyd (Terminal)", 7681), ("OpenCode Web", 4096)):
    on = listening(port)
    print(f"  {'✅' if on else '❌'} {name:20s} {'rodando' if on else 'parado'}")

pf = ROOTS_HOME / "daemon.pid"
daemon = False
if pf.exists():
    try:
        os.kill(int(pf.read_text().strip()), 0); daemon = True
    except (OSError, ValueError):
        pass
print(f"  {'✅' if daemon else '❌'} daemon                {'rodando' if daemon else 'parado'}")

hb = ROOTS_STATE / "heartbeat"
if hb.exists():
    last = hb.read_text().strip()
    try:
        t = time.mktime(time.strptime(last, "%Y-%m-%dT%H:%M:%S"))
        print(f"  💓 heartbeat:           {int(time.time() - t)}s atrás")
    except ValueError:
        print(f"  💓 heartbeat:           {last}")
else:
    print("  💓 heartbeat:           ainda nenhum")

try:
    cpu = subprocess.run(["nproc"], capture_output=True, text=True).stdout.strip()
    mem = subprocess.run(["free", "-h"], capture_output=True, text=True).stdout.splitlines()[1].split()
    print(f"  ⚙️  CPU: {cpu} núcleos · RAM: {mem[1]} total / {mem[2]} usada")
except Exception:
    pass
"""

# ─────────────────────────────────────────────────────────────────────
# CELL 8 — Public URL (Cloudflare) intro + cell
# ─────────────────────────────────────────────────────────────────────
C8 = r"""## 🌐 Recriar URLs públicas (Cloudflare) — opcional

O START já cria URLs públicas temporárias para IDE, Terminal e OpenCode.
Use esta célula apenas se quiser abrir túneis extras/novos sem reiniciar os serviços.
"""

C9 = r"""#@title 🌐 URL PÚBLICA via Cloudflare{display-mode:"form"}
import os, re, subprocess, socket
from pathlib import Path

ROOTS_HOME  = Path(os.environ.get("ROOTS_HOME", str(Path.home() / ".colab-roots")))
ROOTS_STATE = ROOTS_HOME / "state"
PASSWORD = (ROOTS_STATE / "password").read_text().strip() if (ROOTS_STATE / "password").exists() else ""

import shutil
if shutil.which("cloudflared") is None:
    print("📦 Instalando cloudflared…")
    subprocess.run("wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -O /usr/local/bin/cloudflared && chmod +x /usr/local/bin/cloudflared", shell=True)

def listening(port):
    try:
        s = socket.create_connection(("127.0.0.1", port), 0.5); s.close(); return True
    except OSError:
        return False

def start_tunnel(port):
    proc = subprocess.Popen(["cloudflared", "tunnel", "--url", f"http://127.0.0.1:{port}", "--no-autoupdate"],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    url = None
    try:
        for line in proc.stdout:
            m = re.search(r"(https://[a-zA-Z0-9-]+\.trycloudflare\.com)", line)
            if m:
                url = m.group(1); break
    except Exception:
        pass
    return proc, url

print("🌐 Subindo túneis públicos…")
for name, port in (("IDE", 8080), ("Terminal", 7681)):
    if not listening(port):
        print(f"   ⏭️  {name} não está rodando")
        continue
    proc, url = start_tunnel(port)
    if url:
        print(f"  🌐 {name}: {url}")
        if name == "IDE":
            print(f"     senha: {PASSWORD}")
        else:
            print(f"     usuário: roots  senha: {PASSWORD}")
    else:
        print(f"  ⚠️  {name}: não consegui capturar a URL")

print("\n⚠️  URLs públicas somem quando você rodar 🛑 PARAR ou a VM morrer.")
print("    Para derrubar só os túneis: pkill -f '[c]loudflared'")
"""

# ─────────────────────────────────────────────────────────────────────
# CELL 10 — Stop
# ─────────────────────────────────────────────────────────────────────
C10 = r"""#@title 🛑 PARAR (desliga serviços, daemon e tmux){display-mode:"form"}
import os, subprocess, signal, time
from pathlib import Path

ROOTS_HOME  = Path(os.environ.get("ROOTS_HOME", str(Path.home() / ".colab-roots")))
ROOTS_STATE = ROOTS_HOME / "state"
DAEMON_PY   = ROOTS_HOME / "src" / "daemon.py"

print("🛑 Desligando Colab Roots…")

def pkill(pattern):
    subprocess.run(["pkill", "-f", pattern], capture_output=True)

# 1) Daemon primeiro (down gracioso já derruba os serviços)
if DAEMON_PY.exists():
    subprocess.run(["python3", str(DAEMON_PY), "down"], capture_output=True, timeout=15)
    print("   ✅ daemon desligado (via CLI)")
pf = ROOTS_HOME / "daemon.pid"
if pf.exists():
    try:
        os.kill(int(pf.read_text().strip()), signal.SIGTERM)
    except (OSError, ValueError):
        pass
    try:
        pf.unlink()
    except OSError:
        pass

# 2) Sobras (garantia)
pkill("[c]ode-server")
pkill("[t]tyd")
pkill("[o]pencode.*serve")
try:
    tunnel_pid = int((ROOTS_STATE / "opencode-tunnel.pid").read_text().strip())
    os.killpg(os.getpgid(tunnel_pid), signal.SIGTERM)
except (OSError, ValueError, ProcessLookupError):
    pass
(ROOTS_STATE / "opencode-tunnel.pid").unlink(missing_ok=True)
pkill("[n]okey@localhost.run")
pkill("[c]loudflared")

# 3) tmux
subprocess.run(["tmux", "kill-session", "-t", "roots"], capture_output=True)

time.sleep(1)
print("✅ Tudo parado.")
print("   Agora é só sair do runtime: Runtime ▸ Disconnect & delete runtime")
"""

# ─────────────────────────────────────────────────────────────────────
# CELL 11 — Troubleshooting
# ─────────────────────────────────────────────────────────────────────
C11 = r"""## 🧯 Problemas comuns

### A célula de START demora / "travou" no passo 1
Instalação de pacotes via `apt` pode demorar 1–2 min sem imprimir nada. Espere.
Se passar de 10 min no mesmo passo, o Colab pode ter caído: rode a célula de novo.

### O Drive pede autorização toda vez
Normal na primeira vez. Se recusar, o notebook **continua sem backup** — tudo o resto funciona.
Para reconectar o Drive depois: `from google.colab import drive; drive.mount('/content/drive', force_remount=True)`

### Links públicos não abrem depois de um tempo
Os Quick Tunnels são temporários e o runtime também pode ter desligado.
Verifique com 📊 STATUS e rode 🔄 RE-LINK; se os serviços estiverem parados, rode ▶️ INICIAR TUDO.

### OpenCode pede login
Use **usuário `opencode`** e a mesma senha impressa pelo START. O link gerado já contém
a rota do projeto `/content/workspace`; RE-LINK também valida API + SSE antes de exibi-lo.

### OpenCode abre, mas models/agents/sessions ficam vazios
Não use um URL Cloudflare manual para a porta 4096. O OpenCode precisa do contexto do
workspace e de SSE. Rode 🔄 **RE-LINK** para recriar o túnel compatível e a rota do projeto.

### "Address already in use" / portas ocupadas
A célula de START é idempotente: ela limpa processos antigos antes de subir os serviços.
Se mesmo assim acontecer, rode 🛑 PARAR e depois ▶️ INICIAR TUDO.

### Quero rodar de novo com tudo zerado
Runtime ▸ **Factory reset runtime** (apaga a VM inteira) e rode ▶️ INICIAR TUDO de novo.

### CLI dentro do terminal (ttyd/IDE)
```bash
export PATH="$HOME/.colab-roots/bin:$PATH"
roots status     # status dos serviços
roots doctor     # health check
roots logs code-server   # logs do serviço
roots password   # mostra a senha (mascarada)
roots down       # desliga tudo
```
"""


def main():
    cells = [
        markdown(C0),
        markdown(C1),
        code(C2),
        markdown(C3),
        code(C4),
        markdown(C5),
        code(C6),
        code(C7),
        markdown(C8),
        code(C9),
        code(C10),
        markdown(C11),
    ]
    notebook = {
        "nbformat": 4,
        "nbformat_minor": 0,
        "metadata": {
            "colab": {"provenance": [], "gpuType": None},
            "kernelspec": {"name": "python3", "display_name": "Python 3"},
            "language_info": {"name": "python"},
            "accelerator": "None",
        },
        "cells": cells,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(notebook, f, indent=1, ensure_ascii=False)
        f.write("\n")
    print(f"✅ Notebook gerado: {OUT} ({len(cells)} células)")

    # Validação de sintaxe de todas as células de código
    errors = 0
    for i, c in enumerate(cells):
        if c["cell_type"] != "code":
            continue
        code_str = "".join(c["source"])
        try:
            compile(code_str, f"<cell {i}>", "exec")
        except SyntaxError as e:
            errors += 1
            print(f"  ❌ célula {i}: SyntaxError — {e}")
    if errors:
        print(f"❌ {errors} célula(s) com erro de sintaxe")
        sys.exit(1)
    print("✅ Todas as células de código compilam")


if __name__ == "__main__":
    main()