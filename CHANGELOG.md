# Histórico de Versões (Changelog) — SARCC Enterprise

## [v3.2.0] — 2026-11-27
### 🎨 Sprint de UI/UX, Refinamento de Gráficos e Atalhos

* **Atalhos de Teclado (`ScriptsView`):** O Gestor de Scripts agora suporta atalhos nativos: `Ctrl+S` (Salvar), `Ctrl+O` (Importar) e `Delete` (Excluir).
* **Exclusão em Lote (`ScriptsView`):** Agora é possível selecionar múltiplos scripts (usando `Ctrl` ou `Shift`) e excluir todos de uma vez.
* **Seleção Múltipla no Histórico (`HistoryView`):** Implementado suporte nativo a `Shift+Click` e `Ctrl+Click` nos checkboxes, permitindo selecionar dezenas de logs instantaneamente.
* **Paginação no Histórico (`HistoryView`):** Novo seletor para exibir os últimos 10, 20, 50, 100 ou todos os registros. Otimização para eliminar as "travadas" ao abrir a tela.
* **Filtro por Alvo com Autocomplete (`DashboardBIView`):** O Painel BI agora permite filtrar as métricas por uma máquina específica, sugerindo os hosts que já existem no banco.
* **Legendas e Refinamento de Gráficos (`bi_charts.py`):** O gráfico de Donut agora possui legenda vertical e o Gráfico de Barras exibe os números no final das barras com contraste adequado.
* **Padronização Global (`app_window.py`):** Aplicado o estilo `Segoe UI` via CSS para todos os componentes da aplicação.
* **Padronização de Labels (`Views`):** Todos os campos de entrada de hostname foram renomeados para **"Computador Alvo:"**, mantendo a consistência visual.

## [v3.1.0] — 2026-11-25
### 🚀 Painel de Indicadores, Sincronização NTP, BitLocker e Reset de GPO

* **Painel de Indicadores (BI) (`DashboardBIView`):** Nova tela analítica com KPIs em tempo real (Taxa de Sucesso, Total de Execuções, Máquinas Atendidas) e gráficos nativos (Donut de Status e Top 5 Scripts) construídos via `QPainter`.
* **Sincronização de Horário (`SystemManagerView`):** Nova aba "Tempo e NTP" com opção de Sincronização Simples (`w32tm /resync`) e Reset Completo do serviço com reconfiguração para o domínio (`domhier`).
* **Consulta de BitLocker (`SystemManagerView`):** Nova aba "BitLocker" que consulta o status dos volumes criptografados e extrai a chave de recuperação de 48 dígitos.
* **Forçar Reinstalação de GPO (`SystemManagerView`):** Novo botão "Reset GPO de Impressoras" que remove mapeamentos antigos e força a reaplicação da política (`gpupdate /force`).
* **Arquitetura de Timeout em 3 Camadas (`RemoteConnectionManager`):** Timeout configurável que lê diretivas no próprio script (`# @timeout:`), sobrescreve o tempo da categoria e previne o travamento da fila.
* **Integração Segura DPAPI (`GlpiConfigDialog`):** Credenciais OAuth do GLPI salvas criptografadas no cofre do Windows.
* **Normalização de Status (`Enums`):** Criação do `core/enums.py` para padronizar os status de execução (Sucesso, Alerta, Erro).

## [v3.0.0] — 2026-11-25
### 🛡️ Hardening de Segurança, Arquitetura de Timeout e Qualidade de Código

**Segurança (R01 a R05)**
* **R01 (Remoção de Segredos):** Removido o *OAuth Client Secret* do GLPI hardcoded dos scripts. As credenciais agora são lidas via DPAPI (`CredentialStore`) ou variáveis de ambiente.
* **R02 (Prevenção de Vazamento):** Removido o comando `net use` com senha em texto plano (CWE-214) de todos os scripts. O mapeamento de rede agora usa exclusivamente `New-PSDrive` com `PSCredential`.
* **R03 (Integridade de Código):** Implementado manifesto `SHA256` (`manifest.json`). O `ps_loader` agora bloqueia a execução de scripts PowerShell que forem adulterados no disco.
* **R04 (Supply Chain Security):** Removido o fallback do Chocolatey via `Invoke-Expression`. A auto-instalação agora usa o pacote oficial baixado via Winget.
* **R05 (Zero Hardcode):** Removidos IPs do Zabbix, caminhos de compartilhamento SMB e caminhos de disco fixos. Todos foram centralizados no `config.py` e injetados dinamicamente nos scripts.

**Resiliência (R06)**
* **R06 (Timeout Inteligente):** Implementado sistema de timeout em 3 camadas (Diretiva `# @timeout` no script, categoria do script e padrão de 300s) para evitar que scripts pesados travem os workers da interface gráfica.

