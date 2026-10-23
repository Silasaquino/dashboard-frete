import os
import time
import psycopg2
import pandas as pd
import gspread
from datetime import datetime

# ==========================================
# 1. CONFIGURAÇÕES DE CONEXÃO AO REDSHIFT
# ==========================================
REDSHIFT_HOST = "gfg-dwh-prod.dafiti.io"
REDSHIFT_PORT = "5439"
REDSHIFT_DB = "dftdwh"
REDSHIFT_USER = "silasaquino"
REDSHIFT_PASSWORD = "OVpnlp09"

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
# 3. CONSULTAS SQL ORIGINAIS
# ==========================================
QUERY_BASE = """
    SELECT 
        data_solicitacao,
        mes_ano_solicitacao,
        tipo_solicitacao,
        seller_name,
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
        quantidade,
        valor_retorno,
        data_rem,
        data_der,
        data_extravio,
        mes_ano_finalizacao,
        tracking,
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
            SUM(original_item_quantity_order) AS quantidade,
            SUM(reverse_amount) AS valor_retorno,
            rem_date AS data_rem,
            der_date AS data_der,
            status_date_loss AS data_extravio,
            LEFT(COALESCE(rem_date::date, der_date::date, status_date_loss::date), 7) AS mes_ano_finalizacao,
            CASE
                WHEN rem_date IS NOT NULL THEN 'FINALIZADO'
                WHEN der_date IS NOT NULL THEN 'FINALIZADO'
                when src_status = 'return_rejected' THEN 'FINALIZADO'
                WHEN status_date_loss IS NOT NULL THEN 'EXTRAVIO'
                WHEN object_status_description = 'Entregue' THEN 'ENTREGUE AO SELLER'
                WHEN history_status_description = 'Coletado' THEN 'POSTADO/TRANSPORTADOR'
                WHEN type_request_king = 'Insucesso' THEN 'POSTADO/TRANSPORTADOR'
                WHEN history_status_description = 'Prazo de Utilização Expirado' THEN 'REVERSAS EXPIRADAS'
                ELSE 'EM ABERTO'
            END AS tracking,
            CASE
                WHEN (
                    CASE
                        WHEN rem_date IS NOT NULL THEN 'FINALIZADO'
                        WHEN der_date IS NOT NULL THEN 'FINALIZADO'
                        when src_status = 'return_rejected' THEN 'FINALIZADO'
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
        FROM curated_data.a_operation_returns
        WHERE 
          return_order_date >= DATEADD(month, -6, DATE_TRUNC('month', GETDATE()))
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
            src_status
    ) sub
"""

