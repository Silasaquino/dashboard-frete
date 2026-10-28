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
# Planilha Principal (Exclusiva para os RESUMOS)
SHEET_PRINCIPAL_ID = "13R19Vg06Z-E10wKdDl7gqtdKM7KdNeI7unutsVZXrNY"

NOME_ABA_RESUMO_EXPEDICAO = "RESUMO VENDAS_EXPEDIÇÃO"
NOME_ABA_RESUMO_CAF = "RESUMO_CAF"
NOME_ABA_RESUMO_ENTREGAS = "RESUMO_ENTREGAS"
NOME_ABA_RESUMO_PREJUDICADO = "RESUMO_PREJUDICADO"
NOME_ABA_RESUMO_SVA = "RESUMO_SVA"
NOME_ABA_RESUMO_TRACKING = "RESUMO_TRACKING"
NOME_ABA_RESUMO_STATUS_LOJA = "RESUMO_STATUS_LOJA"
NOME_ABA_RESUMO_RCC = "RESUMO_RCC"
NOME_ABA_RESUMO_CAN = "RESUMO_CAN"

# Planilhas Externas Dedicadas (Exclusivas para a BASE detalhada particionada)
NOME_ABA_BASE = "BASE"
PLANILHAS_BASE = [
    {"id": "1VarO61GI5asiRDlaw81Dztx4rRINySnk1KgsBCzPgkI", "gid": "0"},          # Parte 1 (Lote 1: até 300k)
    {"id": "1Cl9MSMrVaMci_mJ-u62NFnc2NWanl-86M8PJI-2bWyU", "gid": "0"},          # Parte 2 (Lote 2: até 600k)
    {"id": "1jGZv0ATiJvCOfmsODT3JPGkpdA18XkmlP60WH_uUCK8", "gid": "0"},          # Parte 3 (Lote 3: até 900k)
    {"id": "1khs25N1XevKrSdBun0w0MIXNpY1kx2KiK4UdK0uchdM", "gid": "0"},          # Parte 4 (Lote 4: até 1.2M)
    {"id": "1NiYyktZdtggxFsDunvazt4Fysmf7dQS2SvkNQldiUc0", "gid": "0"}           # Parte 5 (Lote 5: até 1.5M)
]

LIMIT_LINHAS_POR_SHEET = 300000

