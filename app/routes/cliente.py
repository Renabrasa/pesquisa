from flask import Blueprint, render_template, request
from datetime import datetime
from app.utils.database import execute_query

bp = Blueprint('cliente', __name__)

@bp.route('/<pesquisa_uuid>')
def responder_pesquisa(pesquisa_uuid):
    # Buscar pesquisa
    query = """
    SELECT p.*, tp.nome as tipo_produto, u.nome as agente_nome, u.foto_url as agente_foto
    FROM pesquisas p
    LEFT JOIN tipos_produtos tp ON p.tipo_produto_id = tp.id
    LEFT JOIN usuarios u ON p.agente_id = u.id
    WHERE p.uuid = %s
    """
    
    result = execute_query(query, (pesquisa_uuid,), fetch=True)
    if not result:
        return "Pesquisa não encontrada", 404
    
    pesquisa = result[0]
    
    # Verificar se ainda é válida
    if pesquisa['data_expiracao'] < datetime.now():
        return render_template('cliente/expirada.html')
    
    if pesquisa['respondida']:
        return render_template('cliente/ja_respondida.html')
    
    # Buscar perguntas
    query_perguntas = """
    SELECT * FROM perguntas 
    WHERE tipo_produto_id = %s AND ativa = TRUE 
    ORDER BY ordem
    """
    
    perguntas = execute_query(query_perguntas, (pesquisa['tipo_produto_id'],), fetch=True) or []
    
    # Garantir foto padrão se agente não tiver foto
    if not pesquisa['agente_foto']:
        pesquisa['agente_foto'] = '/static/uploads/avatars/default-avatar.png'
    
    return render_template('cliente/formulario.html', pesquisa=pesquisa, perguntas=perguntas)

@bp.route('/<pesquisa_uuid>/enviar', methods=['POST'])
def enviar_resposta(pesquisa_uuid):
    try:
        # Buscar pesquisa
        query = "SELECT id FROM pesquisas WHERE uuid = %s AND respondida = FALSE"
        result = execute_query(query, (pesquisa_uuid,), fetch=True)
        
        if not result:
            return "Pesquisa não encontrada ou já respondida", 404
        
        pesquisa_id = result[0]['id']
        
        # Salvar respostas
        for campo, valor in request.form.items():
            if campo.startswith('pergunta_') and valor.strip():
                pergunta_id = campo.replace('pergunta_', '')
                
                # Determinar tipo de resposta
                if valor.isdigit():
                    query_resposta = """
                    INSERT INTO respostas (pesquisa_id, pergunta_id, resposta_numerica)
                    VALUES (%s, %s, %s)
                    """
                    params = (pesquisa_id, pergunta_id, float(valor))
                else:
                    query_resposta = """
                    INSERT INTO respostas (pesquisa_id, pergunta_id, resposta_texto)
                    VALUES (%s, %s, %s)
                    """
                    params = (pesquisa_id, pergunta_id, valor)
                
                execute_query(query_resposta, params)
        
        # Marcar pesquisa como respondida
        query_update = """
        UPDATE pesquisas 
        SET respondida = TRUE, data_resposta = NOW(), ip_resposta = %s
        WHERE id = %s
        """
        
        ip_cliente = request.environ.get('HTTP_X_FORWARDED_FOR', request.environ.get('REMOTE_ADDR'))
        execute_query(query_update, (ip_cliente, pesquisa_id))
        
        return render_template('cliente/sucesso.html')
        
    except Exception as e:
        return f"Erro ao processar resposta: {str(e)}", 500