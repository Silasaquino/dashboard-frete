"""
Script: atualizar_producao.py
Objetivo: Conectar ao Amazon Redshift lendo credenciais de .streamlit/secrets.toml,
          executar a query de produção incluindo a métrica 'media' (produtividade),
          preservar data e hora em 'atualizacao_prod', formatar números decimais
          com vírgula e carregar na aba 'BASE' do Google Sheets.
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
SPREADSHEET_ID = "1ingCLhadaVsgQquO0f58TYO0vQ5H-3Bi4WCMJdo-dl4"
NOME_ABA_BASE = "BASE"
TAMANHO_LOTE = 10000

# ==============================================================================
# 3. QUERY SQL DE PRODUÇÃO (COM CAMPO 'MEDIA' E TIMESTAMP DE ATUALIZAÇÃO)
# ==============================================================================
QUERY_PRODUCAO = """
select 
	periodo as periodo,
	left (periodo, 7) as mes_ano_periodo,
	((date_part(day, periodo::date)::integer - 1) / 7) + 1 as semana_mes,
	date_part(week, periodo::date)::integer as semana_ano,
	setor_dados as setor,
	turno_dados as turno,
	case 
		when setor_dados in (
            'SUPPLY', 'CONFIABILIDADE', 'LUCIENE DA SILVA', 'DANIEL FELIPE VELOSO DE SOUSA',
            'MARCELO RIBERT BARBOSA', 'SANDY NIAMA FRANCO', 'VANESSA MARIA DA SILVA',
            'R12809434409', 'APRENDIZ', '', 'ABONO DE HORAS', 'SMART QUALITY',
            'COMPACTAÇÃO AS', 'QUALIDADE_OUT', 'QUALIDADE_INB', 'DEVOLUÇÃO', 'PREVENÇÃO',
            'BACKOFFICE', 'SALA DE CONTROLE', 'EXTRA', 'ALMOXARIFADO', 'TRANSPORTE',
            'AUTOMAÇÃO', 'PCM'
        ) then 'SUPORTE'
		when setor_dados in (
            'ARMAZENAMENTO AUTOSTORE', 'RECEBIMENTO AUTOSTORE', 
            'REPLENISHMENT AUTOSTORE', 'ARM_REPLENISHMENT'
        ) then 'INBOUND_AS'
		when setor_dados in ('PICKING AUTOSTORE', 'PACKING AUTOSTORE') then 'OUTBOUND_AS'
		when setor_dados like ('%INVENTARIO%') then 'INVENTARIO'
		when setor_dados like ('%FF%') then 'FULL'
		when setor_dados like ('%PESADO%') then 'PESADOS'
		when setor_dados like ('%MILKRUN%') then 'MILKRUN'
		when setor_dados in ('SHIPPING CROSS') then 'PESADOS'
		when setor_dados like ('%CQ%') then 'CONTROLE_QUALIDADE'
		when setor_dados like ('%REVERSA%') then 'REVERSA'
		when setor_dados in ('SEGREGADO') then 'SEGREGADO'
		when setor_dados in ('SHIPPING LEVE', 'PICKING LEVE', 'PACKING LEVE', 'CONSOLIDAÇÃO LEVE') then 'OUTBOUND_LEVE'
		when setor_dados in ('ARMAZENAMENTO LEVE', 'REC 2 LEVE', 'REC 1 LEVE') then 'INBOUND_LEVE'
		when setor_dados like ('FOTO/CONTEUDO') then 'FOTO/CONTEUDO'
		else null	
	end as definicacao_area,
	sum(case when horas_abs = 0 then 0 else 1 end) as total_pessoas,
	sum(horas_abs) as horas,
	sum(horas_enviadas) as horas_enviadas,
	sum(horas_recebidas) as horas_recebidas,
	sum(total_horas) as total_horas,
	sum(qtd_realizada) as qtd_final,
	case 
		when sum(total_horas) = 0 or sum(total_horas) is null then 0
		when sum(qtd_realizada) = 0 or sum(qtd_realizada) is null then 0
		else sum(qtd_realizada)::double precision / sum(total_horas)
	end as media,
	coalesce (max(meta_area),0) as meta_area,
    case 
        when qtd_final > 0 and sum(total_horas) <= 0 then 'Existe produção, mas não temos horas'
        when sum(total_horas) < 0 then 'Enviou mais horas do que recebeu'
        when DATE_PART(DW, periodo) = 0 and turno_dados <> '3° LEAP' and total_pessoas > 0 then 'ABS preenchido no domingo'
        else 'OK'
    end as obs,
    max(etl_load_date)::timestamp as atualizacao_prod