# ==========================================
# 3. CONSULTAS SQL
# ==========================================
QUERY_BASE = """
    with base as (
select 
	case 
		when dev.delivery_type = 'MILKRUN' then min (dev.milkrun_expected_delivery_warehouse_date::date)
		else min (dev.customer_expected_delivery_date::date)
	end as promessa_cliente,
	dev.seller_name as nome_seller,
	dev.sale_order_store_number,
	case 
		when dev.delivery_type = 'MILKRUN' then min (dev.delivery_collect_number)
		else min (dev.delivery_number)
	end as doc_dft,
	dev.sale_order_store_date::date as data_compra,
	case 
		when dev.delivery_type = 'MILKRUN' then coalesce (min (dev.milkrun_carrier_delivered_warehouse_date::date),min (dev.milkrun_warehouse_received_date::date)) 
		else min (dev.delivered_date::date)
	end as data_entrega,
	case 
		when dev.delivery_type = 'MILKRUN' then min (dev.milkrun_expected_ready_to_collect_date::date) 
		else min (dev.shipping_expected_date::date )
	end as data_limite_de_expedicao,
	case 
		when dev.delivery_type = 'MILKRUN' then min(dev.milkrun_collected_date::date)
		else min (dev.shipped_date::date)
	end as data_expedicao_coleta,
	dev.delivery_type,
	case 
		when dev.delivery_type = 'MILKRUN' then count (distinct dev.delivery_collect_number)
		else count (distinct dev.delivery_number)
	end as qtd_doc_dft,
	coalesce (dev.milkrun_failed_collection_quantity,0) as qtd_sva,
	case 
		when dev.delivery_type = 'MILKRUN' and count (distinct dev3.seller_name) > 1 then 'CONSOLIDADO'
		else 'PURO'
	end as tipo,
	dev.paid_date::date as data_pagamento,
	case 
		when dev.delivery_type in ('DAFITI ENVIOS','MILKRUN') then left (data_pagamento,7)
		else left (promessa_cliente,7) 
	end as mes_ano_definido
from 
	showcase.c_operation_outbound_delivery  as dev
left join 
	showcase.c_operation_outbound_delivery  as dev3
	on dev.sale_order_store_number = dev3.sale_order_store_number and dev3.delivery_type not in ('DROPSHIPPING','DAFITI ENVIOS')
where 
	dev.delivery_type in ('DROPSHIPPING','DAFITI ENVIOS','MILKRUN')
group by 
	dev.delivery_type,dev.seller_name,dev.sale_order_store_number,dev.sale_order_store_date,dev.milkrun_failed_collection_quantity,dev.paid_date
 having
 (CASE 
            WHEN dev.delivery_type IN ('DAFITI ENVIOS', 'MILKRUN') THEN MIN(dev.paid_date)
            ELSE MIN(dev.customer_expected_delivery_date::date)
        END) >= DATEADD(MONTH, -6, DATE_TRUNC('MONTH', CURRENT_DATE))

)
,
valor_prej as (
select 
doc_dft,
sum (paid_price) valor_prej
from (
select 
doc_dft,
material,
paid_price
from 
	base as dev
left join 
	showcase.c_operation_outbound_delivery  as dev1
	on doc_dft = (case 
		when dev1.delivery_type = 'MILKRUN' then dev1.delivery_collect_number
		else dev1.delivery_number end) 

where 
	(case 
		when dev1.is_canceled = 1 then 'CAN'
		when dev1.delivery_type = 'MILKRUN' then dev1.milkrun_last_status  
		else dev1.last_status_code
	end) in ('CAN','RCC','CAF')
group by 
	1,2,3
)
group by 
	1
)
,
Ultimo_ponto as (select 
dev.delivery_type,
dev.seller_name as nome_seller,
b.doc_dft as dft,
count (distinct case 
		when dev.delivery_type = 'MILKRUN' then dev.milkrun_last_status  
		else dev.last_status_code
	end) as qtd_pontos,
first_value(dev1.milkrun_last_status) OVER (PARTITION BY dev1.delivery_type,dev1.seller_name,dev1.delivery_collect_number ORDER BY dev1.milkrun_last_status_date desc rows between unbounded preceding and unbounded following) as ultimo_ponto_coleta,
first_value(dev2.last_status_code) OVER (PARTITION BY dev2.delivery_type,dev2.seller_name,dev2.delivery_number ORDER BY dev2.last_status_date desc rows between unbounded preceding and unbounded following) as ultimo_ponto_mkt,
count (distinct dev.is_canceled) as qtd_cancelada,
max (dev.is_canceled) as is_canceled

from 
	base as b
left join
	showcase.c_operation_outbound_delivery  as dev
	on dev.delivery_type = b.delivery_type and dev.seller_name = b.nome_seller and 	(case 
		when dev.delivery_type = 'MILKRUN' then dev.delivery_collect_number
		else dev.delivery_number
	end) = b.doc_dft
left join 
	showcase.c_operation_outbound_delivery  as dev1
	on b.delivery_type = dev1.delivery_type and  b.nome_seller = dev1.seller_name and b.doc_dft = dev1.delivery_collect_number
	and dev1.delivery_type in ('MILKRUN') and dev1.milkrun_last_status_date is not null
left join 
	showcase.c_operation_outbound_delivery  as dev2
	on b.delivery_type = dev2.delivery_type and  b.nome_seller = dev2.seller_name and b.doc_dft = dev2.delivery_number
	and dev2.delivery_type in ('DROPSHIPPING','DAFITI ENVIOS')
where 
	dev.delivery_type in ('DROPSHIPPING','DAFITI ENVIOS','MILKRUN')
	group by dev.delivery_type,dev.seller_name,b.doc_dft,dev1.milkrun_last_status,dev1.delivery_type,dev1.seller_name,dev1.delivery_collect_number,dev1.milkrun_last_status_date,
	dev2.last_status_code,dev2.delivery_type,dev2.seller_name,dev2.delivery_number,dev2.last_status_date
)

select 
*

from (
select 
	b.tipo,
	data_pagamento,
	mes_ano_definido,
	b.promessa_cliente,
	left (b.promessa_cliente,7) as mes_ano_prom_cliente,
	b.nome_seller,
	b.sale_order_store_number,
	b.doc_dft,
	b.data_compra,
	b.data_limite_de_expedicao,
	left (b.data_limite_de_expedicao,7) as mes_ano_dl,
	b.data_expedicao_coleta,
	left (b.data_expedicao_coleta,7) as mes_ano_exp,
	b.data_entrega,
	left (b.data_entrega,7) as mes_ano_entrega,
	b.delivery_type,
	coalesce (ultimo_ponto_coleta,ultimo_ponto_mkt) as ultimo_ponto,
	case 
		when qtd_pontos = 1 and ultimo_ponto = 'TNA' then 'TRANSPORTADOR NÃO ATRIBUIDO' 
		when qtd_pontos = 1 and ultimo_ponto in ('CAN','CAA','SOC') and data_entrega is null then 'CANCELAMENTO_SAC_CLIENTE'
		when qtd_pontos = 1 and ultimo_ponto = 'AOT' and data_entrega is null then 'ITEM_CANCELAMENTO_EXTRAVIO'
		when qtd_pontos = 1 and ultimo_ponto = 'RCC' and data_entrega is null then 'ITEM_CANCELAMENTO_COLETA'
		when qtd_pontos = 1 and ultimo_ponto = 'CAF' and data_entrega is null then 'ITEM_CANCELAMENTO_SELLER'
		when qtd_pontos = 1 and ultimo_ponto in ('REM','RIE','DEV') and data_entrega is null then 'DEVOLVIDO_SELLER'
		when qtd_pontos = 1 and ultimo_ponto in ('POS') and data_entrega is null then 'DEVOLUÇÃO_EM_ABERTO'
		when qtd_pontos = 1 and ultimo_ponto in ('PEP','AVA','TEX','EXC','ROU','TRO','TAV') and data_entrega is null then 'EXTRAVIOS'
		when qtd_cancelada = 1 and u.is_canceled = 1 and data_entrega is null then 'CANCELAMENTO_SAC_CLIENTE' 
		when data_entrega is not null and promessa_cliente >= data_entrega then 'ENTREGAS_PRAZO'
		when data_entrega is not null and promessa_cliente < data_entrega then 'ENTREGAS_ATRASO'
		when min (dev.shipped_date) is not null then 'EXPEDIÇÃO_SEM_ANP'
		when data_entrega is null and data_limite_de_expedicao < data_expedicao_coleta then 'ENVIOS_ATRASO'
		when data_entrega is null and data_limite_de_expedicao >= data_expedicao_coleta then 'ENVIOS_PRAZO'
		when data_expedicao_coleta is null and data_limite_de_expedicao < CURRENT_DATE  then 'EM_ABERTO_ATRASO'
		when data_expedicao_coleta is null and data_limite_de_expedicao = CURRENT_DATE  then 'EM_ABERTO_HOJE'
		when data_expedicao_coleta is null and data_limite_de_expedicao > CURRENT_DATE  then 'EM_ABERTO_PRAZO'
		else 'Validar'
	end as status_pedido,
	case 
		when status_pedido in ('EM_ABERTO_ATRASO') then CURRENT_DATE - b.data_limite_de_expedicao
	else 0
	end as dias_em_atraso,
	case 
		when dias_em_atraso <= 0 then '0'
		when dias_em_atraso = 1 then '1'
		when dias_em_atraso = 2 then '2'
		when dias_em_atraso = 3 then '3'
		when dias_em_atraso = 4 then '4'
		when dias_em_atraso = 5 then '5'
		when dias_em_atraso = 6 then '6'
		when dias_em_atraso = 7 then '7'
		when dias_em_atraso = 8 then '8'
		when dias_em_atraso = 9 then '9'
		when dias_em_atraso = 10 then '10'
		when dias_em_atraso = 11 then '11'
		when dias_em_atraso = 12 then '12'
		when dias_em_atraso = 13 then '13'
		when dias_em_atraso = 14 then '14'
		when dias_em_atraso = 15 then '15'
	else '15+'
	end as grupo_dias_em_atraso,	
	qtd_sva,
	count (b.doc_dft) over (partitiON by  b.sale_order_store_number,b.nome_seller,b.delivery_type) as qtd,
	qtd_doc_dft,
	case 
		when data_expedicao_coleta is null then 'SEM_EXPEDIÇAO'
		when data_expedicao_coleta::date <= data_limite_de_expedicao::date then 'EXPEDIÇÃO_NO_PRAZO'
		when data_expedicao_coleta::date > data_limite_de_expedicao::date then 'EXPEDIÇÃO_FORA_PRAZO'
	end as status_expedicao,
	case 
		when data_entrega is null then 'SEM_ENTREGA'
		when data_entrega::date <= promessa_cliente::date then 'ENTREGA_NO_PRAZO'
		when data_entrega::date > promessa_cliente::date  then 'ENTREGA_FORA_PRAZO'
	end as status_entrega,
	valor_prej

from 
	base as b
left join 
	Ultimo_ponto as u
	on b.doc_dft = u.dft and b.nome_seller = u.nome_seller and b.delivery_type = u.delivery_type
left join 
	showcase.c_operation_outbound_delivery as dev 
	on b.doc_dft = dev.delivery_collect_number and dev.delivery_collect_number is not null and dev.shipped_date is not null and dev.item_quantity > 0 and dev.delivery_type = 'MILKRUN'
left join 
	valor_prej as vp
	on b.doc_dft = vp.doc_dft

group by 
	b.tipo,b.promessa_cliente,b.nome_seller,b.sale_order_store_number,b.doc_dft,b.data_compra,b.data_limite_de_expedicao,b.data_expedicao_coleta,data_pagamento,
	mes_ano_definido,b.data_entrega,b.delivery_type,ultimo_ponto_coleta,ultimo_ponto_mkt,u.qtd_pontos,qtd_doc_dft,qtd_cancelada,u.is_canceled,qtd_sva,valor_prej
	)
where status_pedido like 'EM_ABERTO%'
"""

