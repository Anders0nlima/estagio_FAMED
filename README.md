# Sistema de Gestão e Classificação de Estágios — FAMED/UFPA

Plataforma institucional desenvolvida para automatizar, auditar e dar total transparência jurídica ao processo de seleção dos **Estágios de Férias e Extracurriculares** da Faculdade de Medicina da Universidade Federal do Pará (**FAMED/UFPA**).

O sistema elimina o processamento manual de planilhas, audita notas e inscrições com semáforo visual, executa o algoritmo de alocação de vagas (observando 1ª e 2ª opções, cotas de 50% com vaga ímpar para cotista, desempate por CRG/idade e requisitos de semestre) e gera automaticamente o **Ofício Oficial em Word (.docx)**, **PDFs**, **Listas de Frequência** e **Certificados Digitais**.

---

## 🚀 Como Rodar no Computador do Diretor (Uso Local)

### 1. Pré-requisito Obrigatório
O único pré-requisito necessário é ter o **Python** instalado no computador:
* **Versão recomendada:** Python 3.10, 3.11, 3.12 ou 3.13.
* **Download oficial:** [python.org/downloads](https://www.python.org/downloads/)
* ⚠️ **MUITO IMPORTANTE (Windows):** Ao instalar o Python, marque a caixinha **"Add python.exe to PATH"** (Adicionar Python ao PATH) logo na primeira tela do instalador.

---

### Método 1: Inicialização em 1 Clique (Recomendado para Windows) ⚡

Se o diretor utiliza Windows, o projeto já inclui um inicializador automático:

1. Abra a pasta do projeto no Windows Explorer.
2. Dê um **duplo clique** no arquivo:
   ```text
   iniciar_sistema.bat
   ```
3. O script irá automaticamente:
   - Configurar o ambiente virtual isolado (`.venv`);
   - Instalar as dependências necessárias;
   - Preparar o banco de dados local;
   - Abrir o navegador padrão automaticamente em `http://127.0.0.1:8000/`.

> **Para encerrar o sistema:** Basta fechar a janela preta do terminal ou pressionar `Ctrl + C`.

---

### Método 2: Execução Manual pelo Terminal (Passo a Passo)

Caso prefira rodar manualmente pelo PowerShell, Prompt de Comando (CMD) ou em sistemas macOS/Linux:

#### 1. Abra o terminal na pasta do projeto:
```powershell
cd C:\Projetos\estagio_FAMED
```

#### 2. Crie e ative o ambiente virtual:
* **No Windows (PowerShell):**
  ```powershell
  python -m venv .venv
  .venv\Scripts\Activate.ps1
  ```
* **No Windows (Prompt de Comando - CMD):**
  ```cmd
  python -m venv .venv
  .venv\Scripts\activate.bat
  ```
* **No Linux / macOS:**
  ```bash
  python3 -m venv .venv
  source .venv/bin/activate
  ```

#### 3. Instale as dependências:
```bash
pip install -r requirements.txt
```

#### 4. Aplique as migrações do banco de dados:
```bash
python manage.py migrate
```

#### 5. Inicie o servidor da aplicação:
```bash
python manage.py runserver
```

#### 6. Acesse no seu navegador:
Abra o navegador de sua preferência (Chrome, Edge, Firefox) e acesse:
👉 **[http://127.0.0.1:8000/](http://127.0.0.1:8000/)**

---

## 🔑 Credenciais Padrão de Acesso

O sistema já vem configurado com um usuário administrador padrão para a Direção:

| Campo | Valor Padrão |
| :--- | :--- |
| **Página de Login** | `http://127.0.0.1:8000/` (ou a URL do Render) |
| **Usuário** | `diretor` |
| **Senha** | `FamedUFPA@2027` |

---

## 📋 Guia de Uso da Plataforma (Fluxo de Demonstração)

Abaixo está o roteiro prático para demonstração e utilização completa do sistema pelo Diretor:

```
[1. Login] ➔ [2. Criar/Selecionar Edital] ➔ [3. Anexar Planilhas] ➔ [4. Auditoria Semáforo]
     ➔ [5. Processar Classificação] ➔ [6. Exportar Ofício (.docx/PDF)] ➔ [7. Pós-Estágio / Frequência]
```

### 1. Criar ou Configurar o Processo Seletivo (Edital)
- No painel inicial (Dashboard), clique em **"+ Cadastrar Novo Edital"** ou edite um existente em **"Editar Informações"**.
- Preencha o semestre (ex: `2027.1`), ano, número do ofício e protocolo SIPAC.
- **Parâmetros de Seleção:**
  - **Reserva de Vagas para Cotas:** `50% Cotas (Padrão Federal Lei 12.711)` — quando o número de vagas for ímpar, a vaga excedente é destinada aos cotistas.
  - **Cota Mínima de Mulheres:** `Sem cota de gênero (Padrão)` — classificação puramente por CRG e idade, conforme novas diretrizes da FAMED.

### 2. Importar as Planilhas de Candidatura e Oportunidades
- Clique no edital e vá em **"Anexar Planilhas"**.
- O sistema aceita:
  1. A planilha de respostas do Google Forms dos **alunos** (com nome, matrícula, CRG autodeclarado, gênero, opções 1 e 2, cota).
  2. A planilha de respostas do Google Forms dos **professores/preceptores** (com docente, local, horários, vagas e semestres permitidos).
  3. *(Opcional)* A planilha de conferência de ingressantes cotistas (`forma_ingresso.csv`).
- **Dica para testes:** Clique no botão azul **"Usar Arquivos de Teste do Repositório"** para carregar instantaneamente o cenário real de teste.

### 3. Auditoria pelo Semáforo de Notas
- O sistema cruza os dados e exibe a tela de **Auditoria Inteligente (Semáforo)**:
  - 🟢 **Verde:** Aluno com nota conferida e sem divergência.
  - 🟡 **Amarelo:** Aluno sem nota no arquivo de conferência (o sistema usa o CRG autodeclarado e solicita validação do Diretor).
  - 🔴 **Vermelho:** Divergência entre a nota digitada pelo aluno e a nota oficial.
- O Diretor pode ajustar qualquer nota individualmente ou clicar em **"Homologar Todas as Pendências em Lote"** para prosseguir.

### 4. Processamento da Classificação Automatizada
- Clique no botão verde **"Processar Classificação Final"**.
- O motor de alocação executa as regras em milissegundos:
  1. **Validação de Pré-requisitos:** Verifica se o semestre do aluno é aceito pelo estágio pleiteado.
  2. **1ª Etapa (Primeira Opção):** Aloca os candidatos concorrendo exclusivamente à sua 1ª opção, dividindo as vagas entre Ampla Concorrência e Cotas (vaga ímpar para cotistas).
  3. **Desempate:** Em caso de empate de CRG, o candidato com maior idade tem prioridade.
  4. **2ª Etapa (Segunda Opção):** As vagas que sobrarem na 1ª etapa são ofertadas para quem escolheu a oportunidade como 2ª opção e ainda não foi alocado.
  5. **Cadastro de Reserva / Suplência:** Todos os candidatos elegíveis não contemplados vão para a lista de espera ordenada por CRG/idade.

### 5. Exportação Oficial dos Resultados
Na tela de Resultado Final, o Diretor pode emitir com 1 clique:
- 📄 **Exportar Ofício em Word (.docx):** Documento oficial formatado com o Brasão Colorido da UFPA, preâmbulo institucional, assinatura da direção e tabelas de aprovados e suplentes por oportunidade. *(Oportunidades sem inscritos têm sua tabela omitida automaticamente para manter o documento conciso).*
- 📕 **Exportar Ofício em PDF:** Versão idêntica diagramada via ReportLab pronta para assinatura digital no SIPAC / GOV.BR.
- 📊 **Exportar Planilha Excel (.xlsx):** Relatório analítico completo com todas as etapas e notas para arquivamento.

### 6. Gestão Pós-Estágio, Frequência e Certificados
- No menu do edital, clique em **"Frequência e Certificados"**.
- **Listas de Frequência Diária:** Emita em PDF o diário de presença personalizado de cada preceptor contendo o nome e matrícula dos seus estagiários.
- **Lançamento de Frequência:** Lance a frequência e nota de cada aluno (Aprovado com Conceito Excelente/Bom ou Reprovado).
- **Certificados Digitais com QR Code:** Emita os certificados em PDF com layout oficial da UFPA, carga horária e código verificador de autenticidade.
- **Envio de E-mails:** Envio seguro dos certificados para os estudantes (em modo de teste, os e-mails são simulados na pasta `media/emails_simulados/`).

---

## ⚖️ Regras do Edital FAMED 2027 Incorporadas no Sistema

| Critério | Comportamento no Sistema |
| :--- | :--- |
| **Distribuição de Vagas** | 50% Ampla Concorrência / 50% Cotistas. Vaga ímpar vai para o cotista (ex: 5 vagas = 3 cotas e 2 ampla; 1 vaga = 1 cota). |
| **Cota de Gênero** | Desativada por padrão conforme diretrizes da FAMED 2027 (classificação estrita por mérito acadêmico e idade). |
| **Divisão por Ciclo** | Quando a vaga aceitar múltiplos ciclos (ex: Clínico e Internato), as vagas são divididas igualmente. Vaga ímpar vai para o ciclo mais avançado (com transbordo automático se sobrarem vagas). |
| **Critério de Desempate** | 1º CRG Geral $\rightarrow$ 2º Maior Idade (data de nascimento). |
| **Filtro de Semestre** | Inscrições incompatíveis com os semestres exigidos pelo preceptor são desconsideradas automaticamente. |
| **Prioridade de Opção** | Candidatos de 1ª opção têm prioridade sobre candidatos de 2ª opção. Quem passou na 1ª opção não concorre na 2ª. |
| **Migração de Vagas** | Vagas remanescentes de cotas migram para ampla concorrência caso não haja cotistas suficientes (e vice-versa). |

---

## 🛠️ Tecnologias Utilizadas

- **Linguagem:** Python 3.12+
- **Framework Web:** Django 5.x
- **Processamento Numérico:** Pandas & NumPy
- **Manipulação de Documentos:** `python-docx` (Word) e ReportLab (PDF)
- **Interface:** HTML5 Semântico, Tailwind CSS, Heroicons
- **Banco de Dados:** SQLite (Desenvolvimento / Local) & PostgreSQL (Produção / Docker)
- **Testes Automatizados:** Pytest (19 testes cobrindo todas as regras de classificação)

---

## ❓ Perguntas Frequentes & Resolução de Problemas

#### 1. "O comando python não é reconhecido no terminal..."
- Isso ocorre quando o Python foi instalado sem marcar a opção "Add python.exe to PATH". 
- **Solução:** Reabra o instalador do Python, selecione "Modify" (Modificar) e certifique-se de marcar a opção **Add Python to PATH**.

#### 2. "A porta 8000 já está em uso..."
- Outro programa ou instância anterior do sistema pode estar aberta.
- **Solução:** Você pode rodar em outra porta executando:
  ```powershell
  python manage.py runserver 8080
  ```
  E acessar em `http://127.0.0.1:8080/`.

#### 3. "Como redefinir a senha do usuário diretor?"
- No terminal com o ambiente ativado, execute:
  ```powershell
  python manage.py changepassword diretor
  ```
  Digite a nova senha desejada.

---

**Faculdade de Medicina (FAMED) — Universidade Federal do Pará (UFPA)**  
*Sistema de Gestão de Estágios de Férias e Extracurriculares*