from
	curated_data.operation_production
where 
	considerar_producao = '1'
    and periodo >= DATEADD(MONTH, -48, DATE_TRUNC('MONTH', CURRENT_DATE))
group by 
    1, 2, 3, 4, 5, 6
"""


# ==============================================================================
# 4. FUNÇÕES DE TRATAMENTO E ATUALIZAÇÃO NO SHEETS
# ==============================================================================

def formatar_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Trata os tipos de dados do DataFrame:
    1. Preserva Data e Hora (YYYY-MM-DD HH:MM:SS) na coluna 'atualizacao_prod'.
    2. Converte demais campos de data para texto simples (YYYY-MM-DD).
    3. Mantém todas as casas decimais com vírgula (,).
    4. Trata valores nulos (NaN/None) deixando células vazias.
    """
    df_formatado = df.copy()

    # 1. Formata colunas de datas/horas nativas do Pandas
    for col in df_formatado.select_dtypes(include=["datetime64", "datetimetz"]).columns:
        if col == "atualizacao_prod":
            df_formatado[col] = df_formatado[col].dt.strftime("%Y-%m-%d %H:%M:%S")
        else:
            df_formatado[col] = df_formatado[col].dt.strftime("%Y-%m-%d")

    # 2. Formata objetos date ou datetime isolados em colunas genéricas ('object')
    for col in df_formatado.select_dtypes(include=["object"]).columns:
        if col == "atualizacao_prod":
            df_formatado[col] = df_formatado[col].apply(
                lambda valor: valor.strftime("%Y-%m-%d %H:%M:%S") if isinstance(valor, (datetime.date, datetime.datetime)) else valor
            )
        else:
            df_formatado[col] = df_formatado[col].apply(
                lambda valor: valor.strftime("%Y-%m-%d") if isinstance(valor, (datetime.date, datetime.datetime)) else valor
            )

    # 3. Converte números decimais (float) mantendo todas as casas decimais com vírgula
    for col in df_formatado.select_dtypes(include=["float64", "float32", "float"]).columns:
        df_formatado[col] = df_formatado[col].apply(
            lambda valor: str(valor).replace(".", ",") if pd.notnull(valor) else ""
        )

    # 4. Preenche qualquer outro valor nulo restante com texto vazio
    df_formatado = df_formatado.fillna("")
    return df_formatado


def atualizar_aba_google_sheets(planilha, nome_aba: str, df: pd.DataFrame, tamanho_lote: int = 10000):
    """
    Garante a existência da aba, expande linhas se necessário, limpa dados anteriores
    e envia os dados particionados por lotes.
    """
    worksheet = None
    for aba in planilha.worksheets():
        if aba.title.strip().upper() == nome_aba.strip().upper():
            worksheet = aba
            break

    if worksheet is None:
        print(f"[{datetime.datetime.now()}] ⚠️ Aba '{nome_aba}' não encontrada. A criar aba...")
        worksheet = planilha.add_worksheet(title=nome_aba, rows=1000, cols=30)

    print(f"[{datetime.datetime.now()}] 🧹 A limpar a aba '{worksheet.title}'...")
    worksheet.clear()

    matriz_dados = [df.columns.values.tolist()] + df.values.tolist()
    total_linhas = len(matriz_dados)

    linhas_atuais = worksheet.row_count
    if linhas_atuais < total_linhas:
        linhas_adicionais = total_linhas - linhas_atuais + 500
        print(f"[{datetime.datetime.now()}] 📐 A expandir planilha em +{linhas_adicionais} linhas...")
        worksheet.add_rows(linhas_adicionais)

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
        print(f"[{datetime.datetime.now()}] 📦 Lote de linhas {linha_inicio} a {linha_fim} gravado.")
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

        print(f"[{datetime.datetime.now()}] 📥 A executar a query de produção...")
        df_producao = pd.read_sql(QUERY_PRODUCAO, conexao)
        total_linhas = len(df_producao)
        print(f"[{datetime.datetime.now()}] ✅ Dados extraídos: TOTAL DE {total_linhas:,} LINHAS.".replace(",", "."))

        conexao.close()

    except Exception as erro_sql:
        print(f"[{datetime.datetime.now()}] ❌ Erro ao consultar o Redshift: {erro_sql}")
        return

    # Formatação dos dados
    print(f"[{datetime.datetime.now()}] ⚙️ A formatar datas, timestamps e números decimais com vírgula...")
    df_pronto = formatar_dataframe(df_producao)

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