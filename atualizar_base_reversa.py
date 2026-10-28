import os
import time
import psycopg2
import pandas as pd
import gspread
from datetime import datetime

# ==========================================
# 1. CONFIGURAÇÕES DE CONEXÃO AO REDSHIFT (LENDO DO SECRETS.TOML)
# ==========================================
try:
    import tomllib  # Nativo no Python 3.11+
except ImportError:
    import tomli as tomllib

with open(".streamlit/secrets.toml", "rb") as f:
    secrets = tomllib.load(f)

REDSHIFT_HOST = secrets["REDSHIFT_HOST"]
REDSHIFT_PORT = secrets["REDSHIFT_PORT"]
REDSHIFT_DB = secrets["REDSHIFT_DB"]
REDSHIFT_USER = secrets["REDSHIFT_USER"]
REDSHIFT_PASSWORD = secrets["REDSHIFT_PASSWORD"]

# ==========================================
# 2. CONFIGURAÇÃO DAS PLANILHAS DO GOOGLE SHEETS
# ==========================================
SHEET_PRINCIPAL_ID = "1tYkxqGCSan5C7wAjtqKeKpOE2OeGCgrzSynMaXVBaKU"
NOME_ABA_RESUMO = "RESUMO REVERSA"
NOME_ABA_BASE = "BASE"

PLANILHAS_BASE = [
    {"id": "1tYkxqGCSan5C7wAjtqKeKpOE2OeGCgrzSynMaXVBaKU", "gid": "0"},          # Parte 1 (Principal)
    {"id": "10zd0gTWei38fpjBZ4xNuIe0gdI8FGbscX3bc6uYgewE", "gid": "0"},          # Parte 2
    {"id": "1FBS9BSal8DBtyVSOhGKBcNIa8EmktSunsuCCC9AuM34", "gid": "0"},          # Parte 3
    {"id": "17f48qNZ1MVvgOwI467OypCrgR-iQl3TqZ7sosLp3s7Y", "gid": "638743010"},  # Parte 4
    {"id": "1AyYe3M3kHCnlZYjD-GSR9oHr_6rGqsL8KMBUnnrvcx4", "gid": "0"}           # Parte 5
]

LIMIT_LINHAS_POR_SHEET = 300000

