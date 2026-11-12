"""
Script: atualizar_abs_detalhado.py
Objetivo: Conectar ao Amazon Redshift lendo credenciais de .streamlit/secrets.toml,
          executar a query agrupada por siglas (atual + histórico dos últimos 24 meses),
          tratar datas e números decimais (preservando todas as casas com vírgula)
          e carregar os dados na aba 'BASE' do Google Sheets em lotes seguros.
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
    import tomllib  # Nativo no Python 3.11+
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
SPREADSHEET_ID = "1FnCZLKtYx1nkNhe4aEcwZ_x7hg8VK6Q65e3wWaUTY5Y"
NOME_ABA_DESTINO = "BASE"
TAMANHO_LOTE = 10000

# ==============================================================================
# 3. QUERY SQL DE ABSENTEÍSMO DETALHADO (AGRUPADO POR SIGLAS)
# ==============================================================================
QUERY_ABS_DETALHADO = """
select 
	periodo,
	left(periodo, 7) as mes_ano_periodo,
	setor,
	turno,
	desconsiderar,
	siglas,
	local,
	count(siglas) as qtd
from (
    select 
        to_timestamp(data, 'DD/MM/YYYY')::date as periodo,
        logins,
        nome,
        matricula,
        cargo,
        desconsiderar,
        setor,
        turno,
        case 
		    when UPPER (abs.sigla) in ('LM/LP','LM') then 'LM/LP'
		    when UPPER (abs.sigla) in ('FI','I','F ') then 'FI'
            when UPPER (abs.sigla) in ('DES','DESL','DESP') then 'DES'
            else UPPER (abs.sigla)
	    end as siglas,
        'abs' as local
    from 
        fabric.m_abs_cd_operacao_leap as abs 
    where 
        to_timestamp(data, 'DD/MM/YYYY')::date >= DATEADD(MONTH, -24, DATE_TRUNC('MONTH', CURRENT_DATE))  
        and UPPER (abs.sigla) <> ''
	    and UPPER (abs.sigla) is not null
        and UPPER (abs.sigla) <> 0
    union all

    select 
        to_timestamp(data, 'DD/MM/YYYY')::date as periodo,
        logins,
        nome,
        matricula,
        cargo,
        desconsiderar,
        setor,
        turno,
        case 
		    when UPPER (abs.sigla) in ('LM/LP','LM') then 'LM/LP'
		    when UPPER (abs.sigla) in ('FI','I','F ') then 'FI'
            when UPPER (abs.sigla) in ('DES','DESL','DESP') then 'DES'
            else UPPER (abs.sigla)
	    end as siglas,
        'historico_abs' as local
    from 
        fabric.m_historico_abs_cd_operacao_leap as abs 
    where 
        to_timestamp(data, 'DD/MM/YYYY')::date >= DATEADD(MONTH, -24, DATE_TRUNC('MONTH', CURRENT_DATE))  
        and UPPER (abs.sigla) <> ''
	    and UPPER (abs.sigla) is not null
        and UPPER (abs.sigla) <> 0
) sub
group by 1, 2, 3, 4, 5, 6, 7
"""

# ==============================================================================
# 4. FUNÇÕES DE TRATAMENTO E ATUALIZAÇÃO NO GOOGLE SHEETS
# ==============================================================================

def formatar_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Trata os tipos de dados do DataFrame:
    1. Converte campos temporais para texto simples (YYYY-MM-DD).
    2. Mantém TODAS as casas decimais de números float, trocando '.' por ','.
    3. Trata valores nulos (NaN/None) deixando células vazias.
    """
    df_formatado = df.copy()

    # 1. Formata colunas de datas nativas do Pandas
    for col in df_formatado.select_dtypes(include=["datetime64", "datetimetz"]).columns:
        df_formatado[col] = df_formatado[col].dt.strftime("%Y-%m-%d")

    # 2. Formata objetos date ou datetime isolados em colunas genéricas ('object')
    for col in df_formatado.select_dtypes(include=["object"]).columns:
        df_formatado[col] = df_formatado[col].apply(
            lambda valor: valor.strftime("%Y-%m-%d") if isinstance(valor, (datetime.date, datetime.datetime)) else valor
        )

    # 3. Converte números decimais (float) mantendo TODAS as casas decimais com vírgula
    for col in df_formatado.select_dtypes(include=["float64", "float32", "float"]).columns:
        df_formatado[col] = df_formatado[col].apply(
            lambda valor: str(valor).replace(".", ",") if pd.notnull(valor) else ""
        )

    # 4. Garante que a coluna 'qtd' substitua ponto por vírgula caso contenha decimais
    if "qtd" in df_formatado.columns:
        df_formatado["qtd"] = df_formatado["qtd"].apply(
            lambda valor: str(valor).replace(".", ",") if pd.notnull(valor) and valor != "" else valor
        )

    # 5. Preenche qualquer outro valor nulo restante com texto vazio
    df_formatado = df_formatado.fillna("")
    return df_formatado


