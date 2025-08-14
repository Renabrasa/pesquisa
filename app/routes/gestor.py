from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from app.utils.database import execute_query
from app.routes.auth import login_required, gestor_required
import hashlib
import json

bp = Blueprint('gestor', __name__)

def hash_password(password):
    """Criar hash MD5 da senha"""
    return hashlib.md5(password.encode()).hexdigest()

@bp.route('/')
@gestor_required
def dashboard():
    # Métricas gerais (todas as pesquisas)
    query_metricas = """
    SELECT 
        COUNT(*) as total_pesquisas,
        SUM(CASE WHEN respondida = TRUE THEN 1 ELSE 0 END) as respondidas,
        SUM(CASE WHEN respondida = FALSE AND data_expiracao > NOW() THEN 1 ELSE 0 END) as pendentes,
        SUM(CASE WHEN respondida = FALSE AND data_expiracao <= NOW() THEN 1 ELSE 0 END) as expiradas,
        ROUND(
            (SUM(CASE WHEN respondida = TRUE THEN 1 ELSE 0 END) * 100.0) / 
            NULLIF(COUNT(*), 0), 1
        ) as taxa_resposta,
        COUNT(DISTINCT codigo_cliente) as clientes_unicos
    FROM pesquisas
    """
    
    metricas_result = execute_query(query_metricas, fetch=True)
    metricas = metricas_result[0] if metricas_result else {
        'total_pesquisas': 0, 'respondidas': 0, 'pendentes': 0, 
        'expiradas': 0, 'taxa_resposta': 0, 'clientes_unicos': 0
    }
    
    # Métricas por produto
    query_por_produto = """
    SELECT 
        tp.nome,
        COUNT(p.id) as total,
        SUM(CASE WHEN p.respondida = TRUE THEN 1 ELSE 0 END) as respondidas,
        ROUND(
            (SUM(CASE WHEN p.respondida = TRUE THEN 1 ELSE 0 END) * 100.0) / 
            NULLIF(COUNT(p.id), 0), 1
        ) as taxa,
        ROUND(AVG(
            CASE 
                WHEN r.resposta_texto = 'Muito Satisfeito' THEN 5
                WHEN r.resposta_texto = 'Satisfeito' THEN 4
                WHEN r.resposta_texto = 'Neutro' THEN 3
                WHEN r.resposta_texto = 'Insatisfeito' THEN 2
                WHEN r.resposta_texto = 'Muito Insatisfeito' THEN 1
                ELSE NULL
            END
        ), 1) as media_satisfacao
    FROM tipos_produtos tp
    LEFT JOIN pesquisas p ON tp.id = p.tipo_produto_id
    LEFT JOIN respostas r ON p.id = r.pesquisa_id AND r.resposta_texto IN ('Muito Satisfeito', 'Satisfeito', 'Neutro', 'Insatisfeito', 'Muito Insatisfeito')
    GROUP BY tp.id, tp.nome
    ORDER BY tp.nome
    """
    
    por_produto = execute_query(query_por_produto, fetch=True) or []
    
    # Métricas por agente
    query_por_agente = """
    SELECT 
        COALESCE(u.nome, 'Agente Desconhecido') as nome,
        COUNT(p.id) as total,
        SUM(CASE WHEN p.respondida = TRUE THEN 1 ELSE 0 END) as respondidas,
        ROUND(
            (SUM(CASE WHEN p.respondida = TRUE THEN 1 ELSE 0 END) * 100.0) / 
            NULLIF(COUNT(p.id), 0), 1
        ) as taxa
    FROM pesquisas p
    LEFT JOIN usuarios u ON p.agente_id = u.id
    GROUP BY p.agente_id, u.nome
    ORDER BY total DESC
    """
    
    por_agente = execute_query(query_por_agente, fetch=True) or []
    
    # Métricas temporais
    query_esta_semana = """
    SELECT 
        COUNT(*) as criadas,
        SUM(CASE WHEN respondida = TRUE THEN 1 ELSE 0 END) as respondidas,
        ROUND(
            (SUM(CASE WHEN respondida = TRUE THEN 1 ELSE 0 END) * 100.0) / 
            NULLIF(COUNT(*), 0), 1
        ) as taxa
    FROM pesquisas 
    WHERE YEARWEEK(created_at, 1) = YEARWEEK(CURDATE(), 1)
    """
    
    query_semana_passada = """
    SELECT 
        COUNT(*) as criadas,
        SUM(CASE WHEN respondida = TRUE THEN 1 ELSE 0 END) as respondidas,
        ROUND(
            (SUM(CASE WHEN respondida = TRUE THEN 1 ELSE 0 END) * 100.0) / 
            NULLIF(COUNT(*), 0), 1
        ) as taxa
    FROM pesquisas 
    WHERE YEARWEEK(created_at, 1) = YEARWEEK(CURDATE(), 1) - 1
    """
    
    query_este_mes = """
    SELECT 
        COUNT(*) as criadas,
        SUM(CASE WHEN respondida = TRUE THEN 1 ELSE 0 END) as respondidas,
        ROUND(
            (SUM(CASE WHEN respondida = TRUE THEN 1 ELSE 0 END) * 100.0) / 
            NULLIF(COUNT(*), 0), 1
        ) as taxa
    FROM pesquisas 
    WHERE YEAR(created_at) = YEAR(CURDATE()) 
    AND MONTH(created_at) = MONTH(CURDATE())
    """
    
    query_mes_passado = """
    SELECT 
        COUNT(*) as criadas,
        SUM(CASE WHEN respondida = TRUE THEN 1 ELSE 0 END) as respondidas,
        ROUND(
            (SUM(CASE WHEN respondida = TRUE THEN 1 ELSE 0 END) * 100.0) / 
            NULLIF(COUNT(*), 0), 1
        ) as taxa
    FROM pesquisas 
    WHERE YEAR(created_at) = YEAR(CURDATE() - INTERVAL 1 MONTH) 
    AND MONTH(created_at) = MONTH(CURDATE() - INTERVAL 1 MONTH)
    """
    
    esta_semana_result = execute_query(query_esta_semana, fetch=True)
    esta_semana = esta_semana_result[0] if esta_semana_result else {'criadas': 0, 'respondidas': 0, 'taxa': 0}
    esta_semana = {k: v or 0 for k, v in esta_semana.items()}
    
    semana_passada_result = execute_query(query_semana_passada, fetch=True)
    semana_passada = semana_passada_result[0] if semana_passada_result else {'criadas': 0, 'respondidas': 0, 'taxa': 0}
    semana_passada = {k: v or 0 for k, v in semana_passada.items()}
    
    este_mes_result = execute_query(query_este_mes, fetch=True)
    este_mes = este_mes_result[0] if este_mes_result else {'criadas': 0, 'respondidas': 0, 'taxa': 0}
    este_mes = {k: v or 0 for k, v in este_mes.items()}
    
    mes_passado_result = execute_query(query_mes_passado, fetch=True)
    mes_passado = mes_passado_result[0] if mes_passado_result else {'criadas': 0, 'respondidas': 0, 'taxa': 0}
    mes_passado = {k: v or 0 for k, v in mes_passado.items()}
    
    # Gerar alertas
    alertas = []
    
    # Alerta de baixa taxa de resposta
    if metricas['taxa_resposta'] < 50:
        alertas.append({
            'tipo': 'warning',
            'titulo': 'Taxa de Resposta Baixa',
            'mensagem': f'Taxa atual: {metricas["taxa_resposta"]}%. Considere revisar os links.'
        })
    
    # Alerta de muitas pesquisas expiradas
    if metricas['expiradas'] > metricas['respondidas']:
        alertas.append({
            'tipo': 'danger',
            'titulo': 'Muitas Expiradas',
            'mensagem': f'{metricas["expiradas"]} pesquisas expiraram sem resposta.'
        })
    
    # Alerta de queda na performance
    if esta_semana['taxa'] and semana_passada['taxa'] and esta_semana['taxa'] < semana_passada['taxa'] - 10:
        alertas.append({
            'tipo': 'warning',
            'titulo': 'Queda na Performance',
            'mensagem': f'Taxa caiu {semana_passada["taxa"] - esta_semana["taxa"]:.1f}% esta semana.'
        })
    
    # Organizar métricas
    metricas_completas = {
        'total_pesquisas': metricas['total_pesquisas'],
        'respondidas': metricas['respondidas'],
        'pendentes': metricas['pendentes'],
        'expiradas': metricas['expiradas'],
        'taxa_resposta': metricas['taxa_resposta'],
        'clientes_unicos': metricas['clientes_unicos'],
        'por_produto': por_produto,
        'por_agente': por_agente,
        'esta_semana': esta_semana,
        'semana_passada': semana_passada,
        'este_mes': este_mes,
        'mes_passado': mes_passado,
        'alertas': alertas
    }
    
    # Buscar pesquisas recentes para a tabela
    query_pesquisas = """
    SELECT p.*, tp.nome as tipo_produto, u.nome as agente_nome,
           CASE 
               WHEN p.data_expiracao < NOW() THEN 'expirada'
               WHEN p.respondida = TRUE THEN 'respondida'
               ELSE 'ativa'
           END as status_pesquisa
    FROM pesquisas p
    LEFT JOIN tipos_produtos tp ON p.tipo_produto_id = tp.id
    LEFT JOIN usuarios u ON p.agente_id = u.id
    ORDER BY p.created_at DESC
    LIMIT 20
    """
    
    pesquisas = execute_query(query_pesquisas, fetch=True) or []
    
    return render_template('gestor/dashboard.html', 
                         metricas=metricas_completas, 
                         pesquisas=pesquisas)