**Qualidade e Arquitetura (R07 a R10)**
* **R07 (Parsing Robusto):** Substituída a leitura de texto/colunas do Winget (que quebrava em outros idiomas) pelo processamento nativo de JSON (`--output json`).
* **R08 (Desacoplamento):** A função `fix_mojibake` foi movida da camada de GUI para o `core/text_utils.py`, eliminando o acoplamento entre as views.
* **R09 (Performance DB):** Otimização do `DatabaseManager` com *Thread-Local Connection Pooling*, reduzindo a abertura/fechamento de conexões SQLite em execuções massivas.
* **R10 (Quality Gate):** Adicionado o linter `ruff` e o arquivo `pyproject.toml`. O pipeline de build e a suíte de testes agora falham se houver código sujo (imports não usados, espaços em branco, etc).

**Build**
* O `build_release.ps1` agora gera automaticamente o `manifest.json` antes de executar a bateria de testes e compilar o executável.

## [v2.12.0] — 2026-11-19
### 🚀 Laudo de Garantia, Exportação CSV, Descoberta de Alvos e Automação de Build
* **Laudo Técnico de Garantia em 1 Clique (`SystemManagerView`):** Adicionado botão **📄 Laudo Garantia (.txt)** na aba **Logs de Eventos** que consulta hardware, serial/BIOS, uptime e status S.M.A.R.T. e consolida os eventos exibidos/filtrados em relatório `.txt`.
* **Exportação CSV em Serviços e Impressoras (`SystemManagerView`):** Adicionados botões **📄 Exportar CSV** nas abas **Serviços** e **Impressoras & Spooler** respeitando filtros ativos e codificação `UTF-8 com BOM` (`;`).
* **Descoberta de Alvos por Sub-rede ou Active Directory (`ExecutionView`):** Adicionado botão **🔎 Descobrir Alvos** com suporte a varredura de faixa/CIDR e consulta ao Active Directory (`Get-ADComputer` / `dsquery`).
* **Build Automatizada por Versão (`build_release.ps1`):** Leitura automática de `__version__` em `core/version.py` e validação da presença da versão no `CHANGELOG.md` antes da compilação.
* **Expansão da Suíte de Testes (`tests/test_v2120_features.py`):** Cobertura automatizada para geração de laudo de garantia, exportação CSV, expansão de sub-redes e sondagem de conectividade (`probe_host`).

## [v2.11.0] — 2026-11-19
### 🚀 Diagnóstico de Reinicializações, Filtros de Data/Hora e Melhorias Operacionais
* **Filtro de Reinicializações Inesperadas e Intervalo de Data/Hora (`SystemManagerView` & `get_events.ps1`):** Adicionada opção de filtro para eventos de reinicialização (`41 6008 1074 6006 6009 1001`) e seleção de período (`Últimas 2h`, `Últimas 12h`, `Últimas 24h`, `Últimos 7 dias`, `Últimos 30 dias` e `Intervalo de data/hora (De / Até)`).
* **Filtros de Intervalo de Data/Hora (`HistoryView` & `SchedulerView`):** Adicionada seleção de intervalo (`De / Até` com calendário e horário `HH:mm`) e janelas de tempo recentes na auditoria de logs e suporte a intervalo de datas no agendador.
* **Busca de Impressoras via GPO (`SystemManagerView`):** Adicionado botão **🔎 Buscar Impressoras** na aba **Impressoras & Spooler** para forçar atualização de política de computador (`gpupdate /target:computer /force`) e recarregar a lista de impressoras.
* **Status Real de Sessões e Logoff Seletivo (`DashboardView` & `telemetry.ps1`):** Identificação de sessões **Ativo**, **Desconectado** e **Em 2º Plano** via `quser`, colunas redimensionáveis, logoff de usuário específico e edição remota da descrição/local da máquina.
* **Terminal Interativo e Execução em Lote (`ShellView`, `ExecutionView`, `run_command.ps1` & `RemoteConnectionManager`):** Correção do erro de `OutputEncoding`, conversão `CP850` para `UTF-8` em comandos legados, atalho de reset de rede, execução local via arquivo temporário evitando `WinError 206` e filtro rápido de alvos online.

