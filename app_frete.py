import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
import urllib.parse
import urllib.request
import io
import re

st.set_page_config(page_title="ACOMPANHAMENTO CONTROLE DE FRETE", layout="wide")

# ==========================================
# 1. CONTROLE DE TEMA NO TOPO (PADRÃO ESCURO)
# ==========================================
col_espaco_esq, col_titulo_topo, col_tema_topo = st.columns([1.5, 5, 1.5])

with col_titulo_topo:
    st.markdown(
        "<h2 style='text-align: center; margin: 0; padding-top: 6px; font-weight: 900; letter-spacing: 1px;'>ACOMPANHAMENTO CONTROLE DE FRETE</h2>",
        unsafe_allow_html=True
    )

with col_tema_topo:
    st.markdown("<span style='font-size: 12px; font-weight: 800; color: #9CA3AF; letter-spacing: 1px;'>TEMA DA TELA</span>", unsafe_allow_html=True)
    tema_selecionado = st.selectbox(
        "Tema da Tela",
        ["Escuro 🌙", "Claro ☀️"],
        index=0,
        label_visibility="collapsed"
    )

# ==========================================
# 2. ESTILOS CSS CONFORME O TEMA SELECIONADO
# ==========================================
if tema_selecionado == "Escuro 🌙":
    template_plotly = "plotly_dark"
    cor_texto = "#FFFFFF"
    cor_fundo_app = "#0B0F19"
    cor_fundo_sidebar = "#111827"
    cor_borda = "#1F2937"
    cor_subtexto = "#94A3B8"
    st.markdown(f"""
    <style>
        header[data-testid="stHeader"] {{ background-color: {cor_fundo_app} !important; }}
        .stApp {{ background-color: {cor_fundo_app} !important; color: {cor_texto} !important; }}
        [data-testid="stSidebar"] {{
            background-color: {cor_fundo_sidebar} !important;
            border-right: 1px solid {cor_borda} !important;
        }}
        [data-testid="stSidebar"] * {{
            color: #F3F4F6 !important;
            font-weight: 600 !important;
        }}
        .stTabs [data-baseweb="tab-list"] {{
            gap: 12px;
            border-bottom: 1px solid #333333;
        }}
        .stTabs [data-baseweb="tab"] {{
            height: 48px;
            white-space: pre-wrap;
            background-color: transparent;
            border-radius: 4px 4px 0px 0px;
            color: #7a828e;
            font-size: 14px;
            font-weight: 600;
            padding-left: 16px;
            padding-right: 16px;
        }}
        .stTabs [aria-selected="true"] {{
            color: #FF4B4B !important;
            border-bottom: 2px solid #FF4B4B !important;
            background-color: transparent !important;
        }}
        .botao-erro div.stDownloadButton > button {{
            background-color: #E53935 !important;
            color: #ffffff !important;
            font-weight: 700 !important;
            border-radius: 12px !important;
            border: none !important;
            height: 52px !important;
            width: 100% !important;
            font-size: 15px !important;
            transition: 0.3s !important;
            box-shadow: 0px 4px 10px rgba(229, 57, 53, 0.3) !important;
        }}
        .botao-erro div.stDownloadButton > button:hover {{
            background-color: #C62828 !important;
            color: #ffffff !important;
            border: none !important;
        }}
    </style>
    """, unsafe_allow_html=True)
else:
    template_plotly = "plotly_white"
    cor_texto = "#0F172A"
    cor_fundo_app = "#FFFFFF"
    cor_fundo_sidebar = "#F8FAFC"
    cor_borda = "#E2E8F0"
    cor_subtexto = "#475569"
    st.markdown(f"""
    <style>
        header[data-testid="stHeader"] {{ background-color: {cor_fundo_app} !important; }}
        .stApp {{ background-color: {cor_fundo_app} !important; color: {cor_texto} !important; }}
        [data-testid="stSidebar"] {{
            background-color: {cor_fundo_sidebar} !important;
            border-right: 1px solid {cor_borda} !important;
        }}
        [data-testid="stSidebar"] * {{
            color: {cor_texto} !important;
            font-weight: 600 !important;
        }}
        .stTabs [data-baseweb="tab-list"] {{
            gap: 12px;
            border-bottom: 1px solid #E2E8F0;
        }}
        .stTabs [data-baseweb="tab"] {{
            height: 48px;
            white-space: pre-wrap;
            background-color: transparent;
            border-radius: 4px 4px 0px 0px;
            color: #64748B;
            font-size: 14px;
            font-weight: 600;
            padding-left: 16px;
            padding-right: 16px;
        }}
        .stTabs [aria-selected="true"] {{
            color: #2563EB !important;
            border-bottom: 2px solid #2563EB !important;
            background-color: transparent !important;
        }}
        .botao-erro div.stDownloadButton > button {{
            background-color: #2563EB !important;
            color: #ffffff !important;
            font-weight: 700 !important;
            border-radius: 12px !important;
            border: none !important;
            height: 52px !important;
            width: 100% !important;
            font-size: 15px !important;
            transition: 0.3s !important;
        }}
        .botao-erro div.stDownloadButton > button:hover {{
            background-color: #1D4ED8 !important;
            color: #ffffff !important;
            border: none !important;
        }}
    </style>
    """, unsafe_allow_html=True)

# IDs das Folhas no Google Sheets
SHEET_ID_PRINCIPAL = "1i08DkGeUZQk0agkSb1ruLLEiOuUMST0XjHkosgaFN0I"
SHEET_ID_ERROS_ENVIOS = "1pwor7F7X1IX11BZBxTzrHkmZRlnyetfXOoLQCceQ_qQ"
SHEET_ID_ERROS_COLETA = "1Rn-aTD8ZWMNR5AKQT53jsdLbCXG-6p7ew5eWgIuzvgg"
SHEET_ID_ERROS_REVERSA = "1UcCslCquUeMrahcbkDDwZG7DUDqtHNuZrk-Vyvh7pbY"

def formatar_moeda(val, decimais=2):
    fmt = f"{{:,.{decimais}f}}"
    txt = fmt.format(abs(val)).replace(",", "X").replace(".", ",").replace("X", ".")
    return f"-R$ {txt}" if val < 0 else f"R$ {txt}"

UFS_VALIDAS = {
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA",
    "MT", "MS", "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN",
    "RS", "RO", "RR", "SC", "SP", "SE", "TO"
}

NOMES_UFS = {
    "AC": "ACRE", "AL": "ALAGOAS", "AP": "AMAPÁ", "AM": "AMAZONAS", "BA": "BAHIA",
    "CE": "CEARÁ", "DF": "DISTRITO FEDERAL", "ES": "ESPÍRITO SANTO", "GO": "GOIÁS",
    "MA": "MARANHÃO", "MT": "MATO GROSSO", "MS": "MATO GROSSO DO SUL", "MG": "MINAS GERAIS",
    "PA": "PARÁ", "PB": "PARAÍBA", "PR": "PARANÁ", "PE": "PERNAMBUCO", "PI": "PIAUÍ",
    "RJ": "RIO DE JANEIRO", "RN": "RIO GRANDE DO NORTE", "RS": "RIO GRANDE DO SUL",
    "RO": "RONDÔNIA", "RR": "RORAIMA", "SC": "SANTA CATARINA", "SP": "SÃO PAULO",
    "SE": "SERGIPE", "TO": "TOCANTINS"
}

def converter_numero_vetor(serie):
    return (
        serie.astype(str)
        .str.replace("R$", "", regex=False)
        .str.replace(" ", "", regex=False)
        .str.replace(".", "", regex=False)
        .str.replace(",", ".", regex=False)
        .pipe(pd.to_numeric, errors="coerce")
        .fillna(0.0)
    )

def normalizar_uf_texto(val):
    s = str(val).strip().upper()
    if s in UFS_VALIDAS:
        return s
    for pedaco in s.replace("-", " ").replace("/", " ").split():
        if pedaco in UFS_VALIDAS:
            return pedaco
    return None

def ler_csv_google_sheets(sheet_id, nome_aba=None, gid=None):
    if nome_aba:
        nome_encoded = urllib.parse.quote(nome_aba)
        url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet={nome_encoded}"
    elif gid is not None:
        url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"
    else:
        url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid=0"
    
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    )
    with urllib.request.urlopen(req) as resp:
        conteudo = resp.read().decode("utf-8")
    return pd.read_csv(io.StringIO(conteudo), low_memory=False)

