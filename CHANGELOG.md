# Histórico de Versões (Changelog) — SARCC Enterprise

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
* **Reparo e Deploy Automatizado de Agentes (`DashboardView`):** Novo seletor de ação rápida para reparar, reconfigurar ou instalar silenciosamente **Zabbix Agent 2** (com leitura dinâmica do IP `10.8.245.12`, reconstrução de contadores `PerfMon` e *Auto-Healing*), **UltraVNC Server** (modo *Stealth* com injeção dupla de `ultravnc.ini` e `MSLogonACL`), **GLPI Agent** (com sincronização forçada `--force`) e **Desktop Info** (com lançamento imediato na sessão interativa do usuário).
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