QUERY_RESUMO_EXPEDICAO = """
with base as (
select 
	case 
		when dev.delivery_type = 'MILKRUN' then min (dev.milkrun_expected_delivery_warehouse_date::date)
		else min (dev.customer_expected_delivery_date::date)
	end as promessa_cliente,
	left (promessa_cliente,7) as mes_ano_prom_cliente,
	dev.seller_name as nome_seller,
	dev.sale_order_store_number,
	case 
		when dev.delivery_type = 'MILKRUN' then min (dev.delivery_collect_number)
		else min (dev.delivery_number)
	end as doc_dft,
	dev.sale_order_store_date::date as data_compra,
	case 
		when dev.delivery_type = 'MILKRUN' then coalesce (min (dev.milkrun_carrier_delivered_warehouse_date::date),min (dev.milkrun_warehouse_received_date::date)) 
		else min (dev.delivered_date::date)
	end as data_entrega,
	case 
		when dev.delivery_type = 'MILKRUN' then min (dev.milkrun_expected_ready_to_collect_date::date) 
		else min (dev.shipping_expected_date::date )
	end as data_limite_de_expedicao,
	case 
		when dev.delivery_type = 'MILKRUN' then min(dev.milkrun_collected_date::date)
		else min (dev.shipped_date::date)
	end as data_expedicao_coleta,
	dev.delivery_type,
	case 
		when dev.delivery_type = 'MILKRUN' then count (distinct dev.delivery_collect_number)
		else count (distinct dev.delivery_number)
	end as qtd_doc_dft,
	coalesce (dev.milkrun_failed_collection_quantity,0) as qtd_sva,
	case 
		when dev.delivery_type = 'MILKRUN' and count (distinct dev3.seller_name) > 1 then 'CONSOLIDADO'
		else 'PURO'
	end as tipo,
	case 
		when  data_expedicao_coleta <= data_limite_de_expedicao  then 1
		else 0
	end as expedição_prazo,
	case 
		when data_expedicao_coleta > data_limite_de_expedicao then 1
		else 0
	end as expedição_atraso,
	dev.paid_date::date as data_pagamento,
	case 
		when dev.delivery_type in ('DAFITI ENVIOS','MILKRUN') then left (data_pagamento,7)
		else left (promessa_cliente,7) 
	end as mes_ano_definido
	
from 
	showcase.c_operation_outbound_delivery  as dev
left join 
	showcase.c_operation_outbound_delivery  as dev3
	on dev.sale_order_store_number = dev3.sale_order_store_number and dev3.delivery_type not in ('DROPSHIPPING','DAFITI ENVIOS')
where 
	dev.delivery_type in ('DROPSHIPPING','DAFITI ENVIOS','MILKRUN')
group by 
	dev.delivery_type,dev.seller_name,dev.sale_order_store_number,dev.sale_order_store_date,dev.milkrun_failed_collection_quantity,dev.paid_date
having 
	(case 
		when dev.delivery_type in ('DAFITI ENVIOS','MILKRUN') then min (dev.paid_date)
		else min (dev.customer_expected_delivery_date::date)
	end ) >= DATEADD(MONTH, -6, DATE_TRUNC('MONTH', CURRENT_DATE))
	and (case 
		when dev.delivery_type = 'MILKRUN' then min(dev.milkrun_collected_date::date)
		else min (dev.shipped_date::date)
	end) is not null

)

select 

nome_seller,
delivery_type,
mes_ano_definido,
sum (expedição_prazo) as expedicao_no_prazo,
sum (expedição_atraso) as expedicao_fora_prazo,
expedicao_no_prazo/count (doc_dft)::double precision as taxa_expedicao_no_prazo,
expedicao_fora_prazo/count (doc_dft)::double precision as taxa_expedicao_fora_prazo,
count (distinct doc_dft) as total

from 
	base
group by 
	1,2,3
"""

QUERY_RESUMO_CAF = """
SELECT 
    nome_seller,
    mes_ano_compra,
    delivery_type,
    SUM(qtds) AS qtd,
    SUM(cafs) AS caf,
    CASE 
        WHEN SUM(qtds) > 0 THEN (SUM(cafs)::double precision / SUM(qtds)::double precision)
        ELSE 0.0 
    END AS taxa_cancelamento
FROM (
    SELECT 
        dev.seller_name AS nome_seller,
        LEFT(dev.sale_order_store_date::date, 7) AS mes_ano_compra,
        dev.delivery_type,
        COALESCE(dev.original_item_quantity, 1) AS qtds,
        CASE 
            WHEN dev.caf_status_date IS NOT NULL OR dev.last_status_code = 'CAF' THEN COALESCE(dev.original_item_quantity, 1)
            ELSE 0 
        END AS cafs
    FROM 
        showcase.c_operation_outbound_delivery AS dev
    WHERE 
        dev.delivery_type IN ('DROPSHIPPING', 'DAFITI ENVIOS', 'MILKRUN')
        AND dev.sale_order_store_date::date >= DATEADD(MONTH, -6, DATE_TRUNC('MONTH', CURRENT_DATE))
) AS base_caf
GROUP BY 
    1, 2, 3
HAVING 
    SUM(cafs) > 0
"""

QUERY_RESUMO_ENTREGAS = """
with base as (
select 
	case 
		when dev.delivery_type = 'MILKRUN' then min (dev.milkrun_expected_delivery_warehouse_date::date)
		else min (dev.customer_expected_delivery_date::date)
	end as promessa_cliente,
	left (promessa_cliente,7) as mes_ano_prom_cliente,
	dev.seller_name as nome_seller,
	dev.sale_order_store_number,
	case 
		when dev.delivery_type = 'MILKRUN' then min (dev.delivery_collect_number)
		else min (dev.delivery_number)
	end as doc_dft,
	dev.sale_order_store_date::date as data_compra,
	case 
		when dev.delivery_type = 'MILKRUN' then coalesce (min (dev.milkrun_carrier_delivered_warehouse_date::date),min (dev.milkrun_warehouse_received_date::date)) 
		else min (dev.delivered_date::date)
	end as data_entrega,
	case 
		when dev.delivery_type = 'MILKRUN' then min (dev.milkrun_expected_ready_to_collect_date::date) 
		else min (dev.shipping_expected_date::date )
	end as data_limite_de_expedicao,
	case 
		when dev.delivery_type = 'MILKRUN' then min(dev.milkrun_collected_date::date)
		else min (dev.shipped_date::date)
	end as data_expedicao_coleta,
	dev.delivery_type,
	case 
		when dev.delivery_type = 'MILKRUN' then count (distinct dev.delivery_collect_number)
		else count (distinct dev.delivery_number)
	end as qtd_doc_dft,
	coalesce (dev.milkrun_failed_collection_quantity,0) as qtd_sva,
	case 
		when dev.delivery_type = 'MILKRUN' and count (distinct dev3.seller_name) > 1 then 'CONSOLIDADO'
		else 'PURO'
	end as tipo,
	case 
		when promessa_cliente >= data_entrega then 1
		else 0
	end as entregas_prazo,
	case 
		when promessa_cliente < data_entrega then 1
		else 0
	end as entregas_atraso,
	dev.paid_date::date as data_pagamento,
	case 
		when dev.delivery_type in ('DAFITI ENVIOS','MILKRUN') then left (data_pagamento,7)
		else left (promessa_cliente,7) 
	end as mes_ano_definido
	
from 
	showcase.c_operation_outbound_delivery  as dev
left join 
	showcase.c_operation_outbound_delivery  as dev3
	on dev.sale_order_store_number = dev3.sale_order_store_number and dev3.delivery_type not in ('DROPSHIPPING','DAFITI ENVIOS')
where 
	dev.delivery_type in ('DROPSHIPPING','DAFITI ENVIOS','MILKRUN')
group by 
	dev.delivery_type,dev.seller_name,dev.sale_order_store_number,dev.sale_order_store_date,dev.milkrun_failed_collection_quantity,dev.paid_date
having 
	(case 
		when dev.delivery_type in ('DAFITI ENVIOS','MILKRUN') then min (dev.paid_date)
		else min (dev.customer_expected_delivery_date::date)
	end ) >= DATEADD(MONTH, -6, DATE_TRUNC('MONTH', CURRENT_DATE))
	and (case 
		when dev.delivery_type = 'MILKRUN' then coalesce (min (dev.milkrun_carrier_delivered_warehouse_date::date),min (dev.milkrun_warehouse_received_date::date)) 
		else min (dev.delivered_date::date)
	end) is not null
)

select 

nome_seller,
delivery_type,
mes_ano_definido,
sum (entregas_prazo) as entrega_no_prazo,
sum (entregas_atraso) as entrega_fora_prazo,
entrega_no_prazo/count (distinct doc_dft)::double precision as taxa_entrega_prazo,
entrega_fora_prazo/count (distinct doc_dft)::double precision as taxa_entrega_fora_prazo,
count (distinct doc_dft) as total

from 
	base
group by 
	1,2,3
"""

