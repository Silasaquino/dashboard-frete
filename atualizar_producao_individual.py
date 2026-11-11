"""
Script: atualizar_producao_individual.py
Objetivo: Extrair dados de produção individual do Redshift, calcular o Quartil (1 a 4)
          consolidado por colaborador no mês (mes_ano_periodo, setor e turno),
          preservar todas as casas decimais com vírgula (,), tratar datas e atualizar
          a folha Google Sheets em lotes seguros.
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
SPREADSHEET_ID = "1zs41ZxSK-p-WJ_ZdPZjZyG1qKL0LOSU-CACFfSguT5s"
NOME_ABA_BASE = "BASE"
TAMANHO_LOTE = 10000

# ==============================================================================
# 3. QUERY SQL DE PRODUÇÃO INDIVIDUAL COM QUARTIL CORRIGIDO
# ==============================================================================
QUERY_INDIVIDUAL = """
WITH base_agrupada AS (
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
            when setor_dados in ('SHIPPING CROSS') then 'OUTBOUND_AS'
            when setor_dados like ('%CQ%') then 'CONTROLE_QUALIDADE'
            when setor_dados like ('%REVERSA%') then 'REVERSA'
            when setor_dados in ('SEGREGADO') then 'SEGREGADO'
            when setor_dados in ('SHIPPING LEVE', 'PICKING LEVE', 'PACKING LEVE', 'REC 2 LEVE') then 'OUTBOUND_LEVE'
            when setor_dados in ('ARMAZENAMENTO LEVE', 'CONSOLIDAÇÃO LEVE', 'REC 1 LEVE') then 'INBOUND_LEVE'
            when setor_dados like ('FOTO/CONTEUDO') then 'FOTO/CONTEUDO'
            else null	
        end as definicacao_area,
        setor_colaborador,
        turno_colaborador,
        usuario,
        nome,
        desconsiderar,
        cargo,
        matricula,
        tempo_casa,
        fs,
        devido,
        indevido,
        analise,
        status_abs_apoios,
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
        max(meta_area) as meta_area
    from
        curated_data.operation_production
    where 
        considerar_producao = '1'
        and periodo >= DATEADD(MONTH, -12, DATE_TRUNC('MONTH', CURRENT_DATE))
    group by 
        1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20
),
ranking_colaborador_mes AS (
    -- Correção: usa qtd_final (o nome da coluna em base_agrupada)
    select
        mes_ano_periodo,
        setor,
        turno,
        usuario,
        ntile(4) over (
            partition by mes_ano_periodo, setor, turno 
            order by (
                case 
                    when sum(total_horas) = 0 or sum(total_horas) is null then 0
                    when sum(qtd_final) = 0 or sum(qtd_final) is null then 0
                    else sum(qtd_final)::double precision / sum(total_horas)
                end
            ) asc
        ) as quartil_colaborador_mes
    from base_agrupada
    group by 
        mes_ano_periodo, setor, turno, usuario
)
select 
    b.*,
    r.quartil_colaborador_mes as quartil
from base_agrupada b
left join ranking_colaborador_mes r
    on b.mes_ano_periodo = r.mes_ano_periodo
   and b.setor = r.setor
   and b.turno = r.turno
   and b.usuario = r.usuario
"""

# ==============================================================================
# 4. FUNÇÕES DE TRATAMENTO E ATUALIZAÇÃO NO GOOGLE SHEETS
# ==============================================================================

def formatar_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Trata os tipos de dados do DataFrame:
    1. Converte campos temporais para texto simples (YYYY-MM-DD).
    2. Mantém TODAS as casas decimais de números decimais trocando '.' por ','.
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
        worksheet = planilha.add_worksheet(title=nome_aba, rows=1000, cols=45)

    print(f"[{datetime.datetime.now()}] 🧹 A limpar a aba '{nome_aba}'...")
    worksheet.clear()

    matriz_dados = [df.columns.values.tolist()] + df.values.tolist()
    total_linhas = len(matriz_dados)

    # Verifica se a quantidade de linhas suporta a base e redimensiona
    linhas_atuais = worksheet.row_count
    if linhas_atuais < total_linhas:
        linhas_adicionais = total_linhas - linhas_atuais + 500
        print(f"[{datetime.datetime.now()}] 📐 A expandir planilha em +{linhas_adicionais} linhas...")
        worksheet.add_rows(linhas_adicionais)

    # Verifica se a quantidade de colunas suporta o DataFrame
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

        print(f"[{datetime.datetime.now()}] 📥 A executar a query com Quartil corrigido por Colaborador/Mês...")
        df_producao = pd.read_sql(QUERY_INDIVIDUAL, conexao)
        total_linhas = len(df_producao)
        print(f"[{datetime.datetime.now()}] ✅ Dados extraídos: TOTAL DE {total_linhas:,} LINHAS.".replace(",", "."))

        conexao.close()

    except Exception as erro_sql:
        print(f"[{datetime.datetime.now()}] ❌ Erro ao consultar o Redshift: {erro_sql}")
        return

    # Formatação dos dados
    print(f"[{datetime.datetime.now()}] ⚙️ A formatar datas e números com vírgula (todas as casas mantidas)...")
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