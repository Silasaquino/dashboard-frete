"""
Script: atualizar_absenteismo.py
Objetivo: Conectar ao Redshift lendo credenciais de .streamlit/secrets.toml,
          executar a query unificada de absenteísmo (atual + histórico),
          formatar números decimais preservando todas as casas com vírgula (,)
          e carregar os dados na aba 'BASE' do Google Sheets em lotes.
"""

import os
import time
import datetime
import psycopg2
import pandas as pd
import gspread

# ==============================================================================
# 1. LEITURA DE CREDENCIAIS DO REDSHIFT (.streamlit/secrets.toml)
# ==============================================================================
try:
    import tomllib  # Padrão nativo do Python 3.11+
except ImportError:
    import tomli as tomllib

CAMINHO_SECRETS = os.path.join(".streamlit", "secrets.toml")

with open(CAMINHO_SECRETS, "rb") as arquivo_secrets:
    secrets = tomllib.load(arquivo_secrets)

REDSHIFT_HOST = secrets["REDSHIFT_HOST"]
REDSHIFT_PORT = secrets["REDSHIFT_PORT"]
REDSHIFT_DB = secrets["REDSHIFT_DB"]
REDSHIFT_USER = secrets["REDSHIFT_USER"]
REDSHIFT_PASSWORD = secrets["REDSHIFT_PASSWORD"]

# ==============================================================================
# 2. CONFIGURAÇÕES DO GOOGLE SHEETS
# ==============================================================================
# ID extraído da URL fornecida:
# https://docs.google.com/spreadsheets/d/1Kp2YqEc7W7EfaWrmNNLIfqc-nctiuUQ6DM0T6lHTPeo/edit
SPREADSHEET_ID = "1Kp2YqEc7W7EfaWrmNNLIfqc-nctiuUQ6DM0T6lHTPeo"
NOME_ABA_BASE = "BASE"
TAMANHO_LOTE = 10000

# ==============================================================================
# 3. QUERY SQL DE ABSENTEÍSMO
# ==============================================================================
QUERY_ABSENTEISMO = """
select 
	left(to_timestamp(data, 'DD/MM/YYYY')::date, 7) as mes_ano,
	setor,
	turno,
	cargo,
	count(distinct nome) as qtd
from 
	fabric.m_abs_cd_operacao_leap	
where 
	sigla not in ('P')
	and setor is not null
group by 1, 2, 3, 4

union all

select 
	left(to_timestamp(data, 'DD/MM/YYYY')::date, 7) as mes_ano,
	setor,
	turno,
	cargo,
	count(distinct nome) as qtd
from 
	fabric.m_historico_abs_cd_operacao_leap	
where 
	sigla not in ('P')
	and setor is not null
group by 1, 2, 3, 4
"""

# ==============================================================================
# 4. FUNÇÕES DE TRATAMENTO E ATUALIZAÇÃO NO GOOGLE SHEETS
# ==============================================================================

