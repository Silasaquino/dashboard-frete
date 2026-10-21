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


@st.cache_data(ttl=600)
def carregar_credenciais_google():
    """Lê a folha do Google Sheets com cache de 10 minutos."""
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

        # Regista o acesso na planilha
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
    st.sidebar.title("Navegação")
    st.sidebar.write(f"👤 **Utilizador:** {st.session_state.get('usuario_logado', '')}")
    st.sidebar.write(f"🏢 **Empresa:** {empresa_usuario}")
    st.sidebar.button("🚪 Sair / Logout", on_click=fazer_logout)
    st.sidebar.write("---")

    # ------------------------------------------
    # NAVEGAÇÃO DE MÓDULOS NA BARRA LATERAL
    # ------------------------------------------
    st.sidebar.markdown(
        "<span style='font-size: 18px; font-weight: bold;'>📂 Módulo do Dashboard:</span>",
        unsafe_allow_html=True
    )
    
    opcao_modulo = st.sidebar.radio(
        "Módulo do Dashboard",
        ["🔄 Operação Reversa", "💰 Vendas"],
        label_visibility="collapsed"
    )
    
    st.sidebar.write("---")

    # --- CARREGAMENTO DE DADOS VIA GOOGLE SHEETS ---
    SHEET_ID_REVERSA = "1tYkxqGCSan5C7wAjtqKeKpOE2OeGCgrzSynMaXVBaKU"

    @st.cache_data(ttl=3600)
    def carregar_dados_reversa():
        url_csv_base = f"https://docs.google.com/spreadsheets/d/{SHEET_ID_REVERSA}/gviz/tq?tqx=out:csv&sheet=BASE"
        try:
            df_resultado = pd.read_csv(url_csv_base)
            return df_resultado
        except Exception as e:
            st.error(f"Erro ao carregar dados da folha 'BASE': {e}")
            return pd.DataFrame()

    @st.cache_data(ttl=3600)
    def carregar_dados_resumo():
        url_csv_resumo = f"https://docs.google.com/spreadsheets/d/{SHEET_ID_REVERSA}/gviz/tq?tqx=out:csv&sheet=RESUMO%20REVERSA"
        try:
            df_resumo = pd.read_csv(url_csv_resumo)
            return df_resumo
        except Exception as e:
            st.error(f"Erro ao carregar dados da folha 'RESUMO REVERSA': {e}")
            return pd.DataFrame()

    with st.spinner("⏳ A carregar dados da Operação Reversa..."):
        df_raw_reversa = carregar_dados_reversa()
        df_raw_resumo = carregar_dados_resumo()

    df_filtrado_reversa = df_raw_reversa.copy()
    df_filtrado_resumo = df_raw_resumo.copy()

    # ==========================================
    # FILTROS NA BARRA LATERAL (SIDEBAR)
    # ==========================================
    st.sidebar.subheader("🎯 Filtros do Dashboard")
    st.sidebar.write("")

    # 1º FILTRO: MODALIDADE DE ENTREGA
    st.sidebar.markdown(
        "<span style='font-size: 18px; font-weight: bold;'>🚚 Selecione a Modalidade:</span>",
        unsafe_allow_html=True
    )

    opcoes_modalidade = ["Todos", "Dafiti Envios", "Milkrun", "Dropshipping"]

    modalidade_selecionada = st.sidebar.selectbox(
        "Modalidade de Entrega",
        opcoes_modalidade,
        label_visibility="collapsed"
    )

    if modalidade_selecionada != "Todos":
        mapeamento_modalidades = {
            "Dafiti Envios": ["dafiti envios", "dafiti_envios"],
            "Milkrun": ["milkrun"],
            "Dropshipping": ["dropshipping"]
        }
        valores_aceitos = mapeamento_modalidades.get(modalidade_selecionada, [modalidade_selecionada.lower()])
        
        if 'tipo_processo' in df_filtrado_reversa.columns:
            df_filtrado_reversa = df_filtrado_reversa[
                df_filtrado_reversa['tipo_processo'].astype(str).str.lower().isin(valores_aceitos)
            ]
        if 'delivery_type' in df_filtrado_resumo.columns:
            df_filtrado_resumo = df_filtrado_resumo[
                df_filtrado_resumo['delivery_type'].astype(str).str.lower().isin(valores_aceitos)
            ]

    st.sidebar.write("")

    # 2º FILTRO: SELEÇÃO DE SELLER
    if empresa_usuario.upper() == "DAFITI":
        st.sidebar.markdown(
            "<span style='font-size: 18px; font-weight: bold;'>🎯 Selecione o Seller:</span>",
            unsafe_allow_html=True
        )

        if 'seller_name' in df_filtrado_reversa.columns:
            lista_sellers = ["Todos"] + sorted(list(df_filtrado_reversa['seller_name'].dropna().unique()))
            seller_selecionado = st.sidebar.selectbox(
                "Seleção de Seller",
                lista_sellers,
                label_visibility="collapsed"
            )

            if seller_selecionado != "Todos":
                df_filtrado_reversa = df_filtrado_reversa[df_filtrado_reversa['seller_name'] == seller_selecionado]
                if 'nome_seller' in df_filtrado_resumo.columns:
                    df_filtrado_resumo = df_filtrado_resumo[df_filtrado_resumo['nome_seller'] == seller_selecionado]
        else:
            st.sidebar.warning("Coluna 'seller_name' não encontrada na tabela.")
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

    # ==========================================
    # TELA PRINCIPAL (CABEÇALHO + SELETOR DE TEMA NO TOPO)
    # ==========================================
    col_header_titulo, col_header_tema = st.columns([4, 1])

    with col_header_titulo:
        st.markdown("<h1 style='margin-bottom: 0px;'>📊 Dashboard Sellers</h1>", unsafe_allow_html=True)
        st.markdown(
            f"<p style='font-size: 16px; color: #718096; margin-top: 4px;'>"
            f"Visão de dados ajustada para a empresa: <b>{empresa_usuario}</b></p>", 
            unsafe_allow_html=True
        )

    with col_header_tema:
        st.markdown("<span style='font-size: 14px; font-weight: bold;'>🎨 Tema:</span>", unsafe_allow_html=True)
        tema_selecionado = st.selectbox(
            "Tema do Dashboard",
            ["Claro ☀️", "Escuro 🌙"],
            label_visibility="collapsed"
        )

    # INJEÇÃO DINÂMICA DE CSS COM BASE NO TEMA SELECIONADO NA ÁREA PRINCIPAL
    if tema_selecionado == "Escuro 🌙":
        template_plotly = "plotly_dark"
        cor_grafico = "#63B3ED"
        st.markdown("""
            <style>
                /* Cores para o Modo Escuro */
                .stApp {
                    background-color: #1A202C !important;
                    color: #E2E8F0 !important;
                }
                .subtitulo-destaque {
                    background: linear-gradient(90deg, #2D3748 0%, #1A202C 100%) !important;
                    border-left: 6px solid #63B3ED !important;
                    color: #F7FAFC !important;
                    padding: 12px 20px;
                    border-radius: 6px;
                    font-size: 22px;
                    font-weight: bold;
                    text-align: center !important;
                    margin-bottom: 15px;
                }
                .metric-card {
                    background-color: #2D3748 !important;
                    border: 1px solid #4A5568 !important;
                    border-radius: 10px;
                    padding: 16px 20px;
                    text-align: center;
                    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
                }
                .metric-card-label {
                    font-size: 14px;
                    color: #A0AEC0 !important;
                    font-weight: 600;
                    margin-bottom: 8px;
                }
                .metric-card-value {
                    font-size: 24px;
                    font-weight: bold;
                    color: #FFFFFF !important;
                }
                div[data-testid="stRadio"] label, div[data-testid="stRadio"] label p {
                    color: #FFFFFF !important;
                    font-weight: 600 !important;
                }
                div[data-testid="stDownloadButton"] button {
                    background-color: #E53E3E !important;
                    color: #FFFFFF !important;
                    border: none !important;
                    font-weight: bold !important;
                    font-size: 16px !important;
                    border-radius: 8px !important;
                    padding: 0.75rem 1.25rem !important;
                    width: 100% !important;
                    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3) !important;
                }
                div[data-testid="stDownloadButton"] button:hover {
                    background-color: #C53030 !important;
                    color: #FFFFFF !important;
                }
            </style>
        """, unsafe_allow_html=True)
    else:
        template_plotly = "plotly_white"
        cor_grafico = "#2B6CB0"
        st.markdown("""
            <style>
                /* Cores para o Modo Claro */
                .stApp {
                    background-color: #FFFFFF !important;
                    color: #1A202C !important;
                }
                .subtitulo-destaque {
                    background: linear-gradient(90deg, #f0f4f9 0%, #ffffff 100%) !important;
                    border-left: 6px solid #2B6CB0 !important;
                    color: #2D3748 !important;
                    padding: 12px 20px;
                    border-radius: 6px;
                    font-size: 22px;
                    font-weight: bold;
                    text-align: center !important;
                    margin-bottom: 15px;
                }
                .metric-card {
                    background-color: #f8fafc !important;
                    border: 1px solid #e2e8f0 !important;
                    border-radius: 10px;
                    padding: 16px 20px;
                    text-align: center;
                    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.04);
                }
                .metric-card-label {
                    font-size: 14px;
                    color: #718096 !important;
                    font-weight: 600;
                    margin-bottom: 8px;
                }
                .metric-card-value {
                    font-size: 24px;
                    font-weight: bold;
                    color: #1A202C !important;
                }
                div[data-testid="stRadio"] label, div[data-testid="stRadio"] label p {
                    color: #2D3748 !important;
                    font-weight: 600 !important;
                }
                div[data-testid="stDownloadButton"] button {
                    background-color: #3182CE !important;
                    color: #FFFFFF !important;
                    border: none !important;
                    font-weight: bold !important;
                    font-size: 16px !important;
                    border-radius: 8px !important;
                    padding: 0.75rem 1.25rem !important;
                    width: 100% !important;
                    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1) !important;
                }
                div[data-testid="stDownloadButton"] button:hover {
                    background-color: #2B6CB0 !important;
                    color: #FFFFFF !important;
                }
            </style>
        """, unsafe_allow_html=True)

    st.write("---")

    # ==========================================
    # CONTEÚDO CONDICIONAL CONFORME O MÓDULO SELECIONADO NA BARRA LATERAL
    # ==========================================
    if opcao_modulo == "🔄 Operação Reversa":
        # TÍTULO CENTRALIZADO DO CARTÃO
        st.markdown(
            "<div class='subtitulo-destaque'>📋 Visão Geral da Operação Reversa</div>", 
            unsafe_allow_html=True
        )

        # FILTRO DE VISÃO TEMPORAL REPOSICIONADO PARA O CORPO PRINCIPAL
        col_filtro_tipo, col_filtro_mes = st.columns([1, 1])

        with col_filtro_tipo:
            st.markdown("<b>📅 Escolha o Tipo de Visão:</b>", unsafe_allow_html=True)
            tipo_visao_data = st.radio(
                "Tipo de Visão de Data",
                ["Mês/Ano Solicitação", "Mês/Ano Finalização"],
                horizontal=True,
                label_visibility="collapsed",
                key="radio_tipo_visao_principal"
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
                label_visibility="collapsed",
                key="select_mes_ano_principal"
            )

        # Aplica a filtragem por mês/ano no DataFrame da Operação Reversa
        if mes_selecionado != "Todos" and coluna_data_alvo in df_filtrado_reversa.columns:
            df_filtrado_reversa = df_filtrado_reversa[
                df_filtrado_reversa[coluna_data_alvo].astype(str) == mes_selecionado
            ]

        st.write("")

        # CÁLCULO DA ÚLTIMA ATUALIZAÇÃO
        data_hora_formatada = "N/D"
        if 'ultima_atualizacao_tabela' in df_raw_reversa.columns and not df_raw_reversa.empty:
            data_max = pd.to_datetime(df_raw_reversa['ultima_atualizacao_tabela']).max()
            data_hora_formatada = data_max.strftime('%d/%m/%Y às %H:%M:%S')

        # CÁLCULO DA QUANTIDADE ÚNICA BASEADA EM PEDIDO, REMESSA_RETORNO E PROTOCOLO
        colunas_chaves = ['pedido', 'remessa_retorno', 'protocolo']
        colunas_existentes = [c for c in colunas_chaves if c in df_filtrado_reversa.columns]
        
        if colunas_existentes:
            qtd_remessas_unicas = len(df_filtrado_reversa.drop_duplicates(subset=colunas_existentes))
        else:
            qtd_remessas_unicas = len(df_filtrado_reversa)

        # CARTÕES DE INDICADORES (KPIs) - 4 COLUNAS
        col_kpi1, col_kpi2, col_kpi3, col_kpi4 = st.columns(4)

        with col_kpi1:
            st.markdown(
                f"""
                <div class='metric-card'>
                    <div class='metric-card-label'>Total Linhas Agrupadas</div>
                    <div class='metric-card-value'>{len(df_filtrado_reversa):,}</div>
                </div>
                """.replace(",", "."), 
                unsafe_allow_html=True
            )

        with col_kpi2:
            st.markdown(
                f"""
                <div class='metric-card'>
                    <div class='metric-card-label'>Qtd. Remessas Únicas</div>
                    <div class='metric-card-value'>{qtd_remessas_unicas:,}</div>
                </div>
                """.replace(",", "."), 
                unsafe_allow_html=True
            )

        with col_kpi3:
            st.markdown(
                f"""
                <div class='metric-card'>
                    <div class='metric-card-label'>Última Atualização</div>
                    <div class='metric-card-value'>{data_hora_formatada}</div>
                </div>
                """, 
                unsafe_allow_html=True
            )

        with col_kpi4:
            st.markdown(
                f"""
                <div class='metric-card'>
                    <div class='metric-card-label'>Modalidade Selecionada</div>
                    <div class='metric-card-value'>{modalidade_selecionada}</div>
                </div>
                """, 
                unsafe_allow_html=True
            )

        st.write("")
        st.write("---")

        # ==========================================
        # ANÁLISE GRÁFICA (BLOCO 1: RESUMO REVERSA - TAXA DE SELLER E EM ABERTO)
        # ==========================================
        st.markdown(
            "<h3 style='text-align: center;'>📊 Indicadores de Devolução por Seller e Meta</h3>", 
            unsafe_allow_html=True
        )
        st.write("")

        col_graf3, col_graf4 = st.columns(2)

        META_TAXA_SELLER = 0.09  # Meta de 9%

        # 📊 GRÁFICO 1: EVOLUÇÃO MENSAL DA TAXA GERAL DE DEVOLUÇÃO (SELLER) COM META DE 9%
        with col_graf3:
            st.subheader("🎯 Evolução Mensal da Taxa de Devolução (Seller)")
            if 'mes_ano_definido' in df_filtrado_resumo.columns and 'taxa_devolucao_seller' in df_filtrado_resumo.columns and not df_filtrado_resumo.empty:
                df_resumo_temp = df_filtrado_resumo.copy()
                df_resumo_temp['taxa_devolucao_seller'] = pd.to_numeric(df_resumo_temp['taxa_devolucao_seller'], errors='coerce')
                
                # Agrupa por Mês/Ano calculando a média ponderada/soma das taxas
                if 'qtd_etr' in df_resumo_temp.columns and 'devolvido_seller' in df_resumo_temp.columns:
                    df_evolucao_taxa = df_resumo_temp.groupby('mes_ano_definido').agg(
                        tot_etr=('qtd_etr', 'sum'),
                        tot_dev_seller=('devolvido_seller', 'sum')
                    ).reset_index()
                    df_evolucao_taxa['taxa_calc'] = df_evolucao_taxa['tot_dev_seller'] / df_evolucao_taxa['tot_etr']
                else:
                    df_evolucao_taxa = df_resumo_temp.groupby('mes_ano_definido')['taxa_devolucao_seller'].mean().reset_index()
                    df_evolucao_taxa.rename(columns={'taxa_devolucao_seller': 'taxa_calc'}, inplace=True)

                df_evolucao_taxa = df_evolucao_taxa.sort_values('mes_ano_definido')
                df_evolucao_taxa['taxa_pct_str'] = df_evolucao_taxa['taxa_calc'].apply(lambda v: f"{v*100:.1f}%" if pd.notnull(v) else "0.0%")
                
                # Define as cores dos marcadores: Vermelho se > 9%, azul/tema se <= 9%
                cores_pontos = ['#E53E3E' if val > META_TAXA_SELLER else cor_grafico for val in df_evolucao_taxa['taxa_calc']]

                fig_linha_taxa = go.Figure()

                # Adiciona a Linha da Taxa
                fig_linha_taxa.add_trace(go.Scatter(
                    x=df_evolucao_taxa['mes_ano_definido'],
                    y=df_evolucao_taxa['taxa_calc'],
                    mode='lines+markers+text',
                    text=df_evolucao_taxa['taxa_pct_str'],
                    textposition='top center',
                    line=dict(color=cor_grafico, width=3),
                    marker=dict(size=10, color=cores_pontos),
                    name='Taxa Devolução Seller'
                ))

                # Adiciona a Linha Tracejada de Meta (9%)
                fig_linha_taxa.add_shape(
                    type="line",
                    x0=df_evolucao_taxa['mes_ano_definido'].iloc[0],
                    y0=META_TAXA_SELLER,
                    x1=df_evolucao_taxa['mes_ano_definido'].iloc[-1],
                    y1=META_TAXA_SELLER,
                    line=dict(color="#ECC94B", width=2, dash="dash")
                )

                # Rótulo explicativo da Meta
                fig_linha_taxa.add_annotation(
                    x=df_evolucao_taxa['mes_ano_definido'].iloc[-1],
                    y=META_TAXA_SELLER,
                    text="Meta (9%)",
                    showarrow=False,
                    yshift=12,
                    font=dict(color="#ECC94B", size=12, family="sans-serif")
                )

                fig_linha_taxa.update_layout(
                    template=template_plotly,
                    margin=dict(l=20, r=20, t=30, b=20),
                    height=380,
                    yaxis=dict(tickformat='.1%', title="Taxa (%)"),
                    xaxis_title="",
                    showlegend=False
                )
                st.plotly_chart(fig_linha_taxa, use_container_width=True)
            else:
                st.info("Sem dados suficientes para exibir a evolução da taxa do seller.")

        # 📊 GRÁFICO 2: TOP SELLERS COM MAIOR % DE DEVOLUÇÃO EM ABERTO
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

                df_top_aberto = df_top_aberto.sort_values('taxa_aberto', ascending=False).head(10)
                df_top_aberto = df_top_aberto.sort_values('taxa_aberto', ascending=True)  # Ordena para exibição horizontal
                df_top_aberto['taxa_str'] = df_top_aberto['taxa_aberto'].apply(lambda v: f"{v*100:.1f}%" if pd.notnull(v) else "0.0%")

                fig_top_aberto = px.bar(
                    df_top_aberto,
                    x='taxa_aberto',
                    y='nome_seller',
                    text='taxa_str',
                    orientation='h',
                    labels={'taxa_aberto': '% Em Aberto', 'nome_seller': 'Seller'},
                    template=template_plotly,
                    color_discrete_sequence=['#E53E3E']
                )
                fig_top_aberto.update_traces(
                    textposition='outside'
                )
                fig_top_aberto.update_layout(
                    margin=dict(l=20, r=20, t=30, b=20),
                    height=380,
                    xaxis=dict(tickformat='.1%', title="% Em Aberto"),
                    yaxis_title=""
                )
                st.plotly_chart(fig_top_aberto, use_container_width=True)
            else:
                st.info("Coluna 'taxa_devolucao_aberto' não encontrada no resumo.")

        st.write("---")

        # ==========================================
        # ANÁLISE GRÁFICA (BLOCO 2: BASE DE REMESSAS ÚNICAS E MOTIVOS)
        # ==========================================
        st.markdown(
            "<h3 style='text-align: center;'>📈 Análise Gráfica das Devoluções (Remessas Únicas)</h3>", 
            unsafe_allow_html=True
        )
        st.write("")

        col_graf1, col_graf2 = st.columns(2)
        colunas_unicas = [c for c in ['pedido', 'remessa_retorno', 'protocolo'] if c in df_filtrado_reversa.columns]

        # 📊 GRÁFICO 3: VOLUME DE REMESSAS ÚNICAS AGRUPADO POR MÊS/ANO
        with col_graf1:
            st.subheader("📅 Volume de Remessas Únicas (Mês/Ano)")
            col_mes_grafico = "mes_ano_solicitacao" if tipo_visao_data == "Mês/Ano Solicitação" else "mes_ano_finalizacao"
            
            if col_mes_grafico in df_filtrado_reversa.columns and not df_filtrado_reversa.empty:
                df_temp = df_filtrado_reversa.copy()
                df_temp[col_mes_grafico] = df_temp[col_mes_grafico].astype(str)
                df_temp = df_temp[df_temp[col_mes_grafico].str.strip() != ""]

                if colunas_unicas:
                    df_grafico_mes = df_temp.groupby(col_mes_grafico).apply(
                        lambda g: len(g.drop_duplicates(subset=colunas_unicas))
                    ).reset_index(name='qtd_remessas_unicas')
                else:
                    df_grafico_mes = df_temp.groupby(col_mes_grafico).size().reset_index(name='qtd_remessas_unicas')

                df_grafico_mes = df_grafico_mes.sort_values(col_mes_grafico)

                fig_tempo = px.bar(
                    df_grafico_mes,
                    x=col_mes_grafico,
                    y='qtd_remessas_unicas',
                    text='qtd_remessas_unicas',
                    labels={col_mes_grafico: 'Mês/Ano', 'qtd_remessas_unicas': 'Remessas Únicas'},
                    template=template_plotly,
                    color_discrete_sequence=[cor_grafico]
                )
                fig_tempo.update_traces(
                    texttemplate='%{text:,}',
                    textposition='outside'
                )
                fig_tempo.update_layout(
                    margin=dict(l=20, r=20, t=30, b=20),
                    height=380,
                    xaxis_title="",
                    yaxis_title="Remessas Únicas"
                )
                st.plotly_chart(fig_tempo, use_container_width=True)
            else:
                st.info("Sem dados suficientes para gerar o gráfico mensal.")

        # 📊 GRÁFICO 4: PRINCIPAIS MOTIVOS DE TROCA (BASEADO EM REMESSAS ÚNICAS)
        with col_graf2:
            st.subheader("🔍 Principais Motivos de Troca")
            if 'motivo_troca' in df_filtrado_reversa.columns and not df_filtrado_reversa.empty:
                if colunas_unicas:
                    df_unicos_motivo = df_filtrado_reversa.drop_duplicates(subset=colunas_unicas)
                else:
                    df_unicos_motivo = df_filtrado_reversa.copy()

                df_motivos = df_unicos_motivo['motivo_troca'].value_counts().reset_index()
                df_motivos.columns = ['motivo', 'quantidade']
                df_motivos = df_motivos.head(10).sort_values('quantidade', ascending=True)

                fig_motivos = px.bar(
                    df_motivos,
                    x='quantidade',
                    y='motivo',
                    text='quantidade',
                    orientation='h',
                    labels={'quantidade': 'Remessas Únicas', 'motivo': 'Motivo'},
                    template=template_plotly,
                    color_discrete_sequence=[cor_grafico]
                )
                fig_motivos.update_traces(
                    texttemplate='%{text:,}',
                    textposition='outside'
                )
                fig_motivos.update_layout(
                    margin=dict(l=20, r=20, t=30, b=20),
                    height=380,
                    xaxis_title="Remessas Únicas",
                    yaxis_title=""
                )
                st.plotly_chart(fig_motivos, use_container_width=True)
            else:
                st.info("Coluna 'motivo_troca' não encontrada para gerar o gráfico de motivos.")

        st.write("---")

        # ÁREA DE DOWNLOAD
        st.markdown(
            f"<h3 style='text-align: center;'>📥 Baixar Relatório ({empresa_usuario})</h3>", 
            unsafe_allow_html=True
        )
        st.markdown(
            f"<p style='text-align: center; color: gray;'>"
            f"Filtro ativo: <b>{tipo_visao_data} ({mes_selecionado})</b> | Modalidade: <b>{modalidade_selecionada}</b>"
            "</p>", 
            unsafe_allow_html=True
        )

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

    elif opcao_modulo == "💰 Vendas":
        st.markdown(
            "<div class='subtitulo-destaque'>💰 Visão Geral de Vendas</div>", 
            unsafe_allow_html=True
        )

        col_vendas1, col_vendas2, col_vendas3 = st.columns(3)

        with col_vendas1:
            st.markdown(
                """
                <div class='metric-card'>
                    <div class='metric-card-label'>Total de Pedidos de Venda</div>
                    <div class='metric-card-value'>0</div>
                </div>
                """, 
                unsafe_allow_html=True
            )

        with col_vendas2:
            st.markdown(
                """
                <div class='metric-card'>
                    <div class='metric-card-label'>Faturamento Total</div>
                    <div class='metric-card-value'>R$ 0,00</div>
                </div>
                """, 
                unsafe_allow_html=True
            )

        with col_vendas3:
            st.markdown(
                """
                <div class='metric-card'>
                    <div class='metric-card-label'>Ticket Médio</div>
                    <div class='metric-card-value'>R$ 0,00</div>
                </div>
                """, 
                unsafe_allow_html=True
            )

        st.write("")
        st.write("---")
        st.info("ℹ️ A área de Vendas está configurada e pronta para receber a nova consulta SQL e indicadores.")