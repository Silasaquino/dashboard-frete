import os
import sys
import json
import time
import socket
import subprocess
from datetime import datetime, time as dt_time

# ==========================================
# TRAVA DE INSTÂNCIA ÚNICA (Evita processos fantasmas)
# ==========================================
trava_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    trava_socket.bind(("127.0.0.1", 47289))
except socket.error:
    print("⚠️ AVISO: Já existe uma instância do orquestrador rodando em segundo plano. Encerrando esta execução duplicada.")
    sys.exit(0)

# Garante que a biblioteca requests está acessível
try:
    import requests
except ImportError:
    print("ERRO: A biblioteca 'requests' não está instalada. Execute: pip install requests")
    sys.exit(1)

# ==========================================
# 1. CONFIGURAÇÕES GERAIS E JANELAS HORÁRIAS
# ==========================================
JENKINS_AUTH = None  # Se necessário: ("utilizador", "token_ou_senha")
INTERVALO_CHECAGEM_SEGUNDOS = 300  # 5 minutos
ARQUIVO_ESTADO = "jenkins_builds_processados.json"
ARQUIVO_LOG = "orquestrador.log"

# Janela de monitoramento do Jenkins (06:00:00 até 23:59:59)
HORA_INICIO_JENKINS = dt_time(6, 0, 0)
HORA_FIM_JENKINS = dt_time(23, 59, 59)

# Configuração da tarefa diária agendada (a partir das 01:00:00)
TAREFA_DIARIA_SCRAPER = {
    "chave": "scraper_dafiti",
    "nome": "Scraper Dafiti (Consulta Item Site)",
    "hora_inicio": dt_time(1, 0, 0),
    "scripts": ["scraper_dafiti.py"]
}

CONFIG_JOBS = {
    "reversa": {
        "nome": "Operação Reversa",
        "url_api": "http://hanger.dafiticorp.com:8080/jenkins/job/GLOVE_NQ_curated_data.a_operation_returns/api/json",
        "scripts": ["atualizar_base_reversa.py"]
    },
    "vendas": {
        "nome": "Vendas Outbound",
        "url_api": "http://hanger.dafiticorp.com:8080/jenkins/job/GLOVE_NQ_showcase.c_operation_outbound_delivery/api/json",
        "scripts": ["atualizar_base_vendas.py"]
    },
    "cockpit_doca": {
        "nome": "Cockpit Doca",
        "url_api": "http://hanger.dafiticorp.com:8080/jenkins/job/GLOVE_FILE_raw_sap_ewm.dafiti_cockpit/api/json",
        "scripts": ["cockpit_doca.py"]
    },
    "frete_milkrun": {
        "nome": "Controle de Frete (Milkrun)",
        "url_api": "http://hanger.dafiticorp.com:8080/jenkins/job/GLOVE_NQ_curated_data.controle_frete_coleta_milkrun/api/json",
        "scripts": ["controle_frete.py"]
    },
    "frete_envios": {
        "nome": "Controle de Frete (Envios)",
        "url_api": "http://hanger.dafiticorp.com:8080/jenkins/job/GLOVE_NQ_curated_data.controle_frete_envios/api/json",
        "scripts": ["controle_frete.py"]
    },
    "frete_reversa": {
        "nome": "Controle de Frete (Reversa / Devolução)",
        "url_api": "http://hanger.dafiticorp.com:8080/jenkins/job/GLOVE_NQ_curated_data.controle_frete_reversa_devolucao/api/json",
        "scripts": ["controle_frete.py"]
    },
    "bp_forecast": {
        "nome": "Envio BP Forecast",
        "url_api": "http://hanger.dafiticorp.com:8080/jenkins/job/GLOVE_FILE_manual_input.transports_envio_bp_forecast/api/json",
        "scripts": ["controle_frete.py"]
    },
    "operacao_producao": {
        "nome": "Operação Produção",
        "url_api": "http://hanger.dafiticorp.com:8080/jenkins/job/GLOVE_NQ_curated_data.operation_production/api/json",
        "scripts": ["atualizar_producao_individual.py", "atualizar_producao.py"]
    },
    "absenteismo_operacao": {
        "nome": "Absenteísmo Operação LEAP",
        "url_api": "http://hanger.dafiticorp.com:8080/jenkins/job/GLOVE_FILE_fabric.m_abs_cd_operacao_leap/api/json",
        "scripts": ["atualizar_absenteismo.py", "atualizar_abs_detalhado.py"]
    },
    "historico_absenteismo": {
        "nome": "Histórico Absenteísmo LEAP",
        "url_api": "http://hanger.dafiticorp.com:8080/jenkins/job/GLOVE_FILE_fabric.m_historico_abs_cd_operacao_leap/api/json",
        "scripts": ["atualizar_absenteismo.py", "atualizar_abs_detalhado.py"]
    }
}

