# SARCC v2 - SysAdmin Remote Command Center

O **SARCC v2** é uma plataforma desktop *Enterprise-grade* para administração, telemetria, automação e suporte de computadores Windows em ambientes de rede corporativa (Active Directory / Workgroups). 

Construído em Python com interface gráfica moderna em PyQt6, o projeto orquestra execuções remotas, gestão de softwares, instalação inteligente de drivers e manutenções profundas de forma assíncrona, segura e sem a necessidade de agentes instalados nas máquinas alvo (Agentless).

> **Arquitetura Agentless & Autenticação Transparente:** O sistema utiliza os protocolos nativos do Windows (WinRM, WMI, SMB e PowerShell Remoting), aproveitando a **Autenticação Integrada do Windows (SSO/Kerberos)** do usuário logado, eliminando a necessidade de cofres de senhas locais, garantindo máxima aderência ao Active Directory.

---

## 🚀 Principais Funcionalidades

### 🖥️ Interface e Experiência de Uso (UI/UX)
- **Motor de Temas Dinâmico:** Alternância em tempo real entre Tema Claro e Tema Escuro (qdarktheme) responsivo.
- **Processamento Assíncrono:** Tarefas pesadas rodam em background sem congelar a interface. Pool de threads unificado (12 workers padrão) configurável via variável de ambiente `SARCC_MAX_THREADS`.
- **Logging Central Rotativo:** Arquivo `data/logs/sarcc.log` com rotação (10 MB × 5 backups).
- **Cofre Seguro de Senha (DPAPI):** A interface pede a credencial apenas 1× por sessão (cache em memória) com opção de lembrar criptografada no disco ligada ao perfil do Windows.

### 🌐 Dashboard & Diagnóstico Operacional
- **Telemetria em Tempo Real:** Hostname, SO, IP, MAC, Uptime, CPU, Memória, Status do Antivírus, ocupação do Disco C:.
- **Monitoramento de Agentes:** Validação de Zabbix Agent 2, GLPI, RDP, AnyDesk, UltraVNC, **Winget** e **Reboot Pendente**.
- **Energia e Conexão:** Desligar, Reiniciar, Forçar Logoff e enviar **Wake-on-LAN (WoL)** com rastreador automático de Ping.
- **Licenciamento:** Gestão e injeção remota de chaves do Windows (KMS / GVLK).

### 🛠️ Gestão de Processos, Serviços e Eventos
- **Task Manager Remoto:** Listagem em tempo real de processos e serviços com ações de Kill/Start/Stop/Restart.
- **Resumo Rápido de Eventos Críticos:** Painel com os 5 eventos mais recentes (System + Application) via Event Viewer nativo.

### 📦 Gestão de Softwares e Drivers Inteligentes
- **Inventário Robusto (AppX Bypass):** Fura o isolamento de sessões não-interativas do WinRM descobrindo o binário real do Winget. Faz fallback automático para o Registo do Windows.
- **Filtro "Só com Atualização":** Mostra apenas pacotes desatualizados para upgrade em lote.
- **Deploy Offline em Double Hop:** Instalação silenciosa via rede SMB. A credencial é injetada em Base64 no script, convertida e usada de forma volátil (`New-PSDrive` sem `-Persist`), protegendo os dados.
- **Desinstalação de Força Bruta:** Em caso de falha via WMI/Winget, o SARCC localiza desinstaladores nativos (`uninstall.exe`) diretamente em `Program Files` e pastas de `AppData` e executa-os.
- **Injeção e Extração de Drivers:** Coleta e compara versões de `.inf` com o repositório da rede para atualizar pacotes de Rede, Vídeo, Áudio, Bluetooth e Câmaras em massa.

### ⚡ Central de Execução Remota (Em Lote)
- **Editor de Código:** Syntax Highlighting nativo, numeração de linhas e ferramenta de busca embutida (Ctrl+F) em `gui/widgets/code_editor.py`.
- **Arquitetura de Templates:** Todo o código injetado remotamente repousa organizado em `/core/scripts/`, permitindo expansão e modificação sem tocar na estrutura Python.
- **WMI Resiliente (8 Horas):** Fallback quando WinRM falha; o script é injetado via `C$` e monitorizado.

### ⏱️ Automação (Agendador Remoto)
- Criação de gatilhos agendados no "Agendador de Tarefas" alvo rodando no nível mais alto (`SYSTEM`), utilizando a conta-máquina do domínio (`DOMINIO\MÁQUINA$`) para acesso transparente a shares sem credenciais.

### 📡 Terminal Interativo e Diagnóstico de Rede
- **Shell Remoto PowerShell** com console formatado.
- **17 Atalhos de Rede** prontos (ping min/max/média, tracert, nslookup, netstat, arp, Wi-Fi, etc.).

---

## 📋 Requisitos do Sistema

- **Estação do Administrador (Onde o SARCC roda):**
  - Windows 10 ou superior.
  - Python 3.10 ou superior.
  - Estar logado com um usuário de domínio com privilégios administrativos sobre os alvos.
- **Máquinas Alvo (Endpoints):**
  - WinRM habilitado (Porta 5985) ou WMI/RPC liberados (Portas 135 e 49152-65535).
  - Compartilhamento Administrativo (C$) acessível.
  - Regras ICMP (Ping) liberadas para retorno de telemetria.

---

## 🛠️ Instalação e Execução

1. Clone o repositório e acesse a pasta do projeto:
```powershell
git clone [https://github.com/WSauan/SARCC_Enterprise.git](https://github.com/WSauan/SARCC_Enterprise.git)
Set-Location SARCC_Enterprise