@bp.route('/detalhes/<int:pesquisa_id>')
@gestor_required
def detalhes(pesquisa_id):
    # Buscar pesquisa
    query_pesquisa = """
    SELECT p.*, tp.nome as tipo_produto, u.nome as agente_nome
    FROM pesquisas p
    LEFT JOIN tipos_produtos tp ON p.tipo_produto_id = tp.id
    LEFT JOIN usuarios u ON p.agente_id = u.id
    WHERE p.id = %s
    """
    
    pesquisa_result = execute_query(query_pesquisa, (pesquisa_id,), fetch=True)
    if not pesquisa_result:
        return "Pesquisa não encontrada", 404
    
    pesquisa = pesquisa_result[0]
    
    # Buscar respostas
    query_respostas = """
    SELECT r.*, pg.texto as pergunta_texto
    FROM respostas r
    LEFT JOIN perguntas pg ON r.pergunta_id = pg.id
    WHERE r.pesquisa_id = %s
    ORDER BY pg.ordem
    """
    
    respostas = execute_query(query_respostas, (pesquisa_id,), fetch=True) or []
    
    return render_template('gestor/detalhes.html', pesquisa=pesquisa, respostas=respostas)

# ===== ROTAS DE GERENCIAMENTO DE PERGUNTAS =====

