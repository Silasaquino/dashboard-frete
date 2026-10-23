import os
import psycopg2
import pandas as pd
import gspread
from datetime import datetime

# ==========================================
# 1. CONFIGURAÇÕES DE CONEXÃO E PLANILHA
# ==========================================
REDSHIFT_HOST = "gfg-dwh-prod.dafiti.io"
REDSHIFT_PORT = "5439"
REDSHIFT_DB = "dftdwh"
REDSHIFT_USER = "silasaquino"
REDSHIFT_PASSWORD = "OVpnlp09"

SHEET_ID = "1tYkxqGCSan5C7wAjtqKeKpOE2OeGCgrzSynMaXVBaKU"
NOME_ABA_BASE = "BASE"
NOME_ABA_RESUMO = "RESUMO REVERSA"

# ==========================================
# 2. CONSULTAS SQL
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
          delivery_type IN ('MILKRUN', 'DAFITI_ENVIOS', 'DROPSHIPPING')  
          AND return_order_date >= DATEADD(month, -6, DATE_TRUNC('month', GETDATE()))
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
        CASE 
            WHEN dev.delivery_type = 'MILKRUN' THEN MIN(dev.milkrun_expected_delivery_warehouse_date::date)
            ELSE MIN(dev.customer_expected_delivery_date::date)
        END AS promessa_cliente,
        dev.seller_name AS nome_seller,
        dev.sale_order_store_number,
        CASE 
            WHEN dev.delivery_type = 'MILKRUN' THEN MIN(dev.delivery_collect_number)
            ELSE MIN(dev.delivery_number)
        END AS doc_dft,
        dev.sale_order_store_date::date AS data_compra,
        CASE 
            WHEN dev.delivery_type = 'MILKRUN' THEN COALESCE(MIN(dev.milkrun_carrier_delivered_warehouse_date::date), MIN(dev.milkrun_warehouse_received_date::date)) 
            ELSE MIN(dev.delivered_date::date)
        END AS data_entrega,
        CASE 
            WHEN dev.delivery_type = 'MILKRUN' THEN MIN(dev.milkrun_expected_ready_to_collect_date::date) 
            ELSE MIN(dev.shipping_expected_date::date)
        END AS data_limite_de_expedicao,
        CASE 
            WHEN dev.delivery_type = 'MILKRUN' THEN MIN(dev.milkrun_collected_date::date)
            ELSE MIN(dev.shipped_date::date)
        END AS data_expedicao_coleta,
        dev.delivery_type,
        CASE 
            WHEN dev.delivery_type = 'MILKRUN' THEN COUNT(DISTINCT dev.delivery_collect_number)
            ELSE COUNT(DISTINCT dev.delivery_number)
        END AS qtd_doc_dft,
        COALESCE(dev.milkrun_failed_collection_quantity, 0) AS qtd_sva,
        CASE 
            WHEN dev.delivery_type = 'MILKRUN' AND COUNT(DISTINCT dev3.seller_name) > 1 THEN 'CONSOLIDADO'
            ELSE 'PURO'
        END AS tipo,
        dev.paid_date::date AS data_pagamento,
        CASE 
            WHEN dev.delivery_type IN ('DAFITI ENVIOS', 'MILKRUN') THEN LEFT(data_pagamento, 7)
            ELSE LEFT(promessa_cliente, 7) 
        END AS mes_ano_definido
    FROM 
        showcase.c_operation_outbound_delivery AS dev
    LEFT JOIN 
        showcase.c_operation_outbound_delivery AS dev1
        ON dev.delivery_number = dev1.delivery_collect_number AND dev1.delivery_collect_number IS NOT NULL
    LEFT JOIN 
        showcase.c_operation_outbound_delivery AS dev3
        ON dev.sale_order_store_number = dev3.sale_order_store_number AND dev3.delivery_type NOT IN ('DROPSHIPPING', 'DAFITI ENVIOS')
    WHERE 
        dev.delivery_type IN ('DROPSHIPPING', 'DAFITI ENVIOS', 'MILKRUN')
    GROUP BY 
        dev.delivery_type, dev.seller_name, dev.sale_order_store_number, dev.sale_order_store_date, dev.milkrun_failed_collection_quantity, dev.paid_date
    HAVING 
        (CASE 
            WHEN dev.delivery_type IN ('DAFITI ENVIOS', 'MILKRUN') THEN MIN(dev.paid_date)
            ELSE MIN(dev.customer_expected_delivery_date::date)
        END) >= DATEADD(MONTH, -6, DATE_TRUNC('MONTH', CURRENT_DATE))
),
rev_inv AS (
    SELECT 
        delivery_number,
        MAX(devolvido_seller) AS devolvido_seller,
        MAX(devolucao_reprovada) AS devolucao_reprovada,
        MAX(devolucao_em_aberto) AS devolucao_em_aberto
    FROM (
        SELECT 
            delivery_number,
            CASE WHEN rem_date IS NOT NULL THEN 1 ELSE 0 END AS devolvido_seller,
            CASE WHEN der_date IS NOT NULL THEN 1 ELSE 0 END AS devolucao_reprovada,
            CASE 
                WHEN devolvido_seller = 1 THEN 0
                WHEN devolucao_reprovada = 1 THEN 0
                ELSE 1
            END AS devolucao_em_aberto
        FROM 
            curated_data.a_operation_returns AS rev
        WHERE 
            delivery_type IN ('MILKRUN', 'DAFITI_ENVIOS', 'DROPSHIPPING')
        GROUP BY
            delivery_number, rem_date, der_date
    )
    GROUP BY 
        delivery_number
)
SELECT 
    nome_seller,
    mes_ano_definido,
    delivery_type,
    COUNT(doc_dft) AS qtd_etr,
    SUM(devolvido_seller) AS devolvido_seller,
    SUM(devolucao_reprovada) AS devolucao_reprovada,
    SUM(devolucao_em_aberto) AS devolucao_em_aberto,
    SUM(devolvido_seller) + SUM(devolucao_reprovada) + SUM(devolucao_em_aberto) AS total_reversa,
    SUM(devolucao_em_aberto) / COUNT(doc_dft)::double precision AS taxa_devolucao_aberto,
    SUM(devolvido_seller) / COUNT(doc_dft)::double precision AS taxa_devolucao_seller,
    SUM(devolucao_reprovada) / COUNT(doc_dft)::double precision AS taxa_devolucao_reprovada,
    total_reversa / COUNT(doc_dft)::double precision AS taxa_geral_devolucao
