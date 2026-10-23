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
# 1. CONFIGURAÇÃO E AUTENTICAÇÃO VIA GOOGLE SHEETS
# ==========================================

TEMPO_EXPIRED_MINUTOS = 10

if "autenticado" not in st.session_state:
    st.session_state["autenticado"] = False

if "ultima_atividade" not in st.session_state:
    st.session_state["ultima_atividade"] = None

# ID da planilha e URL de exportação para leitura de credenciais
SHEET_ID = "1WuROB09uYwPUeMaG7fS3CroqPFB9cEXtolcgRoA6erY"
URL_CSV_GOOGLE_SHEETS = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid=0"

# URL DO GOOGLE APPS SCRIPT PARA GRAVAÇÃO DE ACESSOS:
URL_WEBAPP_GOOGLE_SCRIPT = "https://script.google.com/macros/s/AKfycbyvMmlYokWB2PpkxkewxpNAdGCKQmQ_S13ybz0qmqaCvgS77_HVhBtk-ftXukSCcYGX/exec"


@st.cache_data(ttl=300)
def carregar_credenciais_google():
    """Lê a folha do Google Sheets com cache leve de 5 minutos."""
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
    """Envia os dados de acesso para o Google Apps Script em segundo plano."""
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


def verificar_login_google():
    """Valida as credenciais inseridas e inicia o registo do acesso."""
    usuario_input = st.session_state.get("campo_usuario", "").strip()
    senha_input = st.session_state.get("campo_senha", "").strip()
    credenciais_validas = carregar_credenciais_google()

    if usuario_input in credenciais_validas and credenciais_validas[usuario_input]['senha'] == senha_input:
        empresa_logada = credenciais_validas[usuario_input]['empresa']

        st.session_state["autenticado"] = True
        st.session_state["usuario_logado"] = usuario_input
        st.session_state["empresa_logada"] = empresa_logada
        st.session_state["ultima_atividade"] = datetime.now()

        registrar_acesso_google_sheets(usuario_input, empresa_logada)

        st.session_state["campo_usuario"] = ""
        st.session_state["campo_senha"] = ""
    else:
        st.error("❌ Utilizador ou palavra-passe incorretos!")


def fazer_logout():
    """Encerra manualmente a sessão do utilizador."""
    st.session_state["autenticado"] = False
    st.session_state["ultima_atividade"] = None


def validar_tempo_sessao():
    """Valida a expiração por inatividade de 10 minutos."""
    if st.session_state["autenticado"] and st.session_state["ultima_atividade"] is not None:
        tempo_decorrido = datetime.now() - st.session_state["ultima_atividade"]

        if tempo_decorrido > timedelta(minutes=TEMPO_EXPIRED_MINUTOS):
            fazer_logout()
            st.warning("⚠️ A sua sessão expirou por inatividade (10 minutos). Por favor, faça login novamente.")
        else:
            st.session_state["ultima_atividade"] = datetime.now()


@st.cache_data
def converter_df_para_csv(df):
    """Converte o DataFrame em CSV instantâneo e ultra leve."""
    return df.to_csv(index=False, sep=';', encoding='utf-8-sig').encode('utf-8-sig')


validar_tempo_sessao()


# ==========================================
# 2. TELA DE LOGIN (Exibida se NÃO estiver autenticado)
# ==========================================
if not st.session_state["autenticado"]:
    st.markdown("<h2 style='text-align: center;'>🔒 Acesso Restrito ao Dashboard</h2>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: gray;'>Insira os seus dados cadastrados na folha de acessos.</p>", unsafe_allow_html=True)
    st.write("---")

    col1, col2, col3 = st.columns([1, 2, 1])

    with col2:
        st.text_input("Utilizador / Login", key="campo_usuario")
        st.text_input("Palavra-passe", type="password", key="campo_senha")
        st.button("Entrar", on_click=verificar_login_google, use_container_width=True)