def atualizar_aba_google_sheets(planilha, nome_aba: str, df: pd.DataFrame, tamanho_lote: int = 10000):
    """
    Procura a aba ignorando diferenças de maiúsculas/minúsculas (cria apenas se não existir),
    expande linhas/colunas se necessário, limpa dados anteriores e envia os dados em lotes.
    """
    worksheet = None
    for aba in planilha.worksheets():
        if aba.title.strip().upper() == nome_aba.strip().upper():
            worksheet = aba
            break

    if worksheet is None:
        print(f"[{datetime.datetime.now()}] ⚠️ Aba '{nome_aba}' não encontrada. A criar aba...")
        worksheet = planilha.add_worksheet(title=nome_aba, rows=1000, cols=20)

    print(f"[{datetime.datetime.now()}] 🧹 A limpar a aba '{worksheet.title}'...")
    worksheet.clear()

    matriz_dados = [df.columns.values.tolist()] + df.values.tolist()
    total_linhas = len(matriz_dados)

    # Verifica se a planilha suporta a quantidade de linhas e redimensiona
    linhas_atuais = worksheet.row_count
    if linhas_atuais < total_linhas:
        linhas_adicionais = total_linhas - linhas_atuais + 500
        print(f"[{datetime.datetime.now()}] 📐 A expandir planilha em +{linhas_adicionais} linhas...")
        worksheet.add_rows(linhas_adicionais)

    # Verifica se a planilha suporta a quantidade de colunas e redimensiona
    total_colunas = len(df.columns)
    if worksheet.col_count < total_colunas:
        colunas_adicionais = total_colunas - worksheet.col_count + 5
        print(f"[{datetime.datetime.now()}] 📐 A expandir colunas em +{colunas_adicionais} colunas...")
        worksheet.add_cols(colunas_adicionais)

    print(f"[{datetime.datetime.now()}] 📤 A enviar {total_linhas:,} linhas para '{worksheet.title}'...".replace(",", "."))

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

        print(f"[{datetime.datetime.now()}] 📥 A executar a query de absenteísmo agrupado por siglas...")
        df_abs_detalhado = pd.read_sql(QUERY_ABS_DETALHADO, conexao)
        total_linhas = len(df_abs_detalhado)
        print(f"[{datetime.datetime.now()}] ✅ Dados extraídos: TOTAL DE {total_linhas:,} LINHAS.".replace(",", "."))

        conexao.close()

    except Exception as erro_sql:
        print(f"[{datetime.datetime.now()}] ❌ Erro ao consultar o Redshift: {erro_sql}")
        return

    # Formatação dos dados
    print(f"[{datetime.datetime.now()}] ⚙️ A formatar datas e números (vírgulas e todas as casas decimais mantidas)...")
    df_pronto = formatar_dataframe(df_abs_detalhado)

    # Conexão e envio ao Google Sheets
    print(f"[{datetime.datetime.now()}] 🔄 A conectar ao Google Sheets...")
    caminho_credenciais = os.path.join(os.path.dirname(__file__), "credenciais.json")

    try:
        gc = gspread.service_account(filename=caminho_credenciais)
        planilha = gc.open_by_key(SPREADSHEET_ID)

        atualizar_aba_google_sheets(planilha, NOME_ABA_DESTINO, df_pronto, tamanho_lote=TAMANHO_LOTE)
        print(f"[{datetime.datetime.now()}] 🎉 Processo de atualização concluído com sucesso!")

    except Exception as erro_sheets:
        print(f"[{datetime.datetime.now()}] ❌ Erro no Google Sheets: {erro_sheets}")


if __name__ == "__main__":
    executar_automacao()