@st.cache_data(ttl=1800, show_spinner="A carregar dados do Google Sheets...")
def carregar_dados():
    try:
        df_resumo = ler_csv_google_sheets(SHEET_ID_PRINCIPAL, nome_aba="RESUMO")
    except Exception:
        df_resumo = ler_csv_google_sheets(SHEET_ID_PRINCIPAL, gid=0)

    try:
        df_bp = ler_csv_google_sheets(SHEET_ID_PRINCIPAL, nome_aba="BP")
    except Exception:
        df_bp = pd.DataFrame()

    def padronizar_colunas(df):
        if df.empty:
            return df
        df.columns = (
            df.columns.astype(str)
            .str.strip()
            .str.lower()
            .str.replace("ã", "a", regex=False)
            .str.replace("á", "a", regex=False)
            .str.replace("ç", "c", regex=False)
            .str.replace("é", "e", regex=False)
            .str.replace("í", "i", regex=False)
            .str.replace("ó", "o", regex=False)
            .str.replace("ú", "u", regex=False)
        )
        return df

    df_resumo = padronizar_colunas(df_resumo)
    df_bp = padronizar_colunas(df_bp)

    for df in [df_resumo, df_bp]:
        if df.empty:
            continue
        col_periodo = next((c for c in df.columns if any(t in c for t in ["mes_ano_filtro", "mes_ano", "periodo"])), None)
        if col_periodo:
            df[col_periodo] = (
                df[col_periodo]
                .astype(str)
                .str.strip()
                .apply(lambda x: x[:7] if len(x) >= 7 and x[:4].isdigit() and x[4] == "-" else x)
            )

    if not df_resumo.empty:
        col_dup = next((c for c in df_resumo.columns if "duplicidade" in c), None)
        if col_dup:
            df_resumo = df_resumo[df_resumo[col_dup].astype(str).str.strip().str.upper() == "OK"]

        col_obs = next((c for c in df_resumo.columns if "observacao_uc" in c or "observacao" in c), None)
        if col_obs:
            valores_ok = {"DIMENSAO ZERADA", "DIMENSÃO ZERADA", "SEM NF ATIVA SAP", "OK"}
            df_resumo = df_resumo[df_resumo[col_obs].astype(str).str.strip().str.upper().isin(valores_ok)]

    for df in [df_resumo, df_bp]:
        if df.empty:
            continue
        for col in df.columns:
            if any(t in col for t in ["remessa", "qtd", "frete", "custo", "valor", "total", "item", "peca"]):
                df[col] = converter_numero_vetor(df[col])
            elif df[col].dtype == object:
                df[col] = df[col].fillna("").astype(str).str.strip().str.upper()

    col_uf_r = next((c for c in df_resumo.columns if c in ["uf", "estado", "sigla_uf"] or "uf" in c), None)
    if col_uf_r:
        df_resumo["uf_norm"] = df_resumo[col_uf_r].apply(normalizar_uf_texto)

    col_uf_b = next((c for c in df_bp.columns if c in ["uf", "estado", "sigla_uf"] or "uf" in c), None)
    if col_uf_b:
        df_bp["uf_norm"] = df_bp[col_uf_b].apply(normalizar_uf_texto)

    return df_resumo, df_bp

@st.cache_data(ttl=1800, show_spinner=False)
def carregar_csv_erros_sob_demanda(sheet_id):
    try:
        try:
            df = ler_csv_google_sheets(sheet_id, nome_aba="ERRO")
        except Exception:
            try:
                df = ler_csv_google_sheets(sheet_id, nome_aba="erro")
            except Exception:
                df = ler_csv_google_sheets(sheet_id, gid=0)
        return df.to_csv(index=False, sep=";", encoding="utf-8-sig").encode("utf-8-sig")
    except Exception:
        return b""

try:
    df_resumo_raw, df_bp_raw = carregar_dados()
except Exception as e:
    st.error(f"Erro ao carregar bases: {e}")
    st.stop()

def extrair_opcoes(termos_r, termos_b=None, padrao="Todos", exato=False):
    if termos_b is None:
        termos_b = termos_r
        
    valores = set()
    lixo = {"", "NAN", "NONE", "NULL", "TOTAL", "SUBTOTAL", "GERAL", "#N/A", "#REF!", "#VALOR!", "-", "--", "0", "0.0"}

    if exato:
        col_r = next((c for c in df_resumo_raw.columns if c in termos_r), None)
        col_b = next((c for c in df_bp_raw.columns if c in termos_b), None)
    else:
        col_r = next((c for c in df_resumo_raw.columns if any(t in c for t in termos_r)), None)
        col_b = next((c for c in df_bp_raw.columns if any(t in c for t in termos_b)), None)

    if col_r and not df_resumo_raw.empty:
        vals_r = df_resumo_raw[col_r].dropna().unique()
        for v in vals_r:
            v_str = str(v).strip()
            if v_str.upper() not in lixo and not v_str.startswith("="):
                valores.add(v_str)

    if col_b and not df_bp_raw.empty:
        vals_b = df_bp_raw[col_b].dropna().unique()
        for v in vals_b:
            v_str = str(v).strip()
            if v_str.upper() not in lixo and not v_str.startswith("="):
                valores.add(v_str)

    return [padrao] + sorted(list(valores))

# --- BARRA LATERAL ---
st.sidebar.title("🚚 Filtros Gerais")

opcoes_periodo = extrair_opcoes(["mes_ano_filtro", "mes_ano", "periodo"], padrao="Geral (Todos)")
opcoes_periodo = [p for p in opcoes_periodo if p == "Geral (Todos)" or bool(re.match(r"^\d{4}-\d{2}$", p))]
escolha_periodo = st.sidebar.selectbox("📅 Período (mes_ano_filtro):", opcoes_periodo, index=0)

opcoes_versao = extrair_opcoes(["versao"])
escolha_versao = st.sidebar.selectbox("📌 Versão:", opcoes_versao, index=0)

escolha_sheet_title = st.sidebar.selectbox("📑 Sheet Title:", extrair_opcoes(["sheet_title", "sheet"]), index=0)

opcoes_cobranca = extrair_opcoes(["case_rw"], ["tipo_cobranca"])
escolha_cobranca = st.sidebar.selectbox("📦 Cobrança (case_rw):", opcoes_cobranca, index=0)

escolha_transportador = st.sidebar.selectbox("🚛 Transportador:", extrair_opcoes(["transportador"]), index=0)
escolha_contrato = st.sidebar.selectbox("📄 Contrato:", extrair_opcoes(["contrato"]), index=0)
escolha_faixa_peso = st.sidebar.selectbox("⚖️ Faixa de Peso:", extrair_opcoes(["faixa_peso", "peso"]), index=0)
escolha_macroregiao = st.sidebar.selectbox("🗺️ Macroregião:", extrair_opcoes(["macroregiao"], exato=True), index=0)

if st.sidebar.button("🔄 Atualizar Base"):
    st.cache_data.clear()
    st.rerun()

def formatar_tabela_auditoria(df_aud, nome_chave, label_planejado="BP"):
    if df_aud.empty:
        return pd.DataFrame()
    
    col_rem_plan = f"Remessas {label_planejado}"
    col_share_plan = f"Share {label_planejado}"
    col_cmu_plan = f"CMU {label_planejado}"

    t = df_aud[["chave_join", "rem_b", "share_bp", "cmu_bp", "rem_r", "share_real", "cmu_real", "impacto"]].copy()
    t.columns = [nome_chave, col_rem_plan, col_share_plan, col_cmu_plan, "Remessas Real", "Share Real", "CMU Real", "Impacto (R$)"]
    
    tot_rem_b = df_aud["rem_b"].sum()
    tot_frete_b = df_aud["frete_b"].sum() if "frete_b" in df_aud.columns else 0.0
    cmu_bp_total = (tot_frete_b / tot_rem_b) if tot_rem_b > 0 else 0.0

    tot_rem_r = df_aud["rem_r"].sum()
    tot_frete_r = df_aud["frete_r"].sum() if "frete_r" in df_aud.columns else 0.0
    cmu_real_total = (tot_frete_r / tot_rem_r) if tot_rem_r > 0 else 0.0

    total_impacto = df_aud["impacto"].sum()

    t[col_share_plan] = (t[col_share_plan] * 100).map("{:.2f}%".format)
    t["Share Real"] = (t["Share Real"] * 100).map("{:.2f}%".format)
    t[col_cmu_plan] = t[col_cmu_plan].map("R$ {:.2f}".format)
    t["CMU Real"] = t["CMU Real"].map("R$ {:.2f}".format)
    t["Impacto (R$)"] = t["Impacto (R$)"].map("R$ {:.4f}".format)
    t[col_rem_plan] = t[col_rem_plan].map("{:,.0f}".format)
    t["Remessas Real"] = t["Remessas Real"].map("{:,.0f}".format)

    linha_total = pd.DataFrame([{
        nome_chave: "TOTAL GERAL",
        col_rem_plan: f"{tot_rem_b:,.0f}",
        col_share_plan: "100.00%",
        col_cmu_plan: f"R$ {cmu_bp_total:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
        "Remessas Real": f"{tot_rem_r:,.0f}",
        "Share Real": "100.00%",
        "CMU Real": f"R$ {cmu_real_total:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
        "Impacto (R$)": f"R$ {total_impacto:,.4f}".replace(",", "X").replace(".", ",").replace("X", ".")
    }])
    return pd.concat([t, linha_total], ignore_index=True)

def extrair_peso_minimo(texto):
    s = str(texto).upper().replace(",", ".").replace(" ", "")
    if "10" in s and ("+++" in s or ">" in s or "+" in s):
        return 999.0
    numeros = re.findall(r"\d+\.?\d*", s)
    if numeros:
        return float(numeros[0])
    return 500.0