## [v2.10.0] — 2026-11-13
### 🚀 Telemetria Física S.M.A.R.T., Reparo de Agentes e Gestão de Impressoras
* **Inventário Físico e Saúde S.M.A.R.T. (`DashboardView`):** Leitura em tempo real da **Descrição do Computador** (local/setor), **Fabricante e Modelo** do equipamento, **Serial / Service Tag da BIOS**, **Tipo de Mídia** (`NVMe SSD`, `SSD` ou `HDD`), estado físico **S.M.A.R.T.** e **Topologia de Memória RAM** (slots ocupados/totais e frequência em MHz).
* **Reparo e Deploy Automatizado de Agentes (`DashboardView`):** Novo seletor de ação rápida para reparar, reconfigurar ou instalar silenciosamente **Zabbix Agent 2** (com leitura dinâmica do IP `<IP_DO_SERVIDOR_ZABBIX>`, reconstrução de contadores `PerfMon` e *Auto-Healing*), **UltraVNC Server** (modo *Stealth* com injeção dupla de `ultravnc.ini` e `MSLogonACL`), **GLPI Agent** (com sincronização forçada `--force`) e **Desktop Info** (com lançamento imediato na sessão interativa do usuário).
* **Gestão Remota de Impressoras e Spooler (`SystemManagerView`):** Nova aba **🖨️ Impressoras & Spooler** com listagem de impressoras locais e de rede (Nome, Porta/IP, Driver, Trabalhos na Fila e Status), limpeza individual de fila, remoção de impressoras e botão **🧹 Destravar Spooler (Limpar Tudo)** que expurga arquivos `.SHD`/`.SPL` órfãos em `C:\Windows\System32\spool\PRINTERS`.
* **Coleta Inteligente de Drivers por Versão (`drivers_collect.ps1`):** Comparação real da diretiva `DriverVer` dos arquivos `.inf` locais contra o repositório SMB antes de transferir arquivos pela rede.
* **Arquitetura em Camadas (`domain` & `infrastructure`):** Desacoplamento completo das operações SQLite e regras de negócio através de `ScriptRepository`, `ExecutionRepository`, `ScriptService` e `AuditService`.
* **Suíte com 56 Testes Unitários (`pytest`):** Cobertura 1-para-1 expandida para todas as views, serviços de domínio, repositórios, editor de código e templates PowerShell.

## [v2.9.1] — 2026-11-13
### 🛡️ Blindagem de Núcleo (Core) e Interface (Fase 2)
* **Decodificação UTF-8 Nativa (`RemoteConnectionManager`):** Correção definitiva da leitura de acentuação em retornos do PowerShell via WinRM e WMI, eliminando caracteres corrompidos (`Mojibake`).
* **Fallbacks de Ferramentas do Técnico (`Dashboard`):** Localização portátil automática para `vncviewer.exe` (com injeção de `options.vnc`) e `AnyDesk.exe`, incluindo assistente de auto-instalação via compartilhamento SMB ou Winget caso a ferramenta não esteja instalada na estação do técnico.
* **Agendador Integrado ao SQLite (`SchedulerView`):** Carregamento híbrido que disponibiliza todos os scripts cadastrados no banco de dados SQLite diretamente na lista de agendamento remoto.
* **Gerenciador de Sistema Resiliente (`SystemManagerView`):** Tratamento seguro para processos com métricas nulas (`CPU = None`), tradução automática de status de serviços e preservação do retorno JSON em ações diretas de encerramento de processos e controle de serviços.
* **Terminal e Execução em Lote (`ShellView` & `ExecutionView`):** Escape seguro de tags HTML (`<`, `>`, `&`) no console, deduplicação automática de hostnames/IPs e suporte a arquivos de texto em `UTF-8 com BOM` e `Windows-1252 (ANSI)`.

## [v2.9.0] — 2026-11-11
### 📦 Gestão de Softwares, Telemetria Híbrida e Limpeza Blindada
* **Instalação Online Winget & Chocolatey (`SoftwareView`):** Bypass de bloqueio GPO do *Delivery Optimization* via `wininet`, provisionamento automático do índice `source2.msix` (V2) sob conta `SYSTEM`, fallback via Manifesto Oficial do GitHub e auto-instalação do motor Chocolatey no endpoint alvo.
* **Busca Cloud para Chocolatey:** Fallback automático para a API REST OData oficial do Chocolatey quando o cliente local não estiver instalado na máquina do operador.
* **Inventário e Desinstalação Avançada:** Adicionado filtro rápido para ocultar pacotes nativos do Windows (`MSIX`), botão de exportação para `CSV` (compatível com Excel), remoção nativa de pacotes `AppX/MSIX` e janela de **Log Detalhado (Verbose)** com duplo clique.
* **Detecção de Perfis Temporários (`DashboardView`):** Contagem híbrida (`Win32_UserProfile` + varredura física em `C:\Users`) que contabiliza e destaca pastas órfãs `TEMP` e `TEMP.EBSERHNET.*`, ignorando *Junctions* do sistema (`Todos os Usuários` e `Usuário Padrão`).
* **Scripts de Limpeza Blindados (`Limpeza_Padrao` & `Limpeza_Extrema`):** Proteção contra `LocalPath` nulo no WMI, limpeza de chaves `.bak` órfãs no Registro, bloqueio contra exclusão de `ReparsePoint` e expurgo físico de pastas `TEMP*` órfãs.
* **Empacotamento Automatizado (`build_release.ps1`):** Pipeline de build que executa a bateria do `pytest`, compila o executável com elevação UAC (`--uac-admin`) e gera o pacote portátil padronizado (`SemVer + YYYYMMDD`).