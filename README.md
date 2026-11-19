# SARCC Enterprise — SysAdmin Remote Command Center (v2.11.0)

O **SARCC Enterprise** é uma plataforma desktop *Enterprise-grade* para administração remota, telemetria física em tempo real, automação de tarefas, gestão de pacotes, manutenção de impressão e suporte de estações Windows em ambientes corporativos (Active Directory / Workgroups).

Construído em Python com interface gráfica em **PyQt6** e arquitetura em camadas (*Clean Architecture*), o sistema orquestra execuções em lote, reparo de agentes corporativos, inventário e deploy de softwares, extração/instalação de drivers e manutenções profundas de forma assíncrona, segura e sem necessidade de agentes proprietários nas máquinas alvo (*Agentless*).

> **Arquitetura Agentless & Autenticação Transparente:** O sistema utiliza os protocolos nativos do Windows (`WinRM`, `WMI/CIM`, `SMB` e `PowerShell Remoting`), aproveitando a **Autenticação Integrada do Windows (SSO/Kerberos)** do administrador logado e contando com cofre local criptografado via **DPAPI** (`CryptProtectData`) para operações em *Double Hop*.

---

## 🏗️ Arquitetura do Projeto

O projeto é estruturado em camadas desacopladas com cobertura de testes unitários no padrão 1-para-1 (58 testes automatizados):

~~~text
SARCC_Enterprise/
├── core/                        # Núcleo técnico, conexões WinRM/WMI, fila assíncrona, DPAPI e logger
│   └── scripts/                 # Templates PowerShell (.ps1) organizados por módulo
│       ├── dashboard/           # Telemetria física S.M.A.R.T., energia, KMS e reparo de agentes
│       ├── scheduler/           # Gestão de tarefas agendadas sob conta SYSTEM
│       ├── shell/               # Motor de execução do Terminal Interativo
│       ├── software/            # Inventário, Winget/Choco, deploy SMB e coleta/deploy de drivers
│       └── system_manager/      # Processos, serviços, Event Viewer e gestão de Impressoras/Spooler
├── domain/
│   └── services/                # Regras de negócio (ScriptService, AuditService)
├── infrastructure/
│   └── repositories/            # Persistência SQLite em modo WAL (ScriptRepository, ExecutionRepository)
├── gui/
│   ├── dialogs/                 # Diálogos modais e Cofre de Autenticação
│   ├── views/                   # 9 Telas operacionais do sistema
│   └── widgets/                 # Componentes customizados (Editor PowerShell com Syntax Highlighting)
├── tests/                       # Suíte automatizada Pytest (58 testes unitários 1-para-1)
├── build_release.ps1            # Pipeline automatizado de testes, build PyInstaller e empacotamento ZIP
├── CHANGELOG.md                 # Histórico detalhado de versões e entregas
└── main.py                      # Ponto de entrada com AppUserModelID e Exception Hook global
~~~

---

## 🚀 Principais Funcionalidades

### 🖥️ Interface, Segurança e Núcleo Assíncrono
- **Motor de Temas Dinâmico:** Alternância instantânea entre Tema Escuro e Tema Claro (`qdarktheme`).
- **Fila Assíncrona Multi-Thread (`TaskQueueManager`):** Pool unificado de 12 workers em background (configurável via variável de ambiente `SARCC_MAX_THREADS`) que impede travamentos na interface gráfica.
- **Cofre DPAPI (`CredentialStore`):** Solicita a credencial de rede apenas uma vez por sessão, com opção de persistência cifrada em `%APPDATA%\SARCC\credentials.dat` vinculada exclusivamente ao usuário e máquina Windows atual.
- **Logging Central Rotativo:** Registro detalhado em `data/logs/sarcc.log` (`RotatingFileHandler` de 10 MB com 5 backups) compatível com execução compilada `--windowed`.

