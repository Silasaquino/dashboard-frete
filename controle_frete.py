import os
import time
import psycopg2
import pandas as pd
import gspread
from datetime import datetime

# ==========================================
# 1. LEITURA DE CREDENCIAIS (SECRETS.TOML)
# ==========================================
try:
    import tomllib  # Padrão no Python 3.11+
except ImportError:
    import tomli as tomllib

caminho_secrets = os.path.join(os.path.dirname(__file__), ".streamlit", "secrets.toml")

with open(caminho_secrets, "rb") as f:
    secrets = tomllib.load(f)

REDSHIFT_HOST = secrets["REDSHIFT_HOST"]
REDSHIFT_PORT = secrets["REDSHIFT_PORT"]
REDSHIFT_DB = secrets["REDSHIFT_DB"]
REDSHIFT_USER = secrets["REDSHIFT_USER"]
REDSHIFT_PASSWORD = secrets["REDSHIFT_PASSWORD"]

# ==========================================
# 2. CONFIGURAÇÕES DAS PLANILHAS
# ==========================================
# Planilha Principal (Resumo Consolidado e BP)
SHEET_RESUMO_ID = "1i08DkGeUZQk0agkSb1ruLLEiOuUMST0XjHkosgaFN0I"
ABA_RESUMO = "RESUMO"
ABA_BP = "BP"

TAMANHO_LOTE = 10000

# ==========================================
# 3. QUERIES SQL
# ==========================================