FROM 
    base AS b
LEFT JOIN 
    rev_inv AS r
    ON doc_dft = delivery_number
GROUP BY 
    1, 2, 3
HAVING 
    total_reversa > 0;
"""

def atualizar_aba_google_sheets(sh, nome_aba, df, tamanho_lote=10000):
    """Limpa, redimensiona se necessário e atualiza uma aba do Google Sheets em lotes."""
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

    print(f"[{datetime.now()}] 📤 A enviar {total_linhas} linhas para a aba '{nome_aba}'...")
    for i in range(0, total_linhas, tamanho_lote):
        lote = matriz_dados[i : i + tamanho_lote]
        linha_inicio = i + 1
        linha_fim = i + len(lote)
        
        intervalo = f"A{linha_inicio}"
        worksheet.update(intervalo, lote)
        print(f"[{datetime.now()}]   ✅ Lote '{nome_aba}': linhas {linha_inicio} a {linha_fim} enviadas.")

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

        # 1. Extração da BASE REVERSA
        print(f"[{datetime.now()}] 📥 A extrair dados da BASE REVERSA...")
        df_base = pd.read_sql(QUERY_BASE, conexao)
        df_base = df_base.astype(str).replace({'None': '', 'nan': '', '<NaT>': ''})
        print(f"[{datetime.now()}] ✅ Base extraída: {len(df_base)} linhas.")

        # 2. Extração do RESUMO REVERSA
        print(f"[{datetime.now()}] 📥 A extrair dados do RESUMO REVERSA...")
        df_resumo = pd.read_sql(QUERY_RESUMO, conexao)

        # Tratamento das colunas de taxa (mantém como número para o Sheets reconhecer e permitir %):
        colunas_taxas = [
            'taxa_devolucao_aberto', 
            'taxa_devolucao_seller', 
            'taxa_devolucao_reprovada', 
            'taxa_geral_devolucao'
        ]

        for col in colunas_taxas:
            if col in df_resumo.columns:
                df_resumo[col] = pd.to_numeric(df_resumo[col], errors='coerce').round(6)

        df_resumo = df_resumo.fillna('')
        print(f"[{datetime.now()}] ✅ Resumo extraído e formatado: {len(df_resumo)} linhas.")

        conexao.close()

    except Exception as e:
        print(f"[{datetime.now()}] ❌ Erro na consulta ao Redshift: {e}")
        return

    print(f"[{datetime.now()}] 🔄 A conectar ao Google Sheets...")
    caminho_credenciais = os.path.join(os.path.dirname(__file__), "credenciais.json")

    try:
        gc = gspread.service_account(filename=caminho_credenciais)
        sh = gc.open_by_key(SHEET_ID)

        # Atualiza a aba BASE
        atualizar_aba_google_sheets(sh, NOME_ABA_BASE, df_base)

        # Atualiza a aba RESUMO REVERSA
        atualizar_aba_google_sheets(sh, NOME_ABA_RESUMO, df_resumo)

        print(f"[{datetime.now()}] 🎉 Sucesso! Ambas as abas ('{NOME_ABA_BASE}' e '{NOME_ABA_RESUMO}') foram atualizadas no Google Sheets.")

    except Exception as e:
        print(f"[{datetime.now()}] ❌ Erro ao atualizar o Google Sheets: {e}")

if __name__ == "__main__":
    executar_automacao()