QUERY_RESUMO_PREJUDICADO = """
with base as (
select 
	case 
		when dev.delivery_type = 'MILKRUN' then min (dev.milkrun_expected_delivery_warehouse_date::date)
		else min (dev.customer_expected_delivery_date::date)
	end as promessa_cliente,
	left (promessa_cliente,7) as mes_ano_prom_cliente,
	dev.seller_name as nome_seller,
	dev.sale_order_store_number,
	case 
		when dev.delivery_type = 'MILKRUN' then min (dev.delivery_collect_number)
		else min (dev.delivery_number)
	end as doc_dft,
	dev.sale_order_store_date::date as data_compra,
	case 
		when dev.delivery_type = 'MILKRUN' then coalesce (min (dev.milkrun_carrier_delivered_warehouse_date::date),min (dev.milkrun_warehouse_received_date::date)) 
		else min (dev.delivered_date::date)
	end as data_entrega,
	case 
		when dev.delivery_type = 'MILKRUN' then min (dev.milkrun_expected_ready_to_collect_date::date) 
		else min (dev.shipping_expected_date::date )
	end as data_limite_de_expedicao,
	case 
		when dev.delivery_type = 'MILKRUN' then min(dev.milkrun_collected_date::date)
		else min (dev.shipped_date::date)
	end as data_expedicao_coleta,
	dev.delivery_type,
	case 
		when dev.delivery_type = 'MILKRUN' then count (distinct dev.delivery_collect_number)
		else count (distinct dev.delivery_number)
	end as qtd_doc_dft,
	coalesce (dev.milkrun_failed_collection_quantity,0) as qtd_sva,
	case 
		when dev.delivery_type = 'MILKRUN' and count (distinct dev3.seller_name) > 1 then 'CONSOLIDADO'
		else 'PURO'
	end as tipo,
	case 
		when promessa_cliente >= data_entrega then 1
		else 0
	end as entregas_prazo,
	case 
		when promessa_cliente < data_entrega then 1
		else 0
	end as entregas_atraso,
	dev.material,
	dev.paid_price,
	dev.paid_date::date as data_pagamento,
	case 
		when dev.delivery_type in ('DAFITI ENVIOS','MILKRUN') then left (data_pagamento,7)
		else left (promessa_cliente,7) 
	end as mes_ano_definido
	
from 
	showcase.c_operation_outbound_delivery  as dev
left join 
	showcase.c_operation_outbound_delivery  as dev3
	on dev.sale_order_store_number = dev3.sale_order_store_number and dev3.delivery_type not in ('DROPSHIPPING','DAFITI ENVIOS')
where 
	dev.delivery_type in ('DROPSHIPPING','DAFITI ENVIOS','MILKRUN')
	and (case 
		when dev.is_canceled = 1 then 'CAN'
		when dev.delivery_type = 'MILKRUN' then dev.milkrun_last_status  
		else dev.last_status_code
	end) in ('CAN','RCC','CAF')
group by 
	dev.delivery_type,dev.seller_name,dev.sale_order_store_number,dev.sale_order_store_date,dev.milkrun_failed_collection_quantity,dev.material,dev.paid_price,dev.paid_date
having 
	(case 
		when dev.delivery_type in ('DAFITI ENVIOS','MILKRUN') then min (dev.paid_date)
		else min (dev.customer_expected_delivery_date::date)
	end ) >= DATEADD(MONTH, -6, DATE_TRUNC('MONTH', CURRENT_DATE))
)

select 

nome_seller,
delivery_type,
mes_ano_definido,
sum (paid_price) as valor_prej
from 
	base
group by 
	1,2,3
"""

QUERY_RESUMO_SVA = """
with base as (
select 
    case 
        when dev.delivery_type = 'MILKRUN' then min (dev.milkrun_expected_delivery_warehouse_date::date)
        else min (dev.customer_expected_delivery_date::date)
    end as promessa_cliente,
    left (promessa_cliente,7) as mes_ano_prom_cliente,
    dev.seller_name as nome_seller,
    dev.sale_order_store_number,
    case 
        when dev.delivery_type = 'MILKRUN' then min (dev.delivery_collect_number)
        else min (dev.delivery_number)
    end as doc_dft,
    dev.sale_order_store_date::date as data_compra,
    case 
        when dev.delivery_type = 'MILKRUN' then coalesce (min (dev.milkrun_carrier_delivered_warehouse_date::date),min (dev.milkrun_warehouse_received_date::date)) 
        else min (dev.delivered_date::date)
    end as data_entrega,
    case 
        when dev.delivery_type = 'MILKRUN' then min (dev.milkrun_expected_ready_to_collect_date::date) 
        else min (dev.shipping_expected_date::date )
    end as data_limite_de_expedicao,
    case 
        when dev.delivery_type = 'MILKRUN' then min(dev.milkrun_collected_date::date)
        else min (dev.shipped_date::date)
    end as data_expedicao_coleta,
    dev.delivery_type,
    case 
        when dev.delivery_type = 'MILKRUN' then count (distinct dev.delivery_collect_number)
        else count (distinct dev.delivery_number)
    end as qtd_doc_dft,
    dev.milkrun_failed_collection_quantity as qtd_sva,
    case 
        when dev.delivery_type = 'MILKRUN' and count (distinct dev3.seller_name) > 1 then 'CONSOLIDADO'
        else 'PURO'
    end as tipo,
    dev.paid_date::date as data_pagamento,
	case 
		when dev.delivery_type in ('DAFITI ENVIOS','MILKRUN') then left (data_pagamento,7)
		else left (promessa_cliente,7) 
	end as mes_ano_definido

from 
    showcase.c_operation_outbound_delivery  as dev
left join 
    showcase.c_operation_outbound_delivery  as dev3
    on dev.sale_order_store_number = dev3.sale_order_store_number and dev3.delivery_type not in ('DROPSHIPPING','DAFITI ENVIOS')
where 
    dev.delivery_type in ('DROPSHIPPING','DAFITI ENVIOS','MILKRUN')
     and dev.milkrun_failed_collection_quantity > 0
group by 
    dev.delivery_type,dev.seller_name,dev.sale_order_store_number,dev.sale_order_store_date,dev.milkrun_failed_collection_quantity,dev.paid_date
having 
	(case 
		when dev.delivery_type in ('DAFITI ENVIOS','MILKRUN') then min (dev.paid_date)
		else min (dev.customer_expected_delivery_date::date)
	end ) >= DATEADD(MONTH, -6, DATE_TRUNC('MONTH', CURRENT_DATE))
)

select 

nome_seller,
delivery_type,
mes_ano_definido,
count (distinct doc_dft) as qtd_sva

from 
    base
group by 
    1,2,3
"""