def formatar_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Trata os tipos de dados do DataFrame:
    1. Converte campos temporais para texto simples (YYYY-MM-DD).
    2. Mantém TODAS as casas decimais de números, trocando '.' por ','.
    3. Trata valores nulos (NaN/None) deixando células vazias.
    """
    df_formatado = df.copy()

    # Formata colunas de datas nativas do Pandas
    for col in df_formatado.select_dtypes(include=["datetime64", "datetimetz"]).columns:
        df_formatado[col] = df_formatado[col].dt.strftime("%Y-%m-%d")

    # Formata objetos date ou datetime isolados em colunas genéricas ('object')
    for col in df_formatado.select_dtypes(include=["object"]).columns:
        df_formatado[col] = df_formatado[col].apply(
            lambda valor: valor.strftime("%Y-%m-%d") if isinstance(valor, (datetime.date, datetime.datetime)) else valor
        )

    # Converte números decimais (float) mantendo TODAS as casas decimais com vírgula
    for col in df_formatado.select_dtypes(include=["float64", "float32", "float"]).columns:
        df_formatado[col] = df_formatado[col].apply(
            lambda valor: str(valor).replace(".", ",") if pd.notnull(valor) else ""
        )

    # Garante que, se a coluna 'qtd' contiver ponto (caso venha como string ou numérico), seja convertida para vírgula
    if "qtd" in df_formatado.columns:
        df_formatado["qtd"] = df_formatado["qtd"].apply(
            lambda valor: str(valor).replace(".", ",") if pd.notnull(valor) and valor != "" else valor
        )

    # Preenche qualquer outro valor nulo restante com texto vazio
    df_formatado = df_formatado.fillna("")
    return df_formatado


def atualizar_aba_google_sheets(planilha, nome_aba: str, df: pd.DataFrame, tamanho_lote: int = 10000):
    """
    Localiza ou cria a aba, expande linhas e colunas se necessário, limpa dados anteriores
    e envia os dados passando apenas a célula inicial de cada lote (ex.: A1, A10001...).
    """
    try:
        worksheet = planilha.worksheet(nome_aba)
    except gspread.WorksheetNotFound:
        print(f"[{datetime.datetime.now()}] ⚠️ Aba '{nome_aba}' não encontrada. A criar aba...")
        worksheet = planilha.add_worksheet(title=nome_aba, rows=1000, cols=20)

    print(f"[{datetime.datetime.now()}] 🧹 A limpar a aba '{nome_aba}'...")
    worksheet.clear()

    matriz_dados = [df.columns.values.tolist()] + df.values.tolist()
    total_linhas = len(matriz_dados)

    # Garante que a planilha tem linhas suficientes
    linhas_atuais = worksheet.row_count
    if linhas_atuais < total_linhas:
        linhas_adicionais = total_linhas - linhas_atuais + 500
        print(f"[{datetime.datetime.now()}] 📐 A expandir planilha em +{linhas_adicionais} linhas...")
        worksheet.add_rows(linhas_adicionais)

    # Garante que a planilha tem colunas suficientes
    total_colunas = len(df.columns)
    if worksheet.col_count < total_colunas:
        colunas_adicionais = total_colunas - worksheet.col_count + 5
        print(f"[{datetime.datetime.now()}] 📐 A expandir colunas em +{colunas_adicionais} colunas...")
        worksheet.add_cols(colunas_adicionais)

    print(f"[{datetime.datetime.now()}] 📤 A enviar {total_linhas:,} linhas para '{nome_aba}'...".replace(",", "."))

    for inicio in range(0, total_linhas, tamanho_lote):
        lote = matriz_dados[inicio : inicio + tamanho_lote]
        linha_inicio = inicio + 1
        celula_inicio = f"A{linha_inicio}"

        worksheet.update(
            range_name=celula_inicio,
            values=lote,
            value_input_option="USER_ENTERED"
        )

        linha_fim = inicio + len(lote)
        print(f"[{datetime.datetime.now()}] 📦 Lote de linhas {linha_inicio} a {linha_fim} gravado com sucesso.")
        time.sleep(1)


# ==============================================================================
# 5. EXECUÇÃO PRINCIPAL DO PIPELINE
# ==============================================================================

def executar_automacao():
    print(f"[{datetime.datetime.now()}] 🔄 A conectar ao Redshift...")
    try:
        conexao = psycopg2.connect(
            host=REDSHIFT_HOST,
            port=REDSHIFT_PORT,
            dbname=REDSHIFT_DB,
            user=REDSHIFT_USER,
            password=REDSHIFT_PASSWORD
        )

        print(f"[{datetime.datetime.now()}] 📥 A executar a query de absenteísmo...")
        df_absenteismo = pd.read_sql(QUERY_ABSENTEISMO, conexao)
        total_linhas = len(df_absenteismo)
        print(f"[{datetime.datetime.now()}] ✅ Dados extraídos: TOTAL DE {total_linhas:,} LINHAS.".replace(",", "."))

        conexao.close()

    except Exception as erro_sql:
        print(f"[{datetime.datetime.now()}] ❌ Erro ao consultar o Redshift: {erro_sql}")
        return

    # Formatação dos dados
    print(f"[{datetime.datetime.now()}] ⚙️ A formatar dados (vírgulas e todas as casas decimais mantidas)...")
    df_pronto = formatar_dataframe(df_absenteismo)

    # Conexão e envio ao Google Sheets
    print(f"[{datetime.datetime.now()}] 🔄 A conectar ao Google Sheets...")
    caminho_credenciais = os.path.join(os.path.dirname(__file__), "credenciais.json")

    try:
        gc = gspread.service_account(filename=caminho_credenciais)
        planilha = gc.open_by_key(SPREADSHEET_ID)

        atualizar_aba_google_sheets(planilha, NOME_ABA_BASE, df_pronto, tamanho_lote=TAMANHO_LOTE)
        print(f"[{datetime.datetime.now()}] 🎉 Processo de atualização concluído com sucesso!")

    except Exception as erro_sheets:
        print(f"[{datetime.datetime.now()}] ❌ Erro no Google Sheets: {erro_sheets}")


if __name__ == "__main__":
    executar_automacao()