QUERY_RESUMO = """
WITH base AS (
    SELECT 
    	dev.sale_order_store_number as pedido,
    	dev.delivery_type,
        dev.seller_name AS nome_seller,
       CASE 
            WHEN dev.delivery_type = 'MILKRUN' THEN MIN(dev.delivery_collect_number)
            ELSE MIN(dev.delivery_number)
        END AS doc_dft,
        CASE 
            WHEN dev.delivery_type IN ('DAFITI ENVIOS', 'MILKRUN') THEN LEFT(min (dev.paid_date::date), 7)
            ELSE LEFT((CASE 
            WHEN dev.delivery_type = 'MILKRUN' THEN MIN(dev.milkrun_expected_delivery_warehouse_date::date)
            ELSE MIN(dev.customer_expected_delivery_date::date)
        end), 7) 
        END AS mes_ano_definido
    FROM 
        showcase.c_operation_outbound_delivery AS dev
    WHERE 
        dev.delivery_type IN ('DROPSHIPPING', 'DAFITI ENVIOS', 'MILKRUN')
    GROUP BY 
        dev.delivery_type, dev.seller_name, dev.paid_date,dev.delivery_type,dev.sale_order_store_number
    HAVING 
        (CASE 
            WHEN dev.delivery_type IN ('DAFITI ENVIOS', 'MILKRUN') THEN MIN(dev.paid_date)
            ELSE MIN(dev.customer_expected_delivery_date::date)
        END) >= DATEADD(MONTH, -6, DATE_TRUNC('MONTH', CURRENT_DATE))
        
union all 
select
	dev.sale_order_store_number as pedido,
	dev.delivery_type,
     case 
        	when dev.delivery_type = 'RETAIL' then 'LEAP'
        	else dev.seller_name 
        end AS nome_seller,
        MIN(dev.delivery_number) AS doc_dft,
        LEFT(shipped_date::date,7) AS mes_ano_definido
    FROM 
        showcase.c_operation_outbound_delivery AS dev
    WHERE 
        dev.delivery_type IN ('FULFILLMENT', 'RETAIL')
        and item_quantity > 0
    GROUP BY 
        dev.delivery_type, dev.seller_name,shipped_date,dev.delivery_type,dev.sale_order_store_number
    HAVING 
        shipped_date::date >= DATEADD(MONTH, -6, DATE_TRUNC('MONTH', CURRENT_DATE))
),
rev_inv AS (
    SELECT 
        delivery_number,
        delivery_type as tipo_item,
        nome_seller_rev,
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
            end as delivery_type,
             case 
        		when delivery_type = 'RETAIL' then 'LEAP'
        		else seller_name 
        	end AS nome_seller_rev,
            CASE WHEN coalesce (rem_date,bench_date) IS NOT NULL THEN 1 ELSE 0 END AS devolvido,
            CASE WHEN der_date IS NOT NULL THEN 1 ELSE 0 END AS devolucao_reprovada,
            CASE 
                WHEN devolvido = 1 THEN 0
                WHEN devolucao_reprovada = 1 THEN 0
                ELSE 1
            END AS devolucao_em_aberto
        FROM 
            curated_data.a_operation_returns AS rev
        GROUP BY
            delivery_number, rem_date, der_date,seller_name,bench_date,delivery_type
    )
    GROUP BY 
        delivery_number,nome_seller_rev,delivery_type
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
    """Limpa, expande e atualiza uma aba específica em lotes."""
    try:
        worksheet = sh.worksheet(nome_aba)
    except gspread.WorksheetNotFound:
        print(f"[{datetime.now()}] ⚠️ Aba '{nome_aba}' não encontrada. A criar nova aba...")
        worksheet = sh.add_worksheet(title=nome_aba, rows=1000, cols=26)

    print(f"[{datetime.now()}] 🧹 A limpar a aba '{nome_aba}'...")
    worksheet.clear()

    matriz_dados = [df.columns.values.tolist()] + df.values.tolist()
    total_linhas = len(matriz_dados)

    linhas_atuais = worksheet.row_count
    if linhas_atuais < total_linhas:
        linhas_necessarias = total_linhas - linhas_atuais + 500
        print(f"[{datetime.now()}] 📐 A expandir a grelha de '{nome_aba}' em +{linhas_necessarias} linhas...")
        worksheet.add_rows(linhas_necessarias)

    print(f"[{datetime.now()}] 📤 A enviar {total_linhas:,} linhas para a aba '{nome_aba}'...".replace(",", "."))
    for i in range(0, total_linhas, tamanho_lote):
        lote = matriz_dados[i : i + tamanho_lote]
        linha_inicio = i + 1
        linha_fim = i + len(lote)
        
        intervalo = f"A{linha_inicio}"
        worksheet.update(intervalo, lote)
        print(f"[{datetime.now()}]   ✅ Lote '{nome_aba}': linhas {linha_inicio} a {linha_fim} enviadas.")
        time.sleep(1)


def executar_automacao():
    print(f"[{datetime.now()}] 🔄 A iniciar a consulta no Redshift...")
    
    try:
        conexao = psycopg2.connect(
            host=REDSHIFT_HOST,
            port=REDSHIFT_PORT,
            dbname=REDSHIFT_DB,
            user=REDSHIFT_USER,
            password=REDSHIFT_PASSWORD
        )

        # 1. RESUMO REVERSA
        print(f"[{datetime.now()}] 📥 A extrair dados do RESUMO REVERSA...")
        df_resumo = pd.read_sql(QUERY_RESUMO, conexao)

        colunas_taxas = [
            'taxa_devolucao_aberto', 
            'taxa_devolucao', 
            'taxa_devolucao_reprovada', 
            'taxa_geral_devolucao'
        ]

        for col in colunas_taxas:
            if col in df_resumo.columns:
                df_resumo[col] = pd.to_numeric(df_resumo[col], errors='coerce').round(6)

        df_resumo = df_resumo.fillna('')
        print(f"[{datetime.now()}] ✅ Resumo extraído e formatado: {len(df_resumo):,} linhas.".replace(",", "."))

        # 2. BASE REVERSA DETALHADA
        print(f"[{datetime.now()}] 📥 A extrair dados da BASE REVERSA...")
        df_base = pd.read_sql(QUERY_BASE, conexao)
        df_base = df_base.astype(str).replace({'None': '', 'nan': '', '<NaT>': ''})
        total_linhas_base = len(df_base)
        print(f"[{datetime.now()}] ✅ Base extraída: {total_linhas_base:,} linhas.".replace(",", "."))

        conexao.close()

    except Exception as e:
        print(f"[{datetime.now()}] ❌ Erro na consulta ao Redshift: {e}")
        return

    # 3. ENVIO DOS DADOS PARA O GOOGLE SHEETS
    print(f"[{datetime.now()}] 🔄 A conectar à API do Google Sheets...")
    caminho_credenciais = os.path.join(os.path.dirname(__file__), "credenciais.json")

    try:
        gc = gspread.service_account(filename=caminho_credenciais)

        # A) Atualização da aba RESUMO REVERSA na planilha principal
        sh_principal = gc.open_by_key(SHEET_PRINCIPAL_ID)
        atualizar_aba_google_sheets(sh_principal, NOME_ABA_RESUMO, df_resumo)

        # B) Divisão da BASE em lotes de até 300.000 linhas
        blocos_base = [
            df_base[i : i + LIMIT_LINHAS_POR_SHEET]
            for i in range(0, total_linhas_base, LIMIT_LINHAS_POR_SHEET)
        ]

        print(f"[{datetime.now()}] 📦 A base foi dividida em {len(blocos_base)} lote(s) de até {LIMIT_LINHAS_POR_SHEET:,} linhas.".replace(",", "."))

        for idx, df_lote in enumerate(blocos_base):
            if idx < len(PLANILHAS_BASE):
                info_sheet = PLANILHAS_BASE[idx]
                sheet_id = info_sheet["id"]

                print(f"[{datetime.now()}] 🚀 A enviar Lote {idx + 1} ({len(df_lote):,} linhas) para o Sheet ID: {sheet_id}...")
                
                try:
                    sh_lote = gc.open_by_key(sheet_id)
                    atualizar_aba_google_sheets(sh_lote, NOME_ABA_BASE, df_lote)
                    print(f"[{datetime.now()}] ✅ Lote {idx + 1} colado com sucesso!")
                except Exception as err_sheet:
                    print(f"[{datetime.now()}] ❌ Erro ao atualizar o Sheet ID '{sheet_id}': {err_sheet}")
                    print(f"⚠️ Dica: Verifique se o email da Service Account em 'credenciais.json' tem permissão de Editor nesta planilha.")
            else:
                print(f"[{datetime.now()}] ⚠️ Alerta: O total de linhas ({total_linhas_base:,}) excedeu a capacidade das {len(PLANILHAS_BASE)} planilhas de BASE.".replace(",", "."))

        print(f"[{datetime.now()}] 🎉 Sucesso! Processo de atualização do Redshift para o Google Sheets concluído com êxito.")

    except Exception as e:
        print(f"[{datetime.now()}] ❌ Erro ao atualizar o Google Sheets: {e}")


if __name__ == "__main__":
    executar_automacao()