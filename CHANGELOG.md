# Changelog

Todas as mudanças notáveis do SARCC são documentadas neste arquivo.

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/).
Versionamento segue [Semantic Versioning](https://semver.org/lang/pt-BR/).

---
## 2.7.0 - 2026/10/10

### Adicionado
- **Cache de credenciais em memória por sessão**: popup de senha aparece
  apenas 1× por execução do SARCC. Múltiplos scripts reutilizam o cache.
- **Botão "🔒 Esquecer senha" na sidebar** para limpar o cache manualmente.
- **Scripts PS1 com detecção runtime de modo**: `conta-máquina` (SYSTEM,
  via tarefa agendada) vs `credencial explícita` (SARCC ativo).
- **Agendador sem credenciais**: tarefas rodam como SYSTEM e usam
  conta-máquina (`DOMINIO\NOMEDAMÁQUINA$`) via Kerberos — senha nunca é
  gravada em `.ps1` no alvo.
- **Deploy GLPI Agent**: instala/atualiza GLPI Agent via MSI no compartilhamento
  de rede, aplica config OAuth no registro e força inventário.
- **Limpeza de cache dos navegadores**: remove cache de Chrome, Edge e Firefox
  para todos os perfis de usuário. Não afeta cookies/senhas/favoritos.

### Modificado
- **Credenciais migradas para Base64**: elimina problemas com caracteres
  especiais em senhas (`$`, `"`, `'`, `` ` ``, `\n`). O `TaskWorker` codifica
  em Base64; os scripts decodificam em runtime.

### Corrigido
- **`prepare_new_script`** agora usa `setPlainText("")` no CodeEditorWidget.
- **`app_window.py`**: variáveis `_max_threads` e `queue_manager` declaradas
  corretamente no `__init__`.
- **Filtros de senha com `\n` residual**: `senha.strip()` em `_get_credentials`.

## [2.6.0] - 2026/10/10

### Adicionado
- **Logging central rotativo** (`core/logger.py`): log em `data/logs/sarcc.log`
  (10 MB × 5 backups) + console em WARNING+. Auditoria completa de sessão com
  startup/shutdown, ações e traceback de erros.
- **`BaseView`** (`gui/views/base_view.py`): classe base para todas as views com
  `_force_uppercase` centralizado — elimina ~200 linhas duplicadas.
- **Pool de threads unificado**: `MainWindow.queue_manager` compartilhado por
  Dashboard, Execução, Agendador e Software. Reduz de ~25 threads ociosas para
  12 threads reais. Configurável via `SARCC_MAX_THREADS` (env).
- **Inventário Winget com IDs reais**: parser robusto com `--source winget`,
  detecção de "já instalado" como sucesso, coluna "Nova Versão" populada
  automaticamente, filtro **"Só com atualização"**.
- **Reboot Pendente no Dashboard**: detecção de WU / CBS / PendingFileRename
  com cores (verde OK / laranja pendente).
- **Winget no Dashboard**: versão do App Installer com fallback em 4 camadas.
- **Últimos 5 Eventos Críticos** na aba Logs do Gerenciador: consulta System +
  Application, com dialog de detalhes em duplo clique.
- **Atalhos de diagnóstico de rede** no ShellView: 17 atalhos prontos (ping,
  tracert, nslookup, netstat, ipconfig, arp, Get-NetRoute, etc.) com encoding
  correto para comandos nativos.
- **Shutdown gracioso** do `TaskQueueManager` ao fechar o app.

### Modificado
- **Credenciais unificadas**: `[[ADMIN_USER]]`, `[[ADMIN_PASS]]`, `[[VNC_PASS]]`
  como padrão único. Injeção centralizada no `TaskWorker` via dict `credentials`.
  Marcador `[REQUIRE_CREDENTIALS]` obsoleto.
- **Scripts migrados**: Zabbix, DesktopInfo, UltraVNC e deploy offline agora
  usam `New-PSDrive -Credential` (sem `net use` com senha em linha de comando).
- **`execute_action`** (Software): 4 bugs de formatação corrigidos, `--source
  winget` em todas as chamadas, `--force` opt-in via checkbox.

### Corrigido
- **Inventário Winget**: caía silenciosamente no fallback do Registro por causa
  de BOM no arquivo temporário e `IndexOf` case-sensitive.
- **Parser Winget search**: `text=True` corrompia UTF-8 → agora `_smart_decode`.
- **Deploy offline**: erro 1603 por acesso SMB durante MSI → cópia local antes
  de executar.
- **Duplicação de logs**: cada execução gravava 2 entradas no BD.
- **`prepare_new_script`**: `CodeEditorWidget` não tinha `.clear()`.
- **SyntaxWarnings**: 3 escapes inválidos eliminados.

### Segurança
- Senhas **não aparecem mais** em `Win32_Process`, Event 4688 ou `Get-Process`
  (era o caso do `net use` original).
- Credenciais trafegam apenas em memória, jamais em arquivo ou banco.

---

## 2.0.0 - 2026

Versão inicial com:
- Dashboard de telemetria (CPU, RAM, Disco, Uptime, Antivírus, Agentes).
- Terminal Interativo Remoto (PowerShell).
- Gerenciador de Processos, Serviços e Eventos.
- Central de Execução Remota em lote.
- Gestão de Softwares (Winget/Chocolatey) e Drivers.
- Agendador de Tarefas Remotas.
- Gestor de Scripts (editor com syntax highlighting).
- Histórico e auditoria em SQLite.
- Wake-on-LAN, RDP, VNC, AnyDesk, Assistência Rápida.
- Motor de temas claro/escuro dinâmico.