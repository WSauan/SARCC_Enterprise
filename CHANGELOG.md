# Histórico de Versões (Changelog) — SARCC Enterprise

## [v2.9.1] — 2026-11-13
### 🛡️ Blindagem de Núcleo (Core) e Interface (Fase 2)
* **Decodificação UTF-8 Nativa (`RemoteConnectionManager`):** Correção definitiva da leitura de acentuação em retornos do PowerShell via WinRM e WMI, eliminando caracteres corrompidos (`Mojibake`).
* **Fallbacks de Ferramentas do Técnico (`Dashboard`):** Localização portátil automática para `vncviewer.exe` (com injeção de `options.vnc`) e `AnyDesk.exe`, incluindo assistente de auto-instalação via compartilhamento SMB ou Winget caso a ferramenta não esteja instalada na estação do técnico.
* **Agendador Integrado ao SQLite (`SchedulerView`):** Carregamento híbrido que disponibiliza todos os scripts cadastrados no banco de dados SQLite diretamente na lista de agendamento remoto.
* **Gerenciador de Sistema Resiliente (`SystemManagerView`):** Tratamento seguro para processos com métricas nulas (`CPU = None`), tradução automática de status de serviços e preservação do retorno JSON em ações diretas de encerramento de processos e controle de serviços.
* **Terminal e Execução em Lote (`ShellView` & `ExecutionView`):** Escape seguro de tags HTML (`<`, `>`, `&`) no console, deduplicação automática de hostnames/IPs e suporte a arquivos de texto em `UTF-8 com BOM` e `Windows-1252 (ANSI)`.
* **Suíte de Testes Automatizados 1-para-1 (`pytest`):** Cobertura expandida para **39 testes unitários** organizados individualmente por módulo (`core/` e `gui/`).

## [v2.9.0] — 2026-11-11
### 🚀 Gestão de Softwares, Telemetria Híbrida e Limpeza Blindada
* **Instalação Online Winget & Chocolatey (`SoftwareView`):** Bypass de bloqueio GPO do *Delivery Optimization* via `wininet`, provisionamento automático do índice `source2.msix` (V2) sob conta `SYSTEM`, fallback via Manifesto Oficial do GitHub e auto-instalação do motor Chocolatey no endpoint alvo.
* **Busca Cloud para Chocolatey:** Fallback automático para a API REST OData oficial do Chocolatey quando o cliente local não estiver instalado na máquina do operador.
* **Inventário e Desinstalação Avançada:** Adicionado filtro rápido para ocultar pacotes nativos do Windows (`MSIX`), botão de exportação para `CSV` (compatível com Excel), remoção nativa de pacotes `AppX/MSIX` e janela de **Log Detalhado (Verbose)** com duplo clique.
* **Detecção de Perfis Temporários (`DashboardView`):** Contagem híbrida (`Win32_UserProfile` + varredura física em `C:\Users`) que contabiliza e destaca pastas órfãs `TEMP` e `TEMP.EBSERHNET.*`, ignorando *Junctions* do sistema (`Todos os Usuários` e `Usuário Padrão`).
* **Scripts de Limpeza Blindados (`Limpeza_Padrao` & `Limpeza_Extrema`):** Proteção contra `LocalPath` nulo no WMI, limpeza de chaves `.bak` órfãs no Registro, bloqueio contra exclusão de `ReparsePoint` e expurgo físico de pastas `TEMP*` órfãs.
* **Empacotamento Automatizado (`build_release.ps1`):** Pipeline de build que executa a bateria do `pytest`, compila o executável com elevação UAC (`--uac-admin`) e gera o pacote portátil padronizado (`SemVer + YYYYMMDD`).