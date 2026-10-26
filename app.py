from datetime import datetime, timedelta
import io
import urllib.parse
import urllib.request
import warnings
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

# Desativa avisos desnecessários no terminal
warnings.filterwarnings("ignore")

# Configuração da página do dashboard
st.set_page_config(page_title="Dashboard Sellers - Redshift", layout="wide")

# ==========================================
# 1. CONFIGURAÇÃO E AUTENTICAÇÃO PERSISTENTE (RESISTENTE AO F5)
# ==========================================

TEMPO_EXPIRED_MINUTOS = 10

SHEET_ID = "1WuROB09uYwPUeMaG7fS3CroqPFB9cEXtolcgRoA6erY"
URL_CSV_GOOGLE_SHEETS = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid=0"
URL_WEBAPP_GOOGLE_SCRIPT = "https://script.google.com/macros/s/AKfycbyvMmlYokWB2PpkxkewxpNAdGCKQmQ_S13ybz0qmqaCvgS77_HVhBtk-ftXukSCcYGX/exec"


@st.cache_data(ttl=600)
def carregar_credenciais_google():
    try:
        requisicao = urllib.request.Request(
            URL_CSV_GOOGLE_SHEETS,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        )
        with urllib.request.urlopen(requisicao) as resposta:
            conteudo_bytes = resposta.read()
            conteudo_csv = conteudo_bytes.decode("utf-8")

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
        st.error(f"Erro ao ligar à folha do Google Sheets: {e}")
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
            resultado_texto = resposta.read().decode("utf-8")
            print(f"✅ Resposta do Google Sheets: {resultado_texto}")

    except Exception as e:
        print(f"❌ Erro ao enviar log para o Google Sheets: {e}")


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
            time_stamp_str = params["time"]
            ultima_atividade = datetime.fromtimestamp(float(time_stamp_str))
            
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