@bp.route('/perguntas')
@gestor_required
def perguntas():
    """Gerenciar perguntas do sistema"""
    
    # Buscar produtos
    query_produtos = "SELECT id, nome FROM tipos_produtos ORDER BY nome"
    produtos = execute_query(query_produtos, fetch=True) or []
    
    # Buscar tipos de perguntas
    query_tipos = "SELECT id, nome, descricao FROM tipos_perguntas ORDER BY nome"
    tipos_perguntas = execute_query(query_tipos, fetch=True) or []
    
    # Buscar perguntas agrupadas por produto
    query_perguntas = """
    SELECT p.*, tp.nome as tipo_nome
    FROM perguntas p
    LEFT JOIN tipos_perguntas tp ON p.tipo_pergunta_id = tp.id
    ORDER BY p.tipo_produto_id, p.ordem
    """
    
    perguntas_todas = execute_query(query_perguntas, fetch=True) or []
    
    # Agrupar perguntas por produto
    perguntas_por_produto = {}
    for produto in produtos:
        perguntas_por_produto[produto['id']] = [
            p for p in perguntas_todas if p['tipo_produto_id'] == produto['id']
        ]
        
        # Processar opções JSON
        for pergunta in perguntas_por_produto[produto['id']]:
            if pergunta['opcoes']:
                try:
                    pergunta['opcoes'] = json.loads(pergunta['opcoes'])
                except:
                    pergunta['opcoes'] = []
    
    return render_template('gestor/perguntas.html', 
                         produtos=produtos,
                         tipos_perguntas=tipos_perguntas,
                         perguntas_por_produto=perguntas_por_produto)

