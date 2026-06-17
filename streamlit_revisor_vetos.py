"""Streamlit app para revisão humana das classificações dos vetos.

Objetivo:
- Mostrar lista de vetos já extraídos
- Exibir classificação sugerida (motivos_ids/justificativa)
- Permitir revisão e correção por uma colega de direito
- Salvar decisões em uma planilha Google Sheets (ou CSV de fallback)
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Dict, List

import json
import os
import pandas as pd
import streamlit as st

try:
    import gspread
    from google.oauth2.service_account import Credentials
except Exception:
    gspread = None
    Credentials = None


CATEGORY_LABELS: Dict[int, str] = {
    1: "Vício de iniciativa",
    2: "Inconstitucionalidade",
    3: "Ilegalidade",
    4: "Contrariedade ao interesse público",
    5: "Impacto orçamentário não previsto",
    6: "Redundância legislativa",
    7: "Inadequação técnica ou vício formal",
    8: "Competência legislativa indevida",
    9: "Ausência de relação bilateral em acordos internacionais",
    10: "Problemas relativos a logradouros ou próprios",
    11: "Problemas relativos à denominação",
    12: "Outros",
}

REVIEW_COLUMNS = [
    "uid",
    "status",
    "revisao_motivos_ids",
    "revisao_justificativa",
    "observacao",
    "revisor",
    "atualizado_em",
]


def get_secret(name: str, default: str) -> str:
    return st.secrets.get(name, default)


@st.cache_data
def load_data(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str).fillna("")
    if "uid" not in df.columns:
        df["uid"] = df["pl_completo"].fillna("").str.strip().replace(r"^$", pd.NA, regex=True)
        if df["uid"].isna().all():
            df["uid"] = df.index.astype(str)
        else:
            duplicates = df["uid"].duplicated(keep=False)
            if duplicates.any():
                df.loc[duplicates, "uid"] = (
                    df.loc[duplicates, "uid"].astype(str).fillna("")
                    + " | idx="
                    + df.loc[duplicates].index.astype(str)
                )

    # Colunas esperadas pela interface
    for col in [
        "tipologia_projeto_normalizada",
        "classificacao_partido",
        "motivos_ids",
        "justificativa",
        "ementa",
        "razoes_veto",
        "artigos_projeto",
        "ano_veto",
    ]:
        if col not in df.columns:
            df[col] = ""

    return df


def parse_motivos_ids(raw: str) -> List[int]:
    if not isinstance(raw, str):
        return []
    raw = raw.strip().strip("()")
    if not raw:
        return []
    out = []
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            val = int(part)
            if 1 <= val <= 12:
                out.append(val)
    return sorted(set(out))


def format_motivos(raw: str) -> str:
    ids = parse_motivos_ids(raw)
    if not ids:
        return "Sem sugestão"
    return ", ".join(f"{i} - {CATEGORY_LABELS.get(i, 'Desconhecida')}" for i in ids)


def normalize_csv_path(name: str) -> str:
    return get_secret(name, name)


def a1_column_letter(n: int) -> str:
    letters = ""
    while n > 0:
        n, rem = divmod(n - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def read_service_account_info():
    candidates = [
        "GOOGLE_SERVICE_ACCOUNT",
        "GOOGLE_SERVICE_ACCOUNT_JSON",
        "SERVICE_ACCOUNT_INFO",
        "GOOGLE_SERVICE_ACCOUNT_INFO",
    ]
    for key in candidates:
        if key in st.secrets:
            raw = st.secrets[key]
            if isinstance(raw, dict):
                return dict(raw)
            if isinstance(raw, str):
                try:
                    return json.loads(raw)
                except Exception:
                    pass
    if "google_service_account" in st.secrets and isinstance(
        st.secrets["google_service_account"], dict
    ):
        return dict(st.secrets["google_service_account"])
    return None


def initialize_google_sheet():
    """Retorna (worksheet, mensagem, ativo)."""
    if gspread is None or Credentials is None:
        return None, "Dependências Google Sheet não instaladas. Use CSV local (fallback).", False

    sheet_id = get_secret("GOOGLE_SHEET_ID", "")
    sheet_url = get_secret("GOOGLE_SHEET_URL", "")
    sheet_name = get_secret("GOOGLE_SHEET_NAME", "revisoes_vetos")
    service_info = read_service_account_info()
    if not service_info:
        return None, "Google Service Account não informado no secrets.", False
    if not sheet_id and not sheet_url:
        return None, "Defina GOOGLE_SHEET_ID ou GOOGLE_SHEET_URL no secrets.", False

    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        creds = Credentials.from_service_account_info(service_info, scopes=scopes)
        gc = gspread.authorize(creds)
        spreadsheet = gc.open_by_key(sheet_id) if sheet_id else gc.open_by_url(sheet_url)
        try:
            ws = spreadsheet.worksheet(sheet_name)
        except Exception:
            ws = spreadsheet.add_worksheet(title=sheet_name, rows=2000, cols=len(REVIEW_COLUMNS))
            ws.append_row(REVIEW_COLUMNS, value_input_option="RAW")

        values = ws.get_all_values()
        if not values:
            ws.append_row(REVIEW_COLUMNS, value_input_option="RAW")
        else:
            header = [h.strip() for h in values[0]]
            if "uid" not in header:
                ws.insert_row(REVIEW_COLUMNS, 1)
            else:
                # Corrige colunas faltantes na linha de cabeçalho preservando ordem principal.
                if any(col not in header for col in REVIEW_COLUMNS):
                    ws.update(f"A1:{a1_column_letter(len(REVIEW_COLUMNS))}1", [REVIEW_COLUMNS])

        return ws, "Conectado ao Google Sheets com sucesso.", True
    except Exception as e:
        return None, f"Falha ao conectar planilha: {e}", False


def read_reviews_from_sheet(worksheet) -> pd.DataFrame:
    if worksheet is None:
        return pd.DataFrame(columns=REVIEW_COLUMNS)
    values = worksheet.get_all_values()
    if not values:
        return pd.DataFrame(columns=REVIEW_COLUMNS)
    header = [c.strip() for c in values[0]]
    rows = values[1:]
    if not rows:
        return pd.DataFrame(columns=header if header else REVIEW_COLUMNS)
    df = pd.DataFrame(rows, columns=header).fillna("")
    for col in REVIEW_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    df = df[REVIEW_COLUMNS]
    return df


def upsert_review_in_sheet(worksheet, row_payload: Dict[str, str]) -> bool:
    if worksheet is None:
        return False
    values = worksheet.get_all_values()
    if not values:
        return False
    header = [h.strip() for h in values[0]]
    if "uid" not in header:
        return False
    uid_index = header.index("uid")
    target_row = len(values) + 1
    uid_target = str(row_payload.get("uid", ""))
    for i, row in enumerate(values[1:], start=2):
        if uid_index < len(row) and row[uid_index] == uid_target:
            target_row = i
            break

    row_values = [str(row_payload.get(col, "")) for col in REVIEW_COLUMNS]
    final_col = a1_column_letter(len(REVIEW_COLUMNS))
    worksheet.update(
        f"A{target_row}:{final_col}{target_row}",
        [row_values],
        value_input_option="RAW",
    )
    return True


def load_reviews_from_csv(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        return pd.DataFrame(columns=REVIEW_COLUMNS)
    return pd.read_csv(path, dtype=str).fillna("")


def save_reviews_to_csv(path: str, review_df: pd.DataFrame) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    review_df.to_csv(path, index=False, encoding="utf-8")


def merge_sources(base_df: pd.DataFrame, reviews_df: pd.DataFrame) -> pd.DataFrame:
    merged = base_df.merge(reviews_df, on="uid", how="left")
    merged["status"] = merged["status"].fillna("Pendente")
    merged["revisao_motivos_ids"] = merged["revisao_motivos_ids"].fillna("")
    merged["revisao_justificativa"] = merged["revisao_justificativa"].fillna("")
    merged["observacao"] = merged["observacao"].fillna("")
    merged["revisor"] = merged["revisor"].fillna("")
    merged["atualizado_em"] = merged["atualizado_em"].fillna("")

    merged["motivos_sugeridos"] = merged["motivos_ids"].apply(format_motivos)
    merged["flag_prioridade"] = merged.apply(needs_attention, axis=1)
    return merged


def needs_attention(row: pd.Series) -> str:
    if row["status"] in ("Pendente", ""):
        return "Pendente"
    if row["status"] != "Aprovado":
        return "Revisar"
    sugeridos = parse_motivos_ids(row.get("motivos_ids", ""))
    revisado = parse_motivos_ids(row.get("revisao_motivos_ids", ""))
    if len(sugeridos) >= 3:
        return "Revisar"
    if not revisado:
        return "Revisar"
    if len(row.get("revisao_justificativa", "")) < 12:
        return "Revisar"
    return "Aprovado"


def apply_password_gate() -> bool:
    password = st.secrets.get("review_password", "")
    if not password:
        return True
    if st.session_state.get("reviewer_authed"):
        return True
    value = st.text_input("Senha de revisão", type="password")
    if st.button("Entrar"):
        if value == password:
            st.session_state["reviewer_authed"] = True
            st.success("Acesso liberado.")
            st.rerun()
        else:
            st.error("Senha incorreta.")
    return False


def build_display_table(df: pd.DataFrame) -> pd.DataFrame:
    view = df.copy()
    view["classificacao_atual"] = view["revisao_motivos_ids"].replace({"": "(sem revisão)"})
    return view[
        [
            "uid",
            "pl_completo",
            "ano_veto",
            "tipologia_projeto_normalizada",
            "classificacao_partido",
            "motivos_sugeridos",
            "classificacao_atual",
            "status",
            "revisor",
            "flag_prioridade",
        ]
    ]


def main() -> None:
    st.set_page_config(page_title="Revisão de Classificação dos Vetos", layout="wide")
    st.title("Revisão de classificações dos vetos")
    st.caption(
        "Interface de validação jurídica para ajustar as categorias dos vetos."
    )

    if not apply_password_gate():
        st.stop()

    # Base de dados (pode ser CSV consolidado local)
    base_path = normalize_csv_path("BASE_VETOS_CSV")
    review_csv_path = normalize_csv_path("REVISOES_CSV")

    # Tenta backend Sheets primeiro
    worksheet, backend_msg, use_sheet = initialize_google_sheet()
    st.sidebar.markdown(f"**Backend de revisão:** {'Google Sheets' if use_sheet else 'CSV local'}")
    st.sidebar.caption(backend_msg)

    base_df = load_data(base_path)

    if use_sheet:
        reviews_df = read_reviews_from_sheet(worksheet)
    else:
        reviews_df = load_reviews_from_csv(review_csv_path)

    merged = merge_sources(base_df, reviews_df)

    st.sidebar.header("Filtros")
    status_options = ["Todos", "Pendente", "Aprovado", "Corrigir", "Revisar"]
    status_filter = st.sidebar.multiselect(
        "Status",
        options=status_options,
        default=["Pendente", "Corrigir", "Revisar"],
    )

    anos = sorted([x for x in merged["ano_veto"].dropna().unique() if x != ""])
    ano_filter = st.sidebar.multiselect("Ano do veto", options=anos, default=anos)
    tipologia = sorted(
        [x for x in merged["tipologia_projeto_normalizada"].dropna().unique() if x != ""]
    )
    tipologia_filter = st.sidebar.multiselect(
        "Tipologia normalizada", options=tipologia, default=tipologia
    )
    partido_filter = st.sidebar.selectbox(
        "Classificação do partido",
        options=["Todos"] + sorted(
            [x for x in merged["classificacao_partido"].dropna().unique() if x != ""]
        ),
        index=0,
    )
    mostrar_apenas_prioritarios = st.sidebar.toggle(
        "Somente itens prioritários", value=False
    )
    texto_busca = st.sidebar.text_input("Buscar por PL/ementa/razões")

    candidato = merged.copy()
    if "Pendente" not in status_filter and "Todos" not in status_filter:
        candidato = candidato[candidato["status"].isin(status_filter)]
    candidato = candidato[candidato["ano_veto"].isin(ano_filter)]
    candidato = candidato[candidato["tipologia_projeto_normalizada"].isin(tipologia_filter)]
    if partido_filter != "Todos":
        candidato = candidato[candidato["classificacao_partido"] == partido_filter]
    if mostrar_apenas_prioritarios:
        candidato = candidato[candidato["flag_prioridade"] == "Revisar"]
    if texto_busca.strip():
        q = texto_busca.lower()
        candidato = candidato[
            candidato["pl_completo"].str.lower().str.contains(q, na=False)
            | candidato["ementa"].str.lower().str.contains(q, na=False)
            | candidato["razoes_veto"].str.lower().str.contains(q, na=False)
        ]

    kpi_cols = st.columns(5)
    kpi_cols[0].metric("Total filtrado", len(candidato))
    kpi_cols[1].metric("Pendentes", int((candidato["status"] == "Pendente").sum()))
    kpi_cols[2].metric("Aprovados", int((candidato["status"] == "Aprovado").sum()))
    kpi_cols[3].metric(
        "Prioritários", int((candidato["flag_prioridade"] == "Revisar").sum())
    )
    kpi_cols[4].metric("Com revisão salva", int((candidato["status"] != "Pendente").sum()))

    st.subheader("Fila de revisão")
    tabela = build_display_table(candidato).copy()
    st.dataframe(tabela)

    st.markdown("---")
    st.subheader("Detalhe do veto selecionado")

    if candidato.empty:
        st.info("Nenhum registro com os filtros atuais.")
        return

    label_map = {
        row["uid"]: f"{row['pl_completo']} — {str(row['ementa'])[:100]}..."
        for _, row in candidato.iterrows()
    }
    selected_uid = st.selectbox(
        "Escolha o veto para revisar",
        options=list(candidato["uid"]),
        format_func=lambda uid: label_map.get(uid, uid),
    )
    selected_row = candidato[candidato["uid"] == selected_uid].iloc[0]

    left, right = st.columns([1.1, 1])
    with left:
        st.text_input("PL", value=selected_row.get("pl_completo", ""), disabled=True)
        st.text_area(
            "Ementa",
            value=selected_row.get("ementa", ""),
            height=140,
            disabled=True,
        )
        st.text_area(
            "Razões do veto",
            value=selected_row.get("razoes_veto", ""),
            height=170,
            disabled=True,
        )
        with st.expander("Artigos do projeto"):
            st.text_area(
                "Artigos",
                value=selected_row.get("artigos_projeto", ""),
                height=200,
                disabled=True,
            )
    with right:
        st.markdown("### Classificação atual (automática)")
        st.markdown(format_motivos(selected_row.get("motivos_ids", "")))
        st.markdown("### Justificativa automática")
        st.write(selected_row.get("justificativa", "Sem justificativa automática."))

    st.markdown("### Minha revisão")
    suggested = parse_motivos_ids(selected_row.get("motivos_ids", ""))
    current = parse_motivos_ids(selected_row.get("revisao_motivos_ids", ""))
    current = current or suggested

    with st.form("form_revisao", clear_on_submit=False):
        novos_motivos = st.multiselect(
            "Categorias finais",
            options=list(CATEGORY_LABELS.keys()),
            default=current,
            format_func=lambda c: f"{c} - {CATEGORY_LABELS.get(c, '')}",
        )
        justificativa_humana = st.text_area(
            "Justificativa da revisão",
            value=selected_row.get("revisao_justificativa", ""),
            height=150,
            help="Escreva uma justificativa curta e objetiva se fizer ajuste.",
        )
        observacao = st.text_area(
            "Observação (opcional)",
            value=selected_row.get("observacao", ""),
            height=80,
        )
        status = st.selectbox(
            "Status",
            options=["Pendente", "Aprovado", "Corrigir", "Revisar"],
            index=["Pendente", "Aprovado", "Corrigir", "Revisar"].index(
                selected_row.get("status", "Pendente")
                if selected_row.get("status", "Pendente") in ["Pendente", "Aprovado", "Corrigir", "Revisar"]
                else "Pendente"
            ),
        )
        revisor = st.text_input(
            "Quem revisou",
            value=selected_row.get("revisor", ""),
            placeholder="Ex.: Maria Souza",
        )

        if st.form_submit_button("Salvar revisão"):
            if not novos_motivos:
                st.warning("Selecione pelo menos uma categoria antes de salvar.")
            else:
                normalized = f"({','.join(str(int(x)) for x in sorted(set(novos_motivos)) )})"
                review_payload = {
                    "uid": selected_uid,
                    "status": status,
                    "revisao_motivos_ids": normalized,
                    "revisao_justificativa": justificativa_humana.strip(),
                    "observacao": observacao.strip(),
                    "revisor": revisor.strip(),
                    "atualizado_em": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }

                if use_sheet and worksheet is not None:
                    ok = upsert_review_in_sheet(worksheet, review_payload)
                    if ok:
                        st.success("Revisão salva no Google Sheets.")
                    else:
                        st.error("Não foi possível salvar no Google Sheets. Ajuste sua configuração.")
                else:
                    existing = reviews_df
                    if "uid" not in existing.columns:
                        existing = pd.DataFrame(columns=REVIEW_COLUMNS)
                    existing = existing[existing["uid"] != selected_uid]
                    existing = pd.concat(
                        [existing, pd.DataFrame([review_payload])], ignore_index=True
                    )
                    save_reviews_to_csv(review_csv_path, existing)
                    st.success("Revisão salva em CSV local.")
                st.rerun()

    st.markdown("---")
    st.subheader("Exportar revisão")
    reviews_final = (
        read_reviews_from_sheet(worksheet)
        if use_sheet
        else load_reviews_from_csv(review_csv_path)
    )
    st.download_button(
        "Baixar arquivo de revisões",
        data=reviews_final.to_csv(index=False).encode("utf-8"),
        file_name="revisoes_vetos.csv",
        mime="text/csv",
    )

    if not reviews_final.empty:
        st.dataframe(reviews_final, use_container_width=True)


if __name__ == "__main__":
    main()