def renderizar_modulo(etapa_filtro=None, tipo_filtro=None, titulo="", modo_praca=False):
    slug_id = titulo.lower().replace(" ", "_").replace("(", "").replace(")", "").replace("-", "_")

    df_r = df_resumo_raw
    df_b_raw_local = df_bp_raw

    v_str = str(escolha_versao).strip().upper()
    s_str = str(escolha_sheet_title).strip().upper()
    if any(k in v_str for k in ["FC", "FORECAST", "8+4", "4+8"]) or s_str.endswith("FC"):
        label_planejado = "FC"
    else:
        label_planejado = "BP"

    def aplicar_filtro_rapido(df, termos, val, padrao="Todos", exato=False):
        if val != padrao and not df.empty:
            if exato:
                col_alvo = next((c for c in df.columns if c in termos), None)
            else:
                col_alvo = next((c for c in df.columns if any(t in c for t in termos)), None)
            if col_alvo:
                return df[df[col_alvo] == str(val).strip().upper()]
        return df

    df_r_filtrado = df_r
    df_r_filtrado = aplicar_filtro_rapido(df_r_filtrado, ["mes_ano_filtro", "mes_ano", "periodo"], escolha_periodo, "Geral (Todos)")
    df_r_filtrado = aplicar_filtro_rapido(df_r_filtrado, ["sheet_title", "sheet"], escolha_sheet_title, "Todos")
    df_r_filtrado = aplicar_filtro_rapido(df_r_filtrado, ["case_rw"], escolha_cobranca, "Todos")
    df_r_filtrado = aplicar_filtro_rapido(df_r_filtrado, ["transportador"], escolha_transportador, "Todos")
    df_r_filtrado = aplicar_filtro_rapido(df_r_filtrado, ["contrato"], escolha_contrato, "Todos")
    df_r_filtrado = aplicar_filtro_rapido(df_r_filtrado, ["faixa_peso", "peso"], escolha_faixa_peso, "Todos")
    df_r_filtrado = aplicar_filtro_rapido(df_r_filtrado, ["macroregiao"], escolha_macroregiao, "Todos", exato=True)

    if etapa_filtro:
        df_r_filtrado = aplicar_filtro_rapido(df_r_filtrado, ["etapa"], etapa_filtro)
    if tipo_filtro:
        df_r_filtrado = aplicar_filtro_rapido(df_r_filtrado, ["tipo"], tipo_filtro)

    df_b_base = aplicar_filtro_rapido(df_b_raw_local, ["mes_ano_filtro", "mes_ano", "periodo"], escolha_periodo, "Geral (Todos)")
    df_b_base = aplicar_filtro_rapido(df_b_base, ["tipo_cobranca"], escolha_cobranca, "Todos")
    df_b_base = aplicar_filtro_rapido(df_b_base, ["transportador"], escolha_transportador, "Todos")
    df_b_base = aplicar_filtro_rapido(df_b_base, ["contrato"], escolha_contrato, "Todos")
    df_b_base = aplicar_filtro_rapido(df_b_base, ["faixa_peso", "peso"], escolha_faixa_peso, "Todos")
    df_b_base = aplicar_filtro_rapido(df_b_base, ["macroregiao"], escolha_macroregiao, "Todos", exato=True)

    if etapa_filtro:
        df_b_base = aplicar_filtro_rapido(df_b_base, ["etapa"], etapa_filtro)
    if tipo_filtro:
        df_b_base = aplicar_filtro_rapido(df_b_base, ["tipo_expedicao"], tipo_filtro)

    df_b = df_b_base
    df_b = aplicar_filtro_rapido(df_b, ["versao"], escolha_versao, "Todos")
    df_b = aplicar_filtro_rapido(df_b, ["sheet_title", "sheet"], escolha_sheet_title, "Todos")

    col_sheet_b = next((c for c in df_b_base.columns if "sheet" in c), None)
    col_versao_b = next((c for c in df_b_base.columns if "versao" in c), None)

    if col_sheet_b:
        mask_is_bp = df_b_base[col_sheet_b].str.endswith("BP")
        mask_is_fc = df_b_base[col_sheet_b].str.endswith("FC")
    elif col_versao_b:
        mask_is_bp = df_b_base[col_versao_b].str.contains("BP")
        mask_is_fc = df_b_base[col_versao_b].str.contains("FC|FORECAST|8+4")
    else:
        mask_is_bp = pd.Series(True, index=df_b_base.index)
        mask_is_fc = pd.Series(True, index=df_b_base.index)

    df_b_bp = df_b_base[mask_is_bp] if mask_is_bp.any() else df_b
    df_b_fc = df_b_base[mask_is_fc] if mask_is_fc.any() else df_b

    col_rem_r = next((c for c in df_r_filtrado.columns if any(t in c for t in ["remessa", "qtd"])), None)
    col_rem_b = next((c for c in df_b.columns if any(t in c for t in ["remessa", "qtd"])), None)
    col_frete_r = next((c for c in df_r_filtrado.columns if any(t in c for t in ["frete", "custo", "valor", "total"])), None)
    col_frete_b = next((c for c in df_b.columns if any(t in c for t in ["frete", "custo", "valor", "total"])), None)

    tot_rem_b = df_b[col_rem_b].sum() if col_rem_b and not df_b.empty else 0.0
    tot_frete_b = df_b[col_frete_b].sum() if col_frete_b and not df_b.empty else 0.0
    cmu_forecast = (tot_frete_b / tot_rem_b) if tot_rem_b > 0 else 0.0

    tot_rem_r = df_r_filtrado[col_rem_r].sum() if col_rem_r and not df_r_filtrado.empty else 0.0
    tot_frete_r = df_r_filtrado[col_frete_r].sum() if col_frete_r and not df_r_filtrado.empty else 0.0
    cmu_gerencial = (tot_frete_r / tot_rem_r) if tot_rem_r > 0 else 0.0

    def padronizar_chave_valor(val, tipo):
        s = str(val)
        if tipo == "faixa_peso":
            s = s.replace("KG", "").replace("KILOS", "").replace("G", "")
            s = s.replace(",", ".").replace(" ", "")
            s = s.replace("ATE", "0-").replace("ATÉ", "0-")
            s = s.replace("A", "-")
        return s

    def calcular_efeito_share_custom(df_real, df_plan, coluna_exata_r, coluna_exata_b, tipo_chave="padrao"):
        col_c_r = coluna_exata_r if coluna_exata_r in df_real.columns else next((c for c in df_real.columns if coluna_exata_r in c), None)
        col_c_b = coluna_exata_b if coluna_exata_b in df_plan.columns else next((c for c in df_plan.columns if coluna_exata_b in c), None)

        if not col_c_r or not col_c_b:
            return 0.0, pd.DataFrame()

        p = df_plan if not df_plan.empty else pd.DataFrame(columns=[col_c_b, col_rem_b, col_frete_b])
        v = df_real if not df_real.empty else pd.DataFrame(columns=[col_c_r, col_rem_r, col_frete_r])

        lixo = {"OK", "0", "0.0", "", "NAN", "NONE", "TOTAL", "SUBTOTAL"}
        p = p[~p[col_c_b].isin(lixo)].copy()
        v = v[~v[col_c_r].isin(lixo)].copy()

        p["chave_join"] = p[col_c_b].apply(lambda x: padronizar_chave_valor(x, tipo_chave))
        g_b = p.groupby("chave_join", as_index=False).agg(
            rem_b=(col_rem_b, "sum"),
            frete_b=(col_frete_b, "sum")
        )

        t_rem_b = g_b["rem_b"].sum() if not g_b.empty else 0.0
        g_b["share_bp"] = g_b["rem_b"] / t_rem_b if t_rem_b > 0 else 0.0
        g_b["cmu_bp"] = np.where(g_b["rem_b"] > 0, g_b["frete_b"] / g_b["rem_b"], 0.0)

        v["chave_join"] = v[col_c_r].apply(lambda x: padronizar_chave_valor(x, tipo_chave))
        g_r = v.groupby("chave_join", as_index=False).agg(
            rem_r=(col_rem_r, "sum"),
            frete_r=(col_frete_r, "sum")
        )

        t_rem_r = g_r["rem_r"].sum() if not g_r.empty else 0.0
        g_r["share_real"] = g_r["rem_r"] / t_rem_r if t_rem_r > 0 else 0.0
        g_r["cmu_real"] = np.where(g_r["rem_r"] > 0, g_r["frete_r"] / g_r["rem_r"], 0.0)

        m = pd.merge(g_b, g_r, on="chave_join", how="outer").fillna(0.0)
        m["impacto"] = (m["share_real"] - m["share_bp"]) * m["cmu_bp"]
        efeito = m["impacto"].sum()
        return float(efeito), m

    if modo_praca:
        delta_praca, df_aud_praca = calcular_efeito_share_custom(df_r_filtrado, df_b, "cidade_class", "cidade", tipo_chave="padrao")
        demais_impactos = cmu_gerencial - (cmu_forecast + delta_praca)

        categorias = [f"{label_planejado}", "Share Praça", "Demais impactos", "Gerencial"]
        medidas = ["absolute", "relative", "relative", "total"]
        valores = [cmu_forecast, delta_praca, demais_impactos, cmu_gerencial]
    else:
        delta_regiao, df_aud_reg = calcular_efeito_share_custom(df_r_filtrado, df_b, "macroregiao", "macroregiao", tipo_chave="macroregiao")
        delta_contrato, df_aud_con = calcular_efeito_share_custom(df_r_filtrado, df_b, "contrato", "contrato", tipo_chave="contrato")
        delta_peso, df_aud_peso = calcular_efeito_share_custom(df_r_filtrado, df_b, "faixa_peso", "faixa_peso", tipo_chave="faixa_peso")

        demais_impactos = cmu_gerencial - (cmu_forecast + delta_regiao + delta_contrato + delta_peso)

        categorias = [f"{label_planejado}", "Share Região", "Share Contrato", "Share Fx Peso", "Demais impactos", "Gerencial"]
        medidas = ["absolute", "relative", "relative", "relative", "relative", "total"]
        valores = [cmu_forecast, delta_regiao, delta_contrato, delta_peso, demais_impactos, cmu_gerencial]

    rotulos = [formatar_moeda(val, 2) for val in valores]

    col_m1, col_m2, col_m3, col_m4 = st.columns(4)
    col_m1.metric(f"CMU {label_planejado}", formatar_moeda(cmu_forecast, 2))
    col_m2.metric("CMU Gerencial", formatar_moeda(cmu_gerencial, 2))
    col_m3.metric("Remessas Real", f"{tot_rem_r:,.0f}".replace(",", "."))
    col_m4.metric(f"Remessas {label_planejado}", f"{tot_rem_b:,.0f}".replace(",", "."))

    fig = go.Figure(go.Waterfall(
        name="Impactos CMU",
        orientation="v",
        measure=medidas,
        x=categorias,
        y=valores,
        text=rotulos,
        textposition="outside",
        connector={"line": {"color": "#6c757d", "width": 1, "dash": "solid"}},
        decreasing={"marker": {"color": "#E65100"}},
        increasing={"marker": {"color": "#1B6CA8"}},
        totals={"marker": {"color": "#1B5E20"}}
    ))

    fig.update_layout(
        template=template_plotly,
        title=dict(text=f"Impactos CMU - {titulo}", y=0.98),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        yaxis_title="R$",
        height=480,
        margin=dict(l=40, r=40, t=60, b=40),
        xaxis=dict(showgrid=False),
        yaxis=dict(showgrid=False, zeroline=False)
    )

    st.plotly_chart(fig, use_container_width=True, key=f"waterfall_{slug_id}")

    st.markdown("### 🔎 Painéis de Auditoria por Campo")

    if modo_praca:
        titulo_praca = f"🏙️ Auditoria: Share Praça (cidade_class vs cidade) - Total: {formatar_moeda(delta_praca, 2)}"
        with st.expander(titulo_praca, expanded=False):
            if not df_aud_praca.empty:
                st.dataframe(formatar_tabela_auditoria(df_aud_praca, "Praça (Cidade)", label_planejado=label_planejado), use_container_width=True)
            else:
                st.info("Nenhum dado encontrado para cruzamento de Praça.")

        with st.expander(f"📊 Auditoria: Conciliação Geral ({titulo})", expanded=False):
            c_a1, c_a2 = st.columns(2)
            with c_a1:
                st.write("**Bases Consolidadas:**")
                st.write(f"- **Frete Total {label_planejado}:** {formatar_moeda(tot_frete_b, 2)}")
                st.write(f"- **Remessas {label_planejado}:** {tot_rem_b:,.0f}".replace(",", "."))
                st.write(f"- **CMU {label_planejado}:** {formatar_moeda(cmu_forecast, 4)}")
                st.write("---")
                st.write(f"- **Frete Total Real:** {formatar_moeda(tot_frete_r, 2)}")
                st.write(f"- **Remessas Real:** {tot_rem_r:,.0f}".replace(",", "."))
                st.write(f"- **CMU Gerencial:** {formatar_moeda(cmu_gerencial, 4)}")
            with c_a2:
                st.write("**Fechamento da Cascata:**")
                st.write(f"1. (+) {label_planejado}: {formatar_moeda(cmu_forecast, 4)}")
                st.write(f"2. (+/-) Share Praça: {formatar_moeda(delta_praca, 4)}")
                st.write(f"3. (+/-) Demais Impactos: {formatar_moeda(demais_impactos, 4)}")
                st.write(f"**(=) CMU Gerencial Fechado:** {formatar_moeda(cmu_gerencial, 4)}")
    else:
        titulo_reg = f"🗺️ 1. Auditoria: Share Região ({titulo}) - Total: {formatar_moeda(delta_regiao, 2)}"
        with st.expander(titulo_reg, expanded=False):
            if not df_aud_reg.empty:
                st.dataframe(formatar_tabela_auditoria(df_aud_reg, "Macroregião", label_planejado=label_planejado), use_container_width=True)

        titulo_con = f"📄 2. Auditoria: Share Contrato ({titulo}) - Total: {formatar_moeda(delta_contrato, 2)}"
        with st.expander(titulo_con, expanded=False):
            if not df_aud_con.empty:
                st.dataframe(formatar_tabela_auditoria(df_aud_con, "Contrato", label_planejado=label_planejado), use_container_width=True)

        titulo_peso = f"⚖️ 3. Auditoria: Share Faixa de Peso ({titulo}) - Total: {formatar_moeda(delta_peso, 2)}"
        with st.expander(titulo_peso, expanded=False):
            if not df_aud_peso.empty:
                st.dataframe(formatar_tabela_auditoria(df_aud_peso, "Faixa de Peso", label_planejado=label_planejado), use_container_width=True)

        with st.expander(f"📊 4. Auditoria: Conciliação Geral ({titulo})", expanded=False):
            c_a1, c_a2 = st.columns(2)
            with c_a1:
                st.write("**Bases Consolidadas:**")
                st.write(f"- **Frete Total {label_planejado}:** {formatar_moeda(tot_frete_b, 2)}")
                st.write(f"- **Remessas {label_planejado}:** {tot_rem_b:,.0f}".replace(",", "."))
                st.write(f"- **CMU {label_planejado}:** {formatar_moeda(cmu_forecast, 4)}")
                st.write("---")
                st.write(f"- **Frete Total Real:** {formatar_moeda(tot_frete_r, 2)}")
                st.write(f"- **Remessas Real:** {tot_rem_r:,.0f}".replace(",", "."))
                st.write(f"- **CMU Gerencial:** {formatar_moeda(cmu_gerencial, 4)}")
            with c_a2:
                st.write("**Fechamento da Cascata:**")
                st.write(f"1. (+) {label_planejado}: {formatar_moeda(cmu_forecast, 4)}")
                st.write(f"2. (+/-) Share Região: {formatar_moeda(delta_regiao, 4)}")
                st.write(f"3. (+/-) Share Contrato: {formatar_moeda(delta_contrato, 4)}")
                st.write(f"4. (+/-) Share Fx Peso: {formatar_moeda(delta_peso, 4)}")
                st.write(f"5. (+/-) Demais Impactos: {formatar_moeda(demais_impactos, 4)}")
                st.write(f"**(=) CMU Gerencial Fechado:** {formatar_moeda(cmu_gerencial, 4)}")

    col_transp_r = next((c for c in df_r_filtrado.columns if "transportador" in c), None)
    col_transp_b = next((c for c in df_b_base.columns if "transportador" in c), None)

    if col_transp_r and col_transp_b and not df_r_filtrado.empty:
        df_r_tr = df_r_filtrado.groupby(col_transp_r, as_index=False).agg(
            rem_r=(col_rem_r, "sum"),
            frete_r=(col_frete_r, "sum")
        )
        df_r_tr["cmu_real"] = np.where(df_r_tr["rem_r"] > 0, df_r_tr["frete_r"] / df_r_tr["rem_r"], 0.0)

        df_b_tr = df_b_bp.groupby(col_transp_b, as_index=False).agg(
            rem_b=(col_rem_b, "sum"),
            frete_b=(col_frete_b, "sum")
        )
        df_b_tr["cmu_bp"] = np.where(df_b_tr["rem_b"] > 0, df_b_tr["frete_b"] / df_b_tr["rem_b"], 0.0)

        df_fc_tr = df_b_fc.groupby(col_transp_b, as_index=False).agg(
            rem_fc=(col_rem_b, "sum"),
            frete_fc=(col_frete_b, "sum")
        )
        df_fc_tr["cmu_fc"] = np.where(df_fc_tr["rem_fc"] > 0, df_fc_tr["frete_fc"] / df_fc_tr["rem_fc"], 0.0)

        df_tr = pd.merge(df_r_tr, df_b_tr, left_on=col_transp_r, right_on=col_transp_b, how="outer")
        df_tr = pd.merge(df_tr, df_fc_tr, left_on=col_transp_r, right_on=col_transp_b, how="outer").fillna(0.0)
        df_tr["transportador"] = np.where(df_tr[col_transp_r] != 0.0, df_tr[col_transp_r], df_tr[col_transp_b])

        df_tr["vs_bp_pct"] = np.where((df_tr["cmu_bp"] > 0) & (df_tr["cmu_real"] > 0), ((df_tr["cmu_real"] - df_tr["cmu_bp"]) / df_tr["cmu_bp"]) * 100, np.nan)
        df_tr["vs_fc_pct"] = np.where((df_tr["cmu_fc"] > 0) & (df_tr["cmu_real"] > 0), ((df_tr["cmu_real"] - df_tr["cmu_fc"]) / df_tr["cmu_fc"]) * 100, np.nan)

        df_tr = df_tr.sort_values(by="cmu_real", ascending=False)
        df_tr = df_tr[(df_tr["rem_r"] > 0) | (df_tr["rem_b"] > 0) | (df_tr["rem_fc"] > 0)]

        st.markdown("---")
        st.markdown("### 🚛 Desempenho por Transportador")
        col_g1, col_g2 = st.columns(2)

        with col_g1:
            rotulos_cmu = [formatar_moeda(v, 2) if v > 0 else "" for v in df_tr["cmu_real"]]
            fig_cmu = go.Figure(go.Bar(
                x=df_tr["transportador"],
                y=df_tr["cmu_real"],
                text=rotulos_cmu,
                textposition="outside",
                marker_color="#2196F3"
            ))
            fig_cmu.update_layout(
                template=template_plotly,
                title=dict(text="Transportador - CMU Real", y=0.98),
                xaxis_title="Transportador",
                yaxis_title="CMU (Personalizado)",
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                height=450,
                margin=dict(l=40, r=40, t=60, b=40),
                xaxis=dict(showgrid=False),
                yaxis=dict(showgrid=False, zeroline=False)
            )
            st.plotly_chart(fig_cmu, use_container_width=True, key=f"cmu_transp_{slug_id}")

        with col_g2:
            fig_var = go.Figure()
            fig_var.add_trace(go.Bar(
                x=df_tr["transportador"],
                y=df_tr["vs_bp_pct"].fillna(0),
                name="vs BP (%)",
                text=[f"{v:.2f}%" if pd.notnull(v) and v != 0 else "" for v in df_tr["vs_bp_pct"]],
                textposition="outside",
                marker_color="#FFA000"
            ))
            fig_var.add_trace(go.Bar(
                x=df_tr["transportador"],
                y=df_tr["vs_fc_pct"].fillna(0),
                name="vs FC (%)",
                text=[f"{v:.2f}%" if pd.notnull(v) and v != 0 else "" for v in df_tr["vs_fc_pct"]],
                textposition="outside",
                marker_color="#7B1FA2"
            ))
            fig_var.update_layout(
                template=template_plotly,
                title=dict(text="Transportador - Variação CMU", y=0.98),
                barmode="group",
                xaxis_title="Transportador",
                yaxis_title="Variação (%)",
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                height=450,
                margin=dict(l=40, r=40, t=80, b=40),
                xaxis=dict(showgrid=False),
                yaxis=dict(showgrid=False, zeroline=False, ticksuffix="%"),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0)
            )
            st.plotly_chart(fig_var, use_container_width=True, key=f"var_transp_{slug_id}")

    if modo_praca:
        col_praca_r = "cidade_class" if "cidade_class" in df_r_filtrado.columns else next((c for c in df_r_filtrado.columns if c in ["cidade_class", "cidade"]), None)
        col_praca_b = "cidade" if "cidade" in df_b_base.columns else next((c for c in df_b_base.columns if c in ["cidade", "cidade_class"]), None)

        if col_praca_r and col_praca_b and not df_r_filtrado.empty:
            st.markdown("---")
            st.markdown("### 🏙️ Desempenho por Praça de Coleta")
            col_pr1, col_pr2 = st.columns(2)

            lixo_praca = {"OK", "0", "0.0", "", "NAN", "NONE", "TOTAL", "SUBTOTAL"}
            df_r_limpo = df_r_filtrado[~df_r_filtrado[col_praca_r].isin(lixo_praca)]
            df_bp_limpo = df_b_bp[~df_b_bp[col_praca_b].isin(lixo_praca)]
            df_fc_limpo = df_b_fc[~df_b_fc[col_praca_b].isin(lixo_praca)]

            df_r_pr = df_r_limpo.groupby(col_praca_r, as_index=False).agg(
                rem_r=(col_rem_r, "sum"),
                frete_r=(col_frete_r, "sum")
            )
            df_r_pr.rename(columns={col_praca_r: "chave_join"}, inplace=True)
            df_r_pr["cmu_real"] = np.where(df_r_pr["rem_r"] > 0, df_r_pr["frete_r"] / df_r_pr["rem_r"], 0.0)

            df_bp_pr = df_bp_limpo.groupby(col_praca_b, as_index=False).agg(
                rem_bp=(col_rem_b, "sum"),
                frete_bp=(col_frete_b, "sum")
            )
            df_bp_pr.rename(columns={col_praca_b: "chave_join"}, inplace=True)
            df_bp_pr["cmu_bp"] = np.where(df_bp_pr["rem_bp"] > 0, df_bp_pr["frete_bp"] / df_bp_pr["rem_bp"], 0.0)

            df_fc_pr = df_fc_limpo.groupby(col_praca_b, as_index=False).agg(
                rem_fc=(col_rem_b, "sum"),
                frete_fc=(col_frete_b, "sum")
            )
            df_fc_pr.rename(columns={col_praca_b: "chave_join"}, inplace=True)
            df_fc_pr["cmu_fc"] = np.where(df_fc_pr["rem_fc"] > 0, df_fc_pr["frete_fc"] / df_fc_pr["rem_fc"], 0.0)

            m_pr = pd.merge(df_r_pr, df_bp_pr, on="chave_join", how="outer")
            m_pr = pd.merge(m_pr, df_fc_pr, on="chave_join", how="outer").fillna(0.0)
            m_pr = m_pr.sort_values(by="cmu_real", ascending=False)
            m_pr = m_pr[(m_pr["rem_r"] > 0) | (m_pr["rem_bp"] > 0) | (m_pr["rem_fc"] > 0)]

            m_pr["vs_bp_pct"] = np.where((m_pr["cmu_bp"] > 0) & (m_pr["cmu_real"] > 0), ((m_pr["cmu_real"] - m_pr["cmu_bp"]) / m_pr["cmu_bp"]) * 100, np.nan)
            m_pr["vs_fc_pct"] = np.where((m_pr["cmu_fc"] > 0) & (m_pr["cmu_real"] > 0), ((m_pr["cmu_real"] - m_pr["cmu_fc"]) / m_pr["cmu_fc"]) * 100, np.nan)

            with col_pr1:
                rotulos_pr = [formatar_moeda(v, 2) if v > 0 else "" for v in m_pr["cmu_real"]]
                fig_cmu_pr = go.Figure(go.Bar(
                    x=m_pr["chave_join"],
                    y=m_pr["cmu_real"],
                    text=rotulos_pr,
                    textposition="outside",
                    marker_color="#2196F3"
                ))
                fig_cmu_pr.update_layout(
                    template=template_plotly,
                    title=dict(text="Praça de coleta", y=0.98),
                    xaxis_title="Praça de coleta",
                    yaxis_title="CMU (Personalizado)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    paper_bgcolor="rgba(0,0,0,0)",
                    height=450,
                    margin=dict(l=40, r=40, t=60, b=40),
                    xaxis=dict(showgrid=False),
                    yaxis=dict(showgrid=False, zeroline=False)
                )
                st.plotly_chart(fig_cmu_pr, use_container_width=True, key=f"cmu_praca_{slug_id}")

            with col_pr2:
                fig_var_pr = go.Figure()
                fig_var_pr.add_trace(go.Bar(
                    x=m_pr["chave_join"],
                    y=m_pr["vs_bp_pct"].fillna(0),
                    name="vs BP (%)",
                    text=[f"{v:.2f}%" if pd.notnull(v) and v != 0 else "" for v in m_pr["vs_bp_pct"]],
                    textposition="outside",
                    marker_color="#FFA000"
                ))
                fig_var_pr.add_trace(go.Bar(
                    x=m_pr["chave_join"],
                    y=m_pr["vs_fc_pct"].fillna(0),
                    name="vs FC (%)",
                    text=[f"{v:.2f}%" if pd.notnull(v) and v != 0 else "" for v in m_pr["vs_fc_pct"]],
                    textposition="outside",
                    marker_color="#7B1FA2"
                ))
                fig_var_pr.update_layout(
                    template=template_plotly,
                    title=dict(text="Praça de coleta", y=0.98),
                    barmode="group",
                    xaxis_title="Praça de coleta",
                    yaxis_title="Variação (%)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    paper_bgcolor="rgba(0,0,0,0)",
                    height=450,
                    margin=dict(l=40, r=40, t=80, b=40),
                    xaxis=dict(showgrid=False),
                    yaxis=dict(showgrid=False, zeroline=False, ticksuffix="%"),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0)
                )
                st.plotly_chart(fig_var_pr, use_container_width=True, key=f"var_praca_{slug_id}")

    else:
        col_con_r = next((c for c in df_r_filtrado.columns if "contrato" in c), None)
        col_con_b = next((c for c in df_b_base.columns if "contrato" in c), None)

        if col_con_r and col_con_b and not df_r_filtrado.empty:
            st.markdown("---")
            st.markdown("### 📄 Desempenho por Contrato")
            col_c1, col_c2, col_c3 = st.columns(3)

            df_r_con = df_r_filtrado.groupby(col_con_r, as_index=False).agg(frete_real=(col_frete_r, "sum"), rem_real=(col_rem_r, "sum"))
            df_r_con["cmu_real"] = np.where(df_r_con["rem_real"] > 0, df_r_con["frete_real"] / df_r_con["rem_real"], 0.0)

            with col_c1:
                fig_donut_con = px.pie(
                    df_r_con,
                    names=col_con_r,
                    values="frete_real",
                    hole=0.6,
                    title="Contrato (Tamanho: frete_realizado)",
                    color_discrete_sequence=["#00A4EF", "#FFB900", "#7FBA00", "#F25022"],
                    template=template_plotly
                )
                fig_donut_con.update_traces(
                    textposition='inside',
                    textinfo='percent+label',
                    insidetextorientation='horizontal'
                )
                fig_donut_con.update_layout(
                    plot_bgcolor="rgba(0,0,0,0)",
                    paper_bgcolor="rgba(0,0,0,0)",
                    height=420,
                    margin=dict(l=10, r=10, t=60, b=40),
                    legend=dict(orientation="h", yanchor="top", y=-0.05, xanchor="center", x=0.5)
                )
                st.plotly_chart(fig_donut_con, use_container_width=True, key=f"donut_con_{slug_id}")

            df_bp_con = df_b_bp.groupby(col_con_b, as_index=False).agg(frete_bp=(col_frete_b, "sum"), rem_bp=(col_rem_b, "sum"))
            df_bp_con["cmu_bp"] = np.where(df_bp_con["rem_bp"] > 0, df_bp_con["frete_bp"] / df_bp_con["rem_bp"], 0.0)

            df_fc_con = df_b_fc.groupby(col_con_b, as_index=False).agg(frete_fc=(col_frete_b, "sum"), rem_fc=(col_rem_b, "sum"))
            df_fc_con["cmu_fc"] = np.where(df_fc_con["rem_fc"] > 0, df_fc_con["frete_fc"] / df_fc_con["rem_fc"], 0.0)

            m_con = pd.merge(df_r_con, df_bp_con, left_on=col_con_r, right_on=col_con_b, how="outer")
            m_con = pd.merge(m_con, df_fc_con, left_on=col_con_r, right_on=col_con_b, how="outer").fillna(0.0)
            m_con["chave"] = np.where(m_con[col_con_r] != 0.0, m_con[col_con_r], m_con[col_con_b])
            m_con = m_con.sort_values(by="cmu_real", ascending=True)

            m_con["vs_bp_pct"] = np.where((m_con["cmu_bp"] > 0) & (m_con["cmu_real"] > 0), ((m_con["cmu_real"] - m_con["cmu_bp"]) / m_con["cmu_bp"]) * 100, np.nan)
            m_con["vs_fc_pct"] = np.where((m_con["cmu_fc"] > 0) & (m_con["cmu_real"] > 0), ((m_con["cmu_real"] - m_con["cmu_fc"]) / m_con["cmu_fc"]) * 100, np.nan)

            with col_c2:
                fig_bar_con = go.Figure()
                fig_bar_con.add_trace(go.Bar(x=m_con["chave"], y=m_con["cmu_real"], name="CMU", marker_color="#00A4EF", text=[formatar_moeda(v, 2) if v > 0 else "" for v in m_con["cmu_real"]], textposition="outside"))
                fig_bar_con.add_trace(go.Bar(x=m_con["chave"], y=m_con["cmu_bp"], name="CMU BP", marker_color="#FFB900", text=[formatar_moeda(v, 2) if v > 0 else "" for v in m_con["cmu_bp"]], textposition="outside"))
                fig_bar_con.add_trace(go.Bar(x=m_con["chave"], y=m_con["cmu_fc"], name="CMU FC", marker_color="#80397B", text=[formatar_moeda(v, 2) if v > 0 else "" for v in m_con["cmu_fc"]], textposition="outside"))
                fig_bar_con.update_layout(
                    template=template_plotly,
                    title=dict(text="Contrato - CMU vs BP e FC", y=0.98),
                    barmode="group",
                    height=420,
                    plot_bgcolor="rgba(0,0,0,0)",
                    paper_bgcolor="rgba(0,0,0,0)",
                    margin=dict(l=10, r=10, t=80, b=10),
                    yaxis=dict(showgrid=False, zeroline=False),
                    xaxis=dict(showgrid=False),
                    yaxis_title="R$",
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0)
                )
                st.plotly_chart(fig_bar_con, use_container_width=True, key=f"bar_cmu_con_{slug_id}")

            with col_c3:
                fig_var_con = go.Figure()
                fig_var_con.add_trace(go.Bar(x=m_con["chave"], y=m_con["vs_bp_pct"].fillna(0), name="vs BP (%)", marker_color="#FFB900", text=[f"{v:.2f}%" if pd.notnull(v) and v != 0 else "" for v in m_con["vs_bp_pct"]], textposition="outside"))
                fig_var_con.add_trace(go.Bar(x=m_con["chave"], y=m_con["vs_fc_pct"].fillna(0), name="vs FC (%)", marker_color="#80397B", text=[f"{v:.2f}%" if pd.notnull(v) and v != 0 else "" for v in m_con["vs_fc_pct"]], textposition="outside"))
                fig_var_con.update_layout(
                    template=template_plotly,
                    title=dict(text="Contrato - Variação %", y=0.98),
                    barmode="group",
                    height=420,
                    plot_bgcolor="rgba(0,0,0,0)",
                    paper_bgcolor="rgba(0,0,0,0)",
                    margin=dict(l=10, r=10, t=80, b=10),
                    yaxis=dict(ticksuffix="%", showgrid=False, zeroline=False),
                    xaxis=dict(showgrid=False),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0)
                )
                st.plotly_chart(fig_var_con, use_container_width=True, key=f"var_con_{slug_id}")

    col_peso_r = next((c for c in df_r_filtrado.columns if "faixa_peso" in c or "peso" in c), None)
    col_peso_b = next((c for c in df_b_base.columns if "faixa_peso" in c or "peso" in c), None)

    if col_peso_r and col_peso_b and not df_r_filtrado.empty:
        st.markdown("---")
        st.markdown("### ⚖️ Desempenho por Faixa de Peso")
        col_p1, col_p2, col_p3 = st.columns(3)

        df_r_p = df_r_filtrado.groupby(col_peso_r, as_index=False).agg(frete_real=(col_frete_r, "sum"), rem_real=(col_rem_r, "sum"))
        df_r_p["cmu_real"] = np.where(df_r_p["rem_real"] > 0, df_r_p["frete_real"] / df_r_p["rem_real"], 0.0)

        with col_p1:
            tot_frete_p = df_r_p["frete_real"].sum()
            rotulos_seguros = []
            for _, row in df_r_p.iterrows():
                pct = (row["frete_real"] / tot_frete_p * 100) if tot_frete_p > 0 else 0
                if pct >= 5.0:
                    rotulos_seguros.append(f"{row[col_peso_r]}<br>{pct:.1f}%")
                else:
                    rotulos_seguros.append("")

            fig_donut_p = go.Pie(
                labels=df_r_p[col_peso_r],
                values=df_r_p["frete_real"],
                hole=0.6,
                text=rotulos_seguros,
                textinfo='text',
                hoverinfo='label+percent+value',
                marker=dict(colors=px.colors.qualitative.Plotly)
            )
            fig_p = go.Figure(fig_donut_p)
            fig_p.update_layout(
                template=template_plotly,
                title=dict(text="Faixa de peso (Tamanho: frete_realizado)", y=0.98),
                height=420,
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                margin=dict(l=10, r=10, t=50, b=10),
                showlegend=False
            )
            st.plotly_chart(fig_p, use_container_width=True, key=f"donut_p_{slug_id}")

        df_bp_p = df_b_bp.groupby(col_peso_b, as_index=False).agg(frete_bp=(col_frete_b, "sum"), rem_bp=(col_rem_b, "sum"))
        df_bp_p["cmu_bp"] = np.where(df_bp_p["rem_bp"] > 0, df_bp_p["frete_bp"] / df_bp_p["rem_bp"], 0.0)

        df_fc_p = df_b_fc.groupby(col_peso_b, as_index=False).agg(frete_fc=(col_frete_b, "sum"), rem_fc=(col_rem_b, "sum"))
        df_fc_p["cmu_fc"] = np.where(df_fc_p["rem_fc"] > 0, df_fc_p["frete_fc"] / df_fc_p["rem_fc"], 0.0)

        m_p = pd.merge(df_r_p, df_bp_p, left_on=col_peso_r, right_on=col_peso_b, how="outer")
        m_p = pd.merge(m_p, df_fc_p, left_on=col_peso_r, right_on=col_peso_b, how="outer").fillna(0.0)
        m_p["chave"] = np.where(m_p[col_peso_r] != 0.0, m_p[col_peso_r], m_p[col_peso_b])

        m_p["ordem_peso"] = m_p["chave"].apply(extrair_peso_minimo)
        m_p = m_p.sort_values(by="ordem_peso", ascending=True)

        m_p["vs_bp_pct"] = np.where((m_p["cmu_bp"] > 0) & (m_p["cmu_real"] > 0), ((m_p["cmu_real"] - m_p["cmu_bp"]) / m_p["cmu_bp"]) * 100, np.nan)
        m_p["vs_fc_pct"] = np.where((m_p["cmu_fc"] > 0) & (m_p["cmu_real"] > 0), ((m_p["cmu_real"] - m_p["cmu_fc"]) / m_p["cmu_fc"]) * 100, np.nan)

        with col_p2:
            fig_bar_p = go.Figure()
            fig_bar_p.add_trace(go.Bar(
                x=m_p["chave"],
                y=m_p["cmu_real"],
                name="CMU",
                marker_color="#00A4EF",
                text=[formatar_moeda(v, 2) if v > 0 else "" for v in m_p["cmu_real"]],
                textposition="outside",
                textfont=dict(size=10)
            ))
            fig_bar_p.add_trace(go.Bar(
                x=m_p["chave"],
                y=m_p["cmu_bp"],
                name="CMU BP",
                marker_color="#FFB900",
                text=[formatar_moeda(v, 2) if v > 0 else "" for v in m_p["cmu_bp"]],
                textposition="outside",
                textfont=dict(size=10)
            ))
            fig_bar_p.add_trace(go.Bar(
                x=m_p["chave"],
                y=m_p["cmu_fc"],
                name="CMU FC",
                marker_color="#80397B",
                text=[formatar_moeda(v, 2) if v > 0 else "" for v in m_p["cmu_fc"]],
                textposition="outside",
                textfont=dict(size=10)
            ))
            fig_bar_p.update_layout(
                template=template_plotly,
                title=dict(text="Faixa de peso - CMU vs BP e FC", y=0.98),
                barmode="group",
                height=420,
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                margin=dict(l=10, r=10, t=80, b=10),
                yaxis_title="R$",
                xaxis=dict(tickangle=-30, showgrid=False),
                yaxis=dict(showgrid=False, zeroline=False),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0)
            )
            st.plotly_chart(fig_bar_p, use_container_width=True, key=f"bar_cmu_p_{slug_id}")

        with col_p3:
            fig_var_p = go.Figure()
            fig_var_p.add_trace(go.Bar(
                x=m_p["chave"],
                y=m_p["vs_bp_pct"].fillna(0),
                name="vs BP (%)",
                marker_color="#FFB900",
                text=[f"{v:.1f}%" if pd.notnull(v) and v != 0 else "" for v in m_p["vs_bp_pct"]],
                textposition="outside",
                textfont=dict(size=10)
            ))
            fig_var_p.add_trace(go.Bar(
                x=m_p["chave"],
                y=m_p["vs_fc_pct"].fillna(0),
                name="vs FC (%)",
                text=[f"{v:.2f}%" if pd.notnull(v) and v != 0 else "" for v in m_p["vs_fc_pct"]],
                textposition="outside",
                textfont=dict(size=10),
                marker_color="#80397B"
            ))
            fig_var_p.update_layout(
                template=template_plotly,
                title=dict(text="Faixa de peso - Variação %", y=0.98),
                barmode="group",
                height=420,
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                margin=dict(l=10, r=10, t=80, b=10),
                yaxis=dict(ticksuffix="%", showgrid=False, zeroline=False),
                xaxis=dict(tickangle=-30, showgrid=False),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0)
            )
            st.plotly_chart(fig_var_p, use_container_width=True, key=f"var_p_{slug_id}")

    st.markdown("### 🗺️ Análise Geográfica por Estado (UF)")

    if "uf_norm" in df_r_filtrado.columns and "uf_norm" in df_b_base.columns and not df_r_filtrado.empty:
        df_r_uf = df_r_filtrado.dropna(subset=["uf_norm"]).groupby("uf_norm", as_index=False).agg(
            rem_r=(col_rem_r, "sum"),
            frete_r=(col_frete_r, "sum")
        )
        df_r_uf["cmu_real"] = np.where(df_r_uf["rem_r"] > 0, df_r_uf["frete_r"] / df_r_uf["rem_r"], 0.0)

        df_bp_uf = df_b_bp.dropna(subset=["uf_norm"]).groupby("uf_norm", as_index=False).agg(
            rem_bp=(col_rem_b, "sum"),
            frete_bp=(col_frete_b, "sum")
        )
        df_bp_uf["cmu_bp"] = np.where(df_bp_uf["rem_bp"] > 0, df_bp_uf["frete_bp"] / df_bp_uf["rem_bp"], 0.0)

        df_fc_uf = df_b_fc.dropna(subset=["uf_norm"]).groupby("uf_norm", as_index=False).agg(
            rem_fc=(col_rem_b, "sum"),
            frete_fc=(col_frete_b, "sum")
        )
        df_fc_uf["cmu_fc"] = np.where(df_fc_uf["rem_fc"] > 0, df_fc_uf["frete_fc"] / df_fc_uf["rem_fc"], 0.0)

        df_mapa = pd.merge(df_r_uf, df_bp_uf, on="uf_norm", how="outer")
        df_mapa = pd.merge(df_mapa, df_fc_uf, on="uf_norm", how="outer").fillna(0.0)
        df_mapa = df_mapa[df_mapa["uf_norm"].isin(UFS_VALIDAS)].copy()

        df_mapa["nome_estado"] = df_mapa["uf_norm"].map(lambda x: NOMES_UFS.get(x, x))
        df_mapa["vs_bp_pct"] = np.where((df_mapa["cmu_bp"] > 0) & (df_mapa["cmu_real"] > 0), ((df_mapa["cmu_real"] - df_mapa["cmu_bp"]) / df_mapa["cmu_bp"]) * 100, 0.0)
        df_mapa["vs_fc_pct"] = np.where((df_mapa["cmu_fc"] > 0) & (df_mapa["cmu_real"] > 0), ((df_mapa["cmu_real"] - df_mapa["cmu_fc"]) / df_mapa["cmu_fc"]) * 100, 0.0)

        escala_azul_modelo = [
            [0.0, "#C7EAFB"],
            [0.35, "#70C2EE"],
            [0.70, "#2B8CBE"],
            [1.0, "#08589E"]
        ]

        escala_semaforo_modelo = [
            [0.0, "#238B45"],
            [0.40, "#74C476"],
            [0.50, "#FED976"],
            [0.70, "#FD8D3C"],
            [1.0, "#BD0026"]
        ]

        df_ord1 = df_mapa.sort_values(by="cmu_real", ascending=False)
        fig_geo1 = px.bar(
            df_ord1,
            x="uf_norm",
            y="cmu_real",
            color="cmu_real",
            color_continuous_scale=escala_azul_modelo,
            text=[formatar_moeda(v, 2) if v > 0 else "" for v in df_ord1["cmu_real"]],
            title="CMU por estado",
            template=template_plotly
        )
        fig_geo1.update_traces(textposition="outside", textfont=dict(size=11))
        fig_geo1.update_layout(
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            height=380,
            xaxis_title="UF",
            yaxis_title="CMU (R$)",
            margin=dict(l=20, r=40, t=50, b=40),
            xaxis=dict(showgrid=False, tickmode="linear"),
            yaxis=dict(showgrid=False, zeroline=False),
            coloraxis_colorbar=dict(title="R$", orientation="v", x=1.01, y=0.5, tickprefix="R$ ")
        )
        st.plotly_chart(fig_geo1, use_container_width=True, key=f"bar_geo_cmu_{slug_id}")

        df_ord2 = df_mapa.sort_values(by="vs_bp_pct", ascending=False)
        fig_geo2 = px.bar(
            df_ord2,
            x="uf_norm",
            y="vs_bp_pct",
            color="vs_bp_pct",
            color_continuous_scale=escala_semaforo_modelo,
            range_color=[-10.0, 10.0],
            text=[f"{v:.1f}%" if v != 0 else "" for v in df_ord2["vs_bp_pct"]],
            title="CMU vs CMU BP (%)",
            template=template_plotly
        )
        fig_geo2.update_traces(textposition="outside", textfont=dict(size=11))
        fig_geo2.update_layout(
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            height=380,
            xaxis_title="UF",
            yaxis_title="Variação (%)",
            margin=dict(l=20, r=40, t=50, b=40),
            xaxis=dict(showgrid=False, tickmode="linear"),
            yaxis=dict(showgrid=False, zeroline=False, ticksuffix="%"),
            coloraxis_colorbar=dict(title="%", orientation="v", x=1.01, y=0.5, ticksuffix="%")
        )
        st.plotly_chart(fig_geo2, use_container_width=True, key=f"bar_geo_bp_{slug_id}")

        df_ord3 = df_mapa.sort_values(by="vs_fc_pct", ascending=False)
        fig_geo3 = px.bar(
            df_ord3,
            x="uf_norm",
            y="vs_fc_pct",
            color="vs_fc_pct",
            color_continuous_scale=escala_semaforo_modelo,
            range_color=[-10.0, 10.0],
            text=[f"{v:.1f}%" if v != 0 else "" for v in df_ord3["vs_fc_pct"]],
            title="CMU vs CMU FC (%)",
            template=template_plotly
        )
        fig_geo3.update_traces(textposition="outside", textfont=dict(size=11))
        fig_geo3.update_layout(
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            height=380,
            xaxis_title="UF",
            yaxis_title="Variação (%)",
            margin=dict(l=20, r=40, t=50, b=40),
            xaxis=dict(showgrid=False, tickmode="linear"),
            yaxis=dict(showgrid=False, zeroline=False, ticksuffix="%"),
            coloraxis_colorbar=dict(title="%", orientation="v", x=1.01, y=0.5, ticksuffix="%")
        )
        st.plotly_chart(fig_geo3, use_container_width=True, key=f"bar_geo_fc_{slug_id}")

    df_r_puro_aba = df_resumo_raw
    if etapa_filtro:
        df_r_puro_aba = aplicar_filtro_rapido(df_r_puro_aba, ["etapa"], etapa_filtro)
    if tipo_filtro:
        df_r_puro_aba = aplicar_filtro_rapido(df_r_puro_aba, ["tipo"], tipo_filtro)

    col_itens_hist = next((c for c in df_r_puro_aba.columns if c in ["qtd_itens", "qtd_item", "itens", "item"]), None)
    col_rem_hist = next((c for c in df_r_puro_aba.columns if c in ["qtd_remessas", "qtd_remessa", "remessas", "remessa"]), None)
    col_per_hist = next((c for c in df_r_puro_aba.columns if c in ["mes_ano_filtro", "mes_ano", "periodo"]), None)

    if col_itens_hist and col_rem_hist and col_per_hist and not df_r_puro_aba.empty:
        regex_data = re.compile(r"^\d{4}-(?:0[1-9]|1[0-2])$")
        mask_data = df_r_puro_aba[col_per_hist].apply(lambda x: bool(regex_data.match(str(x))))
        df_hist = df_r_puro_aba[mask_data]

        if not df_hist.empty:
            df_serie = df_hist.groupby(col_per_hist, as_index=False).agg(
                total_itens=(col_itens_hist, "sum"),
                total_remessas=(col_rem_hist, "sum")
            )

            df_serie = df_serie.sort_values(by=col_per_hist)
            df_serie["itens_por_remessa"] = np.where(
                df_serie["total_remessas"] > 0,
                df_serie["total_itens"] / df_serie["total_remessas"],
                0.0
            )

            df_serie = df_serie[df_serie["total_remessas"] > 0]

            st.markdown("---")
            st.markdown("### 📈 Evolução Histórica: Itens por Remessa (qtd_itens / qtd_remessas)")

            fig_hist = go.Figure()
            fig_hist.add_trace(go.Scatter(
                x=df_serie[col_per_hist],
                y=df_serie["itens_por_remessa"],
                mode="lines+markers+text",
                name="Itens / Remessa",
                line=dict(color="#00A4EF", width=3),
                marker=dict(size=8, color="#00A4EF"),
                text=[f"{v:.2f}" for v in df_serie["itens_por_remessa"]],
                textposition="top center",
                textfont=dict(size=12, color="#ffffff" if tema_selecionado == "Escuro 🌙" else "#0F172A")
            ))

            fig_hist.update_layout(
                template=template_plotly,
                title=dict(text=f"Evolução Temporal: Itens por Remessa - {titulo} (Período Completo da Base)", y=0.98),
                xaxis_title="Período (mes_ano_filtro)",
                yaxis_title="Itens / Remessa",
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                height=380,
                margin=dict(l=20, r=40, t=60, b=40),
                xaxis=dict(
                    type='category',
                    categoryorder='category ascending',
                    showgrid=False
                ),
                yaxis=dict(showgrid=False, zeroline=False)
            )
            st.plotly_chart(fig_hist, use_container_width=True, key=f"serie_itens_rem_{slug_id}")

