import os
import psycopg2
import pandas as pd
import gspread
import requests
from datetime import datetime, timedelta

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

SHEET_ID = "1Ku9ni_ht9YPwJ9DzDJghvgJsgXQbffG6misfl937Lt4"
NOME_ABA_BASE = "Base"
PATH_SERVICE_ACCOUNT = "credenciais.json"

# Webhook do Google Chat
WEBHOOK_URL = "https://chat.googleapis.com/v1/spaces/AAQAMshu3HA/messages?key=AIzaSyDdI0hCZtE6vySjMm-WEfRq3CPzqKqqsHI&token=qpzJu1FNnjNGoVFEOyX_RUTTrj5XyNtcSmHbNEFVZ1s"
LINK_PLANILHA = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}"

# ==========================================
# 2. CONSULTAS SQL
# ==========================================
QUERY_BASE = """
with od_base as (
    select
        od.docid,
        ltrim(max(od.docno), '0') as entrega,
        max(refd.refdocno)::varchar as remessa,
        max(od.refdocno_so)::varchar as ordem_venda,
        min(od.cretst_c) as captacao_ewm_raw,
        max(od.doctype) as tipo_doc,
        max(od.route_id) as itinerario
    from raw_sap_ewm.zvwm_od od
    inner join raw_sap_ewm.zvwm_od_refdoc refd
        on refd.docid = od.docid
        and refd.refdoccat = 'ERP'
    where od.scwm_whno = 'B006'
      and od.refdocno_so is not null
      and od.qty > 0
    group by od.docid
),

cockpit_latest as (
    select
        docid,
        partyno_1 as cod_tsp,
        status as status_processo,
        data_hora as data_hora_confirmacao_raw,
        doc_type as tipo_de_processo
    from (
        select
            cock.docid,
            cock.partyno_1,
            cock.status,
            cock.data_hora,
            cock.doc_type,
            row_number() over (
                partition by cock.docid
                order by cock.data_hora desc
            ) as rn
        from raw_sap_ewm.dafiti_cockpit cock
        inner join od_base od
            on od.docid = cock.docid
        where cock.qty > 0
    )
    where rn = 1
),

wt_latest as (
    select
        docid,
        nlenr as uc,
        confirmed_at as data_confirmacao_uc_raw
    from (
        select
            wt.docid,
            wt.nlenr,
            wt.confirmed_at,
            row_number() over (
                partition by wt.docid
                order by wt.confirmed_at desc
            ) as rn
        from raw_sap_ewm.zvwm_wt wt
        inner join od_base od
            on od.docid = wt.docid
        where wt.nlenr is not null
    )
    where rn = 1
),

base_ewm as (
    select
        od.docid,
        od.entrega,
        od.remessa,
        od.ordem_venda,
        od.captacao_ewm_raw,
        od.tipo_doc,
        od.itinerario,
        cock.cod_tsp,
        transp.name as transportador,
        cock.status_processo,
        cock.data_hora_confirmacao_raw,
        wt.uc,
        cock.tipo_de_processo
    from od_base od
    inner join cockpit_latest cock
        on cock.docid = od.docid
    left join wt_latest wt
        on wt.docid = od.docid
    left join raw_sap_br.zbw000016 transp
        on transp.forwagent = cock.cod_tsp
),

d20_base as (
    select
        d20.deliv_numb::varchar as remessa,
        max(d20.forwagent) as ag_frete,
        max(d20.zprzcdkf) as prazo_cd,
        max(d20.ship_cond) as ship_cond_code,
        max(d20.load_date) as data_limite_raw
    from raw_sap_br.asd_d2000 d20
    inner join (
        select distinct remessa
        from base_ewm
    ) base
        on base.remessa = d20.deliv_numb::varchar
    group by 1
),

ship_cond as (
    select
        sc.ship_cond,
        max(sc.txtsh) as ship_cond_texto
    from raw_sap_br.tship_cond sc
    where sc.langu = 'P'
    group by 1
),

ds06_expedicao as (
    select
        ds06.deliv_numb::varchar as remessa,
        min(
            case
                when ds06.createdon ~ '^[0-9]{8}$'
                    and ds06.zhrpr_c ~ '^[0-9]{6}$'
                    then dateadd(
                        second,
                        substring(ds06.zhrpr_c, 1, 2)::integer * 3600
                            + substring(ds06.zhrpr_c, 3, 2)::integer * 60
                            + substring(ds06.zhrpr_c, 5, 2)::integer,
                        to_timestamp(ds06.createdon, 'yyyymmdd')::timestamp
                    )
            end
        ) as data_expedicao
    from raw_sap_br.azle_ds0600 ds06
    inner join (
        select distinct remessa
        from base_ewm
    ) base
        on base.remessa = ds06.deliv_numb::varchar
    where ds06.zocor_sig in ('ETR')
    group by 1
),

base_d20 as (
    select
        d20.remessa,
        d20.ag_frete,
        d20.prazo_cd,
        coalesce(sc.ship_cond_texto, d20.ship_cond_code) as ship_cond,
        d20.data_limite_raw,
        ds06.data_expedicao
    from d20_base d20
    left join ship_cond sc
        on sc.ship_cond = d20.ship_cond_code
    left join ds06_expedicao ds06
        on ds06.remessa = d20.remessa
),

pagamentos_base as (
    select
        d10.po_number as pedido,
        d10.doc_number as ordem_venda,
        case
            when d10.doc_date ~ '^[0-9]{8}$'
                and d10.doc_time ~ '^[0-9]{6}$'
                then dateadd(
                    second,
                    substring(d10.doc_time, 1, 2)::integer * 3600
                        + substring(d10.doc_time, 3, 2)::integer * 60
                        + substring(d10.doc_time, 5, 2)::integer,
                    to_timestamp(d10.doc_date, 'yyyymmdd')::timestamp
                )
        end as data_pedido,
        case
            when d10.zpap ~ '^[0-9]{8}$'
                and d10.zpap_hr ~ '^[0-9]{6}$'
                then dateadd(
                    second,
                    substring(d10.zpap_hr, 1, 2)::integer * 3600
                        + substring(d10.zpap_hr, 3, 2)::integer * 60
                        + substring(d10.zpap_hr, 5, 2)::integer,
                    to_timestamp(d10.zpap, 'yyyymmdd')::timestamp
                )
        end as data_pagamento,
        case
            when mpay.src_payment_method_description_local_language is not null then mpay.src_payment_method_description_local_language
            when d10.xapymtmeth = 'B' then 'Pix'
            when d10.xapymtmeth = 'L' then 'Pix + Vale'
            when d10.xapymtmeth = 'N' then 'DEBITO ADYEN'
            else d10.xapymtmeth
        end as metodo_pagamento
    from raw_sap_br.asd_d1000 d10
    inner join (
        select distinct ordem_venda
        from base_ewm
    ) base
        on base.ordem_venda = d10.doc_number
    left join mapping_layer.map_payment_method mpay
        on mpay.id_map_payment_method = d10.xapymtmeth
),

pagamentos as (
    select
        pedido,
        ordem_venda,
        max(data_pedido) as data_pedido,
        max(data_pagamento) as data_pagamento,
        max(metodo_pagamento) as metodo_pagamento
    from pagamentos_base
    group by 1,2
),

corte as (
    select distinct
        pt.lifnr as delivery_carrier_code,
        upper(pt.vsbed_txt) as shipping_condition,
        pt.fl_ativo as situation,
        first_value(pt.fl_ativo) over (
            partition by pt.lifnr, pt.vsbed_txt
            order by pt.fl_ativo
            rows between unbounded preceding and unbounded following
        ) as last_situation,
        max((to_timestamp(pt.hora_coleta_cd, 'HH24MISS')::timestamp)::time) over (
            partition by pt.lifnr, pt.vsbed_txt, pt.fl_ativo
        ) as horario_limite_disponibilizacao_transportadora
    from spc_raw_ecc.zleparamttime pt
    where not (pt.hora_corte in ('0', '000000') and pt.hora_coleta_cd in ('0', '000000'))
      and pt.hora_corte ~ '^[0-9]{6}'
      and pt.hora_coleta_cd ~ '^[0-9]{6}'
    qualify situation = last_situation
),

base_final as (
    select
        pagamentos.pedido,
        base_ewm.ordem_venda,
        base_ewm.entrega,
        base_ewm.remessa as remessa_atual,
        base_ewm.docid,
        base_ewm.tipo_doc,
        base_d20.prazo_cd,
        pagamentos.metodo_pagamento,
        try_cast(base_d20.data_limite_raw::varchar as date) as data_limite_expedicao,
        dateadd(hour, -3, to_timestamp(base_ewm.captacao_ewm_raw::varchar, 'yyyymmddhh24miss')::timestamp) as data_captacao_ewm,
        pagamentos.data_pedido as data_pedido_compra,
        pagamentos.data_pagamento as data_pagamento_compra,
        base_ewm.cod_tsp,
        base_ewm.transportador,
        base_d20.ship_cond as contrato,
        base_ewm.itinerario,
        to_timestamp(base_ewm.data_hora_confirmacao_raw::varchar, 'yyyymmddhh24miss')::timestamp as data_hora_confirmacao_movimentacao,
        base_d20.data_expedicao,
        base_ewm.status_processo,
        base_ewm.uc,
        corte.horario_limite_disponibilizacao_transportadora,
        base_ewm.tipo_de_processo
    from base_ewm
    left join base_d20
        on base_d20.remessa = base_ewm.remessa
    left join pagamentos
        on pagamentos.ordem_venda = base_ewm.ordem_venda
    left join corte
        on corte.delivery_carrier_code = base_ewm.cod_tsp
        and corte.shipping_condition = upper(base_d20.ship_cond)
),

classificacao as (
    select
        *,
        case
            when data_expedicao is not null and data_expedicao < current_date then 'EXPEDIDO'
            when data_expedicao is not null then 'PROCESSADO PELO PA'
            when status_processo = 'SCAM' then 'PROCESSADO PELO PA'
            when status_processo = 'SMER' and left(uc, 2) <> '51' then 'SAIDA VIRTUAL'
            when status_processo = 'SMER' then 'VOLUME EM DOCA'
            when status_processo in ('GAIL', 'SHIP', 'CONF') then 'PICKING/SHIPPING'
            else 'ETAPA CD'
        end as status_remessa
    from base_final
),

calculos as (
    select
        *,
        current_date - data_limite_expedicao as qtd_dias_atraso,
        case
            when data_expedicao is not null then left(data_expedicao::time::varchar, 2)
            else left(data_hora_confirmacao_movimentacao::time::varchar, 2)
        end as hora_processo,
        case
            when prazo_cd is null then 'Aguardando atualizacao'
            when data_limite_expedicao < current_date then 'Atrasado'
            when current_date - data_limite_expedicao = 0 or data_limite_expedicao = current_date then 'Vence Hoje'
            else 'D+1'
        end as tipo_prazo,
        case
            when status_remessa = 'ETAPA CD'
                and current_date - data_limite_expedicao > 30
                then 'Sujeira Sistemica'
            when tipo_de_processo = 'MR'
                and status_remessa = 'ETAPA CD'
                and data_expedicao is null
                and current_date - data_limite_expedicao >= 2
                then 'Sujeira Sistemica'
            else 'OK'
        end as limpeza_sistemica
    from classificacao
)

select
    pedido,
    ordem_venda,
    entrega,
    remessa_atual,
    docid,
    tipo_doc,
    prazo_cd,
    metodo_pagamento,
    data_limite_expedicao::varchar as data_limite_expedicao,
    qtd_dias_atraso,
    tipo_prazo as tipo,
    limpeza_sistemica,
    data_captacao_ewm::varchar as data_captacao_ewm,
    data_pedido_compra::varchar as data_pedido_compra,
    data_pagamento_compra::varchar as data_pagamento_compra,
    cod_tsp,
    transportador,
    contrato,
    itinerario,
    data_hora_confirmacao_movimentacao::varchar as data_hora_confirmacao_movimentacao,
    data_expedicao::varchar as data_expedicao,
    hora_processo,
    status_remessa,
    uc,
    horario_limite_disponibilizacao_transportadora::varchar as horario_limite_disponibilizacao_transportadora,
    case
        when status_remessa = 'ETAPA CD' then 'EM PROCESSAMENTO OPERACAO'
        when status_remessa = 'PICKING/SHIPPING' then 'PROXIMO A SER DISPONIBILIZADO'
        when status_remessa in ('PROCESSADO PELO PA', 'VOLUME EM DOCA')
            and horario_limite_disponibilizacao_transportadora >= data_hora_confirmacao_movimentacao::time then 'DENTRO DO CORTE'
        else 'FORA DO CORTE'
    end as status_corte,
    tipo_de_processo,
    ''::varchar as data_hora_atualizacao_base
from calculos
where status_remessa not in ('EXPEDIDO', 'SAIDA VIRTUAL')
  and limpeza_sistemica = 'OK';
"""