QUERY_RESUMO_TRACKING = """
with base as (
select 
    case 
        when dev.delivery_type = 'MILKRUN' then min (dev.milkrun_expected_delivery_warehouse_date::date)
        else min (dev.customer_expected_delivery_date::date)
    end as promessa_cliente,
    dev.seller_name as nome_seller,
    dev.sale_order_store_number,
    case 
        when dev.delivery_type = 'MILKRUN' then min (dev.delivery_collect_number)
        else min (dev.delivery_number)
    end as doc_dft,
    dev.sale_order_store_date::date as data_compra,
    case 
        when dev.delivery_type = 'MILKRUN' then coalesce (min (dev.milkrun_carrier_delivered_warehouse_date::date),min (dev.milkrun_warehouse_received_date::date)) 
        else min (dev.delivered_date::date)
    end as data_entrega,
    case 
        when dev.delivery_type = 'MILKRUN' then min (dev.milkrun_expected_ready_to_collect_date::date) 
        else min (dev.shipping_expected_date::date )
    end as data_limite_de_expedicao,
    case 
        when dev.delivery_type = 'MILKRUN' then min(dev.milkrun_collected_date::date)
        else min (dev.shipped_date::date)
    end as data_expedicao_coleta,
    dev.delivery_type,
    case 
        when dev.delivery_type = 'MILKRUN' then count (distinct dev.delivery_collect_number)
        else count (distinct dev.delivery_number)
    end as qtd_doc_dft,
    coalesce (dev.milkrun_failed_collection_quantity,0) as qtd_sva,
    case 
        when dev.delivery_type = 'MILKRUN' and count (distinct dev3.seller_name) > 1 then 'CONSOLIDADO'
        else 'PURO'
    end as tipo,
    dev.paid_date::date as data_pagamento,
	case 
		when dev.delivery_type in ('DAFITI ENVIOS','MILKRUN') then left (data_pagamento,7)
		else left (promessa_cliente,7) 
	end as mes_ano_definido
from 
    showcase.c_operation_outbound_delivery  as dev
left join 
    showcase.c_operation_outbound_delivery  as dev3
    on dev.sale_order_store_number = dev3.sale_order_store_number and dev3.delivery_type not in ('DROPSHIPPING','DAFITI ENVIOS')
where 
    dev.delivery_type in ('MILKRUN')
group by 
    dev.delivery_type,dev.seller_name,dev.sale_order_store_number,dev.sale_order_store_date,dev.milkrun_failed_collection_quantity,dev.paid_date
having 
	(case 
		when dev.delivery_type in ('DAFITI ENVIOS','MILKRUN') then min (dev.paid_date)
		else min (dev.customer_expected_delivery_date::date)
	end ) >= DATEADD(MONTH, -6, DATE_TRUNC('MONTH', CURRENT_DATE))

)
,
valor_prej as (
select 
doc_dft,
sum (paid_price) valor_prej
from (
select 
doc_dft,
material,
paid_price
from 
    base as dev
left join 
    showcase.c_operation_outbound_delivery  as dev1
    on doc_dft = (case 
        when dev1.delivery_type = 'MILKRUN' then dev1.delivery_collect_number
        else dev1.delivery_number end) 

where 
    (case 
        when dev1.is_canceled = 1 then 'CAN'
        when dev1.delivery_type = 'MILKRUN' then dev1.milkrun_last_status  
        else dev1.last_status_code
    end) in ('CAN','RCC','CAF')
group by 
    1,2,3
)
group by 
    1
)
,
Ultimo_ponto as (
select 
dev.delivery_type,
dev.seller_name as nome_seller,
b.doc_dft as dft,
count (distinct case 
		when dev.delivery_type = 'MILKRUN' then dev.milkrun_last_status  
		else dev.last_status_code
	end) as qtd_pontos,
first_value(dev1.milkrun_last_status) OVER (PARTITION BY dev1.delivery_type,dev1.seller_name,dev1.delivery_collect_number ORDER BY dev1.milkrun_last_status_date desc rows between unbounded preceding and unbounded following) as ultimo_ponto_coleta,
first_value(dev2.last_status_code) OVER (PARTITION BY dev2.delivery_type,dev2.seller_name,dev2.delivery_number ORDER BY dev2.last_status_date desc rows between unbounded preceding and unbounded following) as ultimo_ponto_mkt,
count (distinct dev.is_canceled) as qtd_cancelada,
max (dev.is_canceled) as is_canceled

from 
	base as b
left join
	showcase.c_operation_outbound_delivery  as dev
	on dev.delivery_type = b.delivery_type and dev.seller_name = b.nome_seller and 	(case 
		when dev.delivery_type = 'MILKRUN' then dev.delivery_collect_number
		else dev.delivery_number
	end) = b.doc_dft
left join 
	showcase.c_operation_outbound_delivery  as dev1
	on b.delivery_type = dev1.delivery_type and  b.nome_seller = dev1.seller_name and b.doc_dft = dev1.delivery_collect_number
	and dev1.delivery_type in ('MILKRUN') and dev1.milkrun_last_status_date is not null
left join 
	showcase.c_operation_outbound_delivery  as dev2
	on b.delivery_type = dev2.delivery_type and  b.nome_seller = dev2.seller_name and b.doc_dft = dev2.delivery_number
	and dev2.delivery_type in ('DROPSHIPPING','DAFITI ENVIOS')
where 
	dev.delivery_type in ('DROPSHIPPING','DAFITI ENVIOS','MILKRUN')
	group by dev.delivery_type,dev.seller_name,b.doc_dft,dev1.milkrun_last_status,dev1.delivery_type,dev1.seller_name,dev1.delivery_collect_number,dev1.milkrun_last_status_date,
	dev2.last_status_code,dev2.delivery_type,dev2.seller_name,dev2.delivery_number,dev2.last_status_date

)
,
Status_Calc as (

select 
    b.tipo,
    b.promessa_cliente,
    left (b.promessa_cliente,7) as mes_ano_prom_cliente,
    b.mes_ano_definido,
    b.nome_seller,
    b.sale_order_store_number,
    b.doc_dft,
    b.data_compra,
    b.data_limite_de_expedicao,
    left (b.data_limite_de_expedicao,7) as mes_ano_dl,
    b.data_expedicao_coleta,
    left (b.data_expedicao_coleta,7) as mes_ano_exp,
    b.data_entrega,
    left (b.data_entrega,7) as mes_ano_entrega,
    b.delivery_type,
    coalesce (ultimo_ponto_coleta,ultimo_ponto_mkt) as ultimo_ponto,
    case 
        when qtd_pontos = 1 and ultimo_ponto = 'TNA' then 'TRANSPORTADOR NÃO ATRIBUIDO' 
        when qtd_pontos = 1 and ultimo_ponto in ('CAN','CAA','SOC') and data_entrega is null then 'CANCELAMENTO_SAC_CLIENTE'
        when qtd_pontos = 1 and ultimo_ponto = 'AOT' and data_entrega is null then 'ITEM_CANCELAMENTO_EXTRAVIO'
        when qtd_pontos = 1 and ultimo_ponto = 'RCC' and data_entrega is null then 'ITEM_CANCELAMENTO_COLETA'
        when qtd_pontos = 1 and ultimo_ponto = 'CAF' and data_entrega is null then 'ITEM_CANCELAMENTO_SELLER'
        when qtd_pontos = 1 and ultimo_ponto in ('REM','RIE','DEV') and data_entrega is null then 'DEVOLVIDO_SELLER'
        when qtd_pontos = 1 and ultimo_ponto in ('POS') and data_entrega is null then 'DEVOLUÇÃO_EM_ABERTO'
        when qtd_pontos = 1 and ultimo_ponto in ('PEP','AVA','TEX','EXC','ROU','TRO','TAV') and data_entrega is null then 'EXTRAVIOS'
        when qtd_cancelada = 1 and u.is_canceled = 1 and data_entrega is null then 'CANCELAMENTO_SAC_CLIENTE' 
        when data_entrega is not null and promessa_cliente >= data_entrega then 'ENTREGAS_PRAZO'
        when data_entrega is not null and promessa_cliente < data_entrega then 'ENTREGAS_ATRASO'
        when min (dev.shipped_date) is not null then 'EXPEDIÇÃO_SEM_ANP'
        when data_entrega is null and data_limite_de_expedicao < data_expedicao_coleta then 'ENVIOS_ATRASO'
        when data_entrega is null and data_limite_de_expedicao >= data_expedicao_coleta then 'ENVIOS_PRAZO'
        when data_expedicao_coleta is null and data_limite_de_expedicao < CURRENT_DATE  then 'EM_ABERTO_ATRASO'
        when data_expedicao_coleta is null and data_limite_de_expedicao = CURRENT_DATE  then 'EM_ABERTO_HOJE'
        when data_expedicao_coleta is null and data_limite_de_expedicao > CURRENT_DATE  then 'EM_ABERTO_PRAZO'
        else 'Validar'
    end as status_pedido,
    case
        when status_pedido in ('ENTREGAS_PRAZO','ENTREGAS_ATRASO') then 'ENTREGUE LEAP'
        when status_pedido in ('EM_ABERTO_ATRASO','EM_ABERTO_HOJE','EM_ABERTO_PRAZO') and coalesce (ultimo_ponto_coleta,ultimo_ponto_mkt) not in ('RFC', 'SVA') then 'EM ABERTO'
        when status_pedido in ('EM_ABERTO_ATRASO','EM_ABERTO_HOJE','EM_ABERTO_PRAZO') and coalesce (ultimo_ponto_coleta,ultimo_ponto_mkt) in ('RFC', 'SVA') then 'PRONTO COLETA'
        when status_pedido in ('ENVIOS_ATRASO','ENVIOS_PRAZO') and data_expedicao_coleta is not null then 'EM TRANSFERÊNCIA'
        else 'OUTROS'
    end as status_pedido_1,    
    case 
        when status_pedido in ('EM_ABERTO_ATRASO') then CURRENT_DATE - b.data_limite_de_expedicao
    else 0
    end as dias_em_atraso,
    case 
        when dias_em_atraso <= 0 then '0'
        when dias_em_atraso = 1 then '1'
        when dias_em_atraso = 2 then '2'
        when dias_em_atraso = 3 then '3'
        when dias_em_atraso = 4 then '4'
        when dias_em_atraso = 5 then '5'
        when dias_em_atraso = 6 then '6'
        when dias_em_atraso = 7 then '7'
        when dias_em_atraso = 8 then '8'
        when dias_em_atraso = 9 then '9'
        when dias_em_atraso = 10 then '10'
        when dias_em_atraso = 11 then '11'
        when dias_em_atraso = 12 then '12'
        when dias_em_atraso = 13 then '13'
        when dias_em_atraso = 14 then '14'
        when dias_em_atraso = 15 then '15'
    else '15+'
    end as grupo_dias_em_atraso,    
    qtd_sva,
    count (b.doc_dft) over (partitiON by  b.sale_order_store_number,b.nome_seller,b.delivery_type) as qtd,
    qtd_doc_dft,
    case 
        when data_expedicao_coleta is null then 'SEM_EXPEDIÇAO'
        when data_expedicao_coleta::date <= data_limite_de_expedicao::date then 'EXPEDIÇÃO_NO_PRAZO'
        when data_expedicao_coleta::date > data_limite_de_expedicao::date then 'EXPEDIÇÃO_FORA_PRAZO'
    end as status_expedicao,
    case 
        when data_entrega is null then 'SEM_ENTREGA'
        when data_entrega::date <= promessa_cliente::date then 'ENTREGA_NO_PRAZO'
        when data_entrega::date > promessa_cliente::date  then 'ENTREGA_FORA_PRAZO'
    end as status_entrega,
    valor_prej

from 
    base as b
left join 
    Ultimo_ponto as u
    on b.doc_dft = u.dft and b.nome_seller = u.nome_seller and b.delivery_type = u.delivery_type
left join 
    showcase.c_operation_outbound_delivery as dev 
    on b.doc_dft = dev.delivery_collect_number and dev.delivery_collect_number is not null and dev.shipped_date is not null and dev.item_quantity > 0 and dev.delivery_type = 'MILKRUN'
left join 
    valor_prej as vp
    on b.doc_dft = vp.doc_dft
group by 
    b.tipo,b.promessa_cliente,b.nome_seller,b.sale_order_store_number,b.doc_dft,b.data_compra,b.data_limite_de_expedicao,b.data_expedicao_coleta,b.mes_ano_definido,
    b.data_entrega,b.delivery_type,ultimo_ponto_coleta,ultimo_ponto_mkt,u.qtd_pontos,qtd_doc_dft,qtd_cancelada,u.is_canceled,qtd_sva,valor_prej
  )
  
select 
    nome_seller,
    mes_ano_definido,
    delivery_type,
    status_pedido_1 as status_pedido,
    count(distinct doc_dft) as quantidade
 
 from 
     Status_Calc
 group by 
    nome_seller,
    mes_ano_definido,
    delivery_type,
    status_pedido_1
"""

