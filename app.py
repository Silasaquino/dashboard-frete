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
# 1. CONFIGURAÇÃO E AUTENTICAÇÃO PERSISTENTE (F5 RESISTENTE)
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
# 3. CONTEÚDO DO DASHBOARD (REVERSA COMPLETO)
# ==========================================
else:
    empresa_usuario = st.session_state.get("empresa_logada", "").strip()

    st.sidebar.title("Perfil")
    st.sidebar.write(f"👤 **Utilizador:** {st.session_state.get('usuario_logado', '')}")
    st.sidebar.write(f"🏢 **Empresa:** {empresa_usuario}")
    st.sidebar.button("🚪 Sair / Logout", on_click=fazer_logout, key="btn_logout")

    PLANILHAS_REVERSA_BASE = [
        {"id": "1tYkxqGCSan5C7wAjtqKeKpOE2OeGCgrzSynMaXVBaKU", "gid": "0"},
        {"id": "10zd0gTWei38fpjBZ4xNuIe0gdI8FGbscX3bc6uYgewE", "gid": "0"},
        {"id": "1FBS9BSal8DBtyVSOhGKBcNIa8EmktSunsuCCC9AuM34", "gid": "0"},
        {"id": "17f48qNZ1MVvgOwI467OypCrgR-iQl3TqZ7sosLp3s7Y", "gid": "638743010"},
        {"id": "1AyYe3M3kHCnlZYjD-GSR9oHr_6rGqsL8KMBUnnrvcx4", "gid": "0"}
    ]
    SHEET_ID_RESUMO_REVERSA = "1tYkxqGCSan5C7wAjtqKeKpOE2OeGCgrzSynMaXVBaKU"

    @st.cache_data(ttl=1800, show_spinner=False)
    def carregar_dados_reversa():
        lista_dfs = []
        colunas_desejadas = [
            'data_solicitacao', 'mes_ano_solicitacao', 'tipo_solicitacao', 'seller_name',
            'tipo_processo', 'ultima_atualizacao_tabela', 'pedido', 'remessa_retorno',
            'motivo_troca', 'protocolo', 'mes_ano_finalizacao', 'tracking', 'grupo_aberto_seller'
        ]
        for item in PLANILHAS_REVERSA_BASE:
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
    def extrair_sellers(df_base, col_seller='seller_name'):
        if col_seller in df_base.columns:
            s_validos = sorted([str(s) for s in df_base[col_seller].unique() if s and str(s).lower() not in ['n/a', 'nan', 'none']])
            return ["Todos"] + s_validos
        return ["Todos"]

    with st.spinner("⚡ A carregar base operacional na memória..."):
        df_raw_reversa = carregar_dados_reversa()
        df_raw_resumo_reversa = carregar_resumo_reversa()

    # Controles Superiores: Modal, Seller e Tema
    col_modal, col_seller, col_tema = st.columns([2, 2.5, 1.5])

    with col_seller:
        st.markdown("<span style='font-size:12px; font-weight:800; color:#9CA3AF; letter-spacing:1px;'>🎯 SELEÇÃO DE SELLER</span>", unsafe_allow_html=True)
        if empresa_usuario.upper() == "DAFITI":
            lista_sellers_rev = extrair_sellers(df_raw_reversa, 'seller_name')
            seller_selecionado = st.selectbox("Selecione o Seller (Reversa)", lista_sellers_rev, index=0, label_visibility="collapsed")
        else:
            st.markdown(f"<div style='background-color:#1E293B; padding:8px 12px; border-radius:6px; font-weight:700; color:#60A5FA; font-size:14px;'>🏢 {empresa_usuario}</div>", unsafe_allow_html=True)
            seller_selecionado = empresa_usuario

    df_seller_temp = df_raw_reversa
    if seller_selecionado != "Todos":
        df_seller_temp = df_raw_reversa[df_raw_reversa['seller_name'].str.strip().str.upper() == str(seller_selecionado).strip().upper()]

    modais_existentes = ["GERAL"]
    if 'tipo_processo' in df_seller_temp.columns and not df_seller_temp.empty:
        modais_unicos = df_seller_temp['tipo_processo'].dropna().astype(str).str.strip().unique()
        mapa_modais_limpos = {"dafiti envios": "Dafiti Envios", "milkrun": "Milkrun", "dropshipping": "Dropshipping", "fulfillment": "Fulfillment", "retail": "Retail"}
        for m in modais_unicos:
            m_limpo = mapa_modais_limpos.get(m.lower(), m.title())
            if m_limpo not in modais_existentes:
                modais_existentes.append(m_limpo)

    with col_modal:
        st.markdown("<span style='font-size:12px; font-weight:800; color:#9CA3AF; letter-spacing:1px;'>MODAL ANALISADO</span>", unsafe_allow_html=True)
        modal_selecionado = st.selectbox("Modal Analisado (Reversa)", modais_existentes, index=0, label_visibility="collapsed")

    with col_tema:
        st.markdown("<span style='font-size:12px; font-weight:800; color:#9CA3AF; letter-spacing:1px;'>TEMA DA TELA</span>", unsafe_allow_html=True)
        tema_selecionado = st.selectbox("Tema do Dashboard", ["Escuro 🌙", "Claro ☀️"], index=0, label_visibility="collapsed")

    # Configuração visual de tema
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
                    border-radius: 10px; padding: 18px 20px; text-align: center;
                }
                .metric-card-label { font-size: 13px; color: #CBD5E1 !important; font-weight: 700; margin-bottom: 6px; }
                .metric-card-value { font-size: 26px; font-weight: 900; color: #FFFFFF !important; }
                div[data-testid="stDownloadButton"] button {
                    background-color: #EF4444 !important; color: #FFFFFF !important; border: none !important;
                    font-weight: 900 !important; font-size: 16px !important; border-radius: 8px !important; padding: 0.8rem 1.5rem !important; width: 100% !important;
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
                    border-radius: 10px; padding: 18px 20px; text-align: center;
                }
                .metric-card-label { font-size: 13px; color: #475569 !important; font-weight: 700; margin-bottom: 6px; }
                .metric-card-value { font-size: 26px; font-weight: 900; color: #0F172A !important; }
                div[data-testid="stDownloadButton"] button {
                    background-color: #2563EB !important; color: #FFFFFF !important;
                    font-weight: 900 !important; font-size: 16px !important; border-radius: 8px !important; padding: 0.8rem 1.5rem !important; width: 100% !important;
                }
            </style>
        """, unsafe_allow_html=True)

    mask_reversa = pd.Series(True, index=df_raw_reversa.index)
    mask_resumo_rev = pd.Series(True, index=df_raw_resumo_reversa.index)

    target_seller_rev = seller_selecionado if empresa_usuario.upper() == "DAFITI" else empresa_usuario
    if target_seller_rev != "Todos":
        t_str = str(target_seller_rev).strip().upper()
        if 'seller_name' in df_raw_reversa.columns:
            mask_reversa &= (df_raw_reversa['seller_name'].astype(str).str.strip().str.upper() == t_str)
        if 'nome_seller' in df_raw_resumo_reversa.columns:
            mask_resumo_rev &= (df_raw_resumo_reversa['nome_seller'].astype(str).str.strip().str.upper() == t_str)

    if modal_selecionado != "GERAL":
        map_m = {"Dafiti Envios": ["dafiti envios", "dafiti_envios"], "Milkrun": ["milkrun"], "Dropshipping": ["dropshipping"], "Fulfillment": ["fulfillment"], "Retail": ["retail"]}
        vals = map_m.get(modal_selecionado, [modal_selecionado.lower()])
        if 'tipo_processo' in df_raw_reversa.columns:
            mask_reversa &= df_raw_reversa['tipo_processo'].astype(str).str.lower().isin(vals)
        if 'delivery_type' in df_raw_resumo_reversa.columns:
            mask_resumo_rev &= df_raw_resumo_reversa['delivery_type'].astype(str).str.lower().isin(vals)

    df_filtrado_reversa = df_raw_reversa[mask_reversa]
    df_filtrado_resumo_rev = df_raw_resumo_reversa[mask_resumo_rev]

    data_hora_reversa = "N/D"
    if 'ultima_atualizacao_tabela' in df_raw_reversa.columns and not df_raw_reversa.empty:
        d_max = pd.to_datetime(df_raw_reversa['ultima_atualizacao_tabela']).max()
        data_hora_reversa = d_max.strftime('%d/%m/%Y às %H:%M:%S')

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
        st.markdown(f"<div class='metric-card'><div class='metric-card-label'>Modal Analisado</div><div class='metric-card-value'>{modal_selecionado}</div></div>", unsafe_allow_html=True)

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
            df_top_aberto = df_filtrado_resumo_rev.groupby('nome_seller', as_index=False)['taxa_devolucao_aberto'].mean().sort_values('taxa_devolucao_aberto', ascending=False).head(10).sort_values('taxa_devolucao_aberto', ascending=True)
            df_top_aberto['taxa_str'] = df_top_aberto['taxa_devolucao_aberto'].apply(lambda v: f"{v*100:.1f}%" if pd.notnull(v) else "0.0%")
            fig_top_aberto = px.bar(df_top_aberto, x='taxa_devolucao_aberto', y='nome_seller', text='taxa_str', orientation='h', template=template_plotly, color_discrete_sequence=['#EF4444'])
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