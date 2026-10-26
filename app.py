from datetime import datetime, timedelta
import io
import urllib.parse
import urllib.request
import warnings
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

warnings.filterwarnings("ignore")

st.set_page_config(page_title="Dashboard Sellers - Redshift", layout="wide")

# ==========================================
# 1. CONFIGURAÇÃO E AUTENTICAÇÃO PERSISTENTE
# ==========================================

TEMPO_EXPIRED_MINUTOS = 10

SHEET_ID_AUTH = "1WuROB09uYwPUeMaG7fS3CroqPFB9cEXtolcgRoA6erY"
URL_CSV_GOOGLE_SHEETS = f"https://docs.google.com/spreadsheets/d/{SHEET_ID_AUTH}/export?format=csv&gid=0"
URL_WEBAPP_GOOGLE_SCRIPT = "https://script.google.com/macros/s/AKfycbyvMmlYokWB2PpkxkewxpNAdGCKQmQ_S13ybz0qmqaCvgS77_HVhBtk-ftXukSCcYGX/exec"


@st.cache_data(ttl=600)
def carregar_credenciais_google():
    try:
        requisicao = urllib.request.Request(
            URL_CSV_GOOGLE_SHEETS,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        )
        with urllib.request.urlopen(requisicao) as resposta:
            conteudo_csv = resposta.read().decode("utf-8")

        df_logins = pd.read_csv(io.StringIO(conteudo_csv))
        df_logins['LOGIN'] = df_logins['LOGIN'].astype(str).str.strip()
        df_logins['SENHA'] = df_logins['SENHA'].astype(str).str.strip()
        df_logins['EMPRESA'] = df_logins['EMPRESA'].astype(str).str.strip()

        credenciais = {}
        for _, linha in df_logins.iterrows():
            credenciais[linha['LOGIN']] = {
                'senha': linha['SENHA'],
                'empresa': linha['EMPRESA']
            }
        return credenciais
    except Exception as e:
        st.error(f"Erro ao ligar à folha de autenticação: {e}")
        return {}


def registrar_acesso_google_sheets(login, empresa):
    try:
        data_hora_atual = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        parametros = urllib.parse.urlencode({
            "login": login,
            "empresa": empresa,
            "data_acesso": data_hora_atual
        })
        url_completa = f"{URL_WEBAPP_GOOGLE_SCRIPT}?{parametros}"
        req = urllib.request.Request(
            url_completa,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        )
        with urllib.request.urlopen(req) as resposta:
            pass
    except Exception:
        pass


def fazer_logout():
    st.session_state["autenticado"] = False
    st.session_state["usuario_logado"] = None
    st.session_state["empresa_logada"] = None
    st.session_state["ultima_atividade"] = None
    st.query_params.clear()


def validar_e_restaurar_sessao():
    agora = datetime.now()
    params = st.query_params
    if "user" in params and "empresa" in params and "time" in params:
        try:
            ultima_atividade = datetime.fromtimestamp(float(params["time"]))
            if agora - ultima_atividade <= timedelta(minutes=TEMPO_EXPIRED_MINUTOS):
                st.session_state["autenticado"] = True
                st.session_state["usuario_logado"] = params["user"]
                st.session_state["empresa_logada"] = params["empresa"]
                st.session_state["ultima_atividade"] = agora
                st.query_params["time"] = str(agora.timestamp())
                return True
            else:
                fazer_logout()
                st.warning("⚠️ A sua sessão expirou por inatividade (10 minutos). Por favor, faça login novamente.")
                return False
        except Exception:
            fazer_logout()
            return False

    if st.session_state.get("autenticado", False):
        ultima_atividade = st.session_state.get("ultima_atividade")
        if ultima_atividade and (agora - ultima_atividade > timedelta(minutes=TEMPO_EXPIRED_MINUTOS)):
            fazer_logout()
            st.warning("⚠️ A sua sessão expirou por inatividade (10 minutos). Por favor, faça login novamente.")
            return False
        else:
            st.session_state["ultima_atividade"] = agora
            st.query_params["time"] = str(agora.timestamp())
            return True

    return False


def verificar_login_google():
    usuario_input = st.session_state.get("campo_usuario", "").strip()
    senha_input = st.session_state.get("campo_senha", "").strip()
    credenciais_validas = carregar_credenciais_google()

    if usuario_input in credenciais_validas and credenciais_validas[usuario_input]['senha'] == senha_input:
        empresa_logada = credenciais_validas[usuario_input]['empresa']
        agora = datetime.now()

        st.session_state["autenticado"] = True
        st.session_state["usuario_logado"] = usuario_input
        st.session_state["empresa_logada"] = empresa_logada
        st.session_state["ultima_atividade"] = agora

        st.query_params["user"] = usuario_input
        st.query_params["empresa"] = empresa_logada
        st.query_params["time"] = str(agora.timestamp())

        registrar_acesso_google_sheets(usuario_input, empresa_logada)
        st.session_state["campo_usuario"] = ""
        st.session_state["campo_senha"] = ""
    else:
        st.error("❌ Utilizador ou palavra-passe incorretos!")


