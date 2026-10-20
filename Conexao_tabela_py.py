#pip install mssql-cli
#pip install sqlalchemy
#pip install openpyxl
# ==========================================
# 0. Importação de Bibliotecas e Filtros
# ==========================================
import warnings
import pandas as pd
import pyodbc

# Oculta avisos de compatibilidade do Pandas no terminal
warnings.filterwarnings("ignore", category=UserWarning)

# ==========================================
# 1. Parâmetros de Conexão à Base de Dados
# ==========================================
# Configurações do servidor Amazon Redshift
driver = "Amazon Redshift ODBC Driver (x64)"
server = "gfg-dwh-prod.dafiti.io"
porta = "5439"
database = "dftdwh"
username = "silasaquino"
password = "OVpnlp09"

# ==========================================
# 2. Construção da String de Conexão (ODBC)
# ==========================================
string_conexao = (
    f"DRIVER={{{driver}}};"
    f"Server={server};"
    f"Port={porta};"
    f"Database={database};"
    f"UID={username};"
    f"PWD={password};"
)

# ==========================================
# 3. Execução da Conexão e Consulta SQL
# ==========================================
try:
    print(">>> SCRIPT V5 - APENAS EXIBIÇÃO DE DADOS (SEM FICHEIRO) <<<")

    # Estabelece a ligação à base de dados no Redshift
    conexao = pyodbc.connect(string_conexao, timeout=15)
    print("Conexão estabelecida com sucesso!")

    # ------------------------------------------
    # 4. Definição da Query SQL
    # ------------------------------------------
    # Trazemos as primeiras 100 linhas da tabela
    query_sql = """
        SELECT * 
        FROM curated_data.a_operation_returns 
        LIMIT 100;
    """

    print("A executar a consulta no Redshift...")

    # Leitura dos dados diretamente para o Pandas de forma limpa
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        df_dados = pd.read_sql_query(query_sql, conexao)

    # ------------------------------------------
    # 5. Exibição dos Dados no Terminal
    # ------------------------------------------
    print("\n==========================================")
    print(f"Total de linhas e colunas extraídas: {df_dados.shape}")
    print("------------------------------------------")
    print("Primeiras 5 linhas do resultado:")
    print(df_dados.head())
    print("==========================================")

    # ------------------------------------------
    # 6. Encerramento Seguro da Conexão
    # ------------------------------------------
    conexao.close()
    print("\nConexão encerrada com sucesso.")

except pyodbc.Error as erro:
    print("\nErro de base de dados:")
    print(erro)
except Exception as erro_geral:
    print("\nErro geral na aplicação:")
    print(erro_geral)