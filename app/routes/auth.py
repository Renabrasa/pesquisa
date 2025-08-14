from flask import Blueprint, render_template, request, redirect, url_for, session, flash
import hashlib
from functools import wraps
from app.utils.database import execute_query
from app.utils.upload import save_avatar, delete_avatar, get_default_avatar

bp = Blueprint('auth', __name__)

def hash_password(password):
    """Criar hash MD5 da senha"""
    return hashlib.md5(password.encode()).hexdigest()

def check_password(password, hash_stored):
    """Verificar se a senha está correta"""
    return hash_password(password) == hash_stored

def login_required(f):
    """Decorador para rotas que precisam de login"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

def gestor_required(f):
    """Decorador para rotas que precisam de perfil gestor"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('auth.login'))
        if session.get('user_type') != 'gestor':
            return "Acesso negado - Apenas gestores", 403
        return f(*args, **kwargs)
    return decorated_function

@bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        senha = request.form['senha']
        
        # Buscar usuário no banco
        query = """
        SELECT id, nome, email, senha_hash, tipo_usuario, ativo, foto_url
        FROM usuarios 
        WHERE email = %s AND ativo = TRUE
        """
        
        result = execute_query(query, (email,), fetch=True)
        
        if result and check_password(senha, result[0]['senha_hash']):
            user = result[0]
            
            # Criar sessão
            session['user_id'] = user['id']
            session['user_name'] = user['nome']
            session['user_email'] = user['email']
            session['user_type'] = user['tipo_usuario']
            session['user_foto'] = user['foto_url'] or get_default_avatar()
            
            # Redirecionar baseado no tipo de usuário
            if user['tipo_usuario'] == 'gestor':
                return redirect(url_for('gestor.dashboard'))
            else:
                return redirect(url_for('agente.dashboard'))
        else:
            return render_template('auth/login.html', error='E-mail ou senha incorretos')
    
    return render_template('auth/login.html')

@bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('auth.login'))

@bp.route('/perfil')
@login_required
def perfil():
    """Visualizar perfil do usuário"""
    user_id = session['user_id']
    
    # Buscar dados do usuário
    query = """
    SELECT u.*, 
           COUNT(p.id) as total_pesquisas,
           SUM(CASE WHEN p.respondida = TRUE THEN 1 ELSE 0 END) as pesquisas_respondidas,
           MAX(p.created_at) as ultima_pesquisa
    FROM usuarios u
    LEFT JOIN pesquisas p ON u.id = p.agente_id
    WHERE u.id = %s
    GROUP BY u.id
    """
    
    result = execute_query(query, (user_id,), fetch=True)
    
    if not result:
        flash('Usuário não encontrado!', 'error')
        return redirect(url_for('auth.logout'))
    
    usuario = result[0]
    
    # Garantir foto padrão se não tiver
    if not usuario['foto_url']:
        usuario['foto_url'] = get_default_avatar()
    
    return render_template('auth/perfil.html', usuario=usuario)

# SUBSTITUIR a função editar_perfil() no arquivo: app/routes/auth.py
# Localizar a função atual e substituir por esta versão atualizada