QUERY_RESUMO_STATUS_LOJA = """
select
    delivery_type,
    seller_name as nome_seller,
    seller_id,
    ultima_data as data_ultimo_ponto_mkt,
    (CURRENT_DATE - ultima_data::date) as status_loja
from (
    select
        dev.delivery_type,
        dev.seller_name,
        dev.seller_id,
        greatest(max(dev.milkrun_last_status_date), max(dev.milkrun_collected_date)) as ultima_data
    from 
        showcase.c_operation_outbound_delivery as dev
    where 
        dev.delivery_type in ('MILKRUN')
        and dev.milkrun_last_status not in ('PAP','WMS','SVA','CAN','RCC','TAF','TEX','TRO','TAV','EXC')
    group by
        1,2,3
    having 
        greatest(max(dev.milkrun_last_status_date), max(dev.milkrun_collected_date)) is not null
        and (case 
            when dev.delivery_type = 'MILKRUN' then max(dev.milkrun_expected_delivery_warehouse_date::date)
            else max(dev.customer_expected_delivery_date::date)
        end) >= DATEADD(MONTH, -6, DATE_TRUNC('MONTH', CURRENT_DATE))

    union all 

    select
        dev.delivery_type,
        dev.seller_name,
        dev.seller_id,
        greatest(max(dev.last_status_date), max(dev.last_status_transmission_date)) as ultima_data
    from 
        showcase.c_operation_outbound_delivery as dev
    where 
        dev.delivery_type in ('DROPSHIPPING','DAFITI ENVIOS')
        and dev.last_status_code not in ('PAP','WMS','CAN')
    group by
        1,2,3
    having
        greatest(max(dev.last_status_date), max(dev.last_status_transmission_date)) is not null
        and (case 
            when dev.delivery_type = 'MILKRUN' then max(dev.milkrun_expected_delivery_warehouse_date::date)
            else max(dev.customer_expected_delivery_date::date)
        end) >= DATEADD(MONTH, -6, DATE_TRUNC('MONTH', CURRENT_DATE))
)
"""

