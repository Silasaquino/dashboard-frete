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
    """Limpa sessão e remove os parâmetros da URL para logout seguro."""
    st.session_state["autenticado"] = False
    st.session_state["usuario_logado"] = None
    st.session_state["empresa_logada"] = None
    st.session_state["ultima_atividade"] = None
    st.query_params.clear()


def validar_e_restaurar_sessao():
    """MANTÉM O LOGIN APÓS F5: Verifica a URL e valida o limite de 10 minutos."""
    agora = datetime.now()
    
    # 1. Tenta restaurar da URL se deu F5
    params = st.query_params
    if "user" in params and "empresa" in params and "time" in params:
        try:
            time_stamp_str = params["time"]
            ultima_atividade = datetime.fromtimestamp(float(time_stamp_str))
            
            # Se ainda estiver dentro dos 10 minutos
            if agora - ultima_atividade <= timedelta(minutes=TEMPO_EXPIRED_MINUTOS):
                st.session_state["autenticado"] = True
                st.session_state["usuario_logado"] = params["user"]
                st.session_state["empresa_logada"] = params["empresa"]
                st.session_state["ultima_atividade"] = agora
                # Atualiza a hora da última atividade na URL
                st.query_params["time"] = str(agora.timestamp())
                return True
            else:
                fazer_logout()
                st.warning("⚠️ A sua sessão expirou por inatividade (10 minutos). Por favor, faça login novamente.")
                return False
        except Exception:
            fazer_logout()
            return False

    # 2. Se já estiver no session_state durante o uso contínuo
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

        # Grava os parâmetros na URL para resistir ao F5
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