# 3.1 Query Principal (Consolidada)
QUERY_CONTROLE_FRETE = """
SELECT  
    data_filtro,
    left(data_filtro, 7) as mes_ano_filtro,
    transportador,
    tipo,
    case_rw,
    contrato,
    observacao_uc,
    status_duplicidade,
    qtd_remessas,
    qtd_itens,
    custos,
    valor_nf,
    etapa,
    UPPER(cidade) AS cidade,
    CASE 
        WHEN UPPER(cidade) = 'FRANCA' THEN 'FRANCA'
        WHEN UPPER(cidade) = 'BIRIGUI' THEN 'BIRIGUI'
        WHEN UPPER(cidade) = 'SAO PAULO' THEN 'SAO PAULO'
        WHEN UPPER(cidade) = 'NOVA FRIBURGO' THEN 'NOVA FRIBURGO'
        ELSE 'DEMAIS CIDADES'
    END AS cidade_class,
    faixa_peso,
	separacao,
    uf,
    regiao,
    macroregiao
FROM (
    -- 1. ENVIOS
    SELECT 
        data_filtro,
        transportador,
        tipo,
        case_rw,
        contrato,
        observacao_uc,
        status_duplicidade,
        SUM(qtd_remessas) AS qtd_remessas,
        SUM(qtd_itens) AS qtd_itens,
        SUM(custos) AS custos,
        SUM(valorvenda) AS valor_nf,
        'ENVIOS' AS etapa,
        NULL AS cidade,
        faixa_peso,
		separacao,
        uf,
	    regiao,
	    macroregiao
    FROM (
        SELECT 
            EXPEDICAO AS data_filtro,
            transportador,
            tipo,
            case_rw,
            contrato,
            grupo,
            remessa_entrega,
            remessa_coleta,
            remessa_correio,
            nf,
            case
	            when tipo = 'MARKETPLACE' and nf is null then 'SEM NF ATIVA SAP'
	            when tipo = 'MARKETPLACE' and frete_net_ajustado is null then 'SEM_FRETE_CALCULADO'
	            when tipo = 'MARKETPLACE' and observacao_uc = 'PROBLEMA_NO_PESO' then 'PROBLEMA_NO_PESO'
	            when tipo = 'MARKETPLACE' and observacao_uc = 'PROBLEMA_TABELA_D200' then 'PROBLEMA_TABELA_D200'
	            when tipo = 'MARKETPLACE' and observacao_uc = 'ERRO CADASTRO' then 'ERRO CADASTRO'
	            when tipo = 'MARKETPLACE' and observacao_uc = 'DIMENSÃO ZERADA' then 'DIMENSÃO ZERADA'
	            when tipo = 'MARKETPLACE' then 'OK'
                WHEN frete_net_ajustado IS NULL AND observacao_uc IN ('OK', 'UC NÃO MIGRADA PARA O ECC') THEN 'SEM_FRETE_CALCULADO' 
                ELSE observacao_uc 
            END AS observacao_uc,
            CASE 
                WHEN COUNT(remessa_entrega) OVER (PARTITION BY transportador, grupo, remessa_entrega, remessa_coleta, remessa_correio, nf) = 1 THEN 'OK' 
                ELSE 'DUPLICIDADE' 
            END AS status_duplicidade,
            QTD_REMESSAS,
            QTD_ITENS,
            FRETE_NET_AJUSTADO AS custos,
            valorvenda,
            faixa_peso,
			separacao,
            uf,
	        regiao,
	        macroregiao
        FROM curated_data.controle_frete_envios
        WHERE EXPEDICAO >= DATEADD(MONTH, -12, DATE_TRUNC('MONTH', CURRENT_DATE))  
    )
    GROUP BY 
        1, 2, 3, 4, 5, 6, 7, 13,14,15,16,17,18
        
    UNION ALL 

    -- 2. REVERSA / DEVOLUÇÃO
    SELECT 
        data_filtro,
        transportador,
        tipo,
        case_rw,
        contrato,
        observacao_uc,
        status_duplicidade,
        SUM(qtd_remessas) AS qtd_remessas,
        SUM(qtd_itens) AS qtd_itens,
        SUM(custos) AS custos,
        SUM(valor_entrada_reversa) AS valor_nf,
        etapa,
        NULL AS cidade,
        faixa_peso,
		separacao,
        uf,
	    regiao,
	    macroregiao
    FROM (
        SELECT 
            data_filtro,
            transportadora AS transportador,
            CASE 
                WHEN separacao LIKE '%RETAIL%' THEN 'RETAIL'
                ELSE 'FULL'
            END AS tipo,
            NULL AS case_rw,
            grupo_contrato AS contrato,
            grupo,
            remessa_reversa,
            remessa_correio,
            nf_reversa AS nf,
            observacao AS observacao_uc,
            CASE 
                WHEN COUNT(remessa_reversa) OVER (PARTITION BY transportadora, remessa_reversa, remessa_entrega, remessa_correio, grupo_contrato) = 1 THEN 'OK' 
                ELSE 'DUPLICIDADE' 
            END AS status_duplicidade,
            qtd_remessas,
            qtd_itens,
            melhor_frete_net_s_icms AS custos,
            valor_entrada_reversa,
            CASE 
                WHEN contrato IN ('POSTAGEM', 'COLETA') THEN 'REVERSA'
                ELSE 'INSUCESSO'
            END AS etapa,
            faixa_peso,
			separacao,
            UPPER (uf) as uf,
	        UPPER (regiao) as regiao,
	        UPPER (macroregiao) as macroregiao
        FROM curated_data.controle_frete_reversa_devolucao
        WHERE data_filtro >= DATEADD(MONTH, -12, DATE_TRUNC('MONTH', CURRENT_DATE))  
    )
    GROUP BY 
        1, 2, 3, 4, 5, 6, 7, 12, 13,14,15,16,17,18
        
    UNION ALL 

    -- 3. COLETA MILK RUN
    SELECT 
        data_filtro,
        transportador,
        tipo,
        case_rw,
        contrato,
        observacao_uc,
        status_duplicidade,
        SUM(qtd_remessas) AS qtd_remessas,
        SUM(qtd_itens) AS qtd_itens,
        SUM(custos) AS custos,
        SUM(valorvenda) AS valor_nf,
        'COLETA MR' AS etapa,
        cidade,
        faixa_peso,
		separacao,
        UPPER (uf) as uf,
	    UPPER (regiao) as regiao,
	    UPPER (macroregiao) as macroregiao
    FROM (
        SELECT 
            expedicao AS data_filtro,
            transportador,
            'MARKETPLACE' AS tipo,
            NULL AS case_rw,
            'COLETA MR' AS contrato,
            remessa_coleta,
            n_nf,
            CASE 
                WHEN melhor_frete_peso IS NULL AND observacao = 'OK' THEN 'SEM_FRETE_CALCULADO' 
                ELSE observacao 
            END AS observacao_uc,
            CASE
                WHEN COUNT(remessa_coleta) OVER (PARTITION BY transportador, remessa_coleta) = 1 THEN 'OK'
                ELSE 'DUPLICIDADE'
            END AS status_duplicidade,
            qtd_remessas,
            qtd_itens,
            melhor_frete_net_s_icms AS custos,
            valorvenda,
            cidade_seller AS cidade,
            faixa_peso,
			separacao,
            UPPER (uf_seller) as uf,
	        UPPER (regiao_seller) as regiao,
	        UPPER (macroregiao_seller) as macroregiao
        FROM curated_data.controle_frete_coleta_milkrun	
        WHERE EXPEDICAO >= DATEADD(MONTH, -12, DATE_TRUNC('MONTH', CURRENT_DATE))  
    )
    GROUP BY 
        1, 2, 3, 4, 5, 6, 7, 13,14,15,16,17,18
)
"""