QUERY_RESUMO_RCC = """
SELECT 
    nome_seller,
    mes_ano_compra,
    delivery_type,
    SUM(qtds) AS qtd,
    SUM(rcc) AS rcc,
    CASE 
        WHEN SUM(qtds) > 0 THEN (SUM(rcc)::double precision / SUM(qtds)::double precision)
        ELSE 0.0 
    END AS taxa_rcc
FROM (
    SELECT 
        dev.seller_name AS nome_seller,
        LEFT(dev.sale_order_store_date::date, 7) AS mes_ano_compra,
        dev.delivery_type,
        COALESCE(dev.original_item_quantity, 1) AS qtds,
        CASE 
            WHEN dev.rcc_date IS NOT NULL THEN COALESCE(dev.original_item_quantity, 1)
            ELSE 0 
        END AS rcc
    FROM 
        showcase.c_operation_outbound_delivery AS dev
    WHERE 
        dev.delivery_type IN ('DROPSHIPPING', 'DAFITI ENVIOS', 'MILKRUN')
        AND dev.sale_order_store_date::date >= DATEADD(MONTH, -6, DATE_TRUNC('MONTH', CURRENT_DATE))
) AS base_caf
GROUP BY 
    1, 2, 3
HAVING 
    SUM(rcc) > 0
"""

QUERY_RESUMO_CAN = """
SELECT 
    nome_seller,
    mes_ano_compra,
    delivery_type,
    SUM(qtds) AS qtd,
    SUM(can) AS can,
    CASE 
        WHEN SUM(qtds) > 0 THEN (SUM(can)::double precision / SUM(qtds)::double precision)
        ELSE 0.0 
    END AS taxa_can
FROM (
    SELECT 
        dev.seller_name AS nome_seller,
        LEFT(dev.sale_order_store_date::date, 7) AS mes_ano_compra,
        dev.delivery_type,
        COALESCE(dev.original_item_quantity, 1) AS qtds,
        CASE 
            WHEN (dev.caf_status_date IS NOT NULL OR dev.last_status_code = 'CAF') THEN 0
            WHEN dev.rcc_date IS NOT NULL THEN 0
            WHEN dev.is_canceled = 1 THEN COALESCE(dev.original_item_quantity, 1)
            ELSE 0 
        END AS can
    FROM 
        showcase.c_operation_outbound_delivery AS dev
    WHERE 
        dev.delivery_type IN ('DROPSHIPPING', 'DAFITI ENVIOS', 'MILKRUN')
        AND dev.sale_order_store_date::date >= DATEADD(MONTH, -6, DATE_TRUNC('MONTH', CURRENT_DATE))
) AS base_can
GROUP BY 
    1, 2, 3
HAVING 
    SUM(can) > 0
"""

