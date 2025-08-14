import pymysql
import os
from dotenv import load_dotenv

load_dotenv()

# Configuração do banco
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', 3306)),
    'user': os.getenv('DB_USER', 'root'),
    'password': os.getenv('DB_PASSWORD', ''),
    'database': os.getenv('DB_NAME', 'sistema_pesquisa'),
    'charset': 'utf8mb4'
}

def get_db_connection():
    """Criar conexão com o banco de dados"""
    try:
        connection = pymysql.connect(**DB_CONFIG)
        return connection
    except Exception as e:
        print(f"Erro na conexão: {e}")
        return None

def execute_query(query, params=None, fetch=False):
    """Executar query no banco"""
    connection = get_db_connection()
    if not connection:
        return None
    
    try:
        with connection.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(query, params)
            if fetch:
                result = cursor.fetchall()
            else:
                connection.commit()
                result = cursor.rowcount
        return result
    except Exception as e:
        print(f"Erro na query: {e}")
        return None
    finally:
        connection.close()