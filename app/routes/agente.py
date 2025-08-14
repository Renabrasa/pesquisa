from flask import Blueprint, render_template, request, jsonify, session
import uuid
from datetime import datetime, timedelta
import os
from app.utils.database import execute_query
from app.routes.auth import login_required

bp = Blueprint('agente', __name__)

@bp.route('/')
@login_required
def dashboard():
    agente_id = session['user_id']  # Usar o ID do usuário logado
    
    # Métricas gerais do agente específico
    query_metricas = """
    SELECT 
        COUNT(*) as total_pesquisas,
        SUM(CASE WHEN respondida = TRUE THEN 1 ELSE 0 END) as pesquisas_respondidas,
        SUM(CASE WHEN respondida = FALSE AND data_expiracao > NOW() THEN 1 ELSE 0 END) as pesquisas_pendentes,
        ROUND(
            (SUM(CASE WHEN respondida = TRUE THEN 1 ELSE 0 END) * 100.0) / 
            NULLIF(COUNT(*), 0), 1
        ) as taxa_resposta
    FROM pesquisas 
    WHERE agente_id = %s
    """
    
    metricas_result = execute_query(query_metricas, (agente_id,), fetch=True)
    metricas = metricas_result[0] if metricas_result else {
        'total_pesquisas': 0, 'pesquisas_respondidas': 0, 
        'pesquisas_pendentes': 0, 'taxa_resposta': 0
    }
    
    # Métricas por produto apenas do agente logado
    query_por_produto = """
    SELECT 
        tp.nome,
        COUNT(p.id) as total,
        SUM(CASE WHEN p.respondida = TRUE THEN 1 ELSE 0 END) as respondidas,
        ROUND(
            (SUM(CASE WHEN p.respondida = TRUE THEN 1 ELSE 0 END) * 100.0) / 
            NULLIF(COUNT(p.id), 0), 1
        ) as taxa
    FROM tipos_produtos tp
    LEFT JOIN pesquisas p ON tp.id = p.tipo_produto_id AND p.agente_id = %s
    GROUP BY tp.id, tp.nome
    ORDER BY tp.nome
    """
    
    por_produto = execute_query(query_por_produto, (agente_id,), fetch=True) or []
    
    # Métricas temporais apenas do agente logado
    query_esta_semana = """
    SELECT 
        COUNT(*) as criadas,
        SUM(CASE WHEN respondida = TRUE THEN 1 ELSE 0 END) as respondidas
    FROM pesquisas 
    WHERE agente_id = %s 
    AND YEARWEEK(created_at, 1) = YEARWEEK(CURDATE(), 1)
    """
    
    query_semana_passada = """
    SELECT 
        COUNT(*) as criadas,
        SUM(CASE WHEN respondida = TRUE THEN 1 ELSE 0 END) as respondidas
    FROM pesquisas 
    WHERE agente_id = %s 
    AND YEARWEEK(created_at, 1) = YEARWEEK(CURDATE(), 1) - 1
    """
    
    query_este_mes = """
    SELECT 
        COUNT(*) as criadas,
        SUM(CASE WHEN respondida = TRUE THEN 1 ELSE 0 END) as respondidas
    FROM pesquisas 
    WHERE agente_id = %s 
    AND YEAR(created_at) = YEAR(CURDATE()) 
    AND MONTH(created_at) = MONTH(CURDATE())
    """
    
    esta_semana_result = execute_query(query_esta_semana, (agente_id,), fetch=True)
    esta_semana = esta_semana_result[0] if esta_semana_result else {'criadas': 0, 'respondidas': 0}
    esta_semana = {k: v or 0 for k, v in esta_semana.items()}
    
    semana_passada_result = execute_query(query_semana_passada, (agente_id,), fetch=True)
    semana_passada = semana_passada_result[0] if semana_passada_result else {'criadas': 0, 'respondidas': 0}
    semana_passada = {k: v or 0 for k, v in semana_passada.items()}
    
    este_mes_result = execute_query(query_este_mes, (agente_id,), fetch=True)
    este_mes = este_mes_result[0] if este_mes_result else {'criadas': 0, 'respondidas': 0}
    este_mes = {k: v or 0 for k, v in este_mes.items()}
    
    # Últimas pesquisas apenas do agente logado
    query_ultimas = """
    SELECT p.*, tp.nome as tipo_produto
    FROM pesquisas p
    LEFT JOIN tipos_produtos tp ON p.tipo_produto_id = tp.id
    WHERE p.agente_id = %s
    ORDER BY p.created_at DESC
    LIMIT 10
    """
    
    ultimas_pesquisas = execute_query(query_ultimas, (agente_id,), fetch=True) or []
    
    # Organizar dados
    metricas_completas = {
        'total_pesquisas': metricas['total_pesquisas'],
        'pesquisas_respondidas': metricas['pesquisas_respondidas'],
        'pesquisas_pendentes': metricas['pesquisas_pendentes'],
        'taxa_resposta': metricas['taxa_resposta'],
        'por_produto': por_produto,
        'esta_semana': esta_semana,
        'semana_passada': semana_passada,
        'este_mes': este_mes
    }
    
    return render_template('agente/dashboard.html', 
                         metricas=metricas_completas, 
                         ultimas_pesquisas=ultimas_pesquisas)

@bp.route('/gerar-link', methods=['GET', 'POST'])
@login_required
def gerar_link():
    if request.method == 'POST':
        try:
            data = request.get_json()
            
            # Gerar UUID único
            pesquisa_uuid = str(uuid.uuid4())
            
            # Calcular data de expiração (48 horas)
            data_expiracao = datetime.now() + timedelta(hours=48)
            
            # Inserir no banco usando o ID do agente logado
            query = """
            INSERT INTO pesquisas 
            (uuid, agente_id, tipo_produto_id, codigo_cliente, nome_cliente, 
             nome_treinamento, data_expiracao) 
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
            
            params = (
                pesquisa_uuid,
                session['user_id'],  # ID do agente logado
                data.get('tipo_produto_id'),
                data.get('codigo_cliente'),
                data.get('nome_cliente'),
                data.get('nome_treinamento'),
                data_expiracao
            )
            
            result = execute_query(query, params)
            
            if result:
                app_url = os.getenv('APP_URL', 'http://localhost:5000')
                link = f"{app_url}/pesquisa/{pesquisa_uuid}"
                
                return jsonify({
                    'success': True,
                    'link': link,
                    'expiracao': data_expiracao.strftime('%d/%m/%Y %H:%M')
                })
            else:
                return jsonify({'success': False, 'error': 'Erro ao criar pesquisa'})
                
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)})
    
    return render_template('agente/gerar_link.html')

@bp.route('/minhas-pesquisas')
@login_required
def minhas_pesquisas():
    """Lista apenas as pesquisas do agente logado"""
    agente_id = session['user_id']
    
    query = """
    SELECT p.*, tp.nome as tipo_produto,
           CASE 
               WHEN p.data_expiracao < NOW() THEN 'expirada'
               WHEN p.respondida = TRUE THEN 'respondida'
               ELSE 'ativa'
           END as status_pesquisa
    FROM pesquisas p
    LEFT JOIN tipos_produtos tp ON p.tipo_produto_id = tp.id
    WHERE p.agente_id = %s
    ORDER BY p.created_at DESC
    """
    
    pesquisas = execute_query(query, (agente_id,), fetch=True) or []
    return render_template('agente/minhas_pesquisas.html', pesquisas=pesquisas)