# ==========================================
# 2. FUNÇÕES DE SUPORTE E HISTÓRICO
# ==========================================
def carregar_estado():
    if os.path.exists(ARQUIVO_ESTADO):
        try:
            with open(ARQUIVO_ESTADO, "r", encoding="utf-8") as f:
                dados = json.load(f)
                if "tarefas_diarias" not in dados:
                    dados["tarefas_diarias"] = {}
                return dados
        except Exception:
            pass
    return {"builds": {}, "historico": {}, "tarefas_diarias": {}}


def salvar_estado(estado):
    try:
        with open(ARQUIVO_ESTADO, "w", encoding="utf-8") as f:
            json.dump(estado, f, indent=4)
    except Exception as e:
        print(f"Erro ao salvar estado: {e}")


def atualizar_arquivo_log(estado):
    """Reescreve o orquestrador.log mantendo as 2 últimas execuções de cada tarefa e janela ativa."""
    agora = datetime.now()
    hora_agora_str = agora.strftime("%d/%m/%Y %H:%M:%S")
    hora_atual = agora.time()
    historico = estado.get("historico", {})

    em_janela_jenkins = HORA_INICIO_JENKINS <= hora_atual <= HORA_FIM_JENKINS
    status_janela = "ATIVO (06:00 às 23:59)" if em_janela_jenkins else "PAUSADO (Aguardando 06:00)"

    linhas = [
        "==================================================================",
        f" PAINEL DE MONITORAMENTO JENKINS (Última Checagem: {hora_agora_str})",
        f" Status Jenkins: {status_janela}",
        "==================================================================",
        ""
    ]

    # 1. Bloco da Tarefa Diária (Scraper)
    chave_scraper = TAREFA_DIARIA_SCRAPER["chave"]
    nome_scraper = TAREFA_DIARIA_SCRAPER["nome"]
    reg_scraper = historico.get(chave_scraper, [])

    linhas.append(f"🕷️ {nome_scraper.upper()} (Diário a partir das 01:00):")
    if not reg_scraper:
        linhas.append("   (Aguardando primeira execução às 01:00)")
    elif len(reg_scraper) == 1:
        r = reg_scraper[0]
        linhas.append(f"   • ÚLTIMA VEZ:    {r['data_hora']} | Execução: {r['build']} | Duração: {r['duracao']}s | Status: {r['status']}")
        linhas.append("   • PENÚLTIMA VEZ: (Aguardando próxima execução diária)")
    else:
        penultima = reg_scraper[0]
        ultima = reg_scraper[1]
        linhas.append(f"   • PENÚLTIMA VEZ: {penultima['data_hora']} | Execução: {penultima['build']} | Duração: {penultima['duracao']}s | Status: {penultima['status']}")
        linhas.append(f"   • ÚLTIMA VEZ:    {ultima['data_hora']} | Execução: {ultima['build']} | Duração: {ultima['duracao']}s | Status: {ultima['status']}")
    linhas.append("")

    # 2. Blocos das Esteiras Jenkins
    for chave, config in CONFIG_JOBS.items():
        nome = config["nome"]
        registros = historico.get(chave, [])

        linhas.append(f"📌 {nome.upper()}:")
        if not registros:
            linhas.append("   (Aguardando próxima atualização)")
        elif len(registros) == 1:
            r = registros[0]
            linhas.append(f"   • ÚLTIMA VEZ:    {r['data_hora']} | Build #{r['build']} | Duração: {r['duracao']}s | Status: {r['status']}")
            linhas.append("   • PENÚLTIMA VEZ: (Aguardando próxima atualização)")
        else:
            penultima = registros[0]
            ultima = registros[1]
            linhas.append(f"   • PENÚLTIMA VEZ: {penultima['data_hora']} | Build #{penultima['build']} | Duração: {penultima['duracao']}s | Status: {penultima['status']}")
            linhas.append(f"   • ÚLTIMA VEZ:    {ultima['data_hora']} | Build #{ultima['build']} | Duração: {ultima['duracao']}s | Status: {ultima['status']}")
        linhas.append("")

    linhas.append("------------------------------------------------------------------")
    linhas.append("⏱️ Monitoramento ativo rodando em segundo plano (checagem a cada 5 min).")
    linhas.append("==================================================================")

    try:
        with open(ARQUIVO_LOG, "w", encoding="utf-8") as f:
            f.write("\n".join(linhas) + "\n")
    except Exception as e:
        print(f"Erro ao atualizar orquestrador.log: {e}")