# 3.2 Query BP Forecast
QUERY_BP_FORECAST = """
SELECT 
    tipo_cobranca,
    tipo_expedicao,
    transportador,
    to_date(periodo, 'dd/mm/yyyy') as periodo,
    left(to_date(periodo, 'dd/mm/yyyy'), 7) as mes_ano_periodo,
    cidade,
    regiao,
    uf,
    UPPER (macroregiao) as macroregiao,
    modal,
    faixa_peso,
    UPPER (contrato) as contrato,
    chave,
    remessas,
    frete,
    versao,
    sheet_title
FROM 
    manual_input.envio_bp_forecast
WHERE
    to_date(periodo, 'dd/mm/yyyy') >= DATEADD(MONTH, -12, DATE_TRUNC('MONTH', CURRENT_DATE))
"""

# 3.3 Queries de Erros / Inconsistências
QUERY_ERRO_ENVIOS = """
SELECT *
FROM (
    SELECT
        *,
        CASE
            when tipo = 'MARKETPLACE' and nf is null then 'SEM NF ATIVA SAP'
            when tipo = 'MARKETPLACE' and frete_net_ajustado is null then 'SEM_FRETE_CALCULADO'
            when tipo = 'MARKETPLACE' and observacao_uc = 'PROBLEMA_NO_PESO' then 'PROBLEMA_NO_PESO'
            when tipo = 'MARKETPLACE' and observacao_uc = 'PROBLEMA_TABELA_D200' then 'PROBLEMA_TABELA_D200'
            when tipo = 'MARKETPLACE' and observacao_uc = 'ERRO CADASTRO' then 'ERRO CADASTRO'
            when tipo = 'MARKETPLACE' and observacao_uc = 'DIMENSÃO ZERADA' then 'DIMENSÃO ZERADA'
            when tipo = 'MARKETPLACE' then 'OK'
            WHEN frete_net_ajustado IS NULL AND observacao_uc IN ('OK', 'UC NÃO MIGRADA PARA O ECC') THEN 'SEM_FRETE_CALCULADO'
            ELSE observacao_uc
        END AS observacao_uc_ajustada,
        CASE
            WHEN COUNT(remessa_entrega) OVER (PARTITION BY transportador, grupo, remessa_entrega, remessa_coleta, remessa_correio, nf) = 1 THEN 'OK'
            ELSE 'DUPLICIDADE'
        END AS status_duplicidade
    FROM curated_data.controle_frete_envios
    WHERE EXPEDICAO >= DATEADD(MONTH, -1, DATE_TRUNC('MONTH', CURRENT_DATE))
)
WHERE observacao_uc_ajustada <> 'OK' OR status_duplicidade <> 'OK'
"""

QUERY_ERRO_REVERSA = """
SELECT *
FROM (
    SELECT
        *,
        CASE
            WHEN melhor_frete_net_s_icms IS NULL AND observacao IN ('OK', 'UC NÃO MIGRADA PARA O ECC') THEN 'SEM_FRETE_CALCULADO'
            ELSE observacao
        END AS observacao_uc_ajustada,
        CASE
            WHEN COUNT(remessa_reversa) OVER (PARTITION BY transportadora, remessa_reversa, remessa_entrega, remessa_correio, grupo_contrato) = 1 THEN 'OK' 
            ELSE 'DUPLICIDADE'
        END AS status_duplicidade
    FROM curated_data.controle_frete_reversa_devolucao 
    WHERE data_filtro >= DATEADD(MONTH, -1, DATE_TRUNC('MONTH', CURRENT_DATE))
)
WHERE observacao_uc_ajustada <> 'OK' OR status_duplicidade <> 'OK'
"""

QUERY_ERRO_COLETA = """
SELECT *
FROM (
    SELECT
        *,
        CASE
            WHEN melhor_frete_peso IS NULL AND observacao IN ('OK', 'UC NÃO MIGRADA PARA O ECC') THEN 'SEM_FRETE_CALCULADO'
            ELSE observacao
        END AS observacao_uc_ajustada,
        CASE
            WHEN COUNT(remessa_coleta) OVER (PARTITION BY transportador, remessa_coleta) = 1 THEN 'OK'
            ELSE 'DUPLICIDADE'
        END AS status_duplicidade
    FROM curated_data.controle_frete_coleta_milkrun	
    WHERE EXPEDICAO >= DATEADD(MONTH, -1, DATE_TRUNC('MONTH', CURRENT_DATE))
)
WHERE observacao_uc_ajustada <> 'OK' OR status_duplicidade <> 'OK'
"""

