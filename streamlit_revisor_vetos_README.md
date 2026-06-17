# Revisão de Classificação dos Vetos (Streamlit)

App para revisão jurídica dos vetos com backend de revisão em **Google Sheets** (e fallback para CSV local).

## Arquivos principais

- `streamlit_revisor_vetos.py`: aplicação Streamlit de revisão.
- `streamlit_revisor_requirements.txt`: dependências Python.
- `todos_vetos_classificados_tipologia_normalizadav2.csv`: base de vetos sugeridos.
- `.streamlit/secrets.toml`: configuração de segredo (chaves de acesso e credenciais).

Arquivos de revisão

- Principal: Google Sheets (recomendado para acesso remoto).
- Fallback local: `revisoes_vetos.csv` (gravado quando Sheets não estiver disponível).

## Passo 1 — preparar a Google Sheet

1. Crie uma planilha no Google Sheets com um nome de aba, por exemplo `revisoes_vetos`.
2. Crie uma conta de serviço no Google Cloud e gere uma chave JSON:
   - IAM & Admin → Service Accounts
   - Chave → JSON
3. Compartilhe a planilha com o `client_email` da service account, com permissão de **Editor**.
4. Copie o ID da planilha (entre `/d/` e `/edit` na URL).

## Passo 2 — preparar o `secrets.toml`

Exemplo de `/.streamlit/secrets.toml`:

```toml
review_password = "SUA_SENHA_SEGURA"

BASE_VETOS_CSV = "todos_vetos_classificados_tipologia_normalizadav2.csv"
REVISOES_CSV = "revisoes_vetos.csv"

# Opção 1: chave da planilha
GOOGLE_SHEET_ID = "SUA_GOOGLE_SHEET_ID"
GOOGLE_SHEET_NAME = "revisoes_vetos"

# Opção 2: pode usar GOOGLE_SHEET_URL no lugar de GOOGLE_SHEET_ID
# GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/..."

# Opção A: JSON inline (string única)
GOOGLE_SERVICE_ACCOUNT_JSON = '{"type":"service_account","project_id":"...","private_key_id":"...","private_key":"-----BEGIN PRIVATE KEY-----\\n...\\n-----END PRIVATE KEY-----\\n","client_email":"...","client_id":"...","auth_uri":"https://accounts.google.com/o/oauth2/auth","token_uri":"https://oauth2.googleapis.com/token","auth_provider_x509_cert_url":"https://www.googleapis.com/oauth2/v1/certs","client_x509_cert_url":"..."}'

# Opção B: bloco TOML estruturado
# [google_service_account]
# type = "service_account"
# project_id = "..."
# private_key_id = "..."
# private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
# client_email = "..."
# client_id = "..."
# auth_uri = "https://accounts.google.com/o/oauth2/auth"
# token_uri = "https://oauth2.googleapis.com/token"
# auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
# client_x509_cert_url = "..."
```

Recomendação: manter só uma fonte de credencial (`GOOGLE_SERVICE_ACCOUNT_JSON` ou `[google_service_account]`).

## Como rodar localmente

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r streamlit_revisor_requirements.txt
streamlit run streamlit_revisor_vetos.py
```

## Deploy no Streamlit Community Cloud (gratuito)

1. Suba o projeto no GitHub.
2. No Streamlit Cloud, clique em **New app**.
3. Aponte para:
   - `Repository`: seu repo
   - `Branch`: `main`
   - `Main file path`: `streamlit_revisor_vetos.py`
4. Use `streamlit_revisor_requirements.txt`.
5. Em **Secrets**, cole o conteúdo do `secrets.toml`.

Sem `review_password`, o app inicia sem trava de login.

## O que o usuário consegue fazer no app

- Filtrar por status, ano, tipologia, partido e texto.
- Abrir cada veto com sugestão automática e revisar:
  - status
  - motivos (multiseleção)
  - justificativa e observação
- Salvar revisão em tempo real no Google Sheets.
- Baixar CSV local com a coluna de revisões (fallback/backup).