### 🌐 Dashboard, Inventário Físico & Reparo de Agentes
- **Telemetria Física & S.M.A.R.T.:** Leitura em tempo real de Hostname, **Descrição do Computador** (local/setor), **Fabricante e Modelo** do equipamento, **Serial / Service Tag da BIOS**, SO, IP, MAC, Uptime, CPU (uso e temperatura), Antivírus, ocupação do Disco C:, **Tipo de Mídia** (`NVMe SSD`, `SSD` ou `HDD`), saúde física **S.M.A.R.T.** e **Topologia de Memória RAM** (slots ocupados/totais e velocidade em MHz).
- **Detecção Híbrida de Perfis e Pastas `TEMP*`:** Cruza dados do `Win32_UserProfile` com varredura física em `C:\Users`, contabilizando e destacando perfis temporários/órfãos (`TEMP` / `TEMP.EBSERHNET.*`) e filtrando *Junctions* do sistema.
- **Status Real de Sessões e Logoff Seletivo:** Identificação de sessões **Ativo**, **Desconectado** e **Em 2º Plano** via `quser`, colunas redimensionáveis na tabela de usuários e encerramento seletivo por usuário.
- **Monitoramento de Agentes e Estado:** Validação em tempo real de Zabbix Agent 2, GLPI Agent, Desktop Info, RDP, AnyDesk (com extração automática do ID numérico), UltraVNC, versão do **Winget** e alerta de **Reboot Pendente** (`WU`, `CBS`, `PFR`).
- **Reparo e Deploy Automatizado de Agentes (1 Clique):**
  - **Zabbix Agent 2:** Instala ou reconfigura o serviço lendo dinamicamente o IP do servidor (`10.8.245.12`) a partir do `.conf` da rede, reconstrói os contadores de desempenho (`lodctr /R`) e configura *Auto-Healing* (`sc.exe failure`).
  - **UltraVNC Server:** Executa instalação *Stealth*, aplica `ultravnc.ini` em `ProgramData` e `Program Files`, importa permissões `MSLogonACL` e garante a regra de firewall na porta `5900`.
  - **GLPI Agent:** Configura as chaves OAuth no Registro, instala/atualiza via MSI da rede e força a sincronização imediata do inventário (`--force`).
  - **Desktop Info:** Atualiza o binário em `C:\Program Files\Desktop Info`, registra no Startup e dispara o widget imediatamente na sessão interativa do usuário logado (contornando o isolamento da `Session 0` do WinRM).
- **Acesso Remoto com Fallback Inteligente:** Conexão direta via RDP, UltraVNC (com injeção automática de `options.vnc`), AnyDesk e Assistência Rápida, oferecendo auto-instalação local caso a ferramenta não esteja instalada na estação do técnico.
- **Energia e Licenciamento KMS:** Comandos remotos de Reiniciar, Desligar, Forçar Logoff, **Wake-on-LAN (WoL)** com rastreador automático de Ping e troca de edição do Windows via chaves GVLK/KMS.

### 🛠️ Gerenciador de Processos, Serviços, Eventos e Impressoras
- **Task Manager Remoto:** Listagem em tempo real de processos (PID, Memória MB, CPU) e serviços do Windows com ações diretas de `Kill`, `Start`, `Stop` e `Restart`.
- **Auditoria de Eventos Críticos, Reinicializações e Períodos:** Resumo instantâneo dos 5 eventos críticos/erros mais recentes, filtro dedicado para reinicializações inesperadas (`41 6008 1074 6006 6009 1001`), janelas rápidas (`Últimas 2h`, `Últimas 12h`, `Últimas 24h`, `Últimos 7 dias`, `Últimos 30 dias`) e intervalo de data/hora (`De / Até`).
- **Gestão de Impressoras & Spooler:**
  - Inventário completo das impressoras locais e mapeadas na estação (Nome, Porta/IP, Driver, Trabalhos na Fila e Status).
  - **🔎 Buscar Impressoras:** Força atualização de política de computador (`gpupdate /target:computer /force`) e recarrega a lista de impressoras.
  - **🧹 Destravar Spooler (Limpar Tudo):** Para o serviço `Spooler` e processos `splwow64`, elimina todos os arquivos `.SHD` e `.SPL` travados em `C:\Windows\System32\spool\PRINTERS` e reinicia o serviço automaticamente.
  - Ações individuais para **Limpar Fila Selecionada** e **Remover Impressora**.