# ==========================================
# 3. CONSULTAS SQL
# ==========================================
QUERY_BASE = """
    SELECT 
        data_solicitacao,
        mes_ano_solicitacao,
        tipo_solicitacao,
        UPPER (seller_name) as seller_name,
        tipo_processo,
        ultima_atualizacao_tabela,
        pedido,
        remessa_retorno,
        motivo_troca,
        auto_postagem,
        object_tag_number,
        status_rastreio,
        data_postagem,
        data_ultimo_status_correios,
        ultimo_status_correios,
        protocolo,
        sku,
        categoria,
        quantidade,
        valor_retorno,
        data_rem,
        data_der,
        data_extravio,
        mes_ano_finalizacao,
        tracking,
        sub_tracking,
        dias_aberto_seller,
        CASE 
            WHEN dias_aberto_seller IS NULL THEN null
            WHEN dias_aberto_seller = 0 THEN '0 DIAS CORRIDOS'
            WHEN dias_aberto_seller = 1 THEN '1 DIAS CORRIDOS'
            WHEN dias_aberto_seller = 2 THEN '2 DIAS CORRIDOS'
            WHEN dias_aberto_seller = 3 THEN '3 DIAS CORRIDOS'
            WHEN dias_aberto_seller = 4 THEN '4 DIAS CORRIDOS'
            WHEN dias_aberto_seller = 5 THEN '5 DIAS CORRIDOS'
            ELSE '+5 DIAS CORRIDOS'
        END AS grupo_aberto_seller
    FROM (
        SELECT 
            return_order_date AS data_solicitacao,
            LEFT(return_order_date, 7) AS mes_ano_solicitacao,
            type_request_king AS tipo_solicitacao,
            seller_name,
            CASE
                WHEN delivery_type = 'DAFITI_ENVIOS' THEN 'DAFITI ENVIOS'
                WHEN delivery_type = 'FULL' THEN 'FULFILLMENT'
                ELSE delivery_type 
            END AS tipo_processo,
            etl_load_date AS ultima_atualizacao_tabela,
            sale_order_store_number AS pedido, 
            return_delivery_number AS remessa_retorno,
            reason AS motivo_troca,
            definition_tracking AS auto_postagem,
            object_tag_number AS object_tag_number,
            history_status_description AS status_rastreio,
            history_update_date AS data_postagem,
            object_update_date AS data_ultimo_status_correios,
            object_status_description AS ultimo_status_correios,
            protocol AS protocolo,
            product_code_store AS sku,
            UPPER (conf.attribute_set) AS categoria,
            SUM(original_item_quantity_order) AS quantidade,
            SUM(reverse_amount) AS valor_retorno,
            rem_date AS data_rem,
            der_date AS data_der,
            status_date_loss AS data_extravio,
            LEFT(COALESCE(rem_date::date, der_date::date, status_date_loss::date), 7) AS mes_ano_finalizacao,
            CASE
                WHEN rem_date IS NOT NULL THEN 'FINALIZADO'
                WHEN der_date IS NOT NULL THEN 'FINALIZADO'
                WHEN src_status = 'return_rejected' THEN 'FINALIZADO'
                WHEN status_date_loss IS NOT NULL THEN 'FINALIZADO'
                WHEN object_status_description = 'Entregue' THEN 'ENTREGUE AO SELLER'
                WHEN history_status_description = 'Coletado' THEN 'POSTADO/TRANSPORTADOR'
                WHEN type_request_king = 'Insucesso' THEN 'POSTADO/TRANSPORTADOR'
                WHEN history_status_description = 'Prazo de Utilização Expirado' THEN 'FINALIZADO'
                ELSE 'EM ABERTO'
            END AS tracking,
            CASE
                WHEN rem_date IS NOT NULL THEN 'ENTRADA NO SELLER' 
                WHEN der_date IS NOT NULL THEN 'RECUSA SELLER'
                WHEN src_status = 'return_rejected' THEN 'RECUSA SELLER'
                WHEN status_date_loss IS NOT NULL THEN 'EXTRAVIO'
                WHEN history_status_description = 'Prazo de Utilização Expirado' THEN 'REVERSAS EXPIRADAS'
                ELSE NULL
            END AS sub_tracking,
            CASE
                WHEN (
                    CASE
                        WHEN rem_date IS NOT NULL THEN 'FINALIZADO'
                        WHEN der_date IS NOT NULL THEN 'FINALIZADO'
                        WHEN src_status = 'return_rejected' THEN 'FINALIZADO'
                        WHEN status_date_loss IS NOT NULL THEN 'EXTRAVIO'
                        WHEN object_status_description = 'Entregue' THEN 'ENTREGUE AO SELLER'
                        WHEN history_status_description = 'Coletado' THEN 'POSTADO/TRANSPORTADOR'
                        WHEN history_status_description = 'Prazo de Utilização Expirado' THEN 'REVERSAS EXPIRADAS'
                        ELSE 'EM ABERTO'
                    END
                ) = 'ENTREGUE AO SELLER' AND object_update_date IS NOT NULL 
                THEN DATEDIFF(day, object_update_date::date, CURRENT_DATE)
                ELSE NULL
            END AS dias_aberto_seller
        FROM 
            curated_data.a_operation_returns AS rev
        LEFT JOIN 
            business_layer.dim_product_config AS conf 
            ON rev.sku_config = conf.sku_config
        WHERE 
            return_order_date >= DATEADD(month, -6, DATE_TRUNC('month', GETDATE()))
            AND delivery_type IN ('DROPSHIPPING','DAFITI_ENVIOS','MILKRUN')
        GROUP BY 
            return_order_date,
            type_request_king,
            seller_name,
            delivery_type,
            etl_load_date,
            sale_order_store_number, 
            return_delivery_number,
            reason,
            definition_tracking,
            object_tag_number,
            history_status_description,
            history_update_date,
            object_update_date,
            object_status_description,
            protocol,
            product_code_store,
            rem_date,
            der_date,
            status_date_loss,
            src_status,
            conf.attribute_set
    ) sub
"""

