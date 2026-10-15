# SARCC v2 - SysAdmin Remote Command Center

O **SARCC v2** é uma plataforma desktop *Enterprise-grade* para administração, telemetria, automação e suporte de computadores Windows em ambientes de rede corporativa (Active Directory / Workgroups). 

Construído em Python com interface gráfica moderna em PyQt6, o projeto orquestra execuções remotas, gestão de softwares, instalação inteligente de drivers e manutenções profundas de forma assíncrona, segura e sem a necessidade de agentes instalados nas máquinas alvo (Agentless).

> **Arquitetura Agentless & Autenticação Transparente:** O sistema utiliza os protocolos nativos do Windows (WinRM, WMI, SMB e PowerShell Remoting), aproveitando a **Autenticação Integrada do Windows (SSO/Kerberos)** do usuário logado, eliminando a necessidade de cofres de senhas locais.

---

## 🚀 Principais Funcionalidades

### 🖥️ Interface e Experiência de Uso (UI/UX)
- **Motor de Temas Dinâmico:** Alternância em tempo real entre Tema Claro e Tema Escuro (qdarktheme) responsivo.
- **Padronização Visual Completa:** Campos de alvo com conversão automática para maiúsculas, botões e inputs padronizados.
- **Processamento Assíncrono:** Tarefas pesadas rodam em background sem congelar a interface. Pool de threads unificado (12 workers) compartilhado entre as views, configurável via variável de ambiente `SARCC_MAX_THREADS`.
- **Logging Central Rotativo:** Arquivo `data/logs/sarcc.log` com rotação (10 MB × 5 backups), registrando ações, erros e tracebacks completos para auditoria e suporte.
- **Cache de Senha em Memória:** popup único por sessão. Botão "🔒 Esquecer senha" na sidebar limpa o cache.

### 🌐 Dashboard & Diagnóstico Operacional
- **Telemetria em Tempo Real:** Hostname, SO, IP, MAC, Uptime, CPU, Memória, Status do Antivírus, ocupação do Disco C:.
- **Monitoramento de Agentes:** Validação de status do Zabbix Agent 2, GLPI, RDP, AnyDesk, UltraVNC, **Winget** (com versão) e **Reboot Pendente** (WU/CBS/MSI).
- **Energia e Conexão:** Ações rápidas para Desligar, Reiniciar, Forçar Logoff e enviar **Wake-on-LAN (WoL)** com rastreador automático de Ping.
- **Licenciamento:** Gestão e injeção remota de chaves do Windows (KMS / GVLK).

### 🛠️ Gestão de Processos, Serviços e Eventos
- **Task Manager Remoto:** Listagem em tempo real de processos (RAM/CPU) e serviços.
- **Ações Críticas:** Kill de processos e Start/Stop/Restart de serviços com log de retorno.
- **Event Viewer Centralizado:** Busca de logs (System, Application, Security) por severidade.
- **Resumo Rápido de Eventos Críticos:** Painel automático com os 5 eventos mais recentes (System + Application) e dialog de detalhes por duplo clique.

### 📦 Gestão de Softwares e Drivers Inteligentes
- **Inventário Multi-Motor:** Winget, Chocolatey e Registro do Windows (fallback).
- **IDs Reais do Winget:** Inventário expõe `PackageIdentifier` para permitir atualização/desinstalação remota direta.
- **Filtro "Só com Atualização":** Mostra apenas pacotes desatualizados para atualização em lote com um clique.
- **Deploy Offline:** Instalação silenciosa de `.exe`/`.msi` via compartilhamento de rede SMB (com `New-PSDrive -Credential`, sem senha em linha de comando).
- **Bootstrap Automático do Winget:** Se o alvo não tem Winget, instala a partir de MSIX na rede.
- **Coleta Inteligente de Drivers:** Extração comparando versão (`.inf`) com o repositório da rede.
- **Injeção de Drivers:** Instalação automática por categoria (Rede, Display, Áudio, BT, Câmeras).

### ⚡ Central de Execução Remota (Em Lote)
- **Multi-Threading:** Fila que processa dezenas de máquinas simultaneamente via WinRM.
- **Editor de Código:** Syntax Highlighting PowerShell para criar, editar, importar/exportar scripts.
- **Credenciais Unificadas:** Placeholders `[[ADMIN_USER]]` / `[[ADMIN_PASS]]`
  / `[[VNC_PASS]]` injetados em memória como Base64 (sem expor caracteres
  especiais). Senha pedida 1× por sessão via cache.
- **Modo Conta-Máquina (Agendador):** scripts rodam como `SYSTEM` e acessam
  o share via Kerberos como `DOMINIO\NOMEDAMÁQUINA$` — senha nunca vai para
  disco em tarefas agendadas.
- **WMI Resiliente (8 Horas):** Fallback quando WinRM falha; o script é injetado via `C$` e monitorizado por até 8 horas.

### ⏱️ Automação (Agendador Remoto)
- Criação de gatilhos agendados (Boot ou Diariamente) direto no "Agendador de Tarefas" do Windows alvo.
- Leitura e remoção interativa das tarefas SARCC ativas.

### 📡 Terminal Interativo e Diagnóstico de Rede
- **Shell Remoto PowerShell** com console de saída formatado.
- **17 Atalhos de Rede** prontos: ping clássico (min/max/média), tracert, nslookup (A + PTR), netstat, ipconfig, arp, Get-NetRoute, DNS, Wi-Fi visíveis e mais.
- **Encoding Correto** para comandos nativos do Windows (ping.exe, ipconfig, etc.).

### 📋 Auditoria e Histórico de Logs
- **Banco de Dados Local (SQLite):** Registro integral de execuções, tempo, logs crus e status.
- **Lixeira Inteligente:** Soft delete com recuperação e expurgo definitivo.
- **Exportação Profissional:** Relatórios `.txt` padronizados para anexar a chamados de TI (GLPI).

---

## 📋 Requisitos do Sistema

- **Estação do Administrador (Onde o SARCC roda):**
  - Windows 10 ou superior.
  - Python 3.10 ou superior.
  - Estar logado com um usuário de domínio que possua privilégios administrativos sobre as máquinas alvo.
- **Máquinas Alvo (Endpoints):**
  - WinRM habilitado (Porta 5985) ou WMI/RPC liberados no Firewall (Portas 135 e 49152-65535).
  - Compartilhamento Administrativo (C$) acessível.
  - Regras ICMP (Ping) liberadas para retorno de telemetria.

---

## 🛠️ Instalação e Execução

1. Clone o repositório e acesse a pasta do projeto:
```powershell
git clone [https://github.com/WSauan/SARCC_v2.git](https://github.com/WSauan/SARCC_v2.git)
Set-Location SARCC_v2