@bp.route('/perguntas/nova', methods=['POST'])
@gestor_required
def nova_pergunta():
    """Criar nova pergunta"""
    try:
        tipo_produto_id = request.form['tipo_produto_id']
        tipo_pergunta_id = request.form['tipo_pergunta_id']
        texto = request.form['texto']
        ordem = request.form['ordem']
        obrigatoria = 'obrigatoria' in request.form
        ativa = 'ativa' in request.form
        
        # Processar opções se existirem
        opcoes = None
        if 'opcoes' in request.form and request.form['opcoes']:
            try:
                opcoes = request.form['opcoes']  # Já vem como JSON do JavaScript
            except:
                opcoes = None
        
        # Inserir pergunta
        query = """
        INSERT INTO perguntas 
        (tipo_produto_id, tipo_pergunta_id, texto, ordem, obrigatoria, ativa, opcoes)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        
        result = execute_query(query, (
            tipo_produto_id, tipo_pergunta_id, texto, ordem, 
            obrigatoria, ativa, opcoes
        ))
        
        if result:
            flash('Pergunta criada com sucesso!', 'success')
        else:
            flash('Erro ao criar pergunta!', 'error')
            
    except Exception as e:
        flash(f'Erro: {str(e)}', 'error')
    
    return redirect(url_for('gestor.perguntas'))

@bp.route('/perguntas/<int:pergunta_id>/status', methods=['POST'])
@gestor_required
def alterar_status_pergunta(pergunta_id):
    """Alterar status ativo/inativo da pergunta"""
    try:
        # Buscar status atual
        query_status = "SELECT ativa FROM perguntas WHERE id = %s"
        result = execute_query(query_status, (pergunta_id,), fetch=True)
        
        if not result:
            return jsonify({'success': False, 'error': 'Pergunta não encontrada'})
        
        status_atual = result[0]['ativa']
        novo_status = not status_atual
        
        # Atualizar status
        query_update = "UPDATE perguntas SET ativa = %s WHERE id = %s"
        resultado = execute_query(query_update, (novo_status, pergunta_id))
        
        if resultado:
            return jsonify({'success': True, 'novo_status': novo_status})
        else:
            return jsonify({'success': False, 'error': 'Erro ao atualizar'})
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@bp.route('/perguntas/<int:pergunta_id>', methods=['DELETE'])
@gestor_required
def excluir_pergunta(pergunta_id):
    """Excluir pergunta"""
    try:
        print(f"Tentando excluir pergunta ID: {pergunta_id}")  # Debug
        
        # Verificar se pergunta tem respostas
        query_check = "SELECT COUNT(*) as total FROM respostas WHERE pergunta_id = %s"
        result = execute_query(query_check, (pergunta_id,), fetch=True)
        
        if result and result[0]['total'] > 0:
            print(f"Pergunta {pergunta_id} tem {result[0]['total']} respostas")  # Debug
            return jsonify({
                'success': False, 
                'error': f'Não é possível excluir pergunta que já possui {result[0]["total"]} resposta(s). Você pode desativá-la ao invés de excluir.'
            })
        
        # Verificar se pergunta existe
        query_exists = "SELECT id FROM perguntas WHERE id = %s"
        exists = execute_query(query_exists, (pergunta_id,), fetch=True)
        
        if not exists:
            print(f"Pergunta {pergunta_id} não encontrada")  # Debug
            return jsonify({'success': False, 'error': 'Pergunta não encontrada'})
        
        # Excluir pergunta
        query_delete = "DELETE FROM perguntas WHERE id = %s"
        resultado = execute_query(query_delete, (pergunta_id,))
        
        print(f"Resultado da exclusão: {resultado}")  # Debug
        
        if resultado:
            return jsonify({'success': True, 'message': 'Pergunta excluída com sucesso'})
        else:
            return jsonify({'success': False, 'error': 'Erro ao excluir pergunta'})
            
    except Exception as e:
        print(f"Erro na exclusão: {str(e)}")  # Debug
        return jsonify({'success': False, 'error': str(e)})

@bp.route('/perguntas/<int:pergunta_id>/editar', methods=['GET', 'POST'])
@gestor_required
def editar_pergunta(pergunta_id):
    """Editar pergunta existente"""
    
    # Verificar quantas respostas esta pergunta já tem
    query_respostas = "SELECT COUNT(*) as total FROM respostas WHERE pergunta_id = %s"
    result_respostas = execute_query(query_respostas, (pergunta_id,), fetch=True)
    total_respostas = result_respostas[0]['total'] if result_respostas else 0
    
    if request.method == 'POST':
        try:
            # Se já tem respostas, permitir apenas alterações "seguras"
            if total_respostas > 0:
                # Permitir apenas alteração de: ordem, obrigatória, ativa
                ordem = request.form['ordem']
                obrigatoria = 'obrigatoria' in request.form
                ativa = 'ativa' in request.form
                
                query = """
                UPDATE perguntas 
                SET ordem = %s, obrigatoria = %s, ativa = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """
                
                result = execute_query(query, (ordem, obrigatoria, ativa, pergunta_id))
                
                if result:
                    flash('Pergunta atualizada com sucesso! (Apenas campos seguros foram alterados devido às respostas existentes)', 'success')
                    return redirect(url_for('gestor.perguntas'))
                else:
                    flash('Erro ao atualizar pergunta!', 'error')
            else:
                # Sem respostas - pode alterar tudo
                tipo_produto_id = request.form['tipo_produto_id']
                tipo_pergunta_id = request.form['tipo_pergunta_id']
                texto = request.form['texto']
                ordem = request.form['ordem']
                obrigatoria = 'obrigatoria' in request.form
                ativa = 'ativa' in request.form
                
                # Processar opções se existirem
                opcoes = None
                if 'opcoes' in request.form and request.form['opcoes']:
                    try:
                        opcoes = request.form['opcoes']  # Já vem como JSON do JavaScript
                    except:
                        opcoes = None
                
                # Atualizar pergunta completa
                query = """
                UPDATE perguntas 
                SET tipo_produto_id = %s, tipo_pergunta_id = %s, texto = %s, 
                    ordem = %s, obrigatoria = %s, ativa = %s, opcoes = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """
                
                result = execute_query(query, (
                    tipo_produto_id, tipo_pergunta_id, texto, ordem, 
                    obrigatoria, ativa, opcoes, pergunta_id
                ))
                
                if result:
                    flash('Pergunta atualizada com sucesso!', 'success')
                    return redirect(url_for('gestor.perguntas'))
                else:
                    flash('Erro ao atualizar pergunta!', 'error')
                
        except Exception as e:
            flash(f'Erro: {str(e)}', 'error')
    
    # GET - Mostrar formulário de edição
    # Buscar dados da pergunta
    query_pergunta = """
    SELECT p.*, tp.nome as tipo_nome
    FROM perguntas p
    LEFT JOIN tipos_perguntas tp ON p.tipo_pergunta_id = tp.id
    WHERE p.id = %s
    """
    
    result = execute_query(query_pergunta, (pergunta_id,), fetch=True)
    if not result:
        flash('Pergunta não encontrada!', 'error')
        return redirect(url_for('gestor.perguntas'))
    
    pergunta = result[0]
    
    # Processar opções JSON
    if pergunta['opcoes']:
        try:
            pergunta['opcoes'] = json.loads(pergunta['opcoes'])
        except:
            pergunta['opcoes'] = []
    else:
        pergunta['opcoes'] = []
    
    # Buscar produtos
    query_produtos = "SELECT id, nome FROM tipos_produtos ORDER BY nome"
    produtos = execute_query(query_produtos, fetch=True) or []
    
    # Buscar tipos de perguntas
    query_tipos = "SELECT id, nome, descricao FROM tipos_perguntas ORDER BY nome"
    tipos_perguntas = execute_query(query_tipos, fetch=True) or []
    
    return render_template('gestor/editar_pergunta.html', 
                         pergunta=pergunta,
                         produtos=produtos,
                         tipos_perguntas=tipos_perguntas,
                         total_respostas=total_respostas)

# ===== ROTAS DE GERENCIAMENTO DE USUÁRIOS =====

@bp.route('/usuarios')
@gestor_required
def usuarios():
    """Gerenciar usuários do sistema"""
    query = """
    SELECT u.*, 
           COUNT(p.id) as total_pesquisas,
           SUM(CASE WHEN p.respondida = TRUE THEN 1 ELSE 0 END) as pesquisas_respondidas
    FROM usuarios u
    LEFT JOIN pesquisas p ON u.id = p.agente_id
    GROUP BY u.id
    ORDER BY u.nome
    """
    
    usuarios = execute_query(query, fetch=True) or []
    return render_template('gestor/usuarios.html', usuarios=usuarios)

@bp.route('/usuarios/novo', methods=['GET', 'POST'])
@gestor_required
def novo_usuario():
    """Criar novo usuário"""
    if request.method == 'POST':
        nome = request.form['nome']
        email = request.form['email']
        senha = request.form['senha']
        tipo_usuario = request.form['tipo_usuario']
        
        # Verificar se email já existe
        query_check = "SELECT id FROM usuarios WHERE email = %s"
        if execute_query(query_check, (email,), fetch=True):
            flash('E-mail já cadastrado!', 'error')
            return render_template('gestor/novo_usuario.html')
        
        # Inserir novo usuário
        query_insert = """
        INSERT INTO usuarios (nome, email, senha_hash, tipo_usuario)
        VALUES (%s, %s, %s, %s)
        """
        
        senha_hash = hash_password(senha)
        result = execute_query(query_insert, (nome, email, senha_hash, tipo_usuario))
        
        if result:
            flash('Usuário criado com sucesso!', 'success')
            return redirect(url_for('gestor.usuarios'))
        else:
            flash('Erro ao criar usuário!', 'error')
    
    return render_template('gestor/novo_usuario.html')

@bp.route('/usuarios/editar/<int:user_id>', methods=['GET', 'POST'])
@gestor_required
def editar_usuario(user_id):
    """Editar usuário existente"""
    if request.method == 'POST':
        nome = request.form['nome']
        email = request.form['email']
        tipo_usuario = request.form['tipo_usuario']
        ativo = 'ativo' in request.form
        
        query_update = """
        UPDATE usuarios 
        SET nome = %s, email = %s, tipo_usuario = %s, ativo = %s
        WHERE id = %s
        """
        
        result = execute_query(query_update, (nome, email, tipo_usuario, ativo, user_id))
        
        if result:
            flash('Usuário atualizado com sucesso!', 'success')
            return redirect(url_for('gestor.usuarios'))
        else:
            flash('Erro ao atualizar usuário!', 'error')
    
    # Buscar dados do usuário
    query = "SELECT * FROM usuarios WHERE id = %s"
    result = execute_query(query, (user_id,), fetch=True)
    
    if not result:
        return "Usuário não encontrado", 404
    
    usuario = result[0]
    return render_template('gestor/editar_usuario.html', usuario=usuario)