QUERY_RESUMO = """
WITH base AS (
    SELECT 
        dev.sale_order_store_number as pedido,
        dev.delivery_type,
        UPPER (dev.seller_name) AS nome_seller,
        CASE 
            WHEN dev.delivery_type = 'MILKRUN' THEN MIN(dev.delivery_collect_number)
            ELSE MIN(dev.delivery_number)
        END AS doc_dft,
        CASE 
            WHEN dev.delivery_type IN ('DAFITI ENVIOS', 'MILKRUN') THEN LEFT(min (dev.paid_date::date), 7)
            ELSE LEFT((CASE 
                WHEN dev.delivery_type = 'MILKRUN' THEN MIN(dev.milkrun_expected_delivery_warehouse_date::date)
                ELSE MIN(dev.customer_expected_delivery_date::date)
            END), 7) 
        END AS mes_ano_definido
    FROM 
        showcase.c_operation_outbound_delivery AS dev
    WHERE 
        dev.delivery_type IN ('DROPSHIPPING', 'DAFITI ENVIOS', 'MILKRUN')
    GROUP BY 
        dev.delivery_type, dev.seller_name, dev.paid_date, dev.delivery_type, dev.sale_order_store_number
    HAVING 
        (CASE 
            WHEN dev.delivery_type IN ('DAFITI ENVIOS', 'MILKRUN') THEN MIN(dev.paid_date)
            ELSE MIN(dev.customer_expected_delivery_date::date)
        END) >= DATEADD(MONTH, -6, DATE_TRUNC('MONTH', CURRENT_DATE))      
),
rev_inv AS (
    SELECT 
        delivery_number,
        delivery_type as tipo_item,
        UPPER (nome_seller_rev) as nome_seller_rev,
        MAX(devolvido) AS devolvido,
        MAX(devolucao_reprovada) AS devolucao_reprovada,
        MAX(devolucao_em_aberto) AS devolucao_em_aberto
    FROM (
        SELECT 
            delivery_number,
            CASE
                WHEN delivery_type = 'DAFITI_ENVIOS' THEN 'DAFITI ENVIOS'
                WHEN delivery_type = 'FULL' THEN 'FULFILLMENT'
                ELSE delivery_type 
            END AS delivery_type,
            UPPER (CASE 
                WHEN delivery_type = 'RETAIL' THEN 'LEAP'
                ELSE seller_name 
            END) AS nome_seller_rev,
            CASE WHEN coalesce (rem_date,bench_date) IS NOT NULL THEN 1 ELSE 0 END AS devolvido,
            CASE WHEN der_date IS NOT NULL THEN 1 ELSE 0 END AS devolucao_reprovada,
            CASE 
                WHEN devolvido = 1 THEN 0
                WHEN devolucao_reprovada = 1 THEN 0
                ELSE 1
            END AS devolucao_em_aberto
        FROM 
            curated_data.a_operation_returns AS rev
        WHERE 
            delivery_type in ('DROPSHIPPING','DAFITI_ENVIOS','MILKRUN')
        GROUP BY
            delivery_number, rem_date, der_date, seller_name, bench_date, delivery_type
    )
    GROUP BY 
        delivery_number, nome_seller_rev, delivery_type
)
SELECT 
    nome_seller,
    mes_ano_definido,
    delivery_type,
    COUNT(doc_dft) AS qtd_etr,
    SUM(devolvido) AS devolvido,
    SUM(devolucao_reprovada) AS devolucao_reprovada,
    SUM(devolucao_em_aberto) AS devolucao_em_aberto,
    SUM(devolvido) + SUM(devolucao_reprovada) + SUM(devolucao_em_aberto) AS total_reversa,
    SUM(devolucao_em_aberto) / COUNT(doc_dft)::double precision AS taxa_devolucao_aberto,
    SUM(devolvido) / COUNT(doc_dft)::double precision AS taxa_devolucao,
    SUM(devolucao_reprovada) / COUNT(doc_dft)::double precision AS taxa_devolucao_reprovada,
    total_reversa / COUNT(doc_dft)::double precision AS taxa_geral_devolucao
FROM 
    base AS b
LEFT JOIN 
    rev_inv AS r
    ON doc_dft = delivery_number and nome_seller = nome_seller_rev and delivery_type = tipo_item
GROUP BY 
    1, 2, 3
HAVING 
    total_reversa > 0;
"""


def atualizar_aba_google_sheets(sh, nome_aba, df, tamanho_lote=10000):
    """Limpa e escreve os dados numa aba do Google Sheets."""
    try:
        worksheet = sh.worksheet(nome_aba)
    except gspread.WorksheetNotFound:
        print(f"[{datetime.now()}] ⚠️ Aba '{nome_aba}' não encontrada. A criar nova aba...")
        worksheet = sh.add_worksheet(title=nome_aba, rows=1000, cols=30)

    print(f"[{datetime.now()}] 🧹 A limpar a aba '{nome_aba}'...")
    worksheet.clear()

    matriz_dados = [df.columns.values.tolist()] + df.values.tolist()
    total_linhas = len(matriz_dados)

    linhas_atuais = worksheet.row_count
    if linhas_atuais < total_linhas:
        linhas_necessarias = total_linhas - linhas_atuais + 500
        print(f"[{datetime.now()}] 📐 A expandir grelha de '{nome_aba}' em +{linhas_necessarias} linhas...")
        worksheet.add_rows(linhas_necessarias)

    print(f"[{datetime.now()}] 📤 A enviar {total_linhas:,} linhas para '{nome_aba}'...".replace(",", "."))
    for i in range(0, total_linhas, tamanho_lote):
        lote = matriz_dados[i : i + tamanho_lote]
        linha_inicio = i + 1
        intervalo = f"A{linha_inicio}"
        worksheet.update(intervalo, lote)
        time.sleep(1)