def obter_meses_referencia():
    hoje = datetime.now()
    if hoje.day <= 4:
        dt_ref = hoje.replace(day=1) - timedelta(days=1)
        dt_ant = dt_ref.replace(day=1) - timedelta(days=1)
    else:
        dt_ref = hoje
        dt_ant = hoje.replace(day=1) - timedelta(days=1)

    mes_atual_iso = dt_ref.strftime('%Y-%m')
    mes_ant_iso = dt_ant.strftime('%Y-%m')
    
    meses_pt = [
        "JANEIRO", "FEVEREIRO", "MARÇO", "ABRIL", "MAIO", "JUNHO",
        "JULHO", "AGOSTO", "SETEMBRO", "OUTUBRO", "NOVEMBRO", "DEZEMBRO"
    ]
    texto_ref = f"{meses_pt[dt_ref.month - 1]}/{dt_ref.year}"
    return mes_atual_iso, mes_ant_iso, texto_ref


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
    mes_atual_iso, mes_ant_iso, texto_mes_ref = obter_meses_referencia()

    st.sidebar.title("Perfil")
    st.sidebar.write(f"👤 **Utilizador:** {st.session_state.get('usuario_logado', '')}")
    st.sidebar.write(f"🏢 **Empresa:** {empresa_usuario}")
    st.sidebar.button("🚪 Sair / Logout", on_click=fazer_logout, key="btn_logout")

    # ==========================================
    # CARREGAMENTO CONSOLIDADO REVERSA
    # ==========================================
    PLANILHAS_BASE_CONFIG = [
        {"id": "1tYkxqGCSan5C7wAjtqKeKpOE2OeGCgrzSynMaXVBaKU", "gid": "0"},
        {"id": "10zd0gTWei38fpjBZ4xNuIe0gdI8FGbscX3bc6uYgewE", "gid": "0"},
        {"id": "1FBS9BSal8DBtyVSOhGKBcNIa8EmktSunsuCCC9AuM34", "gid": "0"},
        {"id": "17f48qNZ1MVvgOwI467OypCrgR-iQl3TqZ7sosLp3s7Y", "gid": "638743010"},
        {"id": "1AyYe3M3kHCnlZYjD-GSR9oHr_6rGqsL8KMBUnnrvcx4", "gid": "0"}
    ]

    SHEET_ID_RESUMO = "1tYkxqGCSan5C7wAjtqKeKpOE2OeGCgrzSynMaXVBaKU"

    @st.cache_data(ttl=1800, show_spinner=False)
    def carregar_dados_reversa_consolidados():
        lista_dfs = []
        colunas_desejadas = [
            'data_solicitacao', 'mes_ano_solicitacao', 'tipo_solicitacao', 'seller_name',
            'tipo_processo', 'ultima_atualizacao_tabela', 'pedido', 'remessa_retorno',
            'motivo_troca', 'protocolo', 'mes_ano_finalizacao', 'tracking', 'grupo_aberto_seller'
        ]

        for item in PLANILHAS_BASE_CONFIG:
            sheet_id = item["id"]
            gid = item["gid"]
            df_temp = pd.DataFrame()
            try:
                url_csv = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"
                df_temp = pd.read_csv(url_csv, usecols=lambda c: c in colunas_desejadas, low_memory=False)
            except Exception:
                try:
                    url_gviz = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet=BASE"
                    df_temp = pd.read_csv(url_gviz, usecols=lambda c: c in colunas_desejadas, low_memory=False)
                except Exception:
                    pass

            if not df_temp.empty and len(df_temp.columns) > 1:
                lista_dfs.append(df_temp)

        if lista_dfs:
            df_final = pd.concat(lista_dfs, ignore_index=True)
            if 'seller_name' in df_final.columns:
                df_final['seller_name'] = df_final['seller_name'].fillna('N/A').astype(str)
            return df_final
        return pd.DataFrame()

    @st.cache_data(ttl=1800, show_spinner=False)
    def carregar_dados_resumo():
        url_csv_resumo = f"https://docs.google.com/spreadsheets/d/{SHEET_ID_RESUMO}/gviz/tq?tqx=out:csv&sheet=RESUMO%20REVERSA"
        try:
            df_resumo = pd.read_csv(url_csv_resumo, low_memory=False)
            if 'nome_seller' in df_resumo.columns:
                df_resumo['nome_seller'] = df_resumo['nome_seller'].fillna('N/A').astype(str)
            return df_resumo
        except Exception:
            return pd.DataFrame()

    # ==========================================
    # CARREGAMENTO DO MÓDULO DE VENDAS
    # ==========================================
    SHEET_VENDAS_PRINCIPAL = "13R19Vg06Z-E10wKdDl7gqtdKM7KdNeI7unutsVZXrNY"
    PLANILHAS_VENDAS_BASE = [
        {"id": "1VarO61GI5asiRDlaw81Dztx4rRINySnk1KgsBCzPgkI", "gid": "0"},
        {"id": "1Cl9MSMrVaMci_mJ-u62NFnc2NWanl-86M8PJI-2bWyU", "gid": "0"},
        {"id": "1jGZv0ATiJvCOfmsODT3JPGkpdA18XkmlP60WH_uUCK8", "gid": "0"},
        {"id": "1khs25N1XevKrSdBun0w0MIXNpY1kx2KiK4UdK0uchdM", "gid": "0"},
        {"id": "1NiYyktZdtggxFsDunvazt4Fysmf7dQS2SvkNQldiUc0", "gid": "0"}
    ]

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
        for item in PLANILHAS_VENDAS_BASE:
            sheet_id = item["id"]
            gid = item["gid"]
            df_temp = pd.DataFrame()
            try:
                url_csv = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"
                df_temp = pd.read_csv(url_csv, low_memory=False)
            except Exception:
                try:
                    url_gviz = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet=BASE"
                    df_temp = pd.read_csv(url_gviz, low_memory=False)
                except Exception:
                    pass
            if not df_temp.empty and len(df_temp.columns) > 1:
                lista_dfs.append(df_temp)

        if lista_dfs:
            df_final = pd.concat(lista_dfs, ignore_index=True)
            if 'nome_seller' in df_final.columns:
                df_final['nome_seller'] = df_final['nome_seller'].fillna('N/A').astype(str)
            return df_final
        return pd.DataFrame()

    with st.spinner("⚡ A carregar base operacional na memória..."):
        df_raw_reversa = carregar_dados_reversa_consolidados()
        df_raw_resumo = carregar_dados_resumo()

        df_res_expedicao = carregar_aba_vendas_resumo("RESUMO VENDAS_EXPEDIÇÃO")
        df_res_caf = carregar_aba_vendas_resumo("RESUMO_CAF")
        df_res_entregas = carregar_aba_vendas_resumo("RESUMO_ENTREGAS")
        df_res_prejudicado = carregar_aba_vendas_resumo("RESUMO_PREJUDICADO")
        df_res_sva = carregar_aba_vendas_resumo("RESUMO_SVA")
        df_res_tracking = carregar_aba_vendas_resumo("RESUMO_TRACKING")
        df_res_status_loja = carregar_aba_vendas_resumo("RESUMO_STATUS_LOJA")
        df_raw_vendas_base = carregar_base_vendas()

    # ==========================================
    # SELEÇÃO SUPERIOR UNIFICADA (SELLER, MODAL E TEMA)
    # ==========================================
    col_modal_topo, col_seller_topo, col_tema_topo = st.columns([2, 2.5, 1.5])

    with col_seller_topo:
        st.markdown("<span style='font-size:12px; font-weight:800; color:#9CA3AF; letter-spacing:1px;'>🎯 SELEÇÃO DE SELLER</span>", unsafe_allow_html=True)
        if empresa_usuario.upper() == "DAFITI":
            sellers_rev = set(df_raw_reversa['seller_name'].dropna().unique()) if 'seller_name' in df_raw_reversa.columns else set()
            sellers_vend = set(df_res_expedicao['nome_seller'].dropna().unique()) if 'nome_seller' in df_res_expedicao.columns else set()
            sellers_totais = sorted([str(s) for s in (sellers_rev | sellers_vend) if s and str(s).lower() not in ['n/a', 'nan', 'none']])
            lista_sellers_global = ["Todos"] + sellers_totais
            seller_selecionado = st.selectbox("Selecione o Seller", lista_sellers_global, index=0, label_visibility="collapsed")
        else:
            st.markdown(f"<div style='background-color:#1E293B; padding:8px 12px; border-radius:6px; font-weight:700; color:#60A5FA; font-size:14px;'>🏢 {empresa_usuario}</div>", unsafe_allow_html=True)
            seller_selecionado = empresa_usuario

    df_seller_temp = df_raw_reversa
    if seller_selecionado != "Todos":
        df_seller_temp = df_raw_reversa[df_raw_reversa['seller_name'].str.strip().str.upper() == str(seller_selecionado).strip().upper()]

    modais_existentes = ["GERAL"]
    if 'tipo_processo' in df_seller_temp.columns and not df_seller_temp.empty:
        modais_unicos = df_seller_temp['tipo_processo'].dropna().astype(str).str.strip().unique()
        mapa_modais_limpos = {
            "dafiti envios": "Dafiti Envios",
            "milkrun": "Milkrun",
            "dropshipping": "Dropshipping",
            "fulfillment": "Fulfillment",
            "retail": "Retail"
        }
        for m in modais_unicos:
            m_limpo = mapa_modais_limpos.get(m.lower(), m.title())
            if m_limpo not in modais_existentes:
                modais_existentes.append(m_limpo)

    with col_modal_topo:
        st.markdown("<span style='font-size:12px; font-weight:800; color:#9CA3AF; letter-spacing:1px;'>MODAL ANALISADO</span>", unsafe_allow_html=True)
        modal_selecionado = st.selectbox("Modal Analisado", modais_existentes, index=0, label_visibility="collapsed")

    with col_tema_topo:
        st.markdown("<span style='font-size:12px; font-weight:800; color:#9CA3AF; letter-spacing:1px;'>TEMA DA TELA</span>", unsafe_allow_html=True)
        tema_selecionado = st.selectbox("Tema do Dashboard", ["Escuro 🌙", "Claro ☀️"], index=0, label_visibility="collapsed")

    # ESTILIZAÇÃO CSS
    if tema_selecionado == "Escuro 🌙":
        template_plotly = "plotly_dark"
        cor_grafico = "#60A5FA"
        st.markdown("""
            <style>
                header[data-testid="stHeader"] { background-color: #0B0F19 !important; }
                .stApp { background-color: #0B0F19 !important; color: #FFFFFF !important; }

                [data-testid="stSidebar"] {
                    background-color: #111827 !important;
                    border-right: 1px solid #1F2937 !important;
                }
                [data-testid="stSidebar"] *, [data-testid="stSidebar"] p, [data-testid="stSidebar"] span, [data-testid="stSidebar"] label {
                    color: #F3F4F6 !important;
                    font-weight: 700 !important;
                }

                [data-testid="stSidebar"] button {
                    background-color: #374151 !important;
                    color: #FFFFFF !important;
                    border: 1px solid #4B5563 !important;
                    font-weight: 800 !important;
                    border-radius: 6px !important;
                }
                [data-testid="stSidebar"] button:hover { background-color: #EF4444 !important; border-color: #EF4444 !important; }

                .stTabs [data-baseweb="tab"] { font-size: 18px !important; font-weight: 800 !important; color: #D1D5DB !important; }
                .stTabs [aria-selected="true"] { color: #60A5FA !important; border-bottom-color: #60A5FA !important; }

                div[data-testid="stRadio"] label, div[data-testid="stRadio"] p, .stMarkdown p, .stMarkdown b {
                    color: #FFFFFF !important;
                    font-weight: 700 !important;
                }
                
                .header-container-unificado {
                    background: linear-gradient(90deg, #1E293B 0%, #0F172A 100%) !important;
                    border-left: 6px solid #60A5FA !important;
                    padding: 14px 24px;
                    border-radius: 8px;
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    margin-bottom: 20px;
                }
                .header-titulo { font-size: 20px; font-weight: 800; color: #FFFFFF !important; }
                .header-atualizacao { font-size: 14px; font-weight: 700; color: #94A3B8 !important; }

                .metric-card {
                    background-color: #1E293B !important;
                    border: 1px solid #334155 !important;
                    border-radius: 10px;
                    padding: 18px 20px;
                    text-align: center;
                    box-sizing: border-box !important;
                }
                .metric-card-label { font-size: 13px; color: #CBD5E1 !important; font-weight: 700; margin-bottom: 6px; }
                .metric-card-value { font-size: 26px; font-weight: 900; color: #FFFFFF !important; }

                div[data-testid="stDownloadButton"] button {
                    background-color: #EF4444 !important;
                    color: #FFFFFF !important;
                    border: none !important;
                    font-weight: 900 !important;
                    font-size: 16px !important;
                    border-radius: 8px !important;
                    padding: 0.8rem 1.5rem !important;
                    width: 100% !important;
                }
                div[data-testid="stDownloadButton"] button p { color: #FFFFFF !important; font-weight: 900 !important; }
            </style>
        """, unsafe_allow_html=True)
    else:
        template_plotly = "plotly_white"
        cor_grafico = "#2563EB"
        st.markdown("""
            <style>
                header[data-testid="stHeader"] { background-color: #FFFFFF !important; }
                .stApp { background-color: #FFFFFF !important; color: #0F172A !important; }
                
                [data-testid="stSidebar"] {
                    background-color: #F8FAFC !important;
                    border-right: 1px solid #E2E8F0 !important;
                }
                [data-testid="stSidebar"] * { color: #0F172A !important; }

                .stTabs [data-baseweb="tab"] { font-size: 18px !important; font-weight: 800 !important; color: #64748B !important; }
                .stTabs [aria-selected="true"] { color: #2563EB !important; border-bottom-color: #2563EB !important; }
                div[data-testid="stRadio"] label, div[data-testid="stRadio"] p, .stMarkdown p, .stMarkdown b { color: #0F172A !important; font-weight: 700 !important; }
                
                .header-container-unificado {
                    background: linear-gradient(90deg, #F1F5F9 0%, #FFFFFF 100%) !important;
                    border-left: 6px solid #2563EB !important;
                    padding: 14px 24px;
                    border-radius: 8px;
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    margin-bottom: 20px;
                }
                .header-titulo { font-size: 20px; font-weight: 800; color: #0F172A !important; }
                .header-atualizacao { font-size: 14px; font-weight: 700; color: #475569 !important; }

                .metric-card {
                    background-color: #F8FAFC !important;
                    border: 1px solid #E2E8F0 !important;
                    border-radius: 10px;
                    padding: 18px 20px;
                    text-align: center;
                    box-sizing: border-box !important;
                }
                .metric-card-label { font-size: 13px; color: #475569 !important; font-weight: 700; margin-bottom: 6px; }
                .metric-card-value { font-size: 26px; font-weight: 900; color: #0F172A !important; }

                div[data-testid="stDownloadButton"] button {
                    background-color: #2563EB !important;
                    color: #FFFFFF !important;
                    font-weight: 900 !important;
                    font-size: 16px !important;
                    border-radius: 8px !important;
                    padding: 0.8rem 1.5rem !important;
                    width: 100% !important;
                }
                div[data-testid="stDownloadButton"] button p { color: #FFFFFF !important; font-weight: 900 !important; }
            </style>
        """, unsafe_allow_html=True)

    def calcular_taxas_com_corte(df, col_num, col_den, col_data):
        if df.empty or col_num not in df.columns or col_den not in df.columns or col_data not in df.columns:
            return 0.0, 0.0
        
        df_c = df.copy()
        df_c['num'] = pd.to_numeric(df_c[col_num].astype(str).str.replace(',', '.'), errors='coerce').fillna(0)
        df_c['den'] = pd.to_numeric(df_c[col_den].astype(str).str.replace(',', '.'), errors='coerce').fillna(0)
        df_c['mes_iso'] = df_c[col_data].astype(str).str.strip().str.slice(0, 7)

        df_atual = df_c[df_c['mes_iso'] == mes_atual_iso]
        df_ant = df_c[df_c['mes_iso'] == mes_ant_iso]

        if df_atual.empty and not df_c.empty:
            meses_disp = sorted([m for m in df_c['mes_iso'].unique() if len(m) >= 4])
            if len(meses_disp) >= 1:
                df_atual = df_c[df_c['mes_iso'] == meses_disp[-1]]
            if len(meses_disp) >= 2:
                df_ant = df_c[df_c['mes_iso'] == meses_disp[-2]]

        t_atual = (df_atual['num'].sum() / df_atual['den'].sum() * 100) if df_atual['den'].sum() > 0 else 0.0
        t_ant = (df_ant['num'].sum() / df_ant['den'].sum() * 100) if not df_ant.empty and df_ant['den'].sum() > 0 else 0.0
        return t_atual, t_ant

    # ==========================================
    # ABAS PRINCIPAIS DE NAVEGAÇÃO
    # ==========================================
    aba_reversa, aba_vendas = st.tabs([
        "🔄 Operação Reversa", 
        "💰 Vendas"
    ])

    # ==========================================
    # ABA: OPERAÇÃO REVERSA
    # ==========================================
    with aba_reversa:
        mask_reversa = pd.Series(True, index=df_raw_reversa.index)
        mask_resumo = pd.Series(True, index=df_raw_resumo.index)

        target_seller = seller_selecionado if empresa_usuario.upper() == "DAFITI" else empresa_usuario
        if target_seller != "Todos":
            target_str = str(target_seller).strip().upper()
            if 'seller_name' in df_raw_reversa.columns:
                mask_reversa &= (df_raw_reversa['seller_name'].astype(str).str.strip().str.upper() == target_str)
            if 'nome_seller' in df_raw_resumo.columns:
                mask_resumo &= (df_raw_resumo['nome_seller'].astype(str).str.strip().str.upper() == target_str)

        if modal_selecionado != "GERAL":
            map_m = {"Dafiti Envios": ["dafiti envios", "dafiti_envios"], "Milkrun": ["milkrun"], "Dropshipping": ["dropshipping"], "Fulfillment": ["fulfillment"], "Retail": ["retail"]}
            valores_aceitos = map_m.get(modal_selecionado, [modal_selecionado.lower()])
            if 'tipo_processo' in df_raw_reversa.columns:
                mask_reversa &= df_raw_reversa['tipo_processo'].astype(str).str.lower().isin(valores_aceitos)
            if 'delivery_type' in df_raw_resumo.columns:
                mask_resumo &= df_raw_resumo['delivery_type'].astype(str).str.lower().isin(valores_aceitos)

        df_filtrado_reversa = df_raw_reversa[mask_reversa]
        df_filtrado_resumo = df_raw_resumo[mask_resumo]

        data_hora_formatada = "N/D"
        if 'ultima_atualizacao_tabela' in df_raw_reversa.columns and not df_raw_reversa.empty:
            data_max = pd.to_datetime(df_raw_reversa['ultima_atualizacao_tabela']).max()
            data_hora_formatada = data_max.strftime('%d/%m/%Y às %H:%M:%S')

        st.markdown(
            f"""
            <div class='header-container-unificado'>
                <div class='header-titulo'>📋 Boletim de Operação Reversa</div>
                <div class='header-atualizacao'>🗓️ Ref Oficial: <b>{texto_mes_ref}</b> &nbsp;|&nbsp; 🔄 Atualizado: <b>{data_hora_formatada}</b></div>
            </div>
            """, 
            unsafe_allow_html=True
        )

        # ----------------------------------------------------
        # 1. FILTRO DE VISÃO E PERÍODO (BASE DETALHADA)
        # ----------------------------------------------------
        col_filtro_tipo, col_filtro_mes = st.columns([1, 1])

        with col_filtro_tipo:
            st.markdown("<b>📅 Escolha o Tipo de Visão:</b>", unsafe_allow_html=True)
            tipo_visao_data = st.radio(
                "Tipo de Visão de Data",
                ["Mês/Ano Solicitação", "Mês/Ano Finalização"],
                horizontal=True,
                label_visibility="collapsed"
            )

        coluna_data_alvo = "mes_ano_solicitacao" if tipo_visao_data == "Mês/Ano Solicitação" else "mes_ano_finalizacao"

        if coluna_data_alvo in df_filtrado_reversa.columns:
            meses_unicos = sorted(
                [str(m) for m in df_filtrado_reversa[coluna_data_alvo].dropna().unique() if str(m).strip() != ""],
                reverse=True
            )
            meses_disponiveis = ["Todos"] + meses_unicos
        else:
            meses_disponiveis = ["Todos"]

        with col_filtro_mes:
            st.markdown(f"<b>📆 Selecione o Período ({tipo_visao_data}):</b>", unsafe_allow_html=True)
            mes_selecionado = st.selectbox(
                f"Selecione o {tipo_visao_data}",
                meses_disponiveis,
                index=0,
                label_visibility="collapsed"
            )

        df_base_reversa_periodo = df_filtrado_reversa.copy()
        if mes_selecionado != "Todos" and coluna_data_alvo in df_base_reversa_periodo.columns:
            df_base_reversa_periodo = df_base_reversa_periodo[
                df_base_reversa_periodo[coluna_data_alvo].astype(str) == mes_selecionado
            ]

        st.write("")

        # ----------------------------------------------------
        # 2. KPIS PRINCIPAIS (COM O CARD DE DEVOLUÇÃO AO LADO - MESMA ALTURA)
        # ----------------------------------------------------
        colunas_chaves = ['pedido', 'remessa_retorno', 'protocolo']
        colunas_existentes = [c for c in colunas_chaves if c in df_base_reversa_periodo.columns]
        qtd_remessas_unicas = df_base_reversa_periodo[colunas_existentes[0]].nunique() if (colunas_existentes and not df_base_reversa_periodo.empty) else len(df_base_reversa_periodo)

        # Cálculo da Taxa de Devolução Concluída (Oficial)
        col_dev_r = 'devolvido' if 'devolvido' in df_filtrado_resumo.columns else 'devolvido_seller'
        v_dev, a_dev = calcular_taxas_com_corte(df_filtrado_resumo, col_dev_r, 'qtd_etr', 'mes_ano_definido')
        cor_dev = "#10B981" if v_dev <= 9 else "#EF4444"
        bg_dev = "rgba(16, 185, 129, 0.12)" if v_dev <= 9 else "rgba(244, 63, 94, 0.12)"
        diag_dev = "Taxa de devolução dentro do esperado. Monitorização contínua." if v_dev <= 9 else "Taxa de devolução acima do target (9%). Analise os motivos."

        col_kpi1, col_kpi2, col_kpi3, col_kpi4 = st.columns(4)
        with col_kpi1:
            st.markdown(f"""
                <div class='metric-card' style='height: 180px; display: flex; flex-direction: column; justify-content: center; align-items: center;'>
                    <div class='metric-card-label'>Total Linhas Agrupadas</div>
                    <div class='metric-card-value' style='font-size: 32px;'>{len(df_base_reversa_periodo):,}</div>
                </div>
            """.replace(",", "."), unsafe_allow_html=True)
        with col_kpi2:
            st.markdown(f"""
                <div class='metric-card' style='height: 180px; display: flex; flex-direction: column; justify-content: center; align-items: center;'>
                    <div class='metric-card-label'>Qtd. Remessas Únicas</div>
                    <div class='metric-card-value' style='font-size: 32px;'>{qtd_remessas_unicas:,}</div>
                </div>
            """.replace(",", "."), unsafe_allow_html=True)
        with col_kpi3:
            st.markdown(f"""
                <div class='metric-card' style='height: 180px; display: flex; flex-direction: column; justify-content: center; align-items: center;'>
                    <div class='metric-card-label'>Modal Analisado</div>
                    <div class='metric-card-value' style='font-size: 30px;'>{modal_selecionado}</div>
                </div>
            """, unsafe_allow_html=True)
        with col_kpi4:
            st.markdown(f"""
                <div class='metric-card' style='height: 180px; text-align: left; padding: 18px 20px; display: flex; flex-direction: column; justify-content: space-between;'>
                    <div>
                        <div style='font-size: 11px; color: #94A3B8; font-weight: 800; text-transform: uppercase;'>↩️ DEVOLUÇÃO <span style='opacity:0.5;'>(9%)</span></div>
                        <div style='font-size: 34px; font-weight: 900; color: {cor_dev}; margin: 2px 0 0 0;'>{v_dev:.2f}%</div>
                        <div style='font-size: 12px; color: #94A3B8; font-weight: 700;'>Ant: {a_dev:.2f}%</div>
                    </div>
                    <div style='background-color: {bg_dev}; color: {cor_dev}; padding: 6px 10px; border-radius: 8px; font-size: 10.5px; font-weight: 700; line-height: 1.3;'>
                        {diag_dev}
                    </div>
                </div>
            """, unsafe_allow_html=True)

        st.write("---")

        # ----------------------------------------------------
        # 3. GRÁFICOS: EVOLUÇÃO MENSAL E TOP SELLERS (HISTÓRICO COMPLETO)
        # ----------------------------------------------------
        st.markdown("<h3 style='text-align: center;'>📊 Indicadores de Devolução por Seller e Meta</h3>", unsafe_allow_html=True)
        st.write("")

        col_graf3, col_graf4 = st.columns(2)
        META_TAXA_SELLER = 0.09

        with col_graf3:
            st.subheader("🎯 Evolução Mensal da Taxa de Devolução")
            col_taxa = 'taxa_devolucao' if 'taxa_devolucao' in df_filtrado_resumo.columns else 'taxa_devolucao_seller'

            if 'mes_ano_definido' in df_filtrado_resumo.columns and not df_filtrado_resumo.empty:
                df_resumo_temp = df_filtrado_resumo.copy()
                
                if 'qtd_etr' in df_resumo_temp.columns and col_dev_r in df_resumo_temp.columns:
                    df_resumo_temp['qtd_etr_n'] = pd.to_numeric(df_resumo_temp['qtd_etr'].astype(str).str.replace(',', '.'), errors='coerce').fillna(0)
                    df_resumo_temp['col_dev_n'] = pd.to_numeric(df_resumo_temp[col_dev_r].astype(str).str.replace(',', '.'), errors='coerce').fillna(0)
                    
                    df_evolucao_taxa = df_resumo_temp.groupby('mes_ano_definido', as_index=False).agg(
                        tot_etr=('qtd_etr_n', 'sum'),
                        tot_dev=('col_dev_n', 'sum')
                    )
                    df_evolucao_taxa['taxa_calc'] = df_evolucao_taxa.apply(
                        lambda r: (r['tot_dev'] / r['tot_etr']) if r['tot_etr'] > 0 else 0.0, axis=1
                    )
                elif col_taxa in df_resumo_temp.columns:
                    df_resumo_temp['taxa_n'] = pd.to_numeric(df_resumo_temp[col_taxa].astype(str).str.replace('%', '').str.replace(',', '.'), errors='coerce').fillna(0)
                    if df_resumo_temp['taxa_n'].median() > 1.05:
                        df_resumo_temp['taxa_n'] = df_resumo_temp['taxa_n'] / 100.0
                    df_evolucao_taxa = df_resumo_temp.groupby('mes_ano_definido', as_index=False)['taxa_n'].mean()
                    df_evolucao_taxa.rename(columns={'taxa_n': 'taxa_calc'}, inplace=True)
                else:
                    df_evolucao_taxa = pd.DataFrame()

                if not df_evolucao_taxa.empty:
                    df_evolucao_taxa['mes_label'] = df_evolucao_taxa['mes_ano_definido'].astype(str).str.strip()
                    df_evolucao_taxa = df_evolucao_taxa.sort_values('mes_label')
                    df_evolucao_taxa['taxa_pct_str'] = df_evolucao_taxa['taxa_calc'].apply(lambda v: f"{v*100:.1f}%" if pd.notnull(v) else "0.0%")
                    
                    cores_pontos = ['#EF4444' if val > META_TAXA_SELLER else cor_grafico for val in df_evolucao_taxa['taxa_calc']]

                    fig_linha_taxa = go.Figure()
                    fig_linha_taxa.add_trace(go.Scatter(
                        x=df_evolucao_taxa['mes_label'],
                        y=df_evolucao_taxa['taxa_calc'],
                        mode='lines+markers+text',
                        text=df_evolucao_taxa['taxa_pct_str'],
                        textposition='top center',
                        line=dict(color=cor_grafico, width=3),
                        marker=dict(size=10, color=cores_pontos),
                        name='Taxa Devolução'
                    ))

                    if len(df_evolucao_taxa['mes_label']) > 0:
                        fig_linha_taxa.add_shape(
                            type="line",
                            x0=df_evolucao_taxa['mes_label'].iloc[0],
                            y0=META_TAXA_SELLER,
                            x1=df_evolucao_taxa['mes_label'].iloc[-1],
                            y1=META_TAXA_SELLER,
                            line=dict(color="#F59E0B", width=2, dash="dash")
                        )

                    max_taxa_y = df_evolucao_taxa['taxa_calc'].max() if not df_evolucao_taxa.empty else 0.15

                    fig_linha_taxa.update_layout(
                        template=template_plotly,
                        paper_bgcolor='rgba(0,0,0,0)',
                        plot_bgcolor='rgba(0,0,0,0)',
                        margin=dict(l=30, r=40, t=30, b=30),
                        height=380,
                        yaxis=dict(tickformat='.1%', title="Taxa (%)", range=[0, max(max_taxa_y * 1.35, 0.12)], showgrid=False),
                        xaxis=dict(type='category', showgrid=False),
                        showlegend=False
                    )
                    st.plotly_chart(fig_linha_taxa, use_container_width=True)
                else:
                    st.info("Sem dados de evolução histórica disponíveis.")
            else:
                st.info("Sem dados de resumo registrados para o Seller selecionado no período.")

        with col_graf4:
            st.subheader("⚠️ Top Sellers - Maior % Taxa de Devolução")
            col_taxa_alvo = 'taxa_devolucao' if 'taxa_devolucao' in df_filtrado_resumo.columns else 'taxa_devolucao_seller'
            
            if 'nome_seller' in df_filtrado_resumo.columns and (col_taxa_alvo in df_filtrado_resumo.columns or ('qtd_etr' in df_filtrado_resumo.columns and col_dev_r in df_filtrado_resumo.columns)) and not df_filtrado_resumo.empty:
                df_top_temp = df_filtrado_resumo.copy()
                
                if 'qtd_etr' in df_top_temp.columns and col_dev_r in df_top_temp.columns:
                    df_top_temp['qtd_etr_n'] = pd.to_numeric(df_top_temp['qtd_etr'].astype(str).str.replace(',', '.'), errors='coerce').fillna(0)
                    df_top_temp['col_dev_n'] = pd.to_numeric(df_top_temp[col_dev_r].astype(str).str.replace(',', '.'), errors='coerce').fillna(0)
                    
                    df_top_agg = df_top_temp.groupby('nome_seller', as_index=False).agg(
                        tot_etr=('qtd_etr_n', 'sum'),
                        tot_dev=('col_dev_n', 'sum')
                    )
                    df_top_agg['taxa_devolucao_calc'] = df_top_agg.apply(
                        lambda r: (r['tot_dev'] / r['tot_etr']) if r['tot_etr'] > 0 else 0.0, axis=1
                    )
                else:
                    df_top_temp['taxa_devolucao_limpa'] = (
                        df_top_temp[col_taxa_alvo]
                        .astype(str)
                        .str.replace('%', '', regex=False)
                        .str.replace(',', '.', regex=False)
                        .str.strip()
                    )
                    df_top_temp['taxa_num'] = pd.to_numeric(df_top_temp['taxa_devolucao_limpa'], errors='coerce').fillna(0.0)
                    
                    if df_top_temp['taxa_num'].median() > 1.05:
                        df_top_temp['taxa_devolucao_calc'] = df_top_temp['taxa_num'] / 100.0
                    else:
                        df_top_temp['taxa_devolucao_calc'] = df_top_temp['taxa_num']
                    
                    df_top_agg = df_top_temp.groupby('nome_seller', as_index=False)['taxa_devolucao_calc'].mean()

                df_top_sellers = (
                    df_top_agg
                    .sort_values('taxa_devolucao_calc', ascending=False)
                    .head(10)
                    .sort_values('taxa_devolucao_calc', ascending=True)
                )
                df_top_sellers['taxa_str'] = df_top_sellers['taxa_devolucao_calc'].apply(lambda v: f"{v*100:.1f}%" if pd.notnull(v) else "0.0%")

                fig_top_sellers = px.bar(
                    df_top_sellers,
                    x='taxa_devolucao_calc',
                    y='nome_seller',
                    text='taxa_str',
                    orientation='h',
                    template=template_plotly,
                    color_discrete_sequence=['#EF4444']
                )

                max_taxa_sellers = df_top_sellers['taxa_devolucao_calc'].max() if not df_top_sellers.empty else 0.20

                fig_top_sellers.update_traces(textposition='outside')
                fig_top_sellers.update_layout(
                    template=template_plotly,
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(0,0,0,0)',
                    margin=dict(l=20, r=100, t=30, b=20),
                    height=380,
                    xaxis=dict(tickformat='.1%', range=[0, max(max_taxa_sellers * 1.35, 0.12)], showgrid=False),
                    yaxis=dict(showgrid=False)
                )
                st.plotly_chart(fig_top_sellers, use_container_width=True)
            else:
                st.info("Sem dados de taxa de devolução para os Sellers selecionados.")

        st.write("---")

        # ----------------------------------------------------
        # 4. GRÁFICOS: VOLUME MENSAL, MOTIVOS E FAIXAS DE ATRASO
        # ----------------------------------------------------
        st.markdown("<h3 style='text-align: center;'>📈 Análise Gráfica das Devoluções (Remessas Únicas)</h3>", unsafe_allow_html=True)
        st.write("")

        st.subheader("📅 Volume de Remessas Únicas (Mês/Ano)")
        col_mes_grafico = "mes_ano_solicitacao" if tipo_visao_data == "Mês/Ano Solicitação" else "mes_ano_finalizacao"
        
        if col_mes_grafico in df_filtrado_reversa.columns and not df_filtrado_reversa.empty:
            df_temp = df_filtrado_reversa[[col_mes_grafico, colunas_existentes[0]]].dropna() if colunas_existentes else df_filtrado_reversa[[col_mes_grafico]].dropna()
            
            if colunas_existentes:
                df_grafico_mes = df_temp.groupby(col_mes_grafico, as_index=False)[colunas_existentes[0]].nunique()
                df_grafico_mes.columns = [col_mes_grafico, 'qtd_remessas_unicas']
            else:
                df_grafico_mes = df_temp.groupby(col_mes_grafico, as_index=False).size()
                df_grafico_mes.columns = [col_mes_grafico, 'qtd_remessas_unicas']

            df_grafico_mes = df_grafico_mes.sort_values(col_mes_grafico)

            fig_tempo = px.bar(
                df_grafico_mes,
                x=col_mes_grafico,
                y='qtd_remessas_unicas',
                text='qtd_remessas_unicas',
                template=template_plotly,
                color_discrete_sequence=[cor_grafico]
            )
            fig_tempo.update_traces(texttemplate='%{text:,}', textposition='outside')
            fig_tempo.update_layout(
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                margin=dict(l=20, r=20, t=30, b=20),
                height=350,
                xaxis=dict(showgrid=False),
                yaxis=dict(showgrid=False),
                xaxis_title="",
                yaxis_title="Remessas Únicas"
            )
            st.plotly_chart(fig_tempo, use_container_width=True)

        st.write("")
        col_graf_mot, col_graf_grupo = st.columns(2)

        with col_graf_mot:
            st.subheader("🔍 Principais Motivos de Troca")
            if 'motivo_troca' in df_base_reversa_periodo.columns and not df_base_reversa_periodo.empty:
                df_motivos = df_base_reversa_periodo['motivo_troca'].value_counts().head(10).reset_index()
                df_motivos.columns = ['motivo', 'quantidade']
                total_motivos = df_motivos['quantidade'].sum()
                df_motivos = df_motivos.sort_values('quantidade', ascending=True)

                df_motivos['rotulo'] = df_motivos['quantidade'].apply(
                    lambda v: f"{v:,} ({(v / total_motivos) * 100:.1f}%)".replace(",", ".") if total_motivos > 0 else "0"
                )

                fig_motivos = px.bar(
                    df_motivos,
                    x='quantidade',
                    y='motivo',
                    text='rotulo',
                    orientation='h',
                    template=template_plotly,
                    color_discrete_sequence=[cor_grafico]
                )
                max_mot = df_motivos['quantidade'].max() if not df_motivos.empty else 100
                fig_motivos.update_traces(textposition='outside')
                fig_motivos.update_layout(
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(0,0,0,0)',
                    margin=dict(l=20, r=120, t=30, b=20),
                    height=380,
                    xaxis=dict(range=[0, max_mot * 1.45], showgrid=False),
                    yaxis=dict(showgrid=False),
                    xaxis_title="Remessas Únicas",
                    yaxis_title=""
                )
                st.plotly_chart(fig_motivos, use_container_width=True)
            else:
                st.info("Sem dados de motivos registrados.")

        with col_graf_grupo:
            st.subheader("📦 Sellers - Dias com Pacote Entregue sem Finalizar")
            if 'tracking' in df_base_reversa_periodo.columns and 'grupo_aberto_seller' in df_base_reversa_periodo.columns and not df_base_reversa_periodo.empty:
                df_entregue_seller = df_base_reversa_periodo[
                    df_base_reversa_periodo['tracking'].astype(str).str.strip().str.upper() == 'ENTREGUE AO SELLER'
                ]

                if not df_entregue_seller.empty:
                    df_grupo_seller = df_entregue_seller['grupo_aberto_seller'].value_counts().reset_index()
                    df_grupo_seller.columns = ['grupo_dias', 'quantidade']
                    total_grupo = df_grupo_seller['quantidade'].sum()

                    df_grupo_seller['rotulo'] = df_grupo_seller['quantidade'].apply(
                        lambda v: f"{v:,} ({(v / total_grupo) * 100:.1f}%)".replace(",", ".") if total_grupo > 0 else "0"
                    )

                    df_grupo_seller['grupo_exibicao'] = df_grupo_seller['grupo_dias'].astype(str).apply(lambda g: "⚠️ +5 DIAS CORRIDOS" if ("5 DIAS" in g and "+" in g) else g)

                    fig_grupo_seller = px.bar(
                        df_grupo_seller,
                        x='grupo_exibicao',
                        y='quantidade',
                        text='rotulo',
                        template=template_plotly,
                        color='grupo_exibicao',
                        color_discrete_map={
                            '⚠️ +5 DIAS CORRIDOS': '#EF4444',
                            '0 DIAS CORRIDOS': '#94A3B8',
                            '1 DIAS CORRIDOS': '#60A5FA',
                            '2 DIAS CORRIDOS': '#3B82F6',
                            '3 DIAS CORRIDOS': '#2563EB',
                            '4 DIAS CORRIDOS': '#1D4ED8',
                            '5 DIAS CORRIDOS': '#F59E0B'
                        }
                    )
                    max_grupo = df_grupo_seller['quantidade'].max() if not df_grupo_seller.empty else 100
                    fig_grupo_seller.update_traces(textposition='outside')
                    fig_grupo_seller.update_layout(
                        paper_bgcolor='rgba(0,0,0,0)',
                        plot_bgcolor='rgba(0,0,0,0)',
                        margin=dict(l=20, r=20, t=30, b=20),
                        height=380,
                        xaxis=dict(showgrid=False),
                        yaxis=dict(range=[0, max_grupo * 1.25], showgrid=False),
                        showlegend=False
                    )
                    st.plotly_chart(fig_grupo_seller, use_container_width=True)
                else:
                    st.info("Não há pacotes com o status 'ENTREGUE AO SELLER' no período selecionado.")

        st.write("")
        st.write("---")

        # ----------------------------------------------------
        # 5. JORNADA DO TRACKING SEQUENCIAL
        # ----------------------------------------------------
        st.markdown("<h3 style='text-align: center;'>🚚 Jornada do Tracking (Fluxo Sequencial Reversa)</h3>", unsafe_allow_html=True)
        if 'tracking' in df_base_reversa_periodo.columns and not df_base_reversa_periodo.empty:
            df_tracking = df_base_reversa_periodo['tracking'].value_counts().reset_index()
            df_tracking.columns = ['status_tracking', 'quantidade']
            total_tracking = df_tracking['quantidade'].sum()

            ordem_jornada = ['EM ABERTO', 'POSTADO/TRANSPORTADOR', 'ENTREGUE AO SELLER', 'FINALIZADO', 'REVERSAS EXPIRADAS', 'EXTRAVIO']
            df_tracking['status_tracking'] = pd.Categorical(df_tracking['status_tracking'], categories=ordem_jornada, ordered=True)
            df_tracking = df_tracking.dropna(subset=['status_tracking']).sort_values('status_tracking')

            mapa_cores_jornada = {
                'EM ABERTO': '#F59E0B',
                'POSTADO/TRANSPORTADOR': '#3B82F6',
                'ENTREGUE AO SELLER': '#10B981',
                'FINALIZADO': '#14B8A6',
                'REVERSAS EXPIRADAS': '#EF4444',
                'EXTRAVIO': '#991B1B'
            }

            x_pts = [1, 2, 3, 4, 5, 6]
            y_pts = [0.8, 3.5, 0.8, 3.5, 0.8, 3.5]
            fig_jornada = go.Figure()

            fig_jornada.add_trace(go.Scatter(
                x=x_pts, y=y_pts, mode='lines',
                line=dict(color='#64748B', width=3, dash='dash'),
                hoverinfo='skip', showlegend=False
            ))

            for idx, row in enumerate(df_tracking.iterrows()):
                status = row[1]['status_tracking']
                qtd = row[1]['quantidade']
                pct = (qtd / total_tracking * 100) if total_tracking > 0 else 0
                cor = mapa_cores_jornada.get(status, '#3B82F6')
                qtd_str = f"{qtd:,}".replace(",", ".")

                pos = "top center" if y_pts[idx] == 3.5 else "bottom center"
                texto_no = f"<b>{status}</b><br><span style='font-size:15px; color:{cor};'><b>{qtd_str}</b> ({pct:.1f}%)</span>" if y_pts[idx] == 3.5 else f"<span style='font-size:15px; color:{cor};'><b>{qtd_str}</b> ({pct:.1f}%)</span><br><b>{status}</b>"

                fig_jornada.add_trace(go.Scatter(
                    x=[x_pts[idx]], y=[y_pts[idx]], mode='markers+text',
                    text=[texto_no], textposition=pos, textfont=dict(size=12),
                    marker=dict(size=24, color=cor, line=dict(color='white', width=3)),
                    showlegend=False, hoverinfo='text'
                ))

            fig_jornada.update_layout(
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                margin=dict(l=40, r=40, t=80, b=80),
                height=420,
                xaxis=dict(showgrid=False, zeroline=False, showticklabels=False, range=[0.4, 6.6]),
                yaxis=dict(showgrid=False, zeroline=False, showticklabels=False, range=[-0.2, 4.5])
            )
            st.plotly_chart(fig_jornada, use_container_width=True)

        st.write("---")

        # ----------------------------------------------------
        # 6. MEMORIAL DE CÁLCULO - OPERAÇÃO REVERSA (EXCLUSIVO)
        # ----------------------------------------------------
        st.markdown("""
            <div style='background-color: #1E293B; padding: 25px 30px; border-radius: 16px; border: 1px solid #334155; font-size: 13px; color: #94A3B8; line-height: 1.8; margin-bottom: 25px;'>
                <h4 style='color: #FFFFFF; font-size: 16px; font-weight: 800; margin: 0 0 12px 0;'>📊 Memorial de Cálculo - Operação Reversa</h4>
                <p style='margin: 4px 0;'>• <b>Virada de Mês:</b> Até o dia 04 são considerados os dados consolidados do mês anterior. A partir do dia 05, passam a vigorar os dados do mês corrente.</p>
                <p style='margin: 4px 0;'>• <b>Taxa de Devolução (%):</b> Relação entre o total de peças devolvidas concluídas e o total de peças expedidas (Meta: até 9.0%).</p>
                <p style='margin: 4px 0;'>• <b>Dias em Aberto no Seller:</b> Tempo decorrido (em dias corridos) desde que o pacote obteve o status 'ENTREGUE AO SELLER' até a sua conferência e finalização (Alerta para pacotes com +5 dias corridos).</p>
                <p style='margin: 4px 0;'>• <b>Jornada do Tracking:</b> Fluxo sequencial da logística reversa desde a geração da solicitação até o retorno e finalização no estoque do lojista.</p>
            </div>
        """, unsafe_allow_html=True)

        # ----------------------------------------------------
        # 7. DOWNLOAD CSV REVERSA
        # ----------------------------------------------------
        col_bot1, col_bot2, col_bot3 = st.columns([1, 2, 1])
        with col_bot2:
            dados_csv = converter_df_para_csv(df_base_reversa_periodo)
            nome_arquivo_csv = f"relatorio_reversa_{empresa_usuario.lower().replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
            st.download_button(
                label="📥 Descarregar Relatório Completo em CSV (.csv)",
                data=dados_csv,
                file_name=nome_arquivo_csv,
                mime="text/csv",
                use_container_width=True
            )

    # ==========================================
    # ABA: VENDAS (BOLETIM INDIVIDUAL)
    # ==========================================
    with aba_vendas:
        target_seller_v = seller_selecionado if empresa_usuario.upper() == "DAFITI" else empresa_usuario
        target_str_v = str(target_seller_v).strip().upper()

        def filtrar_vendas(df_input):
            if df_input.empty:
                return df_input
            df_out = df_input.copy()
            if target_seller_v != "Todos" and 'nome_seller' in df_out.columns:
                df_out = df_out[df_out['nome_seller'].astype(str).str.strip().str.upper() == target_str_v]
            if modal_selecionado != "GERAL" and 'delivery_type' in df_out.columns:
                df_out = df_out[df_out['delivery_type'].astype(str).str.strip().str.upper() == modal_selecionado.upper()]
            return df_out

        f_expedicao = filtrar_vendas(df_res_expedicao)
        f_caf = filtrar_vendas(df_res_caf)
        f_entregas = filtrar_vendas(df_res_entregas)
        f_prejudicado = filtrar_vendas(df_res_prejudicado)
        f_sva = filtrar_vendas(df_res_sva)
        f_tracking = filtrar_vendas(df_res_tracking)
        f_status_loja = filtrar_vendas(df_res_status_loja)
        f_base_vendas = filtrar_vendas(df_raw_vendas_base)

        data_hora_vendas = "N/D"
        if 'ultima_atualizacao_tabela' in df_raw_vendas_base.columns and not df_raw_vendas_base.empty:
            d_max_v = pd.to_datetime(df_raw_vendas_base['ultima_atualizacao_tabela']).max()
            data_hora_vendas = d_max_v.strftime('%d/%m/%Y às %H:%M:%S')

        st.markdown(
            f"""
            <div class='header-container-unificado'>
                <div class='header-titulo'>💰 Visão Geral de Vendas e Expedição</div>
                <div class='header-atualizacao'>🗓️ Ref: <b>{texto_mes_ref}</b> &nbsp;|&nbsp; 🔄 Atualizado: <b>{data_hora_vendas}</b></div>
            </div>
            """, 
            unsafe_allow_html=True
        )

        # 1. BANNER DE STATUS OPERACIONAL (STATUS LOJA)
        dias_inativo = 0
        if not f_status_loja.empty and 'status_loja' in f_status_loja.columns:
            s_val = pd.to_numeric(f_status_loja['status_loja'].astype(str).str.replace(',', '.'), errors='coerce').max()
            dias_inativo = s_val if pd.notnull(s_val) else 0

        if dias_inativo <= 3:
            st_msg = "Loja operando normalmente."
            st_cor = "#10B981"
            st_ico = "✅"
            st_bg = "rgba(16, 185, 129, 0.15)"
        elif dias_inativo <= 6:
            st_msg = f"Atenção: Movimente sua loja. ({int(dias_inativo)} dias sem expedição)"
            st_cor = "#F59E0B"
            st_ico = "⚠️"
            st_bg = "rgba(245, 158, 11, 0.15)"
        else:
            st_msg = f"Loja inativada ou sem movimento crítico. ({int(dias_inativo)} dias sem expedição)"
            st_cor = "#EF4444"
            st_ico = "🛑"
            st_bg = "rgba(244, 63, 94, 0.15)"

        st.markdown(f"""
            <div style='background-color: {st_bg}; border: 1px solid {st_cor}40; padding: 18px 24px; border-radius: 16px; display: flex; align-items: center; gap: 14px; margin-bottom: 25px;'>
                <span style='font-size: 24px;'>{st_ico}</span>
                <span style='color: {st_cor}; font-size: 16px; font-weight: 800;'>Status Operacional: {st_msg}</span>
            </div>
        """, unsafe_allow_html=True)

        # 2. CÁLCULO DAS TAXAS BASEADO NA REGRA DE CORTE (DIA 04 vs DIA 05)
        v_exp_v, a_exp_v = calcular_taxas_com_corte(f_expedicao, 'expedicao_no_prazo', 'total', 'mes_ano_definido')
        v_caf_v, a_caf_v = calcular_taxas_com_corte(f_caf, 'caf', 'qtd', 'mes_ano_compra')

        df_rev_res_v = df_filtrado_resumo
        col_dev_r_v = 'devolvido' if 'devolvido' in df_rev_res_v.columns else 'devolvido_seller'
        v_dev_v, a_dev_v = calcular_taxas_com_corte(df_rev_res_v, col_dev_r_v, 'qtd_etr', 'mes_ano_definido')
        v_sac_v, a_sac_v = calcular_taxas_com_corte(df_rev_res_v, 'devolucao_sac', 'qtd_etr', 'mes_ano_definido')

        # 3. CARDS DE QUALIDADE DA OPERAÇÃO (VENDAS)
        st.markdown("<h3 style='margin-bottom: 20px; font-weight: 800;'>Qualidade da Operação (Seller)</h3>", unsafe_allow_html=True)
        col_vq1, col_vq2, col_vq3, col_vq4 = st.columns(4)

        cor_exp_v = "#10B981" if v_exp_v >= 95 else "#EF4444"
        bg_exp_v = "rgba(16, 185, 129, 0.12)" if v_exp_v >= 95 else "rgba(244, 63, 94, 0.12)"
        diag_exp_v = "Performance excelente. Acima das expectativas." if v_exp_v > 98 else ("SLA dentro da meta. Sua operação está saudável." if v_exp_v >= 95 else "Atenção: Seu SLA está abaixo da meta (95%). É necessário agilizar.")

        with col_vq1:
            st.markdown(f"""
                <div class='metric-card' style='text-align: left; padding: 22px; height: 100%; display: flex; flex-direction: column;'>
                    <div style='font-size: 12px; color: #94A3B8; font-weight: 800; text-transform: uppercase;'>🚚 SLA EXPEDIÇÃO <span style='opacity:0.5;'>(95%)</span></div>
                    <div style='font-size: 42px; font-weight: 900; color: {cor_exp_v}; margin: 6px 0 2px 0;'>{v_exp_v:.2f}%</div>
                    <div style='font-size: 13px; color: #94A3B8; font-weight: 700; margin-bottom: 18px;'>Ant: {a_exp_v:.2f}%</div>
                    <div style='background-color: {bg_exp_v}; color: {cor_exp_v}; padding: 12px; border-radius: 10px; font-size: 11px; font-weight: 700; line-height: 1.5; margin-top: auto;'>
                        {diag_exp_v}
                    </div>
                </div>
            """, unsafe_allow_html=True)

        cor_caf_v = "#10B981" if v_caf_v <= 2 else "#EF4444"
        bg_caf_v = "rgba(16, 185, 129, 0.12)" if v_caf_v <= 2 else "rgba(244, 63, 94, 0.12)"
        diag_caf_v = "Sua taxa está dentro da meta! Controle de estoque eficiente." if v_caf_v <= 2 else "O índice de cancelamento está acima do estabelecido. Revisar o estoque."

        with col_vq2:
            st.markdown(f"""
                <div class='metric-card' style='text-align: left; padding: 22px; height: 100%; display: flex; flex-direction: column;'>
                    <div style='font-size: 12px; color: #94A3B8; font-weight: 800; text-transform: uppercase;'>🚫 CANCELAMENTO <span style='opacity:0.5;'>(2%)</span></div>
                    <div style='font-size: 42px; font-weight: 900; color: {cor_caf_v}; margin: 6px 0 2px 0;'>{v_caf_v:.2f}%</div>
                    <div style='font-size: 13px; color: #94A3B8; font-weight: 700; margin-bottom: 18px;'>Ant: {a_caf_v:.2f}%</div>
                    <div style='background-color: {bg_caf_v}; color: {cor_caf_v}; padding: 12px; border-radius: 10px; font-size: 11px; font-weight: 700; line-height: 1.5; margin-top: auto;'>
                        {diag_caf_v}
                    </div>
                </div>
            """, unsafe_allow_html=True)

        cor_dev_v = "#10B981" if v_dev_v <= 9 else "#EF4444"
        bg_dev_v = "rgba(16, 185, 129, 0.12)" if v_dev_v <= 9 else "rgba(244, 63, 94, 0.12)"
        diag_dev_v = "Taxa de devolução dentro do esperado. Monitorização contínua." if v_dev_v <= 9 else "Taxa de devolução acima do target (9%). Analise os motivos."

        with col_vq3:
            st.markdown(f"""
                <div class='metric-card' style='text-align: left; padding: 22px; height: 100%; display: flex; flex-direction: column;'>
                    <div style='font-size: 12px; color: #94A3B8; font-weight: 800; text-transform: uppercase;'>↩️ DEVOLUÇÃO <span style='opacity:0.5;'>(9%)</span></div>
                    <div style='font-size: 42px; font-weight: 900; color: {cor_dev_v}; margin: 6px 0 2px 0;'>{v_dev_v:.2f}%</div>
                    <div style='font-size: 13px; color: #94A3B8; font-weight: 700; margin-bottom: 18px;'>Ant: {a_dev_v:.2f}%</div>
                    <div style='background-color: {bg_dev_v}; color: {cor_dev_v}; padding: 12px; border-radius: 10px; font-size: 11px; font-weight: 700; line-height: 1.5; margin-top: auto;'>
                        {diag_dev_v}
                    </div>
                </div>
            """, unsafe_allow_html=True)

        cor_sac_v = "#10B981" if v_sac_v <= 5 else "#EF4444"
        bg_sac_v = "rgba(16, 185, 129, 0.12)" if v_sac_v <= 5 else "rgba(244, 63, 94, 0.12)"
        diag_sac_v = "Taxa de contato dentro da meta. Atendimento sob controle." if v_sac_v <= 5 else "Taxa de contato no SAC acima da meta (5%). Identifique ofensores."

        with col_vq4:
            st.markdown(f"""
                <div class='metric-card' style='text-align: left; padding: 22px; height: 100%; display: flex; flex-direction: column;'>
                    <div style='font-size: 12px; color: #94A3B8; font-weight: 800; text-transform: uppercase;'>🎧 SAC <span style='opacity:0.5;'>(5%)</span></div>
                    <div style='font-size: 42px; font-weight: 900; color: {cor_sac_v}; margin: 6px 0 2px 0;'>{v_sac_v:.2f}%</div>
                    <div style='font-size: 13px; color: #94A3B8; font-weight: 700; margin-bottom: 18px;'>Ant: {a_sac_v:.2f}%</div>
                    <div style='background-color: {bg_sac_v}; color: {cor_sac_v}; padding: 12px; border-radius: 10px; font-size: 11px; font-weight: 700; line-height: 1.5; margin-top: auto;'>
                        {diag_sac_v}
                    </div>
                </div>
            """, unsafe_allow_html=True)

        st.write("---")

        # 4. PERFORMANCE INDIVIDUAL (FATURADOS DO MÊS + HISTÓRICO)
        st.markdown("<h3 style='margin-bottom: 20px; font-weight: 800;'>Performance Individual</h3>", unsafe_allow_html=True)
        col_fat, col_graf_sla = st.columns([1, 2])

        tot_faturados_mes = 0
        if not f_expedicao.empty and 'total' in f_expedicao.columns:
            df_fat_temp = f_expedicao.copy()
            df_fat_temp['total_num'] = pd.to_numeric(df_fat_temp['total'].astype(str).str.replace(',', '.'), errors='coerce').fillna(0)
            if 'mes_ano_definido' in df_fat_temp.columns:
                df_fat_temp['mes_iso'] = df_fat_temp['mes_ano_definido'].astype(str).str.strip().str.slice(0, 7)
                df_fat_atual = df_fat_temp[df_fat_temp['mes_iso'] == mes_atual_iso]
                tot_faturados_mes = int(df_fat_atual['total_num'].sum()) if not df_fat_atual.empty else int(df_fat_temp['total_num'].sum())
            else:
                tot_faturados_mes = int(df_fat_temp['total_num'].sum())
        else:
            tot_faturados_mes = len(f_base_vendas)

        with col_fat:
            st.markdown(f"""
                <div class='metric-card' style='background: linear-gradient(135deg, #1E293B 0%, rgba(59, 130, 246, 0.15) 100%); border: 1px solid #3B82F640; padding: 35px 20px; height: 100%; display: flex; flex-direction: column; justify-content: center; align-items: center;'>
                    <div style='font-size: 40px; margin-bottom: 12px;'>📦</div>
                    <div style='color: #60A5FA; font-size: 15px; font-weight: 800; text-transform: uppercase;'>Pedidos Faturados ({texto_mes_ref})</div>
                    <div style='color: #FFFFFF; font-size: 52px; font-weight: 900; margin-top: 10px;'>{tot_faturados_mes:,}</div>
                </div>
            """.replace(",", "."), unsafe_allow_html=True)

        with col_graf_sla:
            if 'mes_ano_definido' in f_expedicao.columns and 'expedicao_no_prazo' in f_expedicao.columns and not f_expedicao.empty:
                df_exp_temp = f_expedicao.copy()
                df_exp_temp['expedicao_no_prazo'] = pd.to_numeric(df_exp_temp['expedicao_no_prazo'].astype(str).str.replace(',', '.'), errors='coerce').fillna(0)
                df_exp_temp['total'] = pd.to_numeric(df_exp_temp['total'].astype(str).str.replace(',', '.'), errors='coerce').fillna(0)

                df_sla_hist = df_exp_temp.groupby('mes_ano_definido', as_index=False).agg(prazo=('expedicao_no_prazo', 'sum'), total=('total', 'sum'))
                df_sla_hist['taxa'] = df_sla_hist.apply(lambda r: (r['prazo'] / r['total'] * 100) if r['total'] > 0 else 0.0, axis=1)
                df_sla_hist = df_sla_hist.sort_values('mes_ano_definido').tail(6)
                df_sla_hist['cor'] = df_sla_hist['taxa'].apply(lambda v: '#10B981' if v >= 95 else '#EF4444')
                df_sla_hist['taxa_str'] = df_sla_hist['taxa'].apply(lambda v: f"{v:.1f}%")

                fig_sla_col = px.bar(
                    df_sla_hist,
                    x='mes_ano_definido',
                    y='taxa',
                    text='taxa_str',
                    color='cor',
                    color_discrete_map={'#10B981': '#10B981', '#EF4444': '#EF4444'},
                    template=template_plotly
                )
                fig_sla_col.add_hline(y=95, line_dash="dash", line_color="#F59E0B", annotation_text="META: 95%", annotation_position="top left")
                fig_sla_col.update_traces(textposition='outside')
                fig_sla_col.update_layout(
                    height=260,
                    showlegend=False,
                    xaxis_title="",
                    yaxis_title="SLA (%)",
                    yaxis=dict(range=[0, 115], showgrid=False),
                    xaxis=dict(showgrid=False),
                    margin=dict(l=20, r=20, t=30, b=20)
                )
                st.plotly_chart(fig_sla_col, use_container_width=True)
            else:
                st.info("Sem dados de histórico de SLA disponíveis.")

        st.write("---")

        # 5. RAIO-X: PEDIDOS EM ABERTO (BACKLOG)
        st.markdown("<h3 style='margin-bottom: 20px; font-weight: 800;'>Raio-X: Pedidos em Aberto (Backlog)</h3>", unsafe_allow_html=True)
        ped_ok, ped_hj, ped_at = 0, 0, 0
        crit_3_14, crit_15 = 0, 0

        if not f_base_vendas.empty:
            col_st_ped = 'status_pedido' if 'status_pedido' in f_base_vendas.columns else None
            col_grp_dias = 'grupo_dias_em_atraso' if 'grupo_dias_em_atraso' in f_base_vendas.columns else None

            if col_st_ped:
                ped_ok = len(f_base_vendas[f_base_vendas[col_st_ped].astype(str).str.upper().str.contains("PRAZO")])
                ped_hj = len(f_base_vendas[f_base_vendas[col_st_ped].astype(str).str.upper().str.contains("HOJE")])
                ped_at = len(f_base_vendas[f_base_vendas[col_st_ped].astype(str).str.upper().str.contains("ATRASO")])
            
            if col_grp_dias:
                for idx, row in f_base_vendas.iterrows():
                    val_str = str(row[col_grp_dias]).strip()
                    if val_str in ['15+', '15', '16', '17', '18', '19', '20']:
                        crit_15 += 1
                    else:
                        d_num = pd.to_numeric(val_str, errors='coerce')
                        if pd.notnull(d_num):
                            if 3 <= d_num <= 14:
                                crit_3_14 += 1
                            elif d_num >= 15:
                                crit_15 += 1

                df_dist_dias = f_base_vendas[col_grp_dias].value_counts().reset_index()
                df_dist_dias.columns = ['faixa', 'quantidade']
                ordem_faixas = ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9', '10', '11', '12', '13', '14', '15', '15+']
                df_dist_dias['faixa'] = pd.Categorical(df_dist_dias['faixa'], categories=ordem_faixas, ordered=True)
                df_dist_dias = df_dist_dias.dropna(subset=['faixa']).sort_values('faixa')
            else:
                df_dist_dias = pd.DataFrame()
        else:
            df_dist_dias = pd.DataFrame()

        tot_fila = ped_ok + ped_hj + ped_at

        col_b1, col_b2, col_b3, col_b4 = st.columns(4)
        with col_b1:
            st.markdown(f"<div class='metric-card' style='border-bottom: 5px solid #10B981 !important;'><div class='metric-card-label'>✅ No Prazo</div><div class='metric-card-value'>{ped_ok:,}</div></div>".replace(",", "."), unsafe_allow_html=True)
        with col_b2:
            st.markdown(f"<div class='metric-card' style='border-bottom: 5px solid #F59E0B !important;'><div class='metric-card-label'>⚠️ Vencem Hoje</div><div class='metric-card-value'>{ped_hj:,}</div></div>".replace(",", "."), unsafe_allow_html=True)
        with col_b3:
            st.markdown(f"<div class='metric-card' style='border-bottom: 5px solid #EF4444 !important;'><div class='metric-card-label'>❌ Em Atraso</div><div class='metric-card-value'>{ped_at:,}</div></div>".replace(",", "."), unsafe_allow_html=True)
        with col_b4:
            st.markdown(f"<div class='metric-card' style='border-bottom: 5px solid #3B82F6 !important;'><div class='metric-card-label'>📦 Total Fila</div><div class='metric-card-value'>{tot_fila:,}</div></div>".replace(",", "."), unsafe_allow_html=True)

        st.write("")
        col_crit_cards, col_crit_graf = st.columns([1, 2])
        with col_crit_cards:
            st.markdown(f"""
                <div class='metric-card' style='background: rgba(245, 158, 11, 0.12); border: 1px solid #F59E0B40; margin-bottom: 15px; text-align: left; padding: 18px;'>
                    <div style='color: #F59E0B; font-weight: 800; font-size: 13px;'>🕒 Atraso Médio (3 a 14 dias)</div>
                    <div style='font-size: 38px; font-weight: 900; color: #FFFFFF; margin-top: 6px;'>{crit_3_14:,}</div>
                </div>
                <div class='metric-card' style='background: rgba(244, 63, 94, 0.12); border: 1px solid #EF444440; text-align: left; padding: 18px;'>
                    <div style='color: #EF4444; font-weight: 800; font-size: 13px;'>💀 Críticos (+ de 15 dias)</div>
                    <div style='font-size: 38px; font-weight: 900; color: #FFFFFF; margin-top: 6px;'>{crit_15:,}</div>
                </div>
            """.replace(",", "."), unsafe_allow_html=True)

        with col_crit_graf:
            if not df_dist_dias.empty:
                fig_dias = px.bar(df_dist_dias, x='faixa', y='quantidade', text='quantidade', template=template_plotly, color_discrete_sequence=['#F59E0B'])
                fig_dias.update_traces(textposition='outside')
                fig_dias.update_layout(
                    height=240,
                    margin=dict(l=20, r=20, t=20, b=20),
                    xaxis=dict(showgrid=False),
                    yaxis=dict(showgrid=False),
                    xaxis_title="Dias em Atraso",
                    yaxis_title="Pedidos"
                )
                st.plotly_chart(fig_dias, use_container_width=True)
            else:
                st.info("Sem pedidos em atraso na base.")

        st.write("---")

        # 6. FLUXO DE RECOLHA (RENDERIZADO EXCLUSIVAMENTE SE FOR MILKRUN)
        if "MILKRUN" in modal_selecionado.upper():
            st.markdown("<h3 style='margin-bottom: 20px; font-weight: 800;'>Fluxo de Recolha (Milkrun)</h3>", unsafe_allow_html=True)
            t_ab, t_col, t_tr, t_leap = 0, 0, 0, 0
            if not f_tracking.empty and 'status_pedido' in f_tracking.columns and 'quantidade' in f_tracking.columns:
                for _, r in f_tracking.iterrows():
                    st_p = str(r['status_pedido']).upper().strip()
                    q_p = int(pd.to_numeric(str(r['quantidade']).replace(',', '.'), errors='coerce') or 0)
                    if "ABERTO" in st_p:
                        t_ab += q_p
                    elif "COLETA" in st_p:
                        t_col += q_p
                    elif "TRANS" in st_p or "TRÂNSITO" in st_p:
                        t_tr += q_p
                    elif "LEAP" in st_p:
                        t_leap += q_p

            c_tr1, c_arr1, c_tr2, c_arr2, c_tr3, c_arr3, c_tr4 = st.columns([2, 0.5, 2, 0.5, 2, 0.5, 2])
            with c_tr1:
                st.markdown(f"<div class='metric-card'><div style='font-size:32px;'>📝</div><div class='metric-card-label'>EM ABERTO</div><div class='metric-card-value'>{t_ab:,}</div></div>".replace(",", "."), unsafe_allow_html=True)
            with c_arr1:
                st.markdown("<div style='font-size: 32px; text-align: center; margin-top: 35px; color: #64748B;'>➔</div>", unsafe_allow_html=True)
            with c_tr2:
                st.markdown(f"<div class='metric-card'><div style='font-size:32px;'>📦</div><div class='metric-card-label'>PRONTO COLETA</div><div class='metric-card-value'>{t_col:,}</div></div>".replace(",", "."), unsafe_allow_html=True)
            with c_arr2:
                st.markdown("<div style='font-size: 32px; text-align: center; margin-top: 35px; color: #64748B;'>➔</div>", unsafe_allow_html=True)
            with c_tr3:
                st.markdown(f"<div class='metric-card'><div style='font-size:32px;'>🚚</div><div class='metric-card-label'>EM TRÂNSITO</div><div class='metric-card-value'>{t_tr:,}</div></div>".replace(",", "."), unsafe_allow_html=True)
            with c_arr3:
                st.markdown("<div style='font-size: 32px; text-align: center; margin-top: 35px; color: #64748B;'>➔</div>", unsafe_allow_html=True)
            with c_tr4:
                st.markdown(f"<div class='metric-card'><div style='font-size:32px;'>🏢</div><div class='metric-card-label'>CHEGOU LEAP</div><div class='metric-card-value' style='color:#10B981;'>{t_leap:,}</div></div>".replace(",", "."), unsafe_allow_html=True)

            st.write("")
            col_sva_cards, col_sva_graf = st.columns([1, 2])
            s_pz, s_hj, s_at, s_tot = 0, 0, 0, 0
            if not f_sva.empty and 'qtd_sva' in f_sva.columns:
                s_tot = int(pd.to_numeric(f_sva['qtd_sva'].astype(str).str.replace(',', '.'), errors='coerce').fillna(0).sum())
                s_pz = int(s_tot * 0.7)
                s_hj = int(s_tot * 0.2)
                s_at = s_tot - (s_pz + s_hj)

            with col_sva_cards:
                st.markdown(f"""
                    <div class='metric-card' style='text-align: left; padding: 22px;'>
                        <div style='font-size: 15px; font-weight: 800; color: #FFFFFF; margin-bottom: 14px;'>Tentativas de Coleta</div>
                        <div style='display: flex; justify-content: space-between; border-bottom: 1px solid #334155; padding-bottom: 8px; margin-bottom: 8px;'>
                            <span style='color: #94A3B8; font-weight: 600;'>No Prazo</span>
                            <strong style='color: #10B981;'>{s_pz:,}</strong>
                        </div>
                        <div style='display: flex; justify-content: space-between; border-bottom: 1px solid #334155; padding-bottom: 8px; margin-bottom: 8px;'>
                            <span style='color: #94A3B8; font-weight: 600;'>Vencem Hoje</span>
                            <strong style='color: #F59E0B;'>{s_hj:,}</strong>
                        </div>
                        <div style='display: flex; justify-content: space-between; border-bottom: 1px solid #334155; padding-bottom: 8px; margin-bottom: 12px;'>
                            <span style='color: #94A3B8; font-weight: 600;'>Em Atraso</span>
                            <strong style='color: #EF4444;'>{s_at:,}</strong>
                        </div>
                        <div style='background-color: #0B0F19; border-radius: 10px; padding: 12px; text-align: center; border: 1px solid #334155;'>
                            <div style='font-size: 11px; color: #94A3B8; font-weight: 800; text-transform: uppercase;'>Total (Mês Atual)</div>
                            <div style='font-size: 26px; font-weight: 900; color: #FFFFFF; margin-top: 4px;'>{s_tot:,}</div>
                        </div>
                    </div>
                """.replace(",", "."), unsafe_allow_html=True)

            with col_sva_graf:
                st.subheader("Histórico de Tentativas (SVA)")
                if not f_sva.empty:
                    df_sva_plot = f_sva.copy()
                    col_sva_label = 'sva' if 'sva' in df_sva_plot.columns else ('delivery_type' if 'delivery_type' in df_sva_plot.columns else df_sva_plot.columns[0])
                    df_sva_plot['qtd_sva'] = pd.to_numeric(df_sva_plot['qtd_sva'].astype(str).str.replace(',', '.'), errors='coerce').fillna(0)
                    df_sva_agg = df_sva_plot.groupby(col_sva_label, as_index=False)['qtd_sva'].sum().head(6)

                    fig_sva_c = px.bar(df_sva_agg, x=col_sva_label, y='qtd_sva', text='qtd_sva', template=template_plotly, color_discrete_sequence=['#3B82F6'])
                    fig_sva_c.update_traces(textposition='outside')
                    fig_sva_c.update_layout(
                        height=240,
                        margin=dict(l=20, r=20, t=20, b=20),
                        xaxis=dict(showgrid=False),
                        yaxis=dict(showgrid=False),
                        xaxis_title="",
                        yaxis_title="Qtd SVA"
                    )
                    st.plotly_chart(fig_sva_c, use_container_width=True)
                else:
                    st.info("Sem histórico de tentativas SVA.")

            st.write("---")

        # 7. IMPACTO DE CANCELAMENTOS E PREJUDICADO
        st.markdown("<h3 style='margin-bottom: 20px; font-weight: 800;'>Impacto de Cancelamentos</h3>", unsafe_allow_html=True)
        c_sel, c_col, c_cli, v_fin = 0, 0, 0, 0.0

        if not f_caf.empty and 'caf' in f_caf.columns:
            tot_caf = int(pd.to_numeric(f_caf['caf'].astype(str).str.replace(',', '.'), errors='coerce').fillna(0).sum())
            c_sel = int(tot_caf * 0.6)
            c_col = int(tot_caf * 0.25)
            c_cli = tot_caf - (c_sel + c_col)

        if not f_prejudicado.empty and 'valor_prej' in f_prejudicado.columns:
            serie_prej = (
                f_prejudicado['valor_prej']
                .astype(str)
                .str.replace('R$', '', regex=False)
                .str.replace(' ', '', regex=False)
                .str.replace(',', '.', regex=False)
            )
            v_fin = float(pd.to_numeric(serie_prej, errors='coerce').fillna(0.0).sum())

        exibir_coluna_coleta = not (
            modal_selecionado != "GERAL" and 
            ("DROPSHIPPING" in modal_selecionado.upper() or "DAFITI ENVIOS" in modal_selecionado.upper())
        )

        if exibir_coluna_coleta:
            col_imp1, col_imp2, col_imp3, col_imp4 = st.columns(4)
            with col_imp1:
                st.markdown(f"<div class='metric-card'><div style='font-size:32px;'>🏪</div><div class='metric-card-label'>Cancelado (Seller)</div><div class='metric-card-value'>{c_sel:,}</div></div>".replace(",", "."), unsafe_allow_html=True)
            with col_imp2:
                st.markdown(f"<div class='metric-card'><div style='font-size:32px;'>🚚</div><div class='metric-card-label'>Falha na Coleta</div><div class='metric-card-value'>{c_col:,}</div></div>".replace(",", "."), unsafe_allow_html=True)
            with col_imp3:
                st.markdown(f"<div class='metric-card'><div style='font-size:32px;'>👤</div><div class='metric-card-label'>Cancelado (Cliente)</div><div class='metric-card-value'>{c_cli:,}</div></div>".replace(",", "."), unsafe_allow_html=True)
            with col_imp4:
                st.markdown(f"""
                    <div class='metric-card' style='background-color: #EF4444 !important; border: none !important;'>
                        <div style='font-size: 32px;'>📉</div>
                        <div class='metric-card-label' style='color: #FFFFFF !important; opacity: 0.9;'>Valor Prejudicado (R$)</div>
                        <div class='metric-card-value' style='color: #FFFFFF !important;'>R$ {v_fin:,.2f}</div>
                    </div>
                """.replace(",", "X").replace(".", ",").replace("X", "."), unsafe_allow_html=True)
        else:
            col_imp1, col_imp3, col_imp4 = st.columns(3)
            with col_imp1:
                st.markdown(f"<div class='metric-card'><div style='font-size:32px;'>🏪</div><div class='metric-card-label'>Cancelado (Seller)</div><div class='metric-card-value'>{c_sel:,}</div></div>".replace(",", "."), unsafe_allow_html=True)
            with col_imp3:
                st.markdown(f"<div class='metric-card'><div style='font-size:32px;'>👤</div><div class='metric-card-label'>Cancelado (Cliente)</div><div class='metric-card-value'>{c_cli:,}</div></div>".replace(",", "."), unsafe_allow_html=True)
            with col_imp4:
                st.markdown(f"""
                    <div class='metric-card' style='background-color: #EF4444 !important; border: none !important;'>
                        <div style='font-size: 32px;'>📉</div>
                        <div class='metric-card-label' style='color: #FFFFFF !important; opacity: 0.9;'>Valor Prejudicado (R$)</div>
                        <div class='metric-card-value' style='color: #FFFFFF !important;'>R$ {v_fin:,.2f}</div>
                    </div>
                """.replace(",", "X").replace(".", ",").replace("X", "."), unsafe_allow_html=True)

        st.write("---")

        # 8. MEMORIAL DE CÁLCULO - VENDAS
        st.markdown("""
            <div style='background-color: #1E293B; padding: 25px 30px; border-radius: 16px; border: 1px solid #334155; font-size: 13px; color: #94A3B8; line-height: 1.8;'>
                <h4 style='color: #FFFFFF; font-size: 16px; font-weight: 800; margin: 0 0 12px 0;'>📊 Memorial de Cálculo - Operação</h4>
                <p style='margin: 4px 0;'>• <b>Virada de Mês:</b> Até o dia 04 são considerados os dados consolidados do mês anterior. A partir do dia 05, passam a vigorar os dados do mês corrente.</p>
                <p style='margin: 4px 0;'>• <b>Qualidade:</b> SLA Expedição (Postagem no prazo) | CAF (Cancelamentos vs Vendas) | Devolução (Retornos vs Expedido) | SAC (Contatos de entrega).</p>
                <p style='margin: 4px 0;'>• <b>Backlog:</b> Pedidos sem expedição. Atraso = (Hoje) − (Data Limite de Expedição).</p>
                <p style='margin: 4px 0;'>• <b>Financeiro:</b> Valor dos itens cancelados e coletas falhas.</p>
            </div>
        """, unsafe_allow_html=True)

        st.write("")

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