@bp.route('/perfil/editar', methods=['GET', 'POST'])
@login_required
def editar_perfil():
    """Editar dados do perfil"""
    user_id = session['user_id']
    
    if request.method == 'POST':
        nome = request.form['nome']
        email = request.form['email']
        
        # Verificar se email já existe (exceto o próprio usuário)
        query_check = "SELECT id FROM usuarios WHERE email = %s AND id != %s"
        if execute_query(query_check, (email, user_id), fetch=True):
            flash('E-mail já está sendo usado por outro usuário!', 'error')
            return redirect(url_for('auth.editar_perfil'))
        
        # Processar configurações de alertas (apenas para gestores)
        alerta_time_is_money = False
        alerta_servidor_nuvem = False
        
        if session.get('user_type') == 'gestor':
            alerta_time_is_money = 'alerta_time_is_money' in request.form
            alerta_servidor_nuvem = 'alerta_servidor_nuvem' in request.form
        
        # Processar upload de foto
        foto_url = None
        if 'foto' in request.files:
            file = request.files['foto']
            if file and file.filename != '':
                try:
                    # Buscar foto atual para deletar depois
                    query_foto_atual = "SELECT foto_url FROM usuarios WHERE id = %s"
                    result_foto = execute_query(query_foto_atual, (user_id,), fetch=True)
                    foto_atual = result_foto[0]['foto_url'] if result_foto else None
                    
                    # Salvar nova foto
                    foto_url = save_avatar(file, user_id)
                    
                    if foto_url:
                        # Deletar foto anterior se não for a padrão
                        if foto_atual and foto_atual != get_default_avatar():
                            delete_avatar(foto_atual)
                    else:
                        flash('Erro ao fazer upload da foto. Verifique o formato e tamanho.', 'error')
                        return redirect(url_for('auth.editar_perfil'))
                        
                except Exception as e:
                    flash(f'Erro ao processar foto: {str(e)}', 'error')
                    return redirect(url_for('auth.editar_perfil'))
        
        # Atualizar dados (incluindo alertas)
        if foto_url:
            query_update = """
            UPDATE usuarios 
            SET nome = %s, email = %s, foto_url = %s, 
                alerta_time_is_money = %s, alerta_servidor_nuvem = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            """
            params = (nome, email, foto_url, alerta_time_is_money, alerta_servidor_nuvem, user_id)
        else:
            query_update = """
            UPDATE usuarios 
            SET nome = %s, email = %s, 
                alerta_time_is_money = %s, alerta_servidor_nuvem = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            """
            params = (nome, email, alerta_time_is_money, alerta_servidor_nuvem, user_id)
        
        result = execute_query(query_update, params)
        
        if result:
            # Atualizar sessão
            session['user_name'] = nome
            session['user_email'] = email
            if foto_url:
                session['user_foto'] = foto_url
            
            flash('Perfil atualizado com sucesso!', 'success')
            return redirect(url_for('auth.perfil'))
        else:
            flash('Erro ao atualizar perfil!', 'error')
    
    # Buscar dados atuais (incluindo alertas)
    query = """
    SELECT id, nome, email, foto_url, tipo_usuario, created_at, updated_at,
           alerta_time_is_money, alerta_servidor_nuvem
    FROM usuarios 
    WHERE id = %s
    """
    result = execute_query(query, (user_id,), fetch=True)
    
    if not result:
        return redirect(url_for('auth.logout'))
    
    usuario = result[0]
    
    # Garantir foto padrão se não tiver
    if not usuario['foto_url']:
        usuario['foto_url'] = get_default_avatar()
    
    return render_template('auth/editar_perfil.html', usuario=usuario)

@bp.route('/alterar-senha', methods=['GET', 'POST'])
@login_required
def alterar_senha():
    """Alterar senha do usuário"""
    user_id = session['user_id']
    
    if request.method == 'POST':
        senha_atual = request.form['senha_atual']
        nova_senha = request.form['nova_senha']
        confirmar_senha = request.form['confirmar_senha']
        
        # Verificar senha atual
        query = "SELECT senha_hash FROM usuarios WHERE id = %s"
        result = execute_query(query, (user_id,), fetch=True)
        
        if not result or not check_password(senha_atual, result[0]['senha_hash']):
            flash('Senha atual incorreta!', 'error')
            return render_template('auth/alterar_senha.html')
        
        # Verificar se nova senha e confirmação coincidem
        if nova_senha != confirmar_senha:
            flash('Nova senha e confirmação não coincidem!', 'error')
            return render_template('auth/alterar_senha.html')
        
        # Verificar se nova senha tem pelo menos 6 caracteres
        if len(nova_senha) < 6:
            flash('Nova senha deve ter pelo menos 6 caracteres!', 'error')
            return render_template('auth/alterar_senha.html')
        
        # Atualizar senha
        nova_senha_hash = hash_password(nova_senha)
        query_update = """
        UPDATE usuarios 
        SET senha_hash = %s, updated_at = CURRENT_TIMESTAMP
        WHERE id = %s
        """
        
        result = execute_query(query_update, (nova_senha_hash, user_id))
        
        if result:
            flash('Senha alterada com sucesso!', 'success')
            return redirect(url_for('auth.perfil'))
        else:
            flash('Erro ao alterar senha!', 'error')
    
    return render_template('auth/alterar_senha.html')