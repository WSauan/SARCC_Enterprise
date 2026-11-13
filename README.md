# SARCC Enterprise — SysAdmin Remote Command Center

O **SARCC Enterprise** é uma plataforma desktop *Enterprise-grade* para administração remota, telemetria em tempo real, automação de tarefas, gestão de pacotes e suporte de estações Windows em ambientes corporativos (Active Directory / Workgroups)[cite: 73].

Construído em Python com interface gráfica em **PyQt6** e arquitetura em camadas (*Clean Architecture*), o sistema orquestra execuções em lote, inventário e deploy de softwares, extração/instalação de drivers e manutenções profundas de forma assíncrona, segura e sem necessidade de agentes proprietários nas máquinas alvo (*Agentless*)[cite: 73].

> **Arquitetura Agentless & Autenticação Transparente:** O sistema utiliza os protocolos nativos do Windows (`WinRM`, `WMI/CIM`, `SMB` e `PowerShell Remoting`), aproveitando a **Autenticação Integrada do Windows (SSO/Kerberos)** do administrador logado e contando com cofre local criptografado via **DPAPI** (`CryptProtectData`) para operações em *Double Hop*[cite: 35, 73].

---

## 🏗️ Arquitetura do Projeto

O projeto é estruturado em camadas desacopladas com cobertura de testes unitários no padrão 1-para-1[cite: 32, 61]:

```text
SARCC_Enterprise/
├── core/                        # Núcleo técnico, conexões WinRM/WMI, fila assíncrona, DPAPI e logger
│   └── scripts/                 # Templates PowerShell (.ps1) organizados por módulo
├── domain/
│   └── services/                # Regras de negócio (ScriptService, AuditService)
├── infrastructure/
│   └── repositories/            # Persistência SQLite em modo WAL (ScriptRepository, ExecutionRepository)
├── gui/
│   ├── dialogs/                 # Diálogos modais e Cofre de Autenticação
│   ├── views/                   # 9 Telas operacionais do sistema
│   └── widgets/                 # Componentes customizados (Editor PowerShell com Syntax Highlighting)
├── tests/                       # Suíte automatizada Pytest (47 testes unitários 1-para-1)
├── build_release.ps1            # Pipeline automatizado de testes, build PyInstaller e empacotamento ZIP
└── main.py                      # Ponto de entrada com AppUserModelID e Exception Hook global
```

---

## 🚀 Principais Funcionalidades

### 🖥️ Interface, Segurança e Núcleo Assíncrono
- **Motor de Temas Dinâmico:** Alternância instantânea entre Tema Escuro e Tema Claro (`qdarktheme`)[cite: 57, 73].
- **Fila Assíncrona Multi-Thread (`TaskQueueManager`):** Pool unificado de 12 workers em background (configurável via variável de ambiente `SARCC_MAX_THREADS`) que impede travamentos na interface gráfica[cite: 39, 45, 73].
- **Cofre DPAPI (`CredentialStore`):** Solicita a credencial de rede apenas 1× por sessão, com opção de persistência cifrada em `%APPDATA%\SARCC\credentials.dat` vinculada exclusivamente ao usuário e máquina Windows atual[cite: 35, 73].
- **Logging Central Rotativo:** Registro detalhado em `data/logs/sarcc.log` (`RotatingFileHandler` de 10 MB × 5 backups) compatível com execução compilada `--windowed`[cite: 40, 73].

### 🌐 Dashboard & Diagnóstico Operacional
- **Telemetria Ultra-Rápida:** Leitura em tempo real de Hostname, SO, IP, MAC, Uptime, CPU (uso e temperatura), RAM, Antivírus e ocupação do Disco C:[cite: 21, 24, 73].
- **Detecção Híbrida de Perfis e Pastas `TEMP*`:** Cruza dados do `Win32_UserProfile` com varredura física em `C:\Users`, contabilizando e destacando perfis temporários/órfãos (`TEMP` / `TEMP.EBSERHNET.*`) e filtrando *Junctions* do sistema[cite: 17, 30].
- **Monitoramento de Agentes e Estado:** Validação de Zabbix Agent, GLPI Agent, RDP, AnyDesk (com extração automática do ID), UltraVNC, versão do **Winget** e alerta de **Reboot Pendente** (`WU`, `CBS`, `PFR`)[cite: 24, 73].
- **Acesso Remoto com Fallback Inteligente:** Conexão direta via RDP, UltraVNC (com injeção automática de `options.vnc`), AnyDesk e Assistência Rápida, oferecendo auto-instalação local caso a ferramenta não esteja instalada na máquina do técnico[cite: 21, 32, 37].
- **Energia e Licenciamento KMS:** Comandos remotos de Reiniciar, Desligar, Forçar Logoff, **Wake-on-LAN (WoL)** com rastreador automático de Ping e troca de edição do Windows via chaves GVLK/KMS[cite: 21, 25, 73].

### 🛠️ Gerenciador de Processos, Serviços e Eventos
- **Task Manager Remoto:** Listagem em tempo real de processos (PID, Memória MB, CPU) e serviços do Windows com ações diretas de `Kill`, `Start`, `Stop` e `Restart`[cite: 54, 66, 67, 73].
- **Auditoria de Eventos Críticos:** Resumo instantâneo dos 5 eventos críticos/erros mais recentes (`System` e `Application`) e buscador completo do Event Viewer com visualização detalhada[cite: 54, 70, 71, 73].