# ==========================================
# 3. CONTEÚDO DO DASHBOARD (Exibido se ESTIVER autenticado)
# ==========================================
else:
    empresa_usuario = st.session_state.get("empresa_logada", "").strip()

    # --- BARRA LATERAL (SIDEBAR) ---
    st.sidebar.title("Perfil")
    st.sidebar.write(f"👤 **Utilizador:** {st.session_state.get('usuario_logado', '')}")
    st.sidebar.write(f"🏢 **Empresa:** {empresa_usuario}")
    st.sidebar.button("🚪 Sair / Logout", on_click=fazer_logout)
    st.sidebar.write("---")

    # ==========================================
    # CARREGAMENTO CONSOLIDADO MULTI-SHEETS DA BASE (5 SHEETS)
    # ==========================================
    PLANILHAS_BASE_CONFIG = [
        {"id": "1tYkxqGCSan5C7wAjtqKeKpOE2OeGCgrzSynMaXVBaKU", "gid": "0"},          # Parte 1 (Principal)
        {"id": "10zd0gTWei38fpjBZ4xNuIe0gdI8FGbscX3bc6uYgewE", "gid": "0"},          # Parte 2
        {"id": "1FBS9BSal8DBtyVSOhGKBcNIa8EmktSunsuCCC9AuM34", "gid": "0"},          # Parte 3
        {"id": "17f48qNZ1MVvgOwI467OypCrgR-iQl3TqZ7sosLp3s7Y", "gid": "638743010"},  # Parte 4
        {"id": "1AyYe3M3kHCnlZYjD-GSR9oHr_6rGqsL8KMBUnnrvcx4", "gid": "0"}           # Parte 5
    ]

    SHEET_ID_RESUMO = "1tYkxqGCSan5C7wAjtqKeKpOE2OeGCgrzSynMaXVBaKU"

    @st.cache_data(ttl=300)
    def carregar_dados_reversa_consolidados():
        """Lê os 5 links das abas BASE do Google Sheets por export e por gviz (dupla checagem)."""
        lista_dfs = []
        for item in PLANILHAS_BASE_CONFIG:
            sheet_id = item["id"]
            gid = item["gid"]
            df_temp = pd.DataFrame()
            
            # Tentativa 1: Exportação CSV direta
            url_csv = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"
            try:
                df_temp = pd.read_csv(url_csv)
            except Exception:
                # Tentativa 2: Consulta via gviz por nome da aba 'BASE'
                try:
                    url_gviz = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet=BASE"
                    df_temp = pd.read_csv(url_gviz)
                except Exception as e:
                    print(f"⚠️ Erro ao carregar Sheet ID {sheet_id}: {e}")

            if not df_temp.empty and len(df_temp.columns) > 1:
                lista_dfs.append(df_temp)

        if lista_dfs:
            return pd.concat(lista_dfs, ignore_index=True)
        else:
            return pd.DataFrame()

    @st.cache_data(ttl=300)
    def carregar_dados_resumo():
        """Lê a aba RESUMO REVERSA do link único principal."""
        url_csv_resumo = f"https://docs.google.com/spreadsheets/d/{SHEET_ID_RESUMO}/gviz/tq?tqx=out:csv&sheet=RESUMO%20REVERSA"
        try:
            df_resumo = pd.read_csv(url_csv_resumo)
            return df_resumo
        except Exception as e:
            st.error(f"Erro ao carregar dados da folha 'RESUMO REVERSA': {e}")
            return pd.DataFrame()

    with st.spinner("⏳ A carregar e consolidar dados da Operação Reversa..."):
        df_raw_reversa = carregar_dados_reversa_consolidados()
        df_raw_resumo = carregar_dados_resumo()

    # ==========================================
    # ABAS SUPERIORES (SOMENTE OS MÓDULOS REAIS)
    # ==========================================
    aba_reversa, aba_vendas = st.tabs([
        "🔄 Operação Reversa", 
        "💰 Vendas"
    ])

    # ==========================================
    # ABA: OPERAÇÃO REVERSA
    # ==========================================
    with aba_reversa:
        # PAINEL CONTROLE SUPERIOR (MODAL ANALISADO + TEMA)
        col_modal, col_vazia, col_tema = st.columns([2.5, 3, 1.5])

        with col_modal:
            st.markdown("<span style='font-size:12px; font-weight:800; color:#9CA3AF; letter-spacing:1px;'>MODAL ANALISADO</span>", unsafe_allow_html=True)
            opcoes_modalidade = ["GERAL", "Dafiti Envios", "Milkrun", "Dropshipping", "Fulfillment", "Retail"]
            modal_selecionado = st.selectbox(
                "Modal Analisado",
                opcoes_modalidade,
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

        # INJEÇÃO CSS GLOBAL DE ALTO CONSTRASTE (CORRIGE TEXTOS E BOTÕES APAGADOS)
        if tema_selecionado == "Escuro 🌙":
            template_plotly = "plotly_dark"
            cor_grafico = "#60A5FA"
            st.markdown("""
                <style>
                    /* Fundo Global e Cores do App */
                    .stApp { background-color: #0B0F19 !important; color: #FFFFFF !important; }
                    
                    /* Texto das Abas Superiores */
                    .stTabs [data-baseweb="tab"] {
                        font-size: 18px !important;
                        font-weight: 800 !important;
                        color: #94A3B8 !important;
                    }
                    .stTabs [aria-selected="true"] {
                        color: #60A5FA !important;
                        border-bottom-color: #60A5FA !important;
                    }

                    /* Rádios e Labels de Filtros */
                    div[data-testid="stRadio"] label, div[data-testid="stRadio"] p, .stMarkdown p, .stMarkdown b, span {
                        color: #FFFFFF !important;
                        font-weight: 700 !important;
                    }
                    
                    /* Card de Titulo Subtitulo */
                    .subtitulo-destaque {
                        background: linear-gradient(90deg, #1E293B 0%, #0F172A 100%) !important;
                        border-left: 6px solid #60A5FA !important;
                        color: #FFFFFF !important;
                        padding: 12px 20px;
                        border-radius: 6px;
                        font-size: 20px;
                        font-weight: bold;
                        text-align: center !important;
                        margin-bottom: 15px;
                    }

                    /* Metric Cards / KPIs */
                    .metric-card {
                        background-color: #1E293B !important;
                        border: 1px solid #334155 !important;
                        border-radius: 10px;
                        padding: 16px 20px;
                        text-align: center;
                    }
                    .metric-card-label { font-size: 13px; color: #CBD5E1 !important; font-weight: 700; margin-bottom: 6px; }
                    .metric-card-value { font-size: 24px; font-weight: 900; color: #FFFFFF !important; }

                    /* Botão de Download CSV Customizado e Legível */
                    div[data-testid="stDownloadButton"] button {
                        background-color: #EF4444 !important;
                        color: #FFFFFF !important;
                        border: none !important;
                        font-weight: 900 !important;
                        font-size: 16px !important;
                        border-radius: 8px !important;
                        padding: 0.8rem 1.5rem !important;
                        width: 100% !important;
                        box-shadow: 0 4px 10px rgba(0, 0, 0, 0.4) !important;
                    }
                    div[data-testid="stDownloadButton"] button p {
                        color: #FFFFFF !important;
                        font-weight: 900 !important;
                    }
                    div[data-testid="stDownloadButton"] button:hover {
                        background-color: #DC2626 !important;
                        color: #FFFFFF !important;
                    }
                </style>
            """, unsafe_allow_html=True)
        else:
            template_plotly = "plotly_white"
            cor_grafico = "#2563EB"
            st.markdown("""
                <style>
                    .stApp { background-color: #FFFFFF !important; color: #0F172A !important; }
                    .stTabs [data-baseweb="tab"] { font-size: 18px !important; font-weight: 800 !important; color: #64748B !important; }
                    .stTabs [aria-selected="true"] { color: #2563EB !important; border-bottom-color: #2563EB !important; }
                    div[data-testid="stRadio"] label, div[data-testid="stRadio"] p, .stMarkdown p, .stMarkdown b, span { color: #0F172A !important; font-weight: 700 !important; }
                    .subtitulo-destaque {
                        background: linear-gradient(90deg, #F1F5F9 0%, #FFFFFF 100%) !important;
                        border-left: 6px solid #2563EB !important;
                        color: #0F172A !important;
                        padding: 12px 20px;
                        border-radius: 6px;
                        font-size: 20px;
                        font-weight: bold;
                        text-align: center !important;
                        margin-bottom: 15px;
                    }
                    .metric-card {
                        background-color: #F8FAFC !important;
                        border: 1px solid #E2E8F0 !important;
                        border-radius: 10px;
                        padding: 16px 20px;
                        text-align: center;
                    }
                    .metric-card-label { font-size: 13px; color: #475569 !important; font-weight: 700; margin-bottom: 6px; }
                    .metric-card-value { font-size: 24px; font-weight: 900; color: #0F172A !important; }
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

        # APLICAÇÃO DOS FILTROS
        df_filtrado_reversa = df_raw_reversa.copy()
        df_filtrado_resumo = df_raw_resumo.copy()

        if modal_selecionado != "GERAL":
            mapeamento_modalidades = {
                "Dafiti Envios": ["dafiti envios", "dafiti_envios"],
                "Milkrun": ["milkrun"],
                "Dropshipping": ["dropshipping"],
                "Fulfillment": ["fulfillment"],
                "Retail": ["retail"]
            }
            valores_aceitos = mapeamento_modalidades.get(modal_selecionado, [modal_selecionado.lower()])

            if 'tipo_processo' in df_filtrado_reversa.columns:
                df_filtrado_reversa = df_filtrado_reversa[
                    df_filtrado_reversa['tipo_processo'].astype(str).str.lower().isin(valores_aceitos)
                ]
            if 'delivery_type' in df_filtrado_resumo.columns:
                df_filtrado_resumo = df_filtrado_resumo[
                    df_filtrado_resumo['delivery_type'].astype(str).str.lower().isin(valores_aceitos)
                ]

        # FILTRO DE SELLER NA BARRA LATERAL
        if empresa_usuario.upper() == "DAFITI":
            if 'seller_name' in df_filtrado_reversa.columns:
                lista_sellers = ["Todos"] + sorted(list(df_filtrado_reversa['seller_name'].dropna().unique()))
                seller_selecionado = st.sidebar.selectbox("🎯 Selecione o Seller:", lista_sellers)

                if seller_selecionado != "Todos":
                    df_filtrado_reversa = df_filtrado_reversa[df_filtrado_reversa['seller_name'] == seller_selecionado]
                    if 'nome_seller' in df_filtrado_resumo.columns:
                        df_filtrado_resumo = df_filtrado_resumo[df_filtrado_resumo['nome_seller'] == seller_selecionado]
        else:
            st.sidebar.info(f"Filtro fixo ativo para a empresa: **{empresa_usuario}**")
            if 'seller_name' in df_filtrado_reversa.columns:
                df_filtrado_reversa = df_filtrado_reversa[
                    df_filtrado_reversa['seller_name'].astype(str).str.lower() == empresa_usuario.lower()
                ]
            if 'nome_seller' in df_filtrado_resumo.columns:
                df_filtrado_resumo = df_filtrado_resumo[
                    df_filtrado_resumo['nome_seller'].astype(str).str.lower() == empresa_usuario.lower()
                ]

        st.markdown("<div class='subtitulo-destaque'>📋 Visão Geral da Operação Reversa</div>", unsafe_allow_html=True)

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

        # CÁLCULO DE KPIS
        data_hora_formatada = "N/D"
        if 'ultima_atualizacao_tabela' in df_raw_reversa.columns and not df_raw_reversa.empty:
            data_max = pd.to_datetime(df_raw_reversa['ultima_atualizacao_tabela']).max()
            data_hora_formatada = data_max.strftime('%d/%m/%Y às %H:%M:%S')

        colunas_chaves = ['pedido', 'remessa_retorno', 'protocolo']
        colunas_existentes = [c for c in colunas_chaves if c in df_filtrado_reversa.columns]
        qtd_remessas_unicas = len(df_filtrado_reversa.drop_duplicates(subset=colunas_existentes)) if colunas_existentes else len(df_filtrado_reversa)

        col_kpi1, col_kpi2, col_kpi3, col_kpi4 = st.columns(4)

        with col_kpi1:
            st.markdown(f"<div class='metric-card'><div class='metric-card-label'>Total Linhas Agrupadas</div><div class='metric-card-value'>{len(df_filtrado_reversa):,}</div></div>".replace(",", "."), unsafe_allow_html=True)
        with col_kpi2:
            st.markdown(f"<div class='metric-card'><div class='metric-card-label'>Qtd. Remessas Únicas</div><div class='metric-card-value'>{qtd_remessas_unicas:,}</div></div>".replace(",", "."), unsafe_allow_html=True)
        with col_kpi3:
            st.markdown(f"<div class='metric-card'><div class='metric-card-label'>Última Atualização</div><div class='metric-card-value'>{data_hora_formatada}</div></div>", unsafe_allow_html=True)
        with col_kpi4:
            st.markdown(f"<div class='metric-card'><div class='metric-card-label'>Modal Analisado</div><div class='metric-card-value'>{modal_selecionado}</div></div>", unsafe_allow_html=True)

        st.write("")
        st.write("---")

        # ==========================================
        # BLOCO 1: GRÁFICOS DE RESUMO (TAXA DE SELLER E TOP ABERTO)
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
                df_resumo_temp = df_filtrado_resumo.copy()
                df_resumo_temp[col_taxa] = pd.to_numeric(df_resumo_temp[col_taxa], errors='coerce')
                
                if 'qtd_etr' in df_resumo_temp.columns and col_dev in df_resumo_temp.columns:
                    df_evolucao_taxa = df_resumo_temp.groupby('mes_ano_definido').agg(
                        tot_etr=('qtd_etr', 'sum'),
                        tot_dev=(col_dev, 'sum')
                    ).reset_index()
                    df_evolucao_taxa['taxa_calc'] = df_evolucao_taxa['tot_dev'] / df_evolucao_taxa['tot_etr']
                else:
                    df_evolucao_taxa = df_resumo_temp.groupby('mes_ano_definido')[col_taxa].mean().reset_index()
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
                st.info("Sem dados suficientes para exibir a evolução da taxa.")

        # GRÁFICO 2: TOP SELLERS EM ABERTO
        with col_graf4:
            st.subheader("⚠️ Top Sellers - Maior % Devolução em Aberto")
            if 'nome_seller' in df_filtrado_resumo.columns and 'taxa_devolucao_aberto' in df_filtrado_resumo.columns and not df_filtrado_resumo.empty:
                df_aberto_temp = df_filtrado_resumo.copy()
                df_aberto_temp['taxa_devolucao_aberto'] = pd.to_numeric(df_aberto_temp['taxa_devolucao_aberto'], errors='coerce')

                if 'qtd_etr' in df_aberto_temp.columns and 'devolucao_em_aberto' in df_aberto_temp.columns:
                    df_top_aberto = df_aberto_temp.groupby('nome_seller').agg(
                        tot_etr=('qtd_etr', 'sum'),
                        tot_aberto=('devolucao_em_aberto', 'sum')
                    ).reset_index()
                    df_top_aberto['taxa_aberto'] = df_top_aberto['tot_aberto'] / df_top_aberto['tot_etr']
                else:
                    df_top_aberto = df_aberto_temp.groupby('nome_seller')['taxa_devolucao_aberto'].mean().reset_index()
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

        st.write("---")

        # ==========================================
        # BLOCO 2: GRÁFICOS DETALHADOS (REMESSAS, MOTIVOS, ATRASOS E TRACKING)
        # ==========================================
        st.markdown("<h3 style='text-align: center;'>📈 Análise Gráfica das Devoluções (Remessas Únicas)</h3>", unsafe_allow_html=True)
        st.write("")

        # GRÁFICO 3: VOLUME MENSAL DE REMESSAS
        st.subheader("📅 Volume de Remessas Únicas (Mês/Ano)")
        col_mes_grafico = "mes_ano_solicitacao" if tipo_visao_data == "Mês/Ano Solicitação" else "mes_ano_finalizacao"
        
        if col_mes_grafico in df_filtrado_reversa.columns and not df_filtrado_reversa.empty:
            df_temp = df_filtrado_reversa.copy()
            df_temp[col_mes_grafico] = df_temp[col_mes_grafico].astype(str)
            df_temp = df_temp[df_temp[col_mes_grafico].str.strip() != ""]

            if colunas_existentes:
                df_grafico_mes = df_temp.groupby(col_mes_grafico).apply(
                    lambda g: len(g.drop_duplicates(subset=colunas_existentes))
                ).reset_index(name='qtd_remessas_unicas')
            else:
                df_grafico_mes = df_temp.groupby(col_mes_grafico).size().reset_index(name='qtd_remessas_unicas')

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
                df_unicos_motivo = df_filtrado_reversa.drop_duplicates(subset=colunas_existentes) if colunas_existentes else df_filtrado_reversa.copy()
                df_motivos = df_unicos_motivo['motivo_troca'].value_counts().reset_index()
                df_motivos.columns = ['motivo', 'quantidade']
                total_motivos = df_motivos['quantidade'].sum()
                df_motivos = df_motivos.head(10).sort_values('quantidade', ascending=True)

                df_motivos['rotulo'] = df_motivos['quantidade'].apply(
                    lambda v: f"{v:,} ({(v / total_motivos) * 100:.1f}%)".replace(",", ".")
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
                    df_unicos_grupo = df_entregue_seller.drop_duplicates(subset=colunas_existentes) if colunas_existentes else df_entregue_seller.copy()
                    df_grupo_seller = df_unicos_grupo['grupo_aberto_seller'].value_counts().reset_index()
                    df_grupo_seller.columns = ['grupo_dias', 'quantidade']
                    total_grupo = df_grupo_seller['quantidade'].sum()

                    df_grupo_seller['rotulo'] = df_grupo_seller['quantidade'].apply(
                        lambda v: f"{v:,} ({(v / total_grupo) * 100:.1f}%)".replace(",", ".")
                    )

                    ordem_grupos = ['0 DIAS CORRIDOS', '1 DIAS CORRIDOS', '2 DIAS CORRIDOS', '3 DIAS CORRIDOS', '4 DIAS CORRIDOS', '5 DIAS CORRIDOS', '+5 DIAS CORRIDOS']
                    df_grupo_seller['grupo_dias'] = pd.Categorical(df_grupo_seller['grupo_dias'], categories=ordem_grupos, ordered=True)
                    df_grupo_seller = df_grupo_seller.sort_values('grupo_dias')
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

        # GRÁFICO 6: JORNADA DO TRACKING (SINUSOIDAL)
        st.markdown("<h3 style='text-align: center;'>🚚 Jornada do Tracking (Fluxo Sequencial Reversa)</h3>", unsafe_allow_html=True)
        if 'tracking' in df_filtrado_reversa.columns and not df_filtrado_reversa.empty:
            df_unicos_tr = df_filtrado_reversa.drop_duplicates(subset=colunas_existentes) if colunas_existentes else df_filtrado_reversa.copy()
            df_tracking = df_unicos_tr['tracking'].value_counts().reset_index()
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

        # ÁREA DE DOWNLOAD DO CSV (TOTALMENTE LEGÍVEL)
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
    # ABA: VENDAS
    # ==========================================
    with aba_vendas:
        st.markdown("<div class='subtitulo-destaque'>💰 Visão Geral de Vendas</div>", unsafe_allow_html=True)
        st.info("ℹ️ Módulo de Vendas pronto para conexão de dados e relatórios comerciais.")