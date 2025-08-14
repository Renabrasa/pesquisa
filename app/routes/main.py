from flask import Blueprint, render_template, redirect, url_for, session
from app.utils.database import get_db_connection

bp = Blueprint('main', __name__)

@bp.route('/')
def index():
    # Se usuário não está logado, redirecionar para login
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    # Se está logado, redirecionar para o dashboard apropriado
    if session.get('user_type') == 'gestor':
        return redirect(url_for('gestor.dashboard'))
    else:
        return redirect(url_for('agente.dashboard'))

@bp.route('/teste-conexao')
def teste_conexao():
    """Testar conexão com o banco"""
    connection = get_db_connection()
    if connection:
        connection.close()
        return "✅ Conexão com banco OK!"
    else:
        return "❌ Erro na conexão com banco"