def executar_automacao():
    print(f"[{datetime.now()}] 🔄 A conectar ao Redshift...")
    
    try:
        conexao = psycopg2.connect(
            host=REDSHIFT_HOST,
            port=REDSHIFT_PORT,
            dbname=REDSHIFT_DB,
            user=REDSHIFT_USER,
            password=REDSHIFT_PASSWORD
        )

        # 1. EXTRAÇÃO DO RESUMO REVERSA
        print(f"[{datetime.now()}] 📥 A extrair RESUMO REVERSA...")
        df_resumo = pd.read_sql(QUERY_RESUMO, conexao)

        colunas_taxas = ['taxa_devolucao_aberto', 'taxa_devolucao', 'taxa_devolucao_reprovada', 'taxa_geral_devolucao']
        for col in colunas_taxas:
            if col in df_resumo.columns:
                df_resumo[col] = pd.to_numeric(df_resumo[col], errors='coerce').round(6)

        df_resumo = df_resumo.fillna('')
        print(f"[{datetime.now()}] ✅ Resumo extraído: {len(df_resumo):,} linhas.".replace(",", "."))

        # 2. EXTRAÇÃO DA BASE REVERSA DETALHADA
        print(f"[{datetime.now()}] 📥 A extrair BASE REVERSA...")
        df_base = pd.read_sql(QUERY_BASE, conexao)
        df_base = df_base.astype(str).replace({'None': '', 'nan': '', '<NaT>': ''})
        total_linhas_base = len(df_base)
        print(f"[{datetime.now()}] ✅ Base extraída do Redshift: TOTAL DE {total_linhas_base:,} LINHAS.".replace(",", "."))

        conexao.close()

    except Exception as e:
        print(f"[{datetime.now()}] ❌ Erro no Redshift: {e}")
        return

    # 3. ENVIO DOS DADOS PARA AS 5 PLANILHAS DO GOOGLE SHEETS
    print(f"[{datetime.now()}] 🔄 A conectar ao Google Sheets...")
    caminho_credenciais = os.path.join(os.path.dirname(__file__), "credenciais.json")

    try:
        gc = gspread.service_account(filename=caminho_credenciais)

        # Atualiza o RESUMO REVERSA na planilha principal
        sh_principal = gc.open_by_key(SHEET_PRINCIPAL_ID)
        atualizar_aba_google_sheets(sh_principal, NOME_ABA_RESUMO, df_resumo)

        # Divisão da BASE em blocos de 300.000 linhas
        blocos_base = [
            df_base[i : i + LIMIT_LINHAS_POR_SHEET]
            for i in range(0, total_linhas_base, LIMIT_LINHAS_POR_SHEET)
        ]

        print(f"[{datetime.now()}] 📦 Total de dados divididos em {len(blocos_base)} lote(s).")

        for idx in range(len(PLANILHAS_BASE)):
            info_sheet = PLANILHAS_BASE[idx]
            sheet_id = info_sheet["id"]
            sh_lote = gc.open_by_key(sheet_id)

            if idx < len(blocos_base):
                df_lote = blocos_base[idx]
                print(f"[{datetime.now()}] 🚀 A enviar Lote {idx + 1} ({len(df_lote):,} linhas) para Sheet ID: {sheet_id}...")
                atualizar_aba_google_sheets(sh_lote, NOME_ABA_BASE, df_lote)
                print(f"[{datetime.now()}] ✅ Lote {idx + 1} gravado com sucesso!")
            else:
                print(f"[{datetime.now()}] 🧹 A limpar planilha sobressalente ID: {sheet_id}...")
                try:
                    ws = sh_lote.worksheet(NOME_ABA_BASE)
                    ws.clear()
                except Exception:
                    pass

        print(f"[{datetime.now()}] 🎉 Atualização de todas as planilhas concluída!")

    except Exception as e:
        print(f"[{datetime.now()}] ❌ Erro no Google Sheets: {e}")


if __name__ == "__main__":
    executar_automacao()