def atualizar_aba_google_sheets(sh, nome_aba, df, tamanho_lote=10000):
    """Limpa e escreve os dados numa aba do Google Sheets de forma segura."""
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
        worksheet.update(range_name=intervalo, values=lote)
        time.sleep(1.2)


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

        # 1. EXTRAÇÃO DO RESUMO VENDAS EXPEDIÇÃO
        print(f"[{datetime.now()}] 📥 A extrair RESUMO VENDAS EXPEDIÇÃO...")
        df_resumo_exp = pd.read_sql(QUERY_RESUMO_EXPEDICAO, conexao)
        for col in ['taxa_expedicao_no_prazo', 'taxa_expedicao_fora_prazo']:
            if col in df_resumo_exp.columns:
                df_resumo_exp[col] = pd.to_numeric(df_resumo_exp[col], errors='coerce').round(6)
        df_resumo_exp = df_resumo_exp.fillna('')
        print(f"[{datetime.now()}] ✅ Resumo Expedição extraído: {len(df_resumo_exp):,} linhas.".replace(",", "."))

        # 2. EXTRAÇÃO DO RESUMO CAF
        print(f"[{datetime.now()}] 📥 A extrair RESUMO CAF...")
        df_resumo_caf = pd.read_sql(QUERY_RESUMO_CAF, conexao)
        if 'taxa_cancelamento' in df_resumo_caf.columns:
            df_resumo_caf['taxa_cancelamento'] = pd.to_numeric(df_resumo_caf['taxa_cancelamento'], errors='coerce').fillna(0).round(6)
        df_resumo_caf = df_resumo_caf.fillna('')
        print(f"[{datetime.now()}] ✅ Resumo CAF extraído: {len(df_resumo_caf):,} linhas.".replace(",", "."))

        # 3. EXTRAÇÃO DO RESUMO ENTREGAS
        print(f"[{datetime.now()}] 📥 A extrair RESUMO ENTREGAS...")
        df_resumo_entregas = pd.read_sql(QUERY_RESUMO_ENTREGAS, conexao)
        for col in ['taxa_entrega_prazo', 'taxa_entrega_fora_prazo']:
            if col in df_resumo_entregas.columns:
                df_resumo_entregas[col] = pd.to_numeric(df_resumo_entregas[col], errors='coerce').round(6)
        df_resumo_entregas = df_resumo_entregas.fillna('')
        print(f"[{datetime.now()}] ✅ Resumo Entregas extraído: {len(df_resumo_entregas):,} linhas.".replace(",", "."))

        # 4. EXTRAÇÃO DO RESUMO PREJUDICADO
        print(f"[{datetime.now()}] 📥 A extrair RESUMO PREJUDICADO...")
        df_resumo_prejudicado = pd.read_sql(QUERY_RESUMO_PREJUDICADO, conexao)
        if 'valor_prej' in df_resumo_prejudicado.columns:
            df_resumo_prejudicado['valor_prej'] = pd.to_numeric(df_resumo_prejudicado['valor_prej'], errors='coerce').fillna(0).round(2)
        df_resumo_prejudicado = df_resumo_prejudicado.fillna('')
        print(f"[{datetime.now()}] ✅ Resumo Prejudicado extraído: {len(df_resumo_prejudicado):,} linhas.".replace(",", "."))

        # 5. EXTRAÇÃO DO RESUMO SVA
        print(f"[{datetime.now()}] 📥 A extrair RESUMO SVA...")
        df_resumo_sva = pd.read_sql(QUERY_RESUMO_SVA, conexao)
        if 'qtd_sva' in df_resumo_sva.columns:
            df_resumo_sva['qtd_sva'] = pd.to_numeric(df_resumo_sva['qtd_sva'], errors='coerce').fillna(0).astype(int)
        df_resumo_sva = df_resumo_sva.fillna('')
        print(f"[{datetime.now()}] ✅ Resumo SVA extraído: {len(df_resumo_sva):,} linhas.".replace(",", "."))

        # 6. EXTRAÇÃO DO RESUMO TRACKING
        print(f"[{datetime.now()}] 📥 A extrair RESUMO TRACKING...")
        df_resumo_tracking = pd.read_sql(QUERY_RESUMO_TRACKING, conexao)
        if 'quantidade' in df_resumo_tracking.columns:
            df_resumo_tracking['quantidade'] = pd.to_numeric(df_resumo_tracking['quantidade'], errors='coerce').fillna(0).astype(int)
        df_resumo_tracking = df_resumo_tracking.fillna('')
        print(f"[{datetime.now()}] ✅ Resumo Tracking extraído: {len(df_resumo_tracking):,} linhas.".replace(",", "."))

        # 7. EXTRAÇÃO DO RESUMO STATUS LOJA
        print(f"[{datetime.now()}] 📥 A extrair RESUMO STATUS LOJA...")
        df_resumo_status_loja = pd.read_sql(QUERY_RESUMO_STATUS_LOJA, conexao)
        if 'status_loja' in df_resumo_status_loja.columns:
            df_resumo_status_loja['status_loja'] = pd.to_numeric(df_resumo_status_loja['status_loja'], errors='coerce').fillna(0).astype(int)
        df_resumo_status_loja = df_resumo_status_loja.astype(str).replace({'None': '', 'nan': '', '<NaT>': ''})
        print(f"[{datetime.now()}] ✅ Resumo Status Loja extraído: {len(df_resumo_status_loja):,} linhas.".replace(",", "."))

        # 8. EXTRAÇÃO DA BASE VENDAS DETALHADA
        print(f"[{datetime.now()}] 📥 A extrair BASE VENDAS...")
        df_base = pd.read_sql(QUERY_BASE, conexao)
        df_base['ultima_atualizacao_tabela'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        df_base = df_base.astype(str).replace({'None': '', 'nan': '', '<NaT>': ''})
        total_linhas_base = len(df_base)
        print(f"[{datetime.now()}] ✅ Base extraída do Redshift: TOTAL DE {total_linhas_base:,} LINHAS.".replace(",", "."))

        # 9. EXTRAÇÃO DO RESUMO RCC
        print(f"[{datetime.now()}] 📥 A extrair RESUMO RCC...")
        df_rcc = pd.read_sql(QUERY_RESUMO_RCC, conexao)
        
        col_taxa_rcc = 'taxa_rcc' if 'taxa_rcc' in df_rcc.columns else 'taxa_cancelamento'
        if col_taxa_rcc in df_rcc.columns:
            df_rcc[col_taxa_rcc] = pd.to_numeric(df_rcc[col_taxa_rcc], errors='coerce').fillna(0).round(6)
            df_rcc[col_taxa_rcc] = df_rcc[col_taxa_rcc].astype(str).str.replace('.', ',', regex=False)
            
        df_rcc = df_rcc.astype(str).replace({'None': '', 'nan': '', '<NaT>': ''})
        total_linhas_rcc = len(df_rcc)
        print(f"[{datetime.now()}] ✅ RESUMO RCC extraído do Redshift: TOTAL DE {total_linhas_rcc:,} LINHAS.".replace(",", "."))

        # 10. EXTRAÇÃO DO RESUMO CAN
        print(f"[{datetime.now()}] 📥 A extrair RESUMO CAN...")
        df_can = pd.read_sql(QUERY_RESUMO_CAN, conexao)
        
        col_taxa_can = 'taxa_can' if 'taxa_can' in df_can.columns else 'taxa_cancelamento'
        if col_taxa_can in df_can.columns:
            df_can[col_taxa_can] = pd.to_numeric(df_can[col_taxa_can], errors='coerce').fillna(0).round(6)
            df_can[col_taxa_can] = df_can[col_taxa_can].astype(str).str.replace('.', ',', regex=False)
            
        df_can = df_can.astype(str).replace({'None': '', 'nan': '', '<NaT>': ''})
        total_linhas_can = len(df_can)
        print(f"[{datetime.now()}] ✅ RESUMO CAN extraído do Redshift: TOTAL DE {total_linhas_can:,} LINHAS.".replace(",", ".")) 
        
        conexao.close()

    except Exception as e:
        print(f"[{datetime.now()}] ❌ Erro no Redshift: {e}")
        return

    # 11. ENVIO DOS DADOS PARA O GOOGLE SHEETS
    print(f"[{datetime.now()}] 🔄 A conectar ao Google Sheets...")
    caminho_credenciais = os.path.join(os.path.dirname(__file__), "credenciais.json")

    try:
        gc = gspread.service_account(filename=caminho_credenciais)
        sh_principal = gc.open_by_key(SHEET_PRINCIPAL_ID)

        # Atualiza os 9 RESUMOS na planilha principal
        print(f"[{datetime.now()}] 📊 Atualizando abas de resumo na planilha principal...")
        atualizar_aba_google_sheets(sh_principal, NOME_ABA_RESUMO_EXPEDICAO, df_resumo_exp)
        atualizar_aba_google_sheets(sh_principal, NOME_ABA_RESUMO_CAF, df_resumo_caf)
        atualizar_aba_google_sheets(sh_principal, NOME_ABA_RESUMO_RCC, df_rcc)
        atualizar_aba_google_sheets(sh_principal, NOME_ABA_RESUMO_CAN, df_can)
        atualizar_aba_google_sheets(sh_principal, NOME_ABA_RESUMO_ENTREGAS, df_resumo_entregas)
        atualizar_aba_google_sheets(sh_principal, NOME_ABA_RESUMO_PREJUDICADO, df_resumo_prejudicado)
        atualizar_aba_google_sheets(sh_principal, NOME_ABA_RESUMO_SVA, df_resumo_sva)
        atualizar_aba_google_sheets(sh_principal, NOME_ABA_RESUMO_TRACKING, df_resumo_tracking)
        atualizar_aba_google_sheets(sh_principal, NOME_ABA_RESUMO_STATUS_LOJA, df_resumo_status_loja)

        # Divisão da BASE em blocos de 300.000 linhas
        blocos_base = [
            df_base[i : i + LIMIT_LINHAS_POR_SHEET]
            for i in range(0, total_linhas_base, LIMIT_LINHAS_POR_SHEET)
        ]

        print(f"[{datetime.now()}] 📦 Total de dados da BASE divididos em {len(blocos_base)} lote(s).")

        # Envio exclusivo para as 5 planilhas externas
        for idx in range(len(PLANILHAS_BASE)):
            info_sheet = PLANILHAS_BASE[idx]
            sheet_id = info_sheet["id"]
            sh_lote = gc.open_by_key(sheet_id)

            if idx < len(blocos_base):
                df_lote = blocos_base[idx]
                print(f"[{datetime.now()}] 🚀 A enviar Lote {idx + 1} ({len(df_lote):,} linhas) para Sheet externa ID: {sheet_id}...")
                atualizar_aba_google_sheets(sh_lote, NOME_ABA_BASE, df_lote)
                print(f"[{datetime.now()}] ✅ Lote {idx + 1} gravado com sucesso!")
            else:
                print(f"[{datetime.now()}] 🧹 A limpar planilha externa sobressalente ID: {sheet_id}...")
                try:
                    ws = sh_lote.worksheet(NOME_ABA_BASE)
                    ws.clear()
                except Exception:
                    pass

        print(f"[{datetime.now()}] 🎉 Atualização de todas as planilhas e resumos concluída com sucesso!")

    except Exception as e:
        print(f"[{datetime.now()}] ❌ Erro no Google Sheets: {e}")


if __name__ == "__main__":
    executar_automacao()