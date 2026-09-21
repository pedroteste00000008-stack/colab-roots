# Security Policy — Colab Roots v2

## Modelo de ameaça

Colab Roots roda numa VM efêmera compartilhada (Colab). Atacante potencial:
qualquer processo local, leitor de logs, ou quem interceptar output do notebook.
Fora da VM, só há acesso via túneis autenticados.

## Garantias implementadas

| # | Vetor | Mitigação | Onde |
|---|-------|-----------|------|
| 1 | Senha em `ps aux` | Nunca logada; `_sanitize_command()` mascara `-c`/`--password-file` | `src/daemon.py:424` |
| 2 | Socket Unix world-readable | `chmod 0600` no bind | `src/daemon.py:621` |
| 3 | Arquivo de senha legível | `chmod 0600` em `password` e `code-server-pw` | `src/daemon.py:253`, notebook cell 4 |
| 4 | Dois daemons concorrentes | `fcntl.flock(LOCK_EX\|LOCK_NB)` em `daemon.lock` | `src/daemon.py:76` |
| 5 | Path traversal em `restart <svc>` | Whitelist contra `all_names()` + sanitização `[a-zA-Z0-9_-]{1,32}` | `src/daemon.py:699` |
| 6 | Comando oversized / binário no socket | Rejeita `len > 1024`, decode `errors="replace"`, timeout 5s | `src/daemon.py:_handle_client` |
| 7 | Tunnel name injection | Strip para `[a-zA-Z0-9_-]`, max 64 chars | `src/daemon.py:_validate_config` |
| 8 | Restart loop infinito | `MAX_RESTARTS=5` + backoff exponencial `2^min(n,4)` + reset após 5min estável | `src/daemon.py:513` |
| 9 | Credencial indo pro Drive | `sensitive = {"password","code-server-pw"}` excluídos do sync | `src/daemon.py:585`, notebook cell 12 |
| 10 | Estado corrompido | Write atômico via `.tmp` + `replace()` | `src/daemon.py:885` |
| 11 | Log gigante (DoS disco) | `RotatingFileHandler` 5MB × 3 | `src/daemon.py:_setup_logging` |
| 12 | Processo zumbi no stop | `killpg(SIGTERM)` → espera 5s → `killpg(SIGKILL)` | `src/daemon.py:380` |
| 13 | Senha fraca / previsível | `secrets.choice` 20 chars (config) + `token_urlsafe` fallback | notebook cell 2 |
| 14 | `password` em output | `roots password` mostra máscara `abc***xyz` | `src/daemon.py:812` |

## O que NÃO é garantido

- **ttyd exige `-c user:pass` em argv.** Quem tem acesso à VM vê via `/proc`. Mitigação parcial: bind em `127.0.0.1` + túnel autenticado na frente. Alternativa futura: migrar para autenticação via reverse-proxy com header.
- **12h / reclaim do Colab.** Nenhum keep-alive impede. Persistência é via Drive, não via processo.
- **Segredo no output do notebook.** A célula de bootstrap imprime a senha uma vez para o dono. Não compartilhe o notebook com output.

## Como reportar

Abra issue com prefixo `[SECURITY]` sem incluir senhas, URLs de túnel ou conteúdo de `/state`. Logs devem passar por `roots logs` (já sanitizados).