# --- CONTROLO RÁPIDO DE ABAS ---
lista_modulos = [
    "📊 Geral",
    "🛍️ ENVIOS RETAIL",
    "📦 ENVIOS FULL",
    "🚚 ENVIOS MILKRUN",
    "🚜 COLETA MILKRUN",
    "🔄 REVERSA RETAIL",
    "🔁 REVERSA FULL",
    "⚠️ INSUCESSO RETAIL",
    "⛔ INSUCESSO FULL"
]

aba_selecionada = st.radio(
    "Escolha a Visão Operacional:",
    lista_modulos,
    horizontal=True,
    label_visibility="collapsed"
)

if aba_selecionada == "📊 Geral":
    renderizar_modulo(etapa_filtro=None, tipo_filtro=None, titulo="Visão Consolidada", modo_praca=False)

    st.markdown("---")
    st.markdown("### 🚨 Relatórios de Erros Operacionais")

    col_btn1, col_btn2, col_btn3 = st.columns(3)
    
    with col_btn1:
        st.markdown('<div class="botao-erro">', unsafe_allow_html=True)
        st.download_button(
            label="📥 Descarregar Erros Envios (.csv)",
            data=carregar_csv_erros_sob_demanda(SHEET_ID_ERROS_ENVIOS),
            file_name="erros_envios.csv",
            mime="text/csv",
            key="btn_erro_envios"
        )
        st.markdown('</div>', unsafe_allow_html=True)

    with col_btn2:
        st.markdown('<div class="botao-erro">', unsafe_allow_html=True)
        st.download_button(
            label="📥 Descarregar Erros Coleta (.csv)",
            data=carregar_csv_erros_sob_demanda(SHEET_ID_ERROS_COLETA),
            file_name="erros_coleta.csv",
            mime="text/csv",
            key="btn_erro_coleta"
        )
        st.markdown('</div>', unsafe_allow_html=True)

    with col_btn3:
        st.markdown('<div class="botao-erro">', unsafe_allow_html=True)
        st.download_button(
            label="📥 Descarregar Erros Reversa/Insucesso (.csv)",
            data=carregar_csv_erros_sob_demanda(SHEET_ID_ERROS_REVERSA),
            file_name="erros_reversa_insucesso.csv",
            mime="text/csv",
            key="btn_erro_reversa"
        )
        st.markdown('</div>', unsafe_allow_html=True)