# ==========================================
# 3. FUNÇÕES DE EXECUÇÃO
# ==========================================
def buscar_dados_redshift():
    """Conecta ao Redshift e extrai o resultado do SQL para um DataFrame Pandas."""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Conectando ao Amazon Redshift...")
    
    conn = psycopg2.connect(
        host=REDSHIFT_HOST,
        port=REDSHIFT_PORT,
        dbname=REDSHIFT_DB,
        user=REDSHIFT_USER,
        password=REDSHIFT_PASSWORD
    )
    
    try:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Executando consulta SQL...")
        cursor = conn.cursor()
        cursor.execute(QUERY_BASE)
        
        colunas = [desc[0] for desc in cursor.description]
        registos = cursor.fetchall()
        
        df = pd.DataFrame(registos, columns=colunas)
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Consulta concluída com sucesso! Total de linhas: {len(df)}")
        return df
    finally:
        conn.close()

def enviar_notificacao_webhook(data_atualizacao, total_linhas):
    """Envia notificação formatada para a sala do Google Chat via Webhook."""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Enviando notificação via Webhook...")
    
    dt_atual = datetime.strptime(data_atualizacao, "%Y-%m-%d %H:%M:%S")
    dt_proxima = dt_atual + timedelta(minutes=30)
    
    referencia_str = dt_atual.strftime("%d/%m/%Y %H:%M:%S")
    proxima_str = dt_proxima.strftime("%d/%m/%Y %H:%M:%S")
    
    mensagem = (
        f"✅ *Acompanhamento Doca*\n\n"
        f"🔗 *Link:* {LINK_PLANILHA}\n"
        f"👤 *Responsável:* Lucas Costa\n"
        f"🏢 *Área:* Transportes\n"
        f"📅 *Referência:* {referencia_str}\n"
        f"📊 *Linhas carregadas:* {total_linhas}\n"
        f"⏰ *Próxima atualização:* {proxima_str}\n"
        f"🔄 *Recorrência:* Segunda a sexta, de hora em hora, das 07:00 às 17:00"
    )
    
    payload = {"text": mensagem}
    
    try:
        response = requests.post(WEBHOOK_URL, json=payload)
        if response.status_code == 200:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Notificação enviada com sucesso!")
        else:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Falha ao enviar notificação. Status: {response.status_code}, Resposta: {response.text}")
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Erro ao disparar webhook: {str(e)}")