# Executa a validação de sessão
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

    # --- BARRA LATERAL (SIDEBAR LIMPA) ---
    st.sidebar.title("Perfil")
    st.sidebar.write(f"👤 **Utilizador:** {st.session_state.get('usuario_logado', '')}")
    st.sidebar.write(f"🏢 **Empresa:** {empresa_usuario}")
    st.sidebar.button("🚪 Sair / Logout", on_click=fazer_logout, key="btn_logout")

    # ==========================================
    # CARREGAMENTO CONSOLIDADO REVERSA (ORIGINAL DE SEXTA)
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
                except Exception as e:
                    print(f"⚠️ Erro ao carregar Sheet ID {sheet_id}: {e}")

            if not df_temp.empty and len(df_temp.columns) > 1:
                lista_dfs.append(df_temp)

        if lista_dfs:
            df_final = pd.concat(lista_dfs, ignore_index=True)
            if 'seller_name' in df_final.columns:
                df_final['seller_name'] = df_final['seller_name'].fillna('N/A').astype(str)
            return df_final
        else:
            return pd.DataFrame()

    @st.cache_data(ttl=1800, show_spinner=False)
    def carregar_dados_resumo():
        url_csv_resumo = f"https://docs.google.com/spreadsheets/d/{SHEET_ID_RESUMO}/gviz/tq?tqx=out:csv&sheet=RESUMO%20REVERSA"
        try:
            df_resumo = pd.read_csv(url_csv_resumo, low_memory=False)
            if 'nome_seller' in df_resumo.columns:
                df_resumo['nome_seller'] = df_resumo['nome_seller'].fillna('N/A').astype(str)
            return df_resumo
        except Exception as e:
            st.error(f"Erro ao carregar dados da folha 'RESUMO REVERSA': {e}")
            return pd.DataFrame()

    @st.cache_data(ttl=1800, show_spinner=False)
    def extrair_lista_sellers(df_base):
        if 'seller_name' in df_base.columns:
            s_validos = sorted([str(s) for s in df_base['seller_name'].unique() if s and str(s).lower() not in ['n/a', 'nan', 'none']])
            return ["Todos"] + s_validos
        return ["Todos"]

    with st.spinner("⚡ A otimizar e carregar base consolidada na memória..."):
        df_raw_reversa = carregar_dados_reversa_consolidados()
        df_raw_resumo = carregar_dados_resumo()

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

    # Carrega dados de vendas de forma preguiçosa/cacheada
    df_res_expedicao = carregar_aba_vendas_resumo("RESUMO VENDAS_EXPEDIÇÃO")
    df_res_caf = carregar_aba_vendas_resumo("RESUMO_CAF")
    df_res_entregas = carregar_aba_vendas_resumo("RESUMO_ENTREGAS")
    df_res_prejudicado = carregar_aba_vendas_resumo("RESUMO_PREJUDICADO")
    df_res_sva = carregar_aba_vendas_resumo("RESUMO_SVA")
    df_res_tracking = carregar_aba_vendas_resumo("RESUMO_TRACKING")
    df_res_status_loja = carregar_aba_vendas_resumo("RESUMO_STATUS_LOJA")
    df_raw_vendas_base = carregar_base_vendas()

    # ==========================================
    # ABAS SUPERIORES DE NAVEGAÇÃO
    # ==========================================
    aba_reversa, aba_vendas = st.tabs([
        "🔄 Operação Reversa", 
        "💰 Vendas"
    ])

    # ==========================================
    # ABA: OPERAÇÃO REVERSA (ESTRUTURA 100% INTACTA DE SEXTA-FEIRA)
    # ==========================================
    with aba_reversa:
        col_modal, col_seller, col_tema = st.columns([2, 2.5, 1.5])

        with col_seller:
            st.markdown("<span style='font-size:12px; font-weight:800; color:#9CA3AF; letter-spacing:1px;'>🎯 SELEÇÃO DE SELLER</span>", unsafe_allow_html=True)
            if empresa_usuario.upper() == "DAFITI":
                lista_sellers = extrair_lista_sellers(df_raw_reversa)
                seller_selecionado = st.selectbox(
                    "Selecione o Seller",
                    lista_sellers,
                    index=0,
                    label_visibility="collapsed"
                )
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

        with col_modal:
            st.markdown("<span style='font-size:12px; font-weight:800; color:#9CA3AF; letter-spacing:1px;'>MODAL ANALISADO</span>", unsafe_allow_html=True)
            modal_selecionado = st.selectbox(
                "Modal Analisado",
                modais_existentes,
                index=0,
                label_visibility="collapsed"
            )

        with col_tema:
            st.markdown("<span style='font-size:12px; font-weight:800; color:#9CA3AF; letter-spacing:1px;'>TEMA DA TELA</span>", unsafe_allow_html=True)
            tema_selecionado = st.selectbox(
                "Tema do Dashboard",
                ["Escuro 🌙", "Claro ☀️"],
                index=0,
                label_visibility="collapsed"
            )

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

        mask_reversa = pd.Series(True, index=df_raw_reversa.index)
        mask_resumo = pd.Series(True, index=df_raw_resumo.index)

        # 1. Filtro por Seller
        target_seller = seller_selecionado if empresa_usuario.upper() == "DAFITI" else empresa_usuario
        if target_seller != "Todos":
            target_str = str(target_seller).strip().upper()
            if 'seller_name' in df_raw_reversa.columns:
                mask_reversa &= (df_raw_reversa['seller_name'].astype(str).str.strip().str.upper() == target_str)
            if 'nome_seller' in df_raw_resumo.columns:
                mask_resumo &= (df_raw_resumo['nome_seller'].astype(str).str.strip().str.upper() == target_str)

        # 2. Filtro por Modal
        if modal_selecionado != "GERAL":
            mapeamento_modalidades = {
                "Dafiti Envios": ["dafiti envios", "dafiti_envios"],
                "Milkrun": ["milkrun"],
                "Dropshipping": ["dropshipping"],
                "Fulfillment": ["fulfillment"],
                "Retail": ["retail"]
            }
            valores_aceitos = mapeamento_modalidades.get(modal_selecionado, [modal_selecionado.lower()])

            if 'tipo_processo' in df_raw_reversa.columns:
                mask_reversa &= df_raw_reversa['tipo_processo'].astype(str).str.lower().isin(valores_aceitos)
            if 'delivery_type' in df_raw_resumo.columns:
                mask_resumo &= df_raw_resumo['delivery_type'].astype(str).str.lower().isin(valores_aceitos)

        df_filtrado_reversa = df_raw_reversa[mask_reversa]
        df_filtrado_resumo = df_raw_resumo[mask_resumo]

        # BARRA DE TÍTULO UNIFICADA
        data_hora_formatada = "N/D"
        if 'ultima_atualizacao_tabela' in df_raw_reversa.columns and not df_raw_reversa.empty:
            data_max = pd.to_datetime(df_raw_reversa['ultima_atualizacao_tabela']).max()
            data_hora_formatada = data_max.strftime('%d/%m/%Y às %H:%M:%S')

        st.markdown(
            f"""
            <div class='header-container-unificado'>
                <div class='header-titulo'>📋 Visão Geral da Operação Reversa</div>
                <div class='header-atualizacao'>🔄 Última Atualização: <b>{data_hora_formatada}</b></div>
            </div>
            """, 
            unsafe_allow_html=True
        )

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
            meses_disponiveis = ["Todos"] + sorted(
                [str(m) for m in df_filtrado_reversa[coluna_data_alvo].dropna().unique() if str(m).strip() != ""],
                reverse=True
            )
        else:
            meses_disponiveis = ["Todos"]

        with col_filtro_mes:
            st.markdown(f"<b>📆 Selecione o Período ({tipo_visao_data}):</b>", unsafe_allow_html=True)
            mes_selecionado = st.selectbox(
                f"Selecione o {tipo_visao_data}",
                meses_disponiveis,
                label_visibility="collapsed"
            )

        if mes_selecionado != "Todos" and coluna_data_alvo in df_filtrado_reversa.columns:
            df_filtrado_reversa = df_filtrado_reversa[
                df_filtrado_reversa[coluna_data_alvo].astype(str) == mes_selecionado
            ]

        st.write("")

        # KPIS
        colunas_chaves = ['pedido', 'remessa_retorno', 'protocolo']
        colunas_existentes = [c for c in colunas_chaves if c in df_filtrado_reversa.columns]
        
        if colunas_existentes and not df_filtrado_reversa.empty:
            qtd_remessas_unicas = df_filtrado_reversa[colunas_existentes[0]].nunique()
        else:
            qtd_remessas_unicas = len(df_filtrado_reversa)

        col_kpi1, col_kpi2, col_kpi3 = st.columns(3)

        with col_kpi1:
            st.markdown(f"<div class='metric-card'><div class='metric-card-label'>Total Linhas Agrupadas</div><div class='metric-card-value'>{len(df_filtrado_reversa):,}</div></div>".replace(",", "."), unsafe_allow_html=True)
        with col_kpi2:
            st.markdown(f"<div class='metric-card'><div class='metric-card-label'>Qtd. Remessas Únicas</div><div class='metric-card-value'>{qtd_remessas_unicas:,}</div></div>".replace(",", "."), unsafe_allow_html=True)
        with col_kpi3:
            st.markdown(f"<div class='metric-card'><div class='metric-card-label'>Modal Analisado</div><div class='metric-card-value'>{modal_selecionado}</div></div>", unsafe_allow_html=True)

        st.write("")
        st.write("---")

        # ==========================================
        # BLOCO 1: GRÁFICOS DE RESUMO
        # ==========================================
        st.markdown("<h3 style='text-align: center;'>📊 Indicadores de Devolução por Seller e Meta</h3>", unsafe_allow_html=True)
        st.write("")

        col_graf3, col_graf4 = st.columns(2)
        META_TAXA_SELLER = 0.09

        # GRÁFICO 1: EVOLUÇÃO MENSAL
        with col_graf3:
            st.subheader("🎯 Evolução Mensal da Taxa de Devolução")
            col_taxa = 'taxa_devolucao' if 'taxa_devolucao' in df_filtrado_resumo.columns else 'taxa_devolucao_seller'
            col_dev = 'devolvido' if 'devolvido' in df_filtrado_resumo.columns else 'devolvido_seller'

            if 'mes_ano_definido' in df_filtrado_resumo.columns and col_taxa in df_filtrado_resumo.columns and not df_filtrado_resumo.empty:
                df_resumo_temp = df_filtrado_resumo
                
                if 'qtd_etr' in df_resumo_temp.columns and col_dev in df_resumo_temp.columns:
                    df_evolucao_taxa = df_resumo_temp.groupby('mes_ano_definido', as_index=False).agg(
                        tot_etr=('qtd_etr', 'sum'),
                        tot_dev=(col_dev, 'sum')
                    )
                    df_evolucao_taxa['taxa_calc'] = df_evolucao_taxa['tot_dev'] / df_evolucao_taxa['tot_etr']
                else:
                    df_evolucao_taxa = df_resumo_temp.groupby('mes_ano_definido', as_index=False)[col_taxa].mean()
                    df_evolucao_taxa.rename(columns={col_taxa: 'taxa_calc'}, inplace=True)

                df_evolucao_taxa = df_evolucao_taxa.sort_values('mes_ano_definido')
                df_evolucao_taxa['taxa_pct_str'] = df_evolucao_taxa['taxa_calc'].apply(lambda v: f"{v*100:.1f}%" if pd.notnull(v) else "0.0%")
                
                cores_pontos = ['#EF4444' if val > META_TAXA_SELLER else cor_grafico for val in df_evolucao_taxa['taxa_calc']]

                fig_linha_taxa = go.Figure()
                fig_linha_taxa.add_trace(go.Scatter(
                    x=df_evolucao_taxa['mes_ano_definido'],
                    y=df_evolucao_taxa['taxa_calc'],
                    mode='lines+markers+text',
                    text=df_evolucao_taxa['taxa_pct_str'],
                    textposition='top center',
                    line=dict(color=cor_grafico, width=3),
                    marker=dict(size=10, color=cores_pontos),
                    name='Taxa Devolução'
                ))

                fig_linha_taxa.add_shape(
                    type="line",
                    x0=df_evolucao_taxa['mes_ano_definido'].iloc[0],
                    y0=META_TAXA_SELLER,
                    x1=df_evolucao_taxa['mes_ano_definido'].iloc[-1],
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
                    yaxis=dict(tickformat='.1%', title="Taxa (%)", range=[0, max_taxa_y * 1.22], showgrid=False),
                    xaxis=dict(showgrid=False),
                    showlegend=False
                )
                st.plotly_chart(fig_linha_taxa, use_container_width=True)
            else:
                st.info("Sem dados de resumo registrados para o Seller selecionado no período.")

        # GRÁFICO 2: TOP SELLERS EM ABERTO
        with col_graf4:
            st.subheader("⚠️ Top Sellers - Maior % Devolução em Aberto")
            if 'nome_seller' in df_filtrado_resumo.columns and 'taxa_devolucao_aberto' in df_filtrado_resumo.columns and not df_filtrado_resumo.empty:
                df_aberto_temp = df_filtrado_resumo
                
                if 'qtd_etr' in df_aberto_temp.columns and 'devolucao_em_aberto' in df_aberto_temp.columns:
                    df_top_aberto = df_aberto_temp.groupby('nome_seller', as_index=False).agg(
                        tot_etr=('qtd_etr', 'sum'),
                        tot_aberto=('devolucao_em_aberto', 'sum')
                    )
                    df_top_aberto['taxa_aberto'] = df_top_aberto['tot_aberto'] / df_top_aberto['tot_etr']
                else:
                    df_top_aberto = df_aberto_temp.groupby('nome_seller', as_index=False)['taxa_devolucao_aberto'].mean()
                    df_top_aberto.rename(columns={'taxa_devolucao_aberto': 'taxa_aberto'}, inplace=True)

                df_top_aberto = df_top_aberto.sort_values('taxa_aberto', ascending=False).head(10).sort_values('taxa_aberto', ascending=True)
                df_top_aberto['taxa_str'] = df_top_aberto['taxa_aberto'].apply(lambda v: f"{v*100:.1f}%" if pd.notnull(v) else "0.0%")

                fig_top_aberto = px.bar(
                    df_top_aberto,
                    x='taxa_aberto',
                    y='nome_seller',
                    text='taxa_str',
                    orientation='h',
                    template=template_plotly,
                    color_discrete_sequence=['#EF4444']
                )

                max_taxa_aberto = df_top_aberto['taxa_aberto'].max() if not df_top_aberto.empty else 0.50

                fig_top_aberto.update_traces(textposition='outside')
                fig_top_aberto.update_layout(
                    template=template_plotly,
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(0,0,0,0)',
                    margin=dict(l=20, r=100, t=30, b=20),
                    height=380,
                    xaxis=dict(tickformat='.1%', range=[0, max_taxa_aberto * 1.35], showgrid=False),
                    yaxis=dict(showgrid=False)
                )
                st.plotly_chart(fig_top_aberto, use_container_width=True)
            else:
                st.info("Sem dados em aberto registrados para este Seller.")

        st.write("---")

        # ==========================================
        # BLOCO 2: GRÁFICOS DETALHADOS
        # ==========================================
        st.markdown("<h3 style='text-align: center;'>📈 Análise Gráfica das Devoluções (Remessas Únicas)</h3>", unsafe_allow_html=True)
        st.write("")

        # GRÁFICO 3: VOLUME MENSAL DE REMESSAS
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

        # GRÁFICO 4: MOTIVOS DE TROCA
        with col_graf_mot:
            st.subheader("🔍 Principais Motivos de Troca")
            if 'motivo_troca' in df_filtrado_reversa.columns and not df_filtrado_reversa.empty:
                df_motivos = df_filtrado_reversa['motivo_troca'].value_counts().head(10).reset_index()
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

        # GRÁFICO 5: FAIXAS DE ATRASO NO SELLER (+5 DIAS)
        with col_graf_grupo:
            st.subheader("📦 Sellers - Dias com Pacote Entregue sem Finalizar")
            if 'tracking' in df_filtrado_reversa.columns and 'grupo_aberto_seller' in df_filtrado_reversa.columns and not df_filtrado_reversa.empty:
                df_entregue_seller = df_filtrado_reversa[
                    df_filtrado_reversa['tracking'].astype(str).str.strip().str.upper() == 'ENTREGUE AO SELLER'
                ]

                if not df_entregue_seller.empty:
                    df_grupo_seller = df_entregue_seller['grupo_aberto_seller'].value_counts().reset_index()
                    df_grupo_seller.columns = ['grupo_dias', 'quantidade']
                    total_grupo = df_grupo_seller['quantidade'].sum()

                    df_grupo_seller['rotulo'] = df_grupo_seller['quantidade'].apply(
                        lambda v: f"{v:,} ({(v / total_grupo) * 100:.1f}%)".replace(",", ".") if total_grupo > 0 else "0"
                    )

                    df_grupo_seller['grupo_exibicao'] = df_grupo_seller['grupo_dias'].astype(str).apply(lambda g: "⚠️ +5 DIAS CORRIDOS" if "5 DIAS" in g and "+" in g else g)

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

        # GRÁFICO 6: JORNADA DO TRACKING
        st.markdown("<h3 style='text-align: center;'>🚚 Jornada do Tracking (Fluxo Sequencial Reversa)</h3>", unsafe_allow_html=True)
        if 'tracking' in df_filtrado_reversa.columns and not df_filtrado_reversa.empty:
            df_tracking = df_filtrado_reversa['tracking'].value_counts().reset_index()
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
                height=480,
                xaxis=dict(showgrid=False, zeroline=False, showticklabels=False, range=[0.4, 6.6]),
                yaxis=dict(showgrid=False, zeroline=False, showticklabels=False, range=[-0.2, 4.5])
            )
            st.plotly_chart(fig_jornada, use_container_width=True)

        st.write("---")

        # ÁREA DE DOWNLOAD DO CSV
        col_bot1, col_bot2, col_bot3 = st.columns([1, 2, 1])
        with col_bot2:
            dados_csv = converter_df_para_csv(df_filtrado_reversa)
            nome_arquivo_csv = f"relatorio_reversa_{empresa_usuario.lower().replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
            st.download_button(
                label="📥 Descarregar Relatório Completo em CSV (.csv)",
                data=dados_csv,
                file_name=nome_arquivo_csv,
                mime="text/csv",
                use_container_width=True
            )

    # ==========================================
    # ABA: VENDAS (MÓDULO COMPLETO CONSTRUÍDO)
    # ==========================================
    with aba_vendas:
        # Seletor de Modal específico para Vendas
        col_v_modal, col_v_esp = st.columns([2, 4])
        modais_vendas = ["GERAL", "DAFITI ENVIOS", "MILKRUN", "DROPSHIPPING"]
        with col_v_modal:
            st.markdown("<span style='font-size:12px; font-weight:800; color:#9CA3AF; letter-spacing:1px;'>MODAL ANALISADO (VENDAS)</span>", unsafe_allow_html=True)
            modal_vendas_sel = st.selectbox("Modal Vendas", modais_vendas, index=0, key="sb_vendas_modal", label_visibility="collapsed")

        # Filtro de dados de vendas para o Seller selecionado/logado
        target_seller_vendas = seller_selecionado if empresa_usuario.upper() == "DAFITI" else empresa_usuario
        target_str_v = str(target_seller_vendas).strip().upper()

        def filtrar_vendas(df_input):
            if df_input.empty:
                return df_input
            df_out = df_input.copy()
            if target_seller_vendas != "Todos" and 'nome_seller' in df_out.columns:
                df_out = df_out[df_out['nome_seller'].astype(str).str.strip().str.upper() == target_str_v]
            if modal_vendas_sel != "GERAL" and 'delivery_type' in df_out.columns:
                df_out = df_out[df_out['delivery_type'].astype(str).str.strip().str.upper() == modal_vendas_sel]
            return df_out

        f_expedicao = filtrar_vendas(df_res_expedicao)
        f_caf = filtrar_vendas(df_res_caf)
        f_entregas = filtrar_vendas(df_res_entregas)
        f_prejudicado = filtrar_vendas(df_res_prejudicado)
        f_sva = filtrar_vendas(df_res_sva)
        f_tracking = filtrar_vendas(df_res_tracking)
        f_status_loja = filtrar_vendas(df_res_status_loja)
        f_base_vendas = filtrar_vendas(df_raw_vendas_base)

        # Barra de Título Vendas
        data_hora_vendas = "N/D"
        if 'ultima_atualizacao_tabela' in df_raw_vendas_base.columns and not df_raw_vendas_base.empty:
            d_max_v = pd.to_datetime(df_raw_vendas_base['ultima_atualizacao_tabela']).max()
            data_hora_vendas = d_max_v.strftime('%d/%m/%Y às %H:%M:%S')

        st.markdown(
            f"""
            <div class='header-container-unificado'>
                <div class='header-titulo'>💰 Visão Geral de Vendas e Expedição</div>
                <div class='header-atualizacao'>🔄 Última Atualização: <b>{data_hora_vendas}</b></div>
            </div>
            """, 
            unsafe_allow_html=True
        )

        # Cálculos com conversão numérica forçada para evitar TypeError/ValueError
        if 'expedicao_no_prazo' in f_expedicao.columns and not f_expedicao.empty:
            tot_exp_prazo = float(pd.to_numeric(f_expedicao['expedicao_no_prazo'].astype(str).str.replace(',', '.'), errors='coerce').fillna(0).sum())
        else:
            tot_exp_prazo = 0.0

        if 'total' in f_expedicao.columns and not f_expedicao.empty:
            tot_exp_pedidos = float(pd.to_numeric(f_expedicao['total'].astype(str).str.replace(',', '.'), errors='coerce').fillna(0).sum())
        else:
            tot_exp_pedidos = 0.0
        taxa_exp_geral = (tot_exp_prazo / tot_exp_pedidos * 100) if tot_exp_pedidos > 0 else 0.0

        if 'entrega_no_prazo' in f_entregas.columns and not f_entregas.empty:
            tot_ent_prazo = float(pd.to_numeric(f_entregas['entrega_no_prazo'].astype(str).str.replace(',', '.'), errors='coerce').fillna(0).sum())
        else:
            tot_ent_prazo = 0.0

        if 'total' in f_entregas.columns and not f_entregas.empty:
            tot_ent_pedidos = float(pd.to_numeric(f_entregas['total'].astype(str).str.replace(',', '.'), errors='coerce').fillna(0).sum())
        else:
            tot_ent_pedidos = 0.0
        taxa_ent_geral = (tot_ent_prazo / tot_ent_pedidos * 100) if tot_ent_pedidos > 0 else 0.0

        if 'caf' in f_caf.columns and not f_caf.empty:
            tot_cafs = float(pd.to_numeric(f_caf['caf'].astype(str).str.replace(',', '.'), errors='coerce').fillna(0).sum())
        else:
            tot_cafs = 0.0

        if 'qtd' in f_caf.columns and not f_caf.empty:
            tot_itens_caf = float(pd.to_numeric(f_caf['qtd'].astype(str).str.replace(',', '.'), errors='coerce').fillna(0).sum())
        else:
            tot_itens_caf = 0.0
        taxa_caf_geral = (tot_cafs / tot_itens_caf * 100) if tot_itens_caf > 0 else 0.0

        if 'valor_prej' in f_prejudicado.columns and not f_prejudicado.empty:
            serie_prej = (
                f_prejudicado['valor_prej']
                .astype(str)
                .str.replace('R$', '', regex=False)
                .str.replace(' ', '', regex=False)
                .str.replace(',', '.', regex=False)
            )
            tot_prejudicado = float(pd.to_numeric(serie_prej, errors='coerce').fillna(0.0).sum())
        else:
            tot_prejudicado = 0.0

        if 'qtd_sva' in f_sva.columns and not f_sva.empty:
            tot_sva = int(pd.to_numeric(f_sva['qtd_sva'].astype(str).str.replace(',', '.'), errors='coerce').fillna(0).sum())
        else:
            tot_sva = 0

        # Cards KPIs de Vendas
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

        # Gráficos de Vendas
        col_g_exp, col_g_track = st.columns(2)

        with col_g_exp:
            st.subheader("📦 Taxa de Expedição no Prazo por Mês")
            if 'mes_ano_definido' in f_expedicao.columns and 'expedicao_no_prazo' in f_expedicao.columns and not f_expedicao.empty:
                df_exp_temp = f_expedicao.copy()
                df_exp_temp['expedicao_no_prazo'] = pd.to_numeric(df_exp_temp['expedicao_no_prazo'].astype(str).str.replace(',', '.'), errors='coerce').fillna(0)
                df_exp_temp['total'] = pd.to_numeric(df_exp_temp['total'].astype(str).str.replace(',', '.'), errors='coerce').fillna(0)

                df_exp_mes = df_exp_temp.groupby('mes_ano_definido', as_index=False).agg(prazo=('expedicao_no_prazo', 'sum'), total=('total', 'sum'))
                df_exp_mes['taxa'] = df_exp_mes.apply(lambda r: (r['prazo'] / r['total']) if r['total'] > 0 else 0.0, axis=1)
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
                df_track_temp = f_tracking.copy()
                df_track_temp['quantidade'] = pd.to_numeric(df_track_temp['quantidade'].astype(str).str.replace(',', '.'), errors='coerce').fillna(0)
                df_track_agg = df_track_temp.groupby('status_pedido', as_index=False)['quantidade'].sum()

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
                df_caf_temp = f_caf.copy()
                df_caf_temp['caf'] = pd.to_numeric(df_caf_temp['caf'].astype(str).str.replace(',', '.'), errors='coerce').fillna(0)
                df_caf_temp['qtd'] = pd.to_numeric(df_caf_temp['qtd'].astype(str).str.replace(',', '.'), errors='coerce').fillna(0)

                df_caf_mes = df_caf_temp.groupby('mes_ano_compra', as_index=False).agg(cafs=('caf', 'sum'), total=('qtd', 'sum'))
                df_caf_mes['taxa_caf'] = df_caf_mes.apply(lambda r: f"{(r['cafs'] / r['total'])*100:.1f}%" if r['total'] > 0 else "0.0%", axis=1)
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
                dias_max = pd.to_numeric(f_status_loja['status_loja'].astype(str).str.replace(',', '.'), errors='coerce').max()
                if pd.isna(dias_max):
                    dias_max = 0
                cor_alerta = "#EF4444" if dias_max > 3 else "#10B981"
                st.markdown(f"""
                    <div class='metric-card' style='border-left: 5px solid {cor_alerta} !important;'>
                        <div class='metric-card-label'>Maior Inatividade Detectada</div>
                        <div class='metric-card-value'>{dias_max:.0f} dia(s)</div>
                    </div>
                """, unsafe_allow_html=True)

        st.write("---")

        # Download do CSV de Vendas
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