elif aba_selecionada == "🛍️ ENVIOS RETAIL":
    renderizar_modulo(etapa_filtro="ENVIOS", tipo_filtro="RETAIL", titulo="ENVIOS RETAIL", modo_praca=False)
elif aba_selecionada == "📦 ENVIOS FULL":
    renderizar_modulo(etapa_filtro="ENVIOS", tipo_filtro="FULL", titulo="ENVIOS FULL", modo_praca=False)
elif aba_selecionada == "🚚 ENVIOS MILKRUN":
    renderizar_modulo(etapa_filtro="ENVIOS", tipo_filtro="MARKETPLACE", titulo="ENVIOS MILKRUN", modo_praca=False)
elif aba_selecionada == "🚜 COLETA MILKRUN":
    renderizar_modulo(etapa_filtro="COLETA MR", tipo_filtro="MARKETPLACE", titulo="COLETA MILKRUN", modo_praca=True)
elif aba_selecionada == "🔄 REVERSA RETAIL":
    renderizar_modulo(etapa_filtro="REVERSA", tipo_filtro="RETAIL", titulo="REVERSA RETAIL", modo_praca=False)
elif aba_selecionada == "🔁 REVERSA FULL":
    renderizar_modulo(etapa_filtro="REVERSA", tipo_filtro="FULL", titulo="REVERSA FULL", modo_praca=False)