# Lista de automações para gravação de erros
CONFIG_ERROS = [
    {
        "nome": "Erros Envios",
        "query": QUERY_ERRO_ENVIOS,
        "sheet_id": "1pwor7F7X1IX11BZBxTzrHkmZRlnyetfXOoLQCceQ_qQ",
        "aba": "ERRO"
    },
    {
        "nome": "Erros Reversa e Insucesso",
        "query": QUERY_ERRO_REVERSA,
        "sheet_id": "1UcCslCquUeMrahcbkDDwZG7DUDqtHNuZrk-Vyvh7pbY",
        "aba": "ERRO"
    },
    {
        "nome": "Erros Coleta Milk Run",
        "query": QUERY_ERRO_COLETA,
        "sheet_id": "1Rn-aTD8ZWMNR5AKQT53jsdLbCXG-6p7ew5eWgIuzvgg",
        "aba": "ERRO"
    }
]

# ==========================================
# 4. FUNÇÕES DE TRATAMENTO DE DADOS
# ==========================================
def preparar_dados_resumo(df: pd.DataFrame) -> pd.DataFrame:
    """Trata campos da aba principal RESUMO."""
    colunas_inteiras = ['qtd_remessas', 'qtd_itens']
    for col in colunas_inteiras:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype('int64')

    colunas_decimais = ['custos', 'valor_nf']
    for col in colunas_decimais:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0).round(2)

    colunas_texto = [col for col in df.columns if col not in colunas_inteiras + colunas_decimais]
    for col in colunas_texto:
        df[col] = df[col].astype(str).replace({'None': '', 'nan': '', '<NaT>': ''})

    return df


def preparar_dados_bp(df: pd.DataFrame) -> pd.DataFrame:
    """Trata campos da aba BP Forecast."""
    if 'remessas' in df.columns:
        df['remessas'] = pd.to_numeric(df['remessas'], errors='coerce').fillna(0).astype('int64')

    if 'frete' in df.columns:
        df['frete'] = pd.to_numeric(df['frete'], errors='coerce').fillna(0.0).round(2)

    for col in df.columns:
        if col not in ['remessas', 'frete']:
            if pd.api.types.is_datetime64_any_dtype(df[col]):
                df[col] = df[col].dt.strftime('%Y-%m-%d').fillna('')
            else:
                df[col] = df[col].fillna('').astype(str).replace({'None': '', 'nan': '', '<NaT>': ''})

    return df


def preparar_dados_erros(df: pd.DataFrame) -> pd.DataFrame:
    """Trata dados das tabelas de erros (select *) preservando números e tratando nulos."""
    colunas_inteiras_comuns = ['qtd_remessas', 'qtd_itens']
    colunas_decimais_comuns = [
        'custos', 'valor_nf', 'valorvenda', 'frete_net_ajustado', 
        'melhor_frete_net_s_icms', 'melhor_frete_peso', 'valor_entrada_reversa'
    ]

    for col in df.columns:
        col_lower = col.lower()
        if col_lower in colunas_inteiras_comuns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype('int64')
        elif col_lower in colunas_decimais_comuns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0).round(2)
        elif pd.api.types.is_datetime64_any_dtype(df[col]):
            df[col] = df[col].astype(str).replace({'NaT': '', 'nan': '', 'None': ''})
        else:
            df[col] = df[col].fillna('').astype(str).replace({'None': '', 'nan': '', '<NaT>': ''})

    return df