@st.cache_data
def converter_df_para_csv(df):
    return df.to_csv(index=False, sep=';', encoding='utf-8-sig').encode('utf-8-sig')


esta_autenticado = validar_e_restaurar_sessao()


# ==========================================
# 2. TELA DE LOGIN
# ==========================================
if not esta_autenticado:
    st.markdown("<h2 style='text-align: center;'>🔒 Acesso Restrito ao Dashboard</h2>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: gray;'>Insira os seus dados cadastrados na folha de acessos.</p>", unsafe_allow_html=True)
    st.write("---")

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.text_input("Utilizador / Login", key="campo_usuario")
        st.text_input("Palavra-passe", type="password", key="campo_senha")
        st.button("Entrar", on_click=verificar_login_google, use_container_width=True)

# ==========================================
# 3. CONTEÚDO DO DASHBOARD
# ==========================================
else:
    empresa_usuario = st.session_state.get("empresa_logada", "").strip()

    st.sidebar.title("Perfil")
    st.sidebar.write(f"👤 **Utilizador:** {st.session_state.get('usuario_logado', '')}")
    st.sidebar.write(f"🏢 **Empresa:** {empresa_usuario}")
    st.sidebar.button("🚪 Sair / Logout", on_click=fazer_logout, key="btn_logout")

    # ==========================================
    # CARREGAMENTO DE DADOS DE ALTA PERFORMANCE
    # ==========================================
    PLANILHAS_REVERSA_BASE = [
        {"id": "1tYkxqGCSan5C7wAjtqKeKpOE2OeGCgrzSynMaXVBaKU", "gid": "0"},
        {"id": "10zd0gTWei38fpjBZ4xNuIe0gdI8FGbscX3bc6uYgewE", "gid": "0"},
        {"id": "1FBS9BSal8DBtyVSOhGKBcNIa8EmktSunsuCCC9AuM34", "gid": "0"},
        {"id": "17f48qNZ1MVvgOwI467OypCrgR-iQl3TqZ7sosLp3s7Y", "gid": "638743010"},
        {"id": "1AyYe3M3kHCnlZYjD-GSR9oHr_6rGqsL8KMBUnnrvcx4", "gid": "0"}
    ]
    SHEET_ID_RESUMO_REVERSA = "1tYkxqGCSan5C7wAjtqKeKpOE2OeGCgrzSynMaXVBaKU"

    SHEET_VENDAS_PRINCIPAL = "13R19Vg06Z-E10wKdDl7gqtdKM7KdNeI7unutsVZXrNY"
    PLANILHAS_VENDAS_BASE = [
        {"id": "1VarO61GI5asiRDlaw81Dztx4rRINySnk1KgsBCzPgkI", "gid": "0"},
        {"id": "1Cl9MSMrVaMci_mJ-u62NFnc2NWanl-86M8PJI-2bWyU", "gid": "0"},
        {"id": "1jGZv0ATiJvCOfmsODT3JPGkpdA18XkmlP60WH_uUCK8", "gid": "0"},
        {"id": "1khs25N1XevKrSdBun0w0MIXNpY1kx2KiK4UdK0uchdM", "gid": "0"},
        {"id": "1NiYyktZdtggxFsDunvazt4Fysmf7dQS2SvkNQldiUc0", "gid": "0"}
    ]

    @st.cache_data(ttl=1800, show_spinner=False)
    def carregar_dados_reversa():
        lista_dfs = []
        colunas_desejadas = [
            'data_solicitacao', 'mes_ano_solicitacao', 'tipo_solicitacao', 'seller_name',
            'tipo_processo', 'ultima_atualizacao_tabela', 'pedido', 'remessa_retorno',
            'motivo_troca', 'protocolo', 'mes_ano_finalizacao', 'tracking', 'grupo_aberto_seller'
        ]
        tipos_otimizados = {
            'seller_name': 'category',
            'tipo_processo': 'category',
            'tracking': 'category',
            'grupo_aberto_seller': 'category',
            'mes_ano_solicitacao': 'category',
            'mes_ano_finalizacao': 'category'
        }
        for item in PLANILHAS_REVERSA_BASE:
            sheet_id = item["id"]
            gid = item["gid"]
            df_temp = pd.DataFrame()
            try:
                url_csv = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"
                df_temp = pd.read_csv(url_csv, usecols=lambda c: c in colunas_desejadas, dtype=tipos_otimizados, low_memory=False)
            except Exception:
                try:
                    url_gviz = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet=BASE"
                    df_temp = pd.read_csv(url_gviz, usecols=lambda c: c in colunas_desejadas, dtype=tipos_otimizados, low_memory=False)
                except Exception:
                    pass
            if not df_temp.empty and len(df_temp.columns) > 1:
                lista_dfs.append(df_temp)

        if lista_dfs:
            return pd.concat(lista_dfs, ignore_index=True)
        return pd.DataFrame()

    @st.cache_data(ttl=1800, show_spinner=False)
    def carregar_resumo_reversa():
        url_csv = f"https://docs.google.com/spreadsheets/d/{SHEET_ID_RESUMO_REVERSA}/gviz/tq?tqx=out:csv&sheet=RESUMO%20REVERSA"
        try:
            df = pd.read_csv(url_csv, low_memory=False)
            if 'nome_seller' in df.columns:
                df['nome_seller'] = df['nome_seller'].fillna('N/A').astype(str)
            return df
        except Exception:
            return pd.DataFrame()

    @st.cache_data(ttl=1800, show_spinner=False)
    def carregar_aba_vendas_resumo(nome_aba):
        nome_encoded = urllib.parse.quote(nome_aba)
        url = f"https://docs.google.com/spreadsheets/d/{SHEET_VENDAS_PRINCIPAL}/gviz/tq?tqx=out:csv&sheet={nome_encoded}"
        try:
            df = pd.read_csv(url, low_memory=False)
            if 'nome_seller' in df.columns:
                df['nome_seller'] = df['nome_seller'].fillna('N/A').astype(str)
            return df
        except Exception:
            return pd.DataFrame()

    @st.cache_data(ttl=1800, show_spinner=False)
    def carregar_base_vendas():
        lista_dfs = []
        tipos_vendas = {
            'nome_seller': 'category',
            'delivery_type': 'category',
            'status_pedido': 'category',
            'grupo_dias_em_atraso': 'category',
            'tipo': 'category'
        }
        for item in PLANILHAS_VENDAS_BASE:
            sheet_id = item["id"]
            gid = item["gid"]
            df_temp = pd.DataFrame()
            try:
                url_csv = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"
                df_temp = pd.read_csv(url_csv, dtype=tipos_vendas, low_memory=False)
            except Exception:
                try:
                    url_gviz = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet=BASE"
                    df_temp = pd.read_csv(url_gviz, dtype=tipos_vendas, low_memory=False)
                except Exception:
                    pass
            if not df_temp.empty and len(df_temp.columns) > 1:
                lista_dfs.append(df_temp)

        if lista_dfs:
            return pd.concat(lista_dfs, ignore_index=True)
        return pd.DataFrame()

    with st.spinner("⚡ A carregar base operacional otimizada..."):
        df_raw_reversa = carregar_dados_reversa()
        df_raw_resumo_reversa = carregar_resumo_reversa()

        df_res_expedicao = carregar_aba_vendas_resumo("RESUMO VENDAS_EXPEDIÇÃO")
        df_res_caf = carregar_aba_vendas_resumo("RESUMO_CAF")
        df_res_entregas = carregar_aba_vendas_resumo("RESUMO_ENTREGAS")
        df_res_prejudicado = carregar_aba_vendas_resumo("RESUMO_PREJUDICADO")
        df_res_sva = carregar_aba_vendas_resumo("RESUMO_SVA")
        df_res_tracking = carregar_aba_vendas_resumo("RESUMO_TRACKING")
        df_res_status_loja = carregar_aba_vendas_resumo("RESUMO_STATUS_LOJA")
        df_raw_vendas_base = carregar_base_vendas()

    # ==========================================
    # SELEÇÃO SUPERIOR DE SELLER E TEMA (UNIFICADO)
    # ==========================================
    col_topo_seller, col_topo_tema = st.columns([4, 1.5])

    with col_topo_seller:
        st.markdown("<span style='font-size:12px; font-weight:800; color:#9CA3AF; letter-spacing:1px;'>🎯 SELEÇÃO DE SELLER</span>", unsafe_allow_html=True)
        if empresa_usuario.upper() == "DAFITI":
            s_rev = set(df_raw_reversa['seller_name'].dropna().astype(str).unique()) if 'seller_name' in df_raw_reversa.columns else set()
            s_vend = set(df_res_expedicao['nome_seller'].dropna().astype(str).unique()) if 'nome_seller' in df_res_expedicao.columns else set()
            sellers_totais = sorted([s for s in (s_rev | s_vend) if s and s.lower() not in ['n/a', 'nan', 'none']])
            lista_sellers_global = ["Todos"] + sellers_totais
            seller_global_selecionado = st.selectbox("Selecione o Seller", lista_sellers_global, index=0, label_visibility="collapsed")
        else:
            st.markdown(f"<div style='background-color:#1E293B; padding:8px 12px; border-radius:6px; font-weight:700; color:#60A5FA; font-size:14px;'>🏢 {empresa_usuario}</div>", unsafe_allow_html=True)
            seller_global_selecionado = empresa_usuario

    with col_topo_tema:
        st.markdown("<span style='font-size:12px; font-weight:800; color:#9CA3AF; letter-spacing:1px;'>TEMA DA TELA</span>", unsafe_allow_html=True)
        tema_selecionado = st.selectbox("Tema do Dashboard", ["Escuro 🌙", "Claro ☀️"], index=0, label_visibility="collapsed")

    if tema_selecionado == "Escuro 🌙":
        template_plotly = "plotly_dark"
        cor_grafico = "#60A5FA"
        st.markdown("""
            <style>
                header[data-testid="stHeader"] { background-color: #0B0F19 !important; }
                .stApp { background-color: #0B0F19 !important; color: #FFFFFF !important; }
                [data-testid="stSidebar"] { background-color: #111827 !important; border-right: 1px solid #1F2937 !important; }
                [data-testid="stSidebar"] * { color: #F3F4F6 !important; font-weight: 700 !important; }
                .header-container-unificado {
                    background: linear-gradient(90deg, #1E293B 0%, #0F172A 100%) !important;
                    border-left: 6px solid #60A5FA !important;
                    padding: 14px 24px; border-radius: 8px; display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;
                }
                .header-titulo { font-size: 20px; font-weight: 800; color: #FFFFFF !important; }
                .header-atualizacao { font-size: 14px; font-weight: 700; color: #94A3B8 !important; }
                .metric-card {
                    background-color: #1E293B !important; border: 1px solid #334155 !important;
                    border-radius: 10px; padding: 16px 18px; text-align: center;
                }
                .metric-card-label { font-size: 12px; color: #CBD5E1 !important; font-weight: 700; margin-bottom: 6px; }
                .metric-card-value { font-size: 24px; font-weight: 900; color: #FFFFFF !important; }
                div[data-testid="stDownloadButton"] button {
                    background-color: #EF4444 !important; color: #FFFFFF !important; border: none !important;
                    font-weight: 900 !important; font-size: 15px !important; border-radius: 8px !important; padding: 0.7rem 1.2rem !important; width: 100% !important;
                }
            </style>
        """, unsafe_allow_html=True)
    else:
        template_plotly = "plotly_white"
        cor_grafico = "#2563EB"
        st.markdown("""
            <style>
                header[data-testid="stHeader"] { background-color: #FFFFFF !important; }
                .stApp { background-color: #FFFFFF !important; color: #0F172A !important; }
                [data-testid="stSidebar"] { background-color: #F8FAFC !important; border-right: 1px solid #E2E8F0 !important; }
                [data-testid="stSidebar"] * { color: #0F172A !important; }
                .header-container-unificado {
                    background: linear-gradient(90deg, #F1F5F9 0%, #FFFFFF 100%) !important;
                    border-left: 6px solid #2563EB !important;
                    padding: 14px 24px; border-radius: 8px; display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;
                }
                .header-titulo { font-size: 20px; font-weight: 800; color: #0F172A !important; }
                .header-atualizacao { font-size: 14px; font-weight: 700; color: #475569 !important; }
                .metric-card {
                    background-color: #F8FAFC !important; border: 1px solid #E2E8F0 !important;
                    border-radius: 10px; padding: 16px 18px; text-align: center;
                }
                .metric-card-label { font-size: 12px; color: #475569 !important; font-weight: 700; margin-bottom: 6px; }
                .metric-card-value { font-size: 24px; font-weight: 900; color: #0F172A !important; }
                div[data-testid="stDownloadButton"] button {
                    background-color: #2563EB !important; color: #FFFFFF !important;
                    font-weight: 900 !important; font-size: 15px !important; border-radius: 8px !important; padding: 0.7rem 1.2rem !important; width: 100% !important;
                }
            </style>
        """, unsafe_allow_html=True)

    aba_reversa, aba_vendas = st.tabs([
        "🔄 Operação Reversa", 
        "💰 Vendas"
    ])

    # ==========================================
    # ABA: OPERAÇÃO REVERSA
    # ==========================================
    with aba_reversa:
        modais_existentes_rev = ["GERAL", "Dafiti Envios", "Milkrun", "Dropshipping"]

        col_modal_rev, col_espaco_rev = st.columns([2, 4])
        with col_modal_rev:
            st.markdown("<span style='font-size:12px; font-weight:800; color:#9CA3AF; letter-spacing:1px;'>MODAL ANALISADO (REVERSA)</span>", unsafe_allow_html=True)
            modal_rev_selecionado = st.selectbox("Modal Analisado", modais_existentes_rev, index=0, key="sb_modal_reversa", label_visibility="collapsed")

        mask_reversa = pd.Series(True, index=df_raw_reversa.index)
        mask_resumo_rev = pd.Series(True, index=df_raw_resumo_reversa.index)

        target_seller_rev = seller_global_selecionado if empresa_usuario.upper() == "DAFITI" else empresa_usuario
        if target_seller_rev != "Todos":
            t_str = str(target_seller_rev).strip().upper()
            if 'seller_name' in df_raw_reversa.columns:
                mask_reversa &= (df_raw_reversa['seller_name'].astype(str).str.strip().str.upper() == t_str)
            if 'nome_seller' in df_raw_resumo_reversa.columns:
                mask_resumo_rev &= (df_raw_resumo_reversa['nome_seller'].astype(str).str.strip().str.upper() == t_str)

        if modal_rev_selecionado != "GERAL":
            map_m = {"Dafiti Envios": ["dafiti envios", "dafiti_envios"], "Milkrun": ["milkrun"], "Dropshipping": ["dropshipping"]}
            vals = map_m.get(modal_rev_selecionado, [modal_rev_selecionado.lower()])
            if 'tipo_processo' in df_raw_reversa.columns:
                mask_reversa &= df_raw_reversa['tipo_processo'].astype(str).str.lower().isin(vals)
            if 'delivery_type' in df_raw_resumo_reversa.columns:
                mask_resumo_rev &= df_raw_resumo_reversa['delivery_type'].astype(str).str.lower().isin(vals)

        df_filtrado_reversa = df_raw_reversa[mask_reversa]
        df_filtrado_resumo_rev = df_raw_resumo_reversa[mask_resumo_rev]

        data_hora_reversa = "N/D"
        if 'ultima_atualizacao_tabela' in df_raw_reversa.columns and not df_raw_reversa.empty:
            val_max = df_raw_reversa['ultima_atualizacao_tabela'].dropna().max()
            if pd.notnull(val_max) and str(val_max).strip() != "":
                try:
                    data_hora_reversa = pd.to_datetime(str(val_max)).strftime('%d/%m/%Y às %H:%M:%S')
                except Exception:
                    data_hora_reversa = str(val_max)

        st.markdown(f"""
            <div class='header-container-unificado'>
                <div class='header-titulo'>📋 Visão Geral da Operação Reversa</div>
                <div class='header-atualizacao'>🔄 Última Atualização: <b>{data_hora_reversa}</b></div>
            </div>
        """, unsafe_allow_html=True)

        col_filtro_tipo, col_filtro_mes = st.columns([1, 1])
        with col_filtro_tipo:
            st.markdown("<b>📅 Escolha o Tipo de Visão:</b>", unsafe_allow_html=True)
            tipo_visao_data = st.radio("Tipo de Visão de Data", ["Mês/Ano Solicitação", "Mês/Ano Finalização"], horizontal=True, label_visibility="collapsed")

        coluna_data_alvo = "mes_ano_solicitacao" if tipo_visao_data == "Mês/Ano Solicitação" else "mes_ano_finalizacao"
        if coluna_data_alvo in df_filtrado_reversa.columns:
            meses_disponiveis = ["Todos"] + sorted([str(m) for m in df_filtrado_reversa[coluna_data_alvo].dropna().unique() if str(m).strip() != ""], reverse=True)
        else:
            meses_disponiveis = ["Todos"]

        with col_filtro_mes:
            st.markdown(f"<b>📆 Selecione o Período ({tipo_visao_data}):</b>", unsafe_allow_html=True)
            mes_selecionado = st.selectbox(f"Selecione o {tipo_visao_data}", meses_disponiveis, label_visibility="collapsed")

        if mes_selecionado != "Todos" and coluna_data_alvo in df_filtrado_reversa.columns:
            df_filtrado_reversa = df_filtrado_reversa[df_filtrado_reversa[coluna_data_alvo].astype(str) == mes_selecionado]

        st.write("")

        colunas_chaves = ['pedido', 'remessa_retorno', 'protocolo']
        colunas_existentes = [c for c in colunas_chaves if c in df_filtrado_reversa.columns]
        qtd_remessas_unicas = df_filtrado_reversa[colunas_existentes[0]].nunique() if colunas_existentes and not df_filtrado_reversa.empty else len(df_filtrado_reversa)

        col_kpi1, col_kpi2, col_kpi3 = st.columns(3)
        with col_kpi1:
            st.markdown(f"<div class='metric-card'><div class='metric-card-label'>Total Linhas Agrupadas</div><div class='metric-card-value'>{len(df_filtrado_reversa):,}</div></div>".replace(",", "."), unsafe_allow_html=True)
        with col_kpi2:
            st.markdown(f"<div class='metric-card'><div class='metric-card-label'>Qtd. Remessas Únicas</div><div class='metric-card-value'>{qtd_remessas_unicas:,}</div></div>".replace(",", "."), unsafe_allow_html=True)
        with col_kpi3:
            st.markdown(f"<div class='metric-card'><div class='metric-card-label'>Modal Analisado</div><div class='metric-card-value'>{modal_rev_selecionado}</div></div>", unsafe_allow_html=True)

        st.write("---")

        col_graf3, col_graf4 = st.columns(2)
        with col_graf3:
            st.subheader("🎯 Evolução Mensal da Taxa de Devolução")
            col_taxa = 'taxa_devolucao' if 'taxa_devolucao' in df_filtrado_resumo_rev.columns else 'taxa_devolucao_seller'
            col_dev = 'devolvido' if 'devolvido' in df_filtrado_resumo_rev.columns else 'devolvido_seller'
            if 'mes_ano_definido' in df_filtrado_resumo_rev.columns and col_taxa in df_filtrado_resumo_rev.columns and not df_filtrado_resumo_rev.empty:
                df_evolucao_taxa = df_filtrado_resumo_rev.groupby('mes_ano_definido', as_index=False).agg(tot_etr=('qtd_etr', 'sum'), tot_dev=(col_dev, 'sum')) if 'qtd_etr' in df_filtrado_resumo_rev.columns and col_dev in df_filtrado_resumo_rev.columns else df_filtrado_resumo_rev.groupby('mes_ano_definido', as_index=False)[col_taxa].mean()
                if 'taxa_calc' not in df_evolucao_taxa.columns:
                    df_evolucao_taxa['taxa_calc'] = df_evolucao_taxa['tot_dev'] / df_evolucao_taxa['tot_etr']
                df_evolucao_taxa = df_evolucao_taxa.sort_values('mes_ano_definido')
                df_evolucao_taxa['taxa_pct_str'] = df_evolucao_taxa['taxa_calc'].apply(lambda v: f"{v*100:.1f}%" if pd.notnull(v) else "0.0%")
                fig_linha_taxa = px.line(df_evolucao_taxa, x='mes_ano_definido', y='taxa_calc', text='taxa_pct_str', markers=True, template=template_plotly)
                fig_linha_taxa.update_traces(textposition="top center", line=dict(color=cor_grafico, width=3))
                fig_linha_taxa.update_layout(yaxis=dict(tickformat='.1%', showgrid=False), xaxis=dict(showgrid=False), height=380)
                st.plotly_chart(fig_linha_taxa, use_container_width=True)
            else:
                st.info("Sem dados de resumo para o Seller selecionado.")

        with col_graf4:
            st.subheader("⚠️ Top Sellers - Maior % Devolução em Aberto")
            if 'nome_seller' in df_filtrado_resumo_rev.columns and 'taxa_devolucao_aberto' in df_filtrado_resumo_rev.columns and not df_filtrado_resumo_rev.empty:
                df_temp_aberto = df_filtrado_resumo_rev.copy()
                df_temp_aberto['taxa_devolucao_aberto'] = (
                    df_temp_aberto['taxa_devolucao_aberto']
                    .astype(str)
                    .str.replace('%', '', regex=False)
                    .str.replace(',', '.', regex=False)
                    .str.strip()
                )
                df_temp_aberto['taxa_devolucao_aberto'] = pd.to_numeric(df_temp_aberto['taxa_devolucao_aberto'], errors='coerce').fillna(0.0)

                df_top_aberto = (
                    df_temp_aberto.groupby('nome_seller', as_index=False)['taxa_devolucao_aberto']
                    .mean()
                    .sort_values('taxa_devolucao_aberto', ascending=False)
                    .head(10)
                    .sort_values('taxa_devolucao_aberto', ascending=True)
                )
                df_top_aberto['taxa_str'] = df_top_aberto['taxa_devolucao_aberto'].apply(lambda v: f"{v*100:.1f}%" if pd.notnull(v) else "0.0%")
                fig_top_aberto = px.bar(
                    df_top_aberto,
                    x='taxa_devolucao_aberto',
                    y='nome_seller',
                    text='taxa_str',
                    orientation='h',
                    template=template_plotly,
                    color_discrete_sequence=['#EF4444']
                )
                fig_top_aberto.update_traces(textposition='outside')
                fig_top_aberto.update_layout(xaxis=dict(tickformat='.1%', showgrid=False), yaxis=dict(showgrid=False), height=380)
                st.plotly_chart(fig_top_aberto, use_container_width=True)
            else:
                st.info("Sem dados em aberto registrados para o Seller selecionado.")

        col_bot1, col_bot2, col_bot3 = st.columns([1, 2, 1])
        with col_bot2:
            dados_csv_rev = converter_df_para_csv(df_filtrado_reversa)
            nome_arquivo_rev = f"relatorio_reversa_{empresa_usuario.lower().replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
            st.download_button(label="📥 Descarregar Relatório Reversa (.csv)", data=dados_csv_rev, file_name=nome_arquivo_rev, mime="text/csv", use_container_width=True)

    # ==========================================
    # ABA: VENDAS
    # ==========================================
    with aba_vendas:
        modais_existentes_vendas = ["GERAL", "DAFITI ENVIOS", "MILKRUN", "DROPSHIPPING"]

        col_modal_vend, col_espaco_vend = st.columns([2, 4])
        with col_modal_vend:
            st.markdown("<span style='font-size:12px; font-weight:800; color:#9CA3AF; letter-spacing:1px;'>MODAL ANALISADO (VENDAS)</span>", unsafe_allow_html=True)
            modal_vend_selecionado = st.selectbox("Modal Analisado", modais_existentes_vendas, index=0, key="sb_modal_vendas", label_visibility="collapsed")

        target_seller_vend = seller_global_selecionado if empresa_usuario.upper() == "DAFITI" else empresa_usuario
        target_str_vend = str(target_seller_vend).strip().upper()

        def filtrar_df_vendas(df_input):
            if df_input.empty:
                return df_input
            df_out = df_input.copy()
            if target_seller_vend != "Todos" and 'nome_seller' in df_out.columns:
                df_out = df_out[df_out['nome_seller'].astype(str).str.strip().str.upper() == target_str_vend]
            if modal_vend_selecionado != "GERAL" and 'delivery_type' in df_out.columns:
                df_out = df_out[df_out['delivery_type'].astype(str).str.strip().str.upper() == modal_vend_selecionado]
            return df_out

        f_expedicao = filtrar_df_vendas(df_res_expedicao)
        f_caf = filtrar_df_vendas(df_res_caf)
        f_entregas = filtrar_df_vendas(df_res_entregas)
        f_prejudicado = filtrar_df_vendas(df_res_prejudicado)
        f_sva = filtrar_df_vendas(df_res_sva)
        f_tracking = filtrar_df_vendas(df_res_tracking)
        f_status_loja = filtrar_df_vendas(df_res_status_loja)
        f_base_vendas = filtrar_df_vendas(df_raw_vendas_base)

        data_hora_vendas = "N/D"
        if 'ultima_atualizacao_tabela' in df_raw_vendas_base.columns and not df_raw_vendas_base.empty:
            val_max_v = df_raw_vendas_base['ultima_atualizacao_tabela'].dropna().max()
            if pd.notnull(val_max_v) and str(val_max_v).strip() != "":
                try:
                    data_hora_vendas = pd.to_datetime(str(val_max_v)).strftime('%d/%m/%Y às %H:%M:%S')
                except Exception:
                    data_hora_vendas = str(val_max_v)

        st.markdown(f"""
            <div class='header-container-unificado'>
                <div class='header-titulo'>💰 Visão Geral de Vendas e Expedição</div>
                <div class='header-atualizacao'>🔄 Última Atualização: <b>{data_hora_vendas}</b></div>
            </div>
        """, unsafe_allow_html=True)

        tot_exp_prazo = f_expedicao['expedicao_no_prazo'].sum() if 'expedicao_no_prazo' in f_expedicao.columns else 0
        tot_exp_pedidos = f_expedicao['total'].sum() if 'total' in f_expedicao.columns else 0
        taxa_exp_geral = (tot_exp_prazo / tot_exp_pedidos * 100) if tot_exp_pedidos > 0 else 0.0

        tot_ent_prazo = f_entregas['entrega_no_prazo'].sum() if 'entrega_no_prazo' in f_entregas.columns else 0
        tot_ent_pedidos = f_entregas['total'].sum() if 'total' in f_entregas.columns else 0
        taxa_ent_geral = (tot_ent_prazo / tot_ent_pedidos * 100) if tot_ent_pedidos > 0 else 0.0

        tot_cafs = f_caf['caf'].sum() if 'caf' in f_caf.columns else 0
        tot_itens_caf = f_caf['qtd'].sum() if 'qtd' in f_caf.columns else 0
        taxa_caf_geral = (tot_cafs / tot_itens_caf * 100) if tot_itens_caf > 0 else 0.0

        tot_prejudicado = f_prejudicado['valor_prej'].sum() if 'valor_prej' in f_prejudicado.columns else 0.0
        tot_sva = f_sva['qtd_sva'].sum() if 'qtd_sva' in f_sva.columns else 0

        c_v1, c_v2, c_v3, c_v4, c_v5 = st.columns(5)
        with c_v1:
            st.markdown(f"<div class='metric-card'><div class='metric-card-label'>Expedição no Prazo</div><div class='metric-card-value'>{taxa_exp_geral:.1f}%</div></div>", unsafe_allow_html=True)
        with c_v2:
            st.markdown(f"<div class='metric-card'><div class='metric-card-label'>Entrega no Prazo</div><div class='metric-card-value'>{taxa_ent_geral:.1f}%</div></div>", unsafe_allow_html=True)
        with c_v3:
            st.markdown(f"<div class='metric-card'><div class='metric-card-label'>Taxa Cancelamento CAF</div><div class='metric-card-value'>{taxa_caf_geral:.1f}%</div></div>", unsafe_allow_html=True)
        with c_v4:
            st.markdown(f"<div class='metric-card'><div class='metric-card-label'>Valor Prejudicado</div><div class='metric-card-value'>R$ {tot_prejudicado:,.2f}</div></div>".replace(",", "X").replace(".", ",").replace("X", "."), unsafe_allow_html=True)
        with c_v5:
            st.markdown(f"<div class='metric-card'><div class='metric-card-label'>Qtd. SVA (Tentativas)</div><div class='metric-card-value'>{tot_sva:,}</div></div>".replace(",", "."), unsafe_allow_html=True)

        st.write("---")

        col_g_exp, col_g_track = st.columns(2)

        with col_g_exp:
            st.subheader("📦 Taxa de Expedição no Prazo por Mês")
            if 'mes_ano_definido' in f_expedicao.columns and 'expedicao_no_prazo' in f_expedicao.columns and not f_expedicao.empty:
                df_exp_mes = f_expedicao.groupby('mes_ano_definido', as_index=False).agg(prazo=('expedicao_no_prazo', 'sum'), total=('total', 'sum'))
                df_exp_mes['taxa'] = df_exp_mes['prazo'] / df_exp_mes['total']
                df_exp_mes = df_exp_mes.sort_values('mes_ano_definido')
                df_exp_mes['taxa_str'] = df_exp_mes['taxa'].apply(lambda v: f"{v*100:.1f}%")

                fig_exp = px.line(df_exp_mes, x='mes_ano_definido', y='taxa', text='taxa_str', markers=True, template=template_plotly)
                fig_exp.update_traces(textposition="top center", line=dict(color='#10B981', width=3))
                fig_exp.update_layout(yaxis=dict(tickformat='.1%', showgrid=False), xaxis=dict(showgrid=False), height=360)
                st.plotly_chart(fig_exp, use_container_width=True)
            else:
                st.info("Sem dados de expedição para o filtro selecionado.")

        with col_g_track:
            st.subheader("🚚 Distribuição de Pedidos em Aberto (Tracking)")
            if 'status_pedido' in f_tracking.columns and 'quantidade' in f_tracking.columns and not f_tracking.empty:
                df_track_agg = f_tracking.groupby('status_pedido', as_index=False)['quantidade'].sum()
                fig_track = px.pie(df_track_agg, names='status_pedido', values='quantidade', hole=0.45, template=template_plotly, color_discrete_sequence=['#3B82F6', '#10B981', '#F59E0B', '#EF4444'])
                fig_track.update_traces(textinfo='label+percent', pull=[0.05]*len(df_track_agg))
                fig_track.update_layout(height=360, showlegend=False)
                st.plotly_chart(fig_track, use_container_width=True)
            else:
                st.info("Sem dados de tracking para os pedidos selecionados.")

        st.write("---")

        col_g_caf, col_g_aging = st.columns(2)

        with col_g_caf:
            st.subheader("🚫 Histórico de Cancelamentos CAF por Mês")
            if 'mes_ano_compra' in f_caf.columns and 'caf' in f_caf.columns and not f_caf.empty:
                df_caf_mes = f_caf.groupby('mes_ano_compra', as_index=False).agg(cafs=('caf', 'sum'), total=('qtd', 'sum'))
                df_caf_mes['taxa_caf'] = (df_caf_mes['cafs'] / df_caf_mes['total']).apply(lambda v: f"{v*100:.1f}%")
                df_caf_mes = df_caf_mes.sort_values('mes_ano_compra')

                fig_caf = px.bar(df_caf_mes, x='mes_ano_compra', y='cafs', text='taxa_caf', template=template_plotly, color_discrete_sequence=['#EF4444'])
                fig_caf.update_traces(textposition='outside')
                fig_caf.update_layout(xaxis=dict(showgrid=False), yaxis=dict(showgrid=False), height=360, yaxis_title="Qtd. Itens Cancelados")
                st.plotly_chart(fig_caf, use_container_width=True)
            else:
                st.info("Sem registros de cancelamento CAF para o período.")

        with col_g_aging:
            st.subheader("⏱️ Faixas de Atraso dos Pedidos em Aberto")
            if 'grupo_dias_em_atraso' in f_base_vendas.columns and not f_base_vendas.empty:
                df_aging = f_base_vendas['grupo_dias_em_atraso'].value_counts().reset_index()
                df_aging.columns = ['faixa', 'quantidade']
                ordem_faixas = ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9', '10', '11', '12', '13', '14', '15', '15+']
                df_aging['faixa'] = pd.Categorical(df_aging['faixa'], categories=ordem_faixas, ordered=True)
                df_aging = df_aging.sort_values('faixa')

                fig_aging = px.bar(df_aging, x='faixa', y='quantidade', text='quantidade', template=template_plotly, color_discrete_sequence=[cor_grafico])
                fig_aging.update_traces(textposition='outside')
                fig_aging.update_layout(xaxis=dict(showgrid=False), yaxis=dict(showgrid=False), height=360, xaxis_title="Dias em Atraso", yaxis_title="Pedidos")
                st.plotly_chart(fig_aging, use_container_width=True)
            else:
                st.info("Não há pedidos em aberto com atraso registrado.")

        st.write("---")

        if not f_status_loja.empty:
            st.subheader("🏪 Monitor de Status da Loja (Última Movimentação)")
            col_l1, col_l2 = st.columns([2, 1])
            with col_l1:
                df_exib_loja = f_status_loja[['nome_seller', 'delivery_type', 'data_ultimo_ponto_mkt', 'status_loja']].drop_duplicates()
                df_exib_loja.columns = ['Seller', 'Modal', 'Último Ponto Mkt', 'Dias sem Movimento']
                st.dataframe(df_exib_loja, use_container_width=True, hide_index=True)
            with col_l2:
                dias_max = pd.to_numeric(f_status_loja['status_loja'], errors='coerce').max()
                cor_alerta = "#EF4444" if dias_max > 3 else "#10B981"
                st.markdown(f"""
                    <div class='metric-card' style='border-left: 5px solid {cor_alerta} !important;'>
                        <div class='metric-card-label'>Maior Inatividade Detectada</div>
                        <div class='metric-card-value'>{dias_max:.0f} dia(s)</div>
                    </div>
                """, unsafe_allow_html=True)

        st.write("---")

        col_bot_v1, col_bot_v2, col_bot_v3 = st.columns([1, 2, 1])
        with col_bot_v2:
            dados_csv_vendas = converter_df_para_csv(f_base_vendas)
            nome_arquivo_vendas = f"pedidos_aberto_{empresa_usuario.lower().replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
            st.download_button(
                label="📥 Descarregar Pedidos em Aberto (.csv)",
                data=dados_csv_vendas,
                file_name=nome_arquivo_vendas,
                mime="text/csv",
                use_container_width=True
            )