### 📦 Gestão Multi-Motor de Softwares e Drivers
- **Suporte Dual-Engine (`Winget` & `Chocolatey`):** Inventário completo com reparo automático de codificação UTF-8, verificação de atualizações disponíveis, filtro rápido para ocultar pacotes nativos do sistema (`MSIX`) e exportação da lista para **CSV** (compatível com Excel)[cite: 3, 12].
- **Instalação Online Blindada contra Bloqueios de GPO:**
  - *Winget:* Configuração automática do downloader `wininet`, provisionamento dinâmico do índice V2 (`source2.msix`) na conta `SYSTEM` e **Fallback via Manifesto Oficial do GitHub (`microsoft/winget-pkgs`)**[cite: 14].
  - *Chocolatey:* Busca local com **Fallback automático para a API Cloud OData** (mesmo sem Chocolatey instalado na estação do técnico) e auto-instalação do motor Chocolatey no endpoint alvo[cite: 12].
- **Deploy Offline via Rede SMB (Double Hop):** Instalação silenciosa de pacotes `.msi` e `.exe` a partir do repositório de rede (`\\hul-vp-imagem-cc\netshared\Softwares`) usando mapeamento volátil autenticado[cite: 5, 39, 73].
- **Desinstalação Multi-Camada:** Remoção via Winget/Chocolatey, remoção nativa de pacotes `AppX/MSIX` (`Remove-AppxPackage -AllUsers`), leitura de `QuietUninstallString` no Registro e busca de `uninstall.exe` locais[cite: 7, 73].
- **Extração e Deploy Inteligente de Drivers:** Coleta seletiva de drivers para a rede (comparando versões `.inf`) e instalação automatizada por modelo de placa-mãe e categorias (Vídeo, Rede, Áudio, Bluetooth, Câmeras)[cite: 6, 73].
- **Log Detalhado (Verbose):** Duplo clique em qualquer tarefa para inspecionar a saída técnica linha a linha[cite: 9, 11].

### ⚡ Central de Comando em Lote, Agendador e Terminal
- **Execução em Lote (`ExecutionView`):** Disparo simultâneo de múltiplos scripts da biblioteca para dezenas de computadores (com importação de listas `.txt`/`.csv` e deduplicação automática)[cite: 51, 73].
- **Scripts de Limpeza Blindados (`Limpeza_Padrao` & `Limpeza_Extrema`):** Expurgo seguro de perfis inativos, chaves `.bak` corrompidas no Registro e pastas `TEMP*` órfãs em `C:\Users`, preservando contas VIP e bloqueando exclusão de *ReparsePoints* (`Junctions`)[cite: 19, 20, 31].
- **Agendador Remoto (`SchedulerView`):** Criação de tarefas agendadas rodando como `NT AUTHORITY\SYSTEM` integradas diretamente à biblioteca SQLite de scripts[cite: 55, 64, 73].
- **Terminal Interativo (`ShellView`):** Console PowerShell remoto com 17 atalhos prontos de diagnóstico de rede (`ping`, `tracert`, `Resolve-DnsName`, `Test-NetConnection`, `netstat`, `arp`, `wlan`, `Firewall`)[cite: 53, 73].
- **Histórico e Relatórios GLPI (`HistoryView`):** Auditoria completa com filtro por data/status, lixeira com restauração, visualização de JSON estruturado e geração de relatório oficial em `.txt` padronizado para chamados do GLPI[cite: 31, 52].

---

## 📋 Requisitos do Sistema

- **Estação do Administrador (Onde o SARCC roda)[cite: 73]:**
  - Windows 10 ou Windows 11 (x64)[cite: 73].
  - Python 3.10 ou superior (para execução via código-fonte) ou executável portátil compilado (`SARCC_vX.Y.Z_YYYYMMDD.exe`)[cite: 33, 73].
- **Máquinas Alvo (Endpoints)[cite: 73]:**
  - WinRM habilitado (Porta TCP `5985`) ou WMI/SMB liberados (Porta TCP `445` / `C$`)[cite: 39, 56, 73].
  - Regras ICMP (Ping) liberadas para verificação de conectividade[cite: 56, 73].

---

## 🛠️ Instalação, Testes e Empacotamento

### 1. Clonar o repositório e preparar o ambiente virtual
```powershell
git clone https://github.com/WSauan/SARCC_Enterprise.git
Set-Location SARCC_Enterprise

python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Executar em modo de desenvolvimento
```powershell
python main.py
```

### 3. Executar a suíte de testes automatizados (Pytest)
```powershell
pytest -v
```

### 4. Gerar executável e pacote de distribuição (Release)
O script `build_release.ps1` executa automaticamente toda a bateria de testes do `pytest`, compila o binário único com elevação de Administrador (`--uac-admin`) e ícone oficial, e monta a pasta portátil e o arquivo `.zip` em `releases/`:
```powershell
.\build_release.ps1 -Version "2.9.1"
```