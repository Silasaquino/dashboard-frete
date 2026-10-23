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

    # ==========================================
    # CARREGAMENTO CONSOLIDADO MULTI-SHEETS DA BASE (5 SHEETS)
    # ==========================================
    FONTES_BASE_REVERSA = [
        {"id": "1tYkxqGCSan5C7wAjtqKeKpOE2OeGCgrzSynMaXVBaKU", "gid": "0"},          # Principal (BASE)
        {"id": "10zd0gTWei38fpjBZ4xNuIe0gdI8FGbscX3bc6uYgewE", "gid": "0"},          # Parte 1
        {"id": "1FBS9BSal8DBtyVSOhGKBcNIa8EmktSunsuCCC9AuM34", "gid": "0"},          # Parte 2
        {"id": "17f48qNZ1MVvgOwI467OypCrgR-iQl3TqZ7sosLp3s7Y", "gid": "638743010"},  # Parte 3
        {"id": "1AyYe3M3kHCnlZYjD-GSR9oHr_6rGqsL8KMBUnnrvcx4", "gid": "0"}           # Parte 4
    ]

    # PLANILHA ÚNICA PARA O RESUMO REVERSA
    SHEET_ID_RESUMO = "1tYkxqGCSan5C7wAjtqKeKpOE2OeGCgrzSynMaXVBaKU"

    @st.cache_data(ttl=3600)
    def carregar_dados_reversa_consolidados():
        """Lê os 5 links das abas BASE do Google Sheets e junta num único DataFrame."""
        lista_dfs = []
        for fonte in FONTES_BASE_REVERSA:
            url_csv = f"https://docs.google.com/spreadsheets/d/{fonte['id']}/export?format=csv&gid={fonte['gid']}"
            try:
                req = urllib.request.Request(
                    url_csv,
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
                )
                with urllib.request.urlopen(req) as resposta:
                    conteudo_csv = resposta.read().decode("utf-8")
                    
                df_temp = pd.read_csv(io.StringIO(conteudo_csv))
                if not df_temp.empty and len(df_temp.columns) > 1:
                    lista_dfs.append(df_temp)
            except Exception:
                pass

        if lista_dfs:
            return pd.concat(lista_dfs, ignore_index=True)
        else:
            return pd.DataFrame()

    @st.cache_data(ttl=3600)
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

    df_filtrado_reversa = df_raw_reversa.copy()
    df_filtrado_resumo = df_raw_resumo.copy()

    # ==========================================
    # FILTROS NA BARRA LATERAL (SIDEBAR)
    # ==========================================
    st.sidebar.subheader("🎯 Filtros do Dashboard")
    st.sidebar.write("")

    # 1º FILTRO: MODALIDADE DE ENTREGA (COM CAIXAS DE SELEÇÃO / CHECKBOXES PARA FLEGAR)
    st.sidebar.markdown(
        "<span style='font-size: 18px; font-weight: bold;'>🚚 Selecione as Modalidades:</span>",
        unsafe_allow_html=True
    )

    opcoes_modalidade = ["Dafiti Envios", "Milkrun", "Dropshipping", "Fulfillment", "Retail"]

    with st.sidebar.expander("Flegar Modalidades", expanded=True):
        col_todas_1, col_todas_2 = st.columns(2)
        with col_todas_1:
            marcar_todas = st.button("Marcar Todas", use_container_width=True)
        with col_todas_2:
            desmarcar_todas = st.button("Limpar", use_container_width=True)

        if marcar_todas:
            for opt in opcoes_modalidade:
                st.session_state[f"chk_{opt}"] = True
        elif desmarcar_todas:
            for opt in opcoes_modalidade:
                st.session_state[f"chk_{opt}"] = False

        modalidades_selecionadas = []
        for opt in opcoes_modalidade:
            if f"chk_{opt}" not in st.session_state:
                st.session_state[f"chk_{opt}"] = True
                
            if st.checkbox(opt, key=f"chk_{opt}"):
                modalidades_selecionadas.append(opt)

    if modalidades_selecionadas:
        mapeamento_modalidades = {
            "Dafiti Envios": ["dafiti envios", "dafiti_envios"],
            "Milkrun": ["milkrun"],
            "Dropshipping": ["dropshipping"],
            "Fulfillment": ["fulfillment"],
            "Retail": ["retail"]
        }
        
        valores_aceitos = []
        for mod in modalidades_selecionadas:
            valores_aceitos.extend(mapeamento_modalidades.get(mod, [mod.lower()]))

        if 'tipo_processo' in df_filtrado_reversa.columns:
            df_filtrado_reversa = df_filtrado_reversa[
                df_filtrado_reversa['tipo_processo'].astype(str).str.lower().isin(valores_aceitos)
            ]
        if 'delivery_type' in df_filtrado_resumo.columns:
            df_filtrado_resumo = df_filtrado_resumo[
                df_filtrado_resumo['delivery_type'].astype(str).str.lower().isin(valores_aceitos)
            ]
    else:
        df_filtrado_reversa = df_filtrado_reversa.iloc[0:0]
        df_filtrado_resumo = df_filtrado_resumo.iloc[0:0]

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
            ["Escuro 🌙", "Claro ☀️"],
            index=0,
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

        str_modalidades = ", ".join(modalidades_selecionadas) if modalidades_selecionadas else "Nenhuma"
        with col_kpi4:
            st.markdown(
                f"""
                <div class='metric-card'>
                    <div class='metric-card-label'>Modalidade(s) Selecionada(s)</div>
                    <div class='metric-card-value' style='font-size: 15px;'>{str_modalidades}</div>
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

        # 📊 GRÁFICO 1: EVOLUÇÃO MENSAL DA TAXA GERAL DE DEVOLUÇÃO COM META DE 9%
        with col_graf3:
            st.subheader("🎯 Evolução Mensal da Taxa de Devolução")
            
            # Ajuste de suporte para 'taxa_devolucao' (antiga 'taxa_devolucao_seller')
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
                
                cores_pontos = ['#E53E3E' if val > META_TAXA_SELLER else cor_grafico for val in df_evolucao_taxa['taxa_calc']]

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
                    line=dict(color="#ECC94B", width=2, dash="dash")
                )

                fig_linha_taxa.add_annotation(
                    x=df_evolucao_taxa['mes_ano_definido'].iloc[-1],
                    y=META_TAXA_SELLER,
                    text="Meta (9%)",
                    showarrow=False,
                    yshift=12,
                    font=dict(color="#ECC94B", size=12, family="sans-serif")
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
                df_top_aberto = df_top_aberto.sort_values('taxa_aberto', ascending=True)
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

                max_taxa_aberto = df_top_aberto['taxa_aberto'].max() if not df_top_aberto.empty else 0.50

                fig_top_aberto.update_traces(
                    textposition='outside'
                )
                fig_top_aberto.update_layout(
                    template=template_plotly,
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(0,0,0,0)',
                    margin=dict(l=20, r=100, t=30, b=20),
                    height=380,
                    xaxis=dict(tickformat='.1%', title="% Em Aberto", range=[0, max_taxa_aberto * 1.35], showgrid=False),
                    yaxis=dict(showgrid=False),
                    yaxis_title=""
                )
                st.plotly_chart(fig_top_aberto, use_container_width=True)
            else:
                st.info("Coluna 'taxa_devolucao_aberto' não encontrada no resumo.")

        st.write("---")

        # ==========================================
        # ANÁLISE GRÁFICA (BLOCO 2: REMESSAS ÚNICAS, MOTIVOS, SELLER E JORNADA DO TRACKING)
        # ==========================================
        st.markdown(
            "<h3 style='text-align: center;'>📈 Análise Gráfica das Devoluções (Remessas Únicas)</h3>", 
            unsafe_allow_html=True
        )
        st.write("")

        colunas_unicas = [c for c in ['pedido', 'remessa_retorno', 'protocolo'] if c in df_filtrado_reversa.columns]

        # 📊 GRÁFICO 3: VOLUME DE REMESSAS ÚNICAS AGRUPADO POR MÊS/ANO
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
        else:
            st.info("Sem dados suficientes para gerar o gráfico mensal.")

        st.write("")

        col_graf_mot, col_graf_grupo = st.columns(2)

        # 📊 GRÁFICO 4: PRINCIPAIS MOTIVOS DE TROCA
        with col_graf_mot:
            st.subheader("🔍 Principais Motivos de Troca")
            if 'motivo_troca' in df_filtrado_reversa.columns and not df_filtrado_reversa.empty:
                if colunas_unicas:
                    df_unicos_motivo = df_filtrado_reversa.drop_duplicates(subset=colunas_unicas)
                else:
                    df_unicos_motivo = df_filtrado_reversa.copy()

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
                    labels={'quantidade': 'Remessas Únicas', 'motivo': 'Motivo'},
                    template=template_plotly,
                    color_discrete_sequence=[cor_grafico]
                )
                
                max_mot = df_motivos['quantidade'].max() if not df_motivos.empty else 100

                fig_motivos.update_traces(
                    textposition='outside'
                )
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
                st.info("Coluna 'motivo_troca' não encontrada para gerar o gráfico de motivos.")

        # 📊 GRÁFICO 5: SELLERS - DIAS COM PACOTE ENTREGUE SEM FINALIZAR (COM ÊNFASE EM +5 DIAS)
        with col_graf_grupo:
            st.subheader("📦 Sellers - Dias com Pacote Entregue sem Finalizar")
            if 'tracking' in df_filtrado_reversa.columns and 'grupo_aberto_seller' in df_filtrado_reversa.columns and not df_filtrado_reversa.empty:
                df_entregue_seller = df_filtrado_reversa[
                    df_filtrado_reversa['tracking'].astype(str).str.strip().str.upper() == 'ENTREGUE AO SELLER'
                ]

                if not df_entregue_seller.empty:
                    if colunas_unicas:
                        df_unicos_grupo = df_entregue_seller.drop_duplicates(subset=colunas_unicas)
                    else:
                        df_unicos_grupo = df_entregue_seller.copy()

                    df_grupo_seller = df_unicos_grupo['grupo_aberto_seller'].value_counts().reset_index()
                    df_grupo_seller.columns = ['grupo_dias', 'quantidade']
                    total_grupo = df_grupo_seller['quantidade'].sum()

                    df_grupo_seller['rotulo'] = df_grupo_seller['quantidade'].apply(
                        lambda v: f"{v:,} ({(v / total_grupo) * 100:.1f}%)".replace(",", ".")
                    )

                    ordem_grupos = [
                        '0 DIAS CORRIDOS',
                        '1 DIAS CORRIDOS',
                        '2 DIAS CORRIDOS',
                        '3 DIAS CORRIDOS',
                        '4 DIAS CORRIDOS',
                        '5 DIAS CORRIDOS',
                        '+5 DIAS CORRIDOS'
                    ]

                    df_grupo_seller['grupo_dias'] = pd.Categorical(
                        df_grupo_seller['grupo_dias'],
                        categories=ordem_grupos,
                        ordered=True
                    )
                    df_grupo_seller = df_grupo_seller.sort_values('grupo_dias')

                    # Nomes personalizados do eixo X para dar ênfase ao gargalo crítico
                    df_grupo_seller['grupo_exibicao'] = df_grupo_seller['grupo_dias'].astype(str).apply(
                        lambda g: "⚠️ +5 DIAS CORRIDOS" if "5 DIAS" in g and "+" in g else g
                    )

                    fig_grupo_seller = px.bar(
                        df_grupo_seller,
                        x='grupo_exibicao',
                        y='quantidade',
                        text='rotulo',
                        labels={'grupo_exibicao': 'Faixa de Dias no Seller', 'quantidade': 'Remessas Únicas'},
                        template=template_plotly,
                        color='grupo_exibicao',
                        color_discrete_map={
                            '⚠️ +5 DIAS CORRIDOS': '#E53E3E',
                            '0 DIAS CORRIDOS': '#A0AEC0',
                            '1 DIAS CORRIDOS': '#63B3ED',
                            '2 DIAS CORRIDOS': '#4299E1',
                            '3 DIAS CORRIDOS': '#3182CE',
                            '4 DIAS CORRIDOS': '#2B6CB0',
                            '5 DIAS CORRIDOS': '#DD6B20'
                        }
                    )

                    max_grupo = df_grupo_seller['quantidade'].max() if not df_grupo_seller.empty else 100

                    fig_grupo_seller.update_traces(
                        textposition='outside'
                    )
                    fig_grupo_seller.update_layout(
                        paper_bgcolor='rgba(0,0,0,0)',
                        plot_bgcolor='rgba(0,0,0,0)',
                        margin=dict(l=20, r=20, t=30, b=20),
                        height=380,
                        xaxis=dict(showgrid=False),
                        yaxis=dict(range=[0, max_grupo * 1.25], showgrid=False),
                        xaxis_title="",
                        yaxis_title="Remessas Únicas",
                        showlegend=False
                    )
                    st.plotly_chart(fig_grupo_seller, use_container_width=True)
                else:
                    st.info("Não há pacotes com o status 'ENTREGUE AO SELLER' no período e filtros selecionados.")
            else:
                st.info("Coluna 'grupo_aberto_seller' não encontrada na base.")

        st.write("")
        st.write("---")

        # 📊 GRÁFICO 6: JORNADA DO TRACKING (SEM SOBREPOSIÇÃO DE RÓTULOS NA LINHA PONTILHADA)
        st.markdown(
            "<h3 style='text-align: center; margin-top: 10px;'>🚚 Jornada do Tracking (Fluxo Sequencial Reversa)</h3>", 
            unsafe_allow_html=True
        )
        if 'tracking' in df_filtrado_reversa.columns and not df_filtrado_reversa.empty:
            if colunas_unicas:
                df_unicos_tr = df_filtrado_reversa.drop_duplicates(subset=colunas_unicas)
            else:
                df_unicos_tr = df_filtrado_reversa.copy()

            df_tracking = df_unicos_tr['tracking'].value_counts().reset_index()
            df_tracking.columns = ['status_tracking', 'quantidade']
            total_tracking = df_tracking['quantidade'].sum()

            ordem_jornada = [
                'EM ABERTO',
                'POSTADO/TRANSPORTADOR',
                'ENTREGUE AO SELLER',
                'FINALIZADO',
                'REVERSAS EXPIRADAS',
                'EXTRAVIO'
            ]

            df_tracking['status_tracking'] = pd.Categorical(
                df_tracking['status_tracking'],
                categories=ordem_jornada,
                ordered=True
            )
            df_tracking = df_tracking.dropna(subset=['status_tracking']).sort_values('status_tracking')

            mapa_cores_jornada = {
                'EM ABERTO': '#DD6B20',            # Laranja
                'POSTADO/TRANSPORTADOR': '#3182CE', # Azul padrão
                'ENTREGUE AO SELLER': '#38A169',  # Verde
                'FINALIZADO': '#319795',          # Azul/Verde água
                'REVERSAS EXPIRADAS': '#E53E3E',  # Vermelho
                'EXTRAVIO': '#9B2C2C'              # Vermelho escuro
            }

            # Amplitude Y expandida: Alternando estritamente entre Base (0.8) e Topo (3.5)
            x_pts = [1, 2, 3, 4, 5, 6]
            y_pts = [0.8, 3.5, 0.8, 3.5, 0.8, 3.5]

            fig_jornada = go.Figure()

            # Linha pontilhada conectando as etapas
            fig_jornada.add_trace(go.Scatter(
                x=x_pts,
                y=y_pts,
                mode='lines',
                line=dict(color='#A0AEC0', width=3, dash='dash'),
                hoverinfo='skip',
                showlegend=False
            ))

            # Criação dos pontos com textposition perfeitamente isolado
            for idx, row in enumerate(df_tracking.iterrows()):
                status = row[1]['status_tracking']
                qtd = row[1]['quantidade']
                pct = (qtd / total_tracking * 100) if total_tracking > 0 else 0
                cor = mapa_cores_jornada.get(status, '#3182CE')
                qtd_str = f"{qtd:,}".replace(",", ".")

                # Pontos altos colocam o texto ACIMA do nó; Pontos baixos colocam o texto ABAIXO do nó
                if y_pts[idx] == 3.5:
                    pos = "top center"
                    texto_no = f"<b>{status}</b><br><span style='font-size:15px; color:{cor};'><b>{qtd_str}</b> ({pct:.1f}%)</span>"
                else:
                    pos = "bottom center"
                    texto_no = f"<span style='font-size:15px; color:{cor};'><b>{qtd_str}</b> ({pct:.1f}%)</span><br><b>{status}</b>"

                fig_jornada.add_trace(go.Scatter(
                    x=[x_pts[idx]],
                    y=[y_pts[idx]],
                    mode='markers+text',
                    text=[texto_no],
                    textposition=pos,
                    textfont=dict(size=12),
                    marker=dict(size=24, color=cor, line=dict(color='white', width=3)),
                    showlegend=False,
                    hoverinfo='text'
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
        else:
            st.info("Coluna 'tracking' não encontrada na tabela.")

        st.write("---")

        # ÁREA DE DOWNLOAD
        st.markdown(
            f"<h3 style='text-align: center;'>📥 Baixar Relatório ({empresa_usuario})</h3>", 
            unsafe_allow_html=True
        )
        st.markdown(
            f"<p style='text-align: center; color: gray;'>"
            f"Filtro ativo: <b>{tipo_visao_data} ({mes_selecionado})</b> | Modalidade(s): <b>{str_modalidades}</b>"
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