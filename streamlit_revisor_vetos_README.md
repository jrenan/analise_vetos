# Revisão de Classificação dos Vetos (Streamlit)

Aplicação para revisão jurídica dos vetos com **persistência em CSV**.

Agora o fluxo padrão é simples: sem Google Sheets.  
Cada pessoa pode definir seu nome no app e salvar em um arquivo próprio (`revisoes_vetos_<nome>.csv`).

## Arquivos principais

- `streamlit_revisor_vetos.py`: app Streamlit de revisão.
- `streamlit_revisor_requirements.txt`: dependências Python.
- `todos_vetos_classificados_tipologia_normalizadav2.csv`: base de vetos sugeridos.
- `revisoes_vetos_...csv`: arquivos de revisão gerados conforme a pessoa revisa.
- `.streamlit/secrets.toml`: configuração leve (apenas paths e senha opcional).

## Como executar localmente

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r streamlit_revisor_requirements.txt
streamlit run streamlit_revisor_vetos.py
```

## Configuração (`.streamlit/secrets.toml`)

```toml
review_password = "SUA_SENHA_SEGURA"

BASE_VETOS_CSV = "todos_vetos_classificados_tipologia_normalizadav2.csv"
REVISOES_CSV = "revisoes_vetos.csv"
```

## Como funciona no Cloud/Internet

1. Faça deploy no Streamlit Community Cloud apontando para `streamlit_revisor_vetos.py`.
2. Em **secrets**, cole o conteúdo acima.
3. Abra o app e, na barra lateral, informe seu nome.

## O que acontece ao revisar

- O app já usa o CSV da revisão selecionada para leitura e gravação.
- Ao clicar **Salvar revisão**, a linha é atualizada e persistida imediatamente no CSV.
- O CSV da pessoa pode ser baixado pelo botão **Baixar arquivo de revisões**.
- Se quiser recomeçar, use **Limpar revisão local**.

## O que ela pode fazer no app

- Filtrar por status, ano, tipologia, partido e busca textual.
- Abrir cada veto com texto original + sugestão automática.
- Revisar e editar:
  - status
  - motivos
  - justificativa
  - observação
- Gerar e baixar seu CSV com as revisões para enviar ao time.