### 📦 Gestão Multi-Motor de Softwares e Drivers
- **Suporte Dual-Engine (`Winget` & `Chocolatey`):** Inventário completo com reparo automático de codificação UTF-8, verificação de atualizações disponíveis, filtro rápido para ocultar pacotes nativos do sistema (`MSIX`) e exportação da lista para **CSV** (compatível com Excel).
- **Instalação Online Blindada contra Bloqueios de GPO:**
  - *Winget:* Configuração automática do downloader `wininet`, provisionamento dinâmico do índice V2 (`source2.msix`) na conta `SYSTEM` e **Fallback via Manifesto Oficial do GitHub (`microsoft/winget-pkgs`)**.
  - *Chocolatey:* Busca local com **Fallback automático para a API Cloud OData** (mesmo sem Chocolatey instalado na estação do técnico) e auto-instalação do motor Chocolatey no endpoint alvo.
- **Deploy Offline via Rede SMB (Double Hop):** Instalação silenciosa de pacotes `.msi` e `.exe` a partir do repositório de rede (`\\hul-vp-imagem-cc\netshared\Softwares`) usando mapeamento volátil autenticado.
- **Desinstalação Multi-Camada:** Remoção via Winget/Chocolatey, remoção nativa de pacotes `AppX/MSIX` (`Remove-AppxPackage -AllUsers`), leitura de `QuietUninstallString` no Registro e busca de `uninstall.exe` locais.
- **Extração e Deploy Inteligente de Drivers:** Coleta seletiva de drivers para a rede comparando a diretiva `DriverVer` dos arquivos `.inf` locais contra o servidor SMB, e instalação automatizada por fabricante/modelo de placa-mãe e categorias (Vídeo, Rede, Áudio, Bluetooth, Câmeras).

### ⚡ Central de Comando em Lote, Agendador e Terminal
- **Execução em Lote (`ExecutionView`):** Disparo simultâneo de múltiplos scripts da biblioteca para dezenas de computadores (com importação de listas `.txt`/`.csv`, deduplicação automática e filtro rápido de alvos online).
- **Scripts de Limpeza Blindados (`Limpeza_Padrao` & `Limpeza_Extrema`):** Expurgo seguro de perfis inativos, chaves `.bak` corrompidas no Registro e pastas `TEMP*` órfãs em `C:\Users`, preservando contas VIP e bloqueando exclusão de *ReparsePoints* (`Junctions`).
- **Agendador Remoto (`SchedulerView`):** Criação de tarefas agendadas rodando como `NT AUTHORITY\SYSTEM` integradas diretamente à biblioteca SQLite de scripts, com suporte a intervalo de datas e notebooks em bateria.
- **Terminal Interativo (`ShellView`):** Console PowerShell remoto com atalhos prontos de diagnóstico e reset de rede (`DNS`, `ARP`, `NetBIOS`), conversão de codificação para comandos legados e execução local via arquivo temporário evitando `WinError 206`.
- **Histórico e Relatórios GLPI (`HistoryView`):** Auditoria completa com filtro por data exata, intervalo de data/hora (`De / Até`), janelas recentes e status, lixeira com restauração, visualização de JSON estruturado e geração de relatório oficial em `.txt` padronizado para anexar em chamados do GLPI.

---

## 📋 Requisitos do Sistema

- **Estação do Administrador (Onde o SARCC roda):**
  - Windows 10 ou Windows 11 (x64).
  - Python 3.10 ou superior (para execução via código-fonte) ou executável portátil compilado (`SARCC_v2.11.0_YYYYMMDD.exe`).
- **Máquinas Alvo (Endpoints):**
  - WinRM habilitado (Porta TCP `5985`) ou WMI/SMB liberados (Porta TCP `445` / `C$`).
  - Regras ICMP (Ping) liberadas para verificação de conectividade.

---

## 🛠️ Instalação, Testes e Empacotamento

### 1. Clonar o repositório e preparar o ambiente virtual
~~~powershell
git clone https://github.com/WSauan/SARCC_Enterprise.git
Set-Location SARCC_Enterprise

python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
~~~

### 2. Executar em modo de desenvolvimento
~~~powershell
python main.py
~~~

### 3. Executar a suíte de testes automatizados (Pytest)
~~~powershell
pytest -v
~~~

### 4. Gerar executável e pacote de distribuição (Release)
O script `build_release.ps1` executa automaticamente toda a bateria de testes do `pytest`, compila o binário único com elevação de Administrador (`--uac-admin`) e ícone oficial, e monta a pasta portátil e o arquivo `.zip` em `releases/`:
~~~powershell
.\build_release.ps1 -Version "2.11.0"
~~~