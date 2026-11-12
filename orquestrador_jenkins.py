import os
import sys
import json
import time
import socket
import subprocess
from datetime import datetime

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
# 1. CONFIGURAÇÕES DOS JOBS E SCRIPTS
# ==========================================
JENKINS_AUTH = None  # Se necessário: ("utilizador", "token_ou_senha")
INTERVALO_CHECAGEM_SEGUNDOS = 300  # 5 minutos
ARQUIVO_ESTADO = "jenkins_builds_processados.json"
ARQUIVO_LOG = "orquestrador.log"

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
                return json.load(f)
        except Exception:
            pass
    return {"builds": {}, "historico": {}}


def salvar_estado(estado):
    try:
        with open(ARQUIVO_ESTADO, "w", encoding="utf-8") as f:
            json.dump(estado, f, indent=4)
    except Exception as e:
        print(f"Erro ao salvar estado: {e}")


def atualizar_arquivo_log(estado):
    """Reescreve o orquestrador.log mantendo estritamente as 2 últimas execuções de cada tabela."""
    hora_agora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    historico = estado.get("historico", {})

    linhas = [
        "==================================================================",
        f" PAINEL DE MONITORAMENTO JENKINS (Última Checagem: {hora_agora})",
        "==================================================================",
        ""
    ]

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


def registrar_execucao_historico(chave_job, build_num, duracao, status, estado):
    """Garante que a lista mantém apenas os 2 últimos registros na memória e no log."""
    if "historico" not in estado:
        estado["historico"] = {}
    if chave_job not in estado["historico"]:
        estado["historico"][chave_job] = []

    novo_registro = {
        "data_hora": datetime.now().strftime("%d/%m/%Y às %H:%M:%S"),
        "build": build_num,
        "duracao": duracao,
        "status": status
    }

    estado["historico"][chave_job].append(novo_registro)

    if len(estado["historico"][chave_job]) > 2:
        estado["historico"][chave_job] = estado["historico"][chave_job][-2:]

    salvar_estado(estado)
    atualizar_arquivo_log(estado)


def executar_scripts(lista_scripts):
    """Executa scripts sequencialmente com timeout protetor contra travamentos infinitos."""
    inicio_total = time.time()
    env_utf8 = os.environ.copy()
    env_utf8["PYTHONIOENCODING"] = "utf-8"

    for script in lista_scripts:
        try:
            # Trava com tempo limite de 30 minutos por script
            resultado = subprocess.run(
                [sys.executable, script],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env_utf8,
                check=False,
                timeout=1800
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
# 3. VERIFICAÇÃO DO JENKINS
# ==========================================
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
                sucesso, duracao = executar_scripts(scripts_alvo)
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
            for chave, config in CONFIG_JOBS.items():
                checar_job(chave, config, estado)
            atualizar_arquivo_log(estado)
        except Exception as e:
            print(f"Erro no ciclo: {e}")

        time.sleep(INTERVALO_CHECAGEM_SEGUNDOS)