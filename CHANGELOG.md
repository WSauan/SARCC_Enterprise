# Changelog

Todas as mudanças notáveis do SARCC são documentadas neste arquivo.

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/).
Versionamento segue [Semantic Versioning](https://semver.org/lang/pt-BR/).

---
## [2.8.0] - 2026-10-26

### Adicionado
- **Reestruturação Enterprise (Fase 0):** Código massivamente limpo (-2000 linhas). Scripts migrados de strings Python (inline) para ficheiros `.ps1` isolados na pasta `core/scripts/`. 
- **Componentização da UI:** Criação das pastas `gui/widgets/` (com `code_editor.py`) e `gui/dialogs/` (com `dialogs.py`), separando a lógica da janela principal.
- **Bypass de AppX (Winget):** Implementado mecanismo para o Winget correr no contexto `SYSTEM` (Sessão 0 / WinRM) contornando o erro de bloqueio da Microsoft Store. O script agora localiza e executa o binário real em `C:\Program Files\WindowsApps` embutido num `cmd.exe`.
- **Desinstalação de Força Bruta Expandida:** Se o WMI e o Winget falharem, o SARCC varre automaticamente o `Program Files` e `Program Files (x86)` à procura de desinstaladores silenciosos (ex: VLC media player).

### Modificado
- **Unidades Mapeadas (New-PSDrive):** Removida a flag `-Persist` das execuções remotas. O Windows não suporta drives persistentes em sessões não-interativas (WinRM), o que causava o erro de "Acesso Negado" no Deploy de Softwares.
- **Mecanismo de Atualização do Winget:** Omitida a flag `--source reset` em tarefas remotas para evitar o erro `0x8a15000f` causado pela ausência de perfil de utilizador na conta SYSTEM.

### Corrigido
- **Inventário "Windows Registry":** Removida a flag `--width 120` do Winget que causava falhas silenciosas na listagem, obrigando o SARCC a usar o fallback do Registo cegamente. Agora, o Winget lista todos os pacotes nativos corretamente.
- **Erro de Parsing de Colunas (Winget):** A coluna "Nova Versão" na aba de inventário passou a isolar rigorosamente apenas o número da versão (ex: `26.05`), eliminando o bug visual que colava a origem (`26.05 winget`).
- **Exceção de Matriz Nula (Drivers):** Corrigido o erro `Não é possível indexar em uma matriz nula` ao iterar ficheiros `.inf` de drivers que não possuíam o atributo de Classe (`Class=`).
- **Nomes de Templates da UI:** Ajustada a ponte entre Python e PowerShell em `software_view.py` (`install.ps1` -> `software_install.ps1`, `action.ps1` -> `software_action.ps1`).

---

## [2.7.0] - 2026-10-10

### Adicionado
- **Cache de credenciais em memória por sessão**: popup de senha aparece apenas 1× por execução do SARCC. Múltiplos scripts reutilizam o cache.
- **Botão "🔒 Esquecer senha" na sidebar** para limpar o cache manualmente.
- **Scripts PS1 com detecção runtime de modo**: `conta-máquina` (SYSTEM, via tarefa agendada) vs `credencial explícita` (SARCC ativo).
- **Agendador sem credenciais**: tarefas rodam como SYSTEM e usam conta-máquina (`DOMINIO\NOMEDAMÁQUINA$`) via Kerberos — senha nunca é gravada em `.ps1` no alvo.
- **Deploy GLPI Agent**: instala/atualiza GLPI Agent via MSI no compartilhamento de rede, aplica config OAuth no registro e força inventário.
- **Limpeza de cache dos navegadores**: remove cache de Chrome, Edge e Firefox para todos os perfis de usuário. Não afeta cookies/senhas/favoritos.

### Modificado
- **Credenciais migradas para Base64**: elimina problemas com caracteres especiais em senhas (`$`, `"`, `'`, `` ` ``, `\n`). O `TaskWorker` codifica em Base64; os scripts decodificam em runtime.

### Corrigido
- **`prepare_new_script`** agora usa `setPlainText("")` no CodeEditorWidget.
- **`app_window.py`**: variáveis `_max_threads` e `queue_manager` declaradas corretamente no `__init__`.
- **Filtros de senha com `\n` residual**: `senha.strip()` em `_get_credentials`.

---

## [2.6.0] - 2026-10-10

### Adicionado
- **Logging central rotativo** (`core/logger.py`): log em `data/logs/sarcc.log`.
- **`BaseView`** (`gui/views/base_view.py`): classe base para todas as views.
- **Pool de threads unificado**: `MainWindow.queue_manager` compartilhado.
- **Reboot Pendente no Dashboard**: detecção de WU / CBS / PendingFileRename.
- **Atalhos de diagnóstico de rede** no ShellView: 17 atalhos prontos.

### Modificado
- **Credenciais unificadas**: `[[ADMIN_USER]]`, `[[ADMIN_PASS]]`, `[[VNC_PASS]]`.
- **Scripts migrados**: Zabbix, DesktopInfo e UltraVNC usam `New-PSDrive -Credential`.

### Corrigido
- **Deploy offline**: erro 1603 por acesso SMB durante MSI corrigido via cópia local.
- **Duplicação de logs**: corrigida gravação dupla no BD.

---

## 2.0.0 - 2026-08

Versão inicial (Dashboard de telemetria, Terminal Interativo, Gerenciador de Processos, Execução Remota em lote, Wake-on-LAN e Motor de temas).