# ==========================================
# 5. ATUALIZAÇÃO NO GOOGLE SHEETS
# ==========================================
def atualizar_aba_google_sheets(sh, nome_aba, df, tamanho_lote=TAMANHO_LOTE):
    """Garante existência da aba, limpa dados anteriores e envia com tipagem USER_ENTERED."""
    try:
        worksheet = sh.worksheet(nome_aba)
    except gspread.WorksheetNotFound:
        print(f"[{datetime.now()}] ⚠️ Aba '{nome_aba}' não encontrada. Criando nova aba...")
        worksheet = sh.add_worksheet(title=nome_aba, rows=1000, cols=max(len(df.columns) + 2, 20))

    print(f"[{datetime.now()}] 🧹 Limpando conteúdo na aba '{nome_aba}'...")
    worksheet.clear()

    if df.empty:
        print(f"[{datetime.now()}] ℹ️ Nenhum registro retornado para a aba '{nome_aba}'. Gravando apenas cabeçalho.")
        worksheet.update("A1", [df.columns.values.tolist()])
        return

    matriz_dados = [df.columns.values.tolist()] + df.values.tolist()
    total_linhas = len(matriz_dados)
    total_colunas = len(df.columns)

    linhas_atuais = worksheet.row_count
    if linhas_atuais < total_linhas:
        linhas_extras = total_linhas - linhas_atuais + 500
        print(f"[{datetime.now()}] 📐 Expandindo a aba em +{linhas_extras} linhas...")
        worksheet.add_rows(linhas_extras)

    colunas_atuais = worksheet.col_count
    if colunas_atuais < total_colunas:
        colunas_extras = total_colunas - colunas_atuais + 5
        print(f"[{datetime.now()}] 📐 Expandindo a aba em +{colunas_extras} colunas...")
        worksheet.add_cols(colunas_extras)

    print(f"[{datetime.now()}] 📤 Enviando {total_linhas:,} linhas para a aba '{nome_aba}'...")
    for i in range(0, total_linhas, tamanho_lote):
        lote = matriz_dados[i : i + tamanho_lote]
        linha_inicio = i + 1
        intervalo = f"A{linha_inicio}"
        
        worksheet.update(intervalo, lote, value_input_option='USER_ENTERED')
        time.sleep(1)


# ==========================================
# 6. ORQUESTRADOR PRINCIPAL
# ==========================================
def executar_automacao():
    print(f"[{datetime.now()}] 🔄 Conectando ao Redshift e Google Sheets...")

    try:
        conexao = psycopg2.connect(
            host=REDSHIFT_HOST,
            port=REDSHIFT_PORT,
            dbname=REDSHIFT_DB,
            user=REDSHIFT_USER,
            password=REDSHIFT_PASSWORD
        )

        caminho_credenciais = os.path.join(os.path.dirname(__file__), "credenciais.json")
        gc = gspread.service_account(filename=caminho_credenciais)

    except Exception as e:
        print(f"[{datetime.now()}] ❌ Falha na conexão inicial: {e}")
        return

    try:
        sh_principal = gc.open_by_key(SHEET_RESUMO_ID)

        # ----------------------------------------------------
        # ETAPA 1: Processamento da Planilha Principal (RESUMO)
        # ----------------------------------------------------
        print(f"\n[{datetime.now()}] --- Processando RESUMO GERAL ---")
        df_resumo = pd.read_sql(QUERY_CONTROLE_FRETE, conexao)
        print(f"[{datetime.now()}] ✅ Extraído Resumo: {len(df_resumo):,} linhas.")
        
        df_resumo = preparar_dados_resumo(df_resumo)
        atualizar_aba_google_sheets(sh_principal, ABA_RESUMO, df_resumo)

        # ----------------------------------------------------
        # ETAPA 1.2: Processamento do BP FORECAST (Aba BP)
        # ----------------------------------------------------
        print(f"\n[{datetime.now()}] --- Processando BP FORECAST ---")
        df_bp = pd.read_sql(QUERY_BP_FORECAST, conexao)
        print(f"[{datetime.now()}] ✅ Extraído BP Forecast: {len(df_bp):,} linhas.")

        df_bp = preparar_dados_bp(df_bp)
        atualizar_aba_google_sheets(sh_principal, ABA_BP, df_bp)

        # ----------------------------------------------------
        # ETAPA 2: Processamento das Planilhas de ERROS
        # ----------------------------------------------------
        for item in CONFIG_ERROS:
            nome_processo = item["nome"]
            query = item["query"]
            sheet_id = item["sheet_id"]
            nome_aba = item["aba"]

            print(f"\n[{datetime.now()}] --- Processando {nome_processo} ---")
            df_erro = pd.read_sql(query, conexao)
            print(f"[{datetime.now()}] ✅ Extraídos {len(df_erro):,} registros com problema.")

            df_erro = preparar_dados_erros(df_erro)
            
            try:
                sh_erro = gc.open_by_key(sheet_id)
                atualizar_aba_google_sheets(sh_erro, nome_aba, df_erro)
                print(f"[{datetime.now()}] ✅ {nome_processo} gravado com sucesso.")
            except Exception as e:
                print(f"[{datetime.now()}] ❌ Erro ao atualizar a planilha ({nome_processo}): {e}")

        print(f"\n[{datetime.now()}] 🎉 Automação completa finalizada com sucesso!")

    except Exception as e:
        print(f"[{datetime.now()}] ❌ Erro durante a execução: {e}")

    finally:
        conexao.close()
        print(f"[{datetime.now()}] 🔒 Conexão com o Redshift encerrada.")


if __name__ == "__main__":
    executar_automacao()