elif aba_selecionada == "⚠️ INSUCESSO RETAIL":
    renderizar_modulo(etapa_filtro="INSUCESSO", tipo_filtro="RETAIL", titulo="INSUCESSO RETAIL", modo_praca=False)
elif aba_selecionada == "⛔ INSUCESSO FULL":
    renderizar_modulo(etapa_filtro="INSUCESSO", tipo_filtro="RETAIL", titulo="INSUCESSO FULL", modo_praca=False)

st.markdown("---")
st.markdown("### 📑 Memorial de Cálculo: Entenda seus Indicadores de Operação")

st.markdown("""
**1. Métricas Principais de Custo e Performance**
* 💰 **CMU Gerencial (Custo Médio Unitário Real):** Custo médio de frete por remessa realizada na operação (Fórmula: $\\text{Frete Real Total} \\div \\text{Remessas Real Total}$).
* 🎯 **CMU Forecast / BP (Planejado):** Custo médio unitário orçado ou projetado na versão selecionada (Fórmula: $\\text{Frete Planejado} \\div \\text{Remessas Planejadas}$).
* ⚖️ **Variação % (vs BP e vs FC):** Mede o desvio relativo entre o realizado e o planejado (Fórmula: $[(\\text{CMU Real} - \\text{CMU Planejado}) \\div \\text{CMU Planejado}] \\times 100$). Valores negativos indicam economia de custo; valores positivos indicam custo acima do planejado.

**2. Impactos CMU (Gráfico Waterfall - Efeito Mix & Share)**
* 📊 **Share (Participação Volumétrica):** Percentual de remessas que uma categoria representa no volume total da operação (Fórmula: $\\text{Remessas da Categoria} \\div \\text{Remessas Totais}$).
* 🔄 **Efeito Share de Linha:** Mede quanto a mudança de mix entre Real e Planejado impactou o CMU unitário (Fórmula: $[\\text{Share Real} - \\text{Share Planejado}] \\times \\text{CMU Planejado}$).
* 🗺️ **Share Região / Contrato / Faixa de Peso / Praça:** Soma de todos os efeitos de share dentro da dimensão analisada. Revela se a operação migrou para regiões, contratos ou perfis de peso com custos diferentes do previsto.
* 🧩 **Demais Impactos:** Diferença residual entre a variação total do CMU e a soma dos efeitos de share identificados (Fórmula: $\\text{CMU Gerencial} - [\\text{CMU Forecast} + \\sum \\text{Efeitos Share}]$), garantindo o fechamento contábil exato da cascata.

**3. Desempenho por Dimensão Operacional**
* 🚛 **Transportador:** Compara o CMU Real de cada parceiro logístico contra a expectativa contratada (BP e FC), permitindo identificar transportadores com custos unitários fora da curva.
* 📄 **Contrato:** Avalia a distribuição de frete realizado em formato Donut e confronta o custo unitário entre as modalidades de contrato vigentes.
* ⚖️ **Faixa de Peso:** Agrupamento por degraus de peso tarifado (ex: $0 - 0.5\\text{ kg}$, $0.5 - 1.0\\text{ kg}$, etc.), ordenados numericamente do menor ao maior peso para monitorar distorções em pacotes pesados.
* 🏙️ **Praça de Coleta (Exclusivo Coleta MR):** Cruza `cidade_class` (Real) contra `cidade` (Planejado) para auditar desvios de contratação em cada polo de coleta.

**4. Análise Geográfica por Estado (UF)**
* 🗺️ **CMU por Estado:** Custo médio unitário realizado em cada uma das 27 Unidades Federativas do Brasil, ordenado dos estados mais caros para os mais econômicos.
* 🚦 **Desvio % por Estado (vs BP e vs FC):** Identifica os estados críticos com maior estouro orçamentário através de gradiente semafórico com intervalo de $-10\\%$ (Verde: economia) a $+10\\%$ (Vermelho: desvio crítico).

**5. Indicadores de Volume e Histórico**
* 📦 **Itens por Remessa (qtd_itens / qtd_remessas):** Mede a densidade média de produtos por pacote despachado ao longo de todos os meses da base (Fórmula: $\\sum \\text{qtd\\_itens} \\div \\sum \\text{qtd\\_remessas}$). Quedas nesse indicador elevam o CMU por diluir menos o custo fixo de frete.

**6. Bases de Dados e Relatórios de Erros (.csv)**
* 📥 **Filtro de Integridade SAP/UC:** Apenas registros com duplicidade `OK` e observação de dimensão/SAP válida são admitidos na apuração gerencial.
* 🚨 **Relatórios de Erros Operacionais:** Arquivos disponibilizados exclusivamente na visão Geral, extraídos em tempo real da aba `erro` das planilhas operacionais (Envios, Coleta e Reversa) para saneamento de cadastros e divergências de frete.
""")