def atualizar_google_sheets(df):
    """Atualiza a aba no Google Sheets e chama o envio da notificação."""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Autenticando na API do Google Sheets...")
    
    agora_dt = datetime.now()
    agora_formatado = agora_dt.strftime("%Y-%m-%d %H:%M:%S")
    df['data_hora_atualizacao_base'] = agora_formatado

    client = gspread.service_account(filename=PATH_SERVICE_ACCOUNT)

    print(f"[{datetime.now().strftime('%H:%M:%S')}] Abrindo a planilha {SHEET_ID}...")
    spreadsheet = client.open_by_key(SHEET_ID)
    worksheet = spreadsheet.worksheet(NOME_ABA_BASE)

    df_clean = df.fillna("").astype(str)
    dados_para_envio = [df_clean.columns.values.tolist()] + df_clean.values.tolist()

    print(f"[{datetime.now().strftime('%H:%M:%S')}] Limpando o conteúdo atual da aba '{NOME_ABA_BASE}'...")
    worksheet.clear()

    print(f"[{datetime.now().strftime('%H:%M:%S')}] Atualizando dados no Google Sheets...")
    worksheet.update('A1', dados_para_envio, value_input_option='USER_ENTERED')
    
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Planilha atualizada com sucesso!")
    
    # Dispara a notificação via webhook
    enviar_notificacao_webhook(data_atualizacao=agora_formatado, total_linhas=len(df))

# ==========================================
# 4. EXECUÇÃO PRINCIPAL
# ==========================================
if __name__ == "__main__":
    try:
        dados_df = buscar_dados_redshift()
        if not dados_df.empty:
            atualizar_google_sheets(dados_df)
        else:
            print("A consulta não retornou dados para atualizar.")
    except Exception as e:
        print(f"Ocorreu um erro durante a execução: {str(e)}")