def registrar_execucao_historico(chave_job, identificador_build, duracao, status, estado):
    """Garante que a lista mantém apenas os 2 últimos registros na memória e no log."""
    if "historico" not in estado:
        estado["historico"] = {}
    if chave_job not in estado["historico"]:
        estado["historico"][chave_job] = []

    novo_registro = {
        "data_hora": datetime.now().strftime("%d/%m/%Y às %H:%M:%S"),
        "build": identificador_build,
        "duracao": duracao,
        "status": status
    }

    estado["historico"][chave_job].append(novo_registro)

    if len(estado["historico"][chave_job]) > 2:
        estado["historico"][chave_job] = estado["historico"][chave_job][-2:]

    salvar_estado(estado)
    atualizar_arquivo_log(estado)


def executar_scripts(lista_scripts, timeout_segundos=1800):
    """Executa scripts sequencialmente com timeout protetor contra travamentos infinitos."""
    inicio_total = time.time()
    env_utf8 = os.environ.copy()
    env_utf8["PYTHONIOENCODING"] = "utf-8"

    for script in lista_scripts:
        try:
            resultado = subprocess.run(
                [sys.executable, script],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env_utf8,
                check=False,
                timeout=timeout_segundos
            )
            if resultado.returncode != 0:
                duracao = round(time.time() - inicio_total, 1)
                return False, duracao
        except Exception:
            duracao = round(time.time() - inicio_total, 1)
            return False, duracao

    duracao = round(time.time() - inicio_total, 1)
    return True, duracao


# ==========================================
# 3. VERIFICAÇÃO DE TAREFAS AGENDADAS E JENKINS
# ==========================================
def checar_tarefa_diaria_scraper(estado):
    """Executa o scraper_dafiti.py uma vez por dia a partir das 01:00:00."""
    agora = datetime.now()
    hora_atual = agora.time()
    data_hoje_str = agora.strftime("%Y-%m-%d")

    chave = TAREFA_DIARIA_SCRAPER["chave"]
    hora_alvo = TAREFA_DIARIA_SCRAPER["hora_inicio"]
    scripts_alvo = TAREFA_DIARIA_SCRAPER["scripts"]

    if "tarefas_diarias" not in estado:
        estado["tarefas_diarias"] = {}

    ultima_data_executada = estado["tarefas_diarias"].get(chave)

    # Dispara se já passou das 01:00:00 e ainda não rodou hoje
    if hora_atual >= hora_alvo and ultima_data_executada != data_hoje_str:
        # Marca a data antes/durante para evitar disparos repetidos
        estado["tarefas_diarias"][chave] = data_hoje_str
        salvar_estado(estado)

        # Timeout ampliado para 3 horas (10800s) caso o web scraping demore
        sucesso, duracao = executar_scripts(scripts_alvo, timeout_segundos=10800)
        status_txt = "SUCESSO" if sucesso else "FALHA"
        registrar_execucao_historico(chave, agora.strftime("%d/%m/%Y"), duracao, status_txt, estado)


def checar_job(chave_job, config, estado):
    url = config["url_api"]
    scripts_alvo = config["scripts"]

    if "builds" not in estado:
        estado["builds"] = {}

    try:
        resposta = requests.get(url, auth=JENKINS_AUTH, timeout=15)
        if resposta.status_code == 200:
            dados = resposta.json()
            ultimo_build_sucesso = dados.get("lastSuccessfulBuild")

            if not ultimo_build_sucesso:
                return

            build_atual = ultimo_build_sucesso.get("number")
            ultimo_processado = estado["builds"].get(chave_job)

            # Primeira checagem da chave
            if ultimo_processado is None or ultimo_processado == 0:
                estado["builds"][chave_job] = build_atual
                salvar_estado(estado)
                registrar_execucao_historico(chave_job, build_atual, 0.0, "Inicializado", estado)

            # Novo build identificado
            elif build_atual > ultimo_processado:
                sucesso, duracao = executar_scripts(scripts_alvo, timeout_segundos=1800)
                status_txt = "SUCESSO" if sucesso else "FALHA"
                registrar_execucao_historico(chave_job, build_atual, duracao, status_txt, estado)

                # Salva o build mesmo que falhe, para o orquestrador não ficar em loop na mesma falha
                estado["builds"][chave_job] = build_atual
                salvar_estado(estado)

    except Exception:
        pass


# ==========================================
# 4. LOOP PRINCIPAL
# ==========================================
if __name__ == "__main__":
    estado = carregar_estado()
    atualizar_arquivo_log(estado)

    while True:
        try:
            agora = datetime.now()
            hora_atual = agora.time()

            # 1. Verifica tarefa diária do Scraper (a partir das 01:00:00)
            checar_tarefa_diaria_scraper(estado)

            # 2. Verifica esteiras do Jenkins apenas entre 06:00:00 e 23:59:59
            if HORA_INICIO_JENKINS <= hora_atual <= HORA_FIM_JENKINS:
                for chave, config in CONFIG_JOBS.items():
                    checar_job(chave, config, estado)

            atualizar_arquivo_log(estado)
        except Exception as e:
            print(f"Erro no ciclo: {e}")

        time.sleep(INTERVALO_CHECAGEM_SEGUNDOS)