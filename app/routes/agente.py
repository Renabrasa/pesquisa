from flask import Blueprint, render_template, request, jsonify, session
import uuid
from datetime import datetime, timedelta
import os
from app.utils.database import execute_query
from app.routes.auth import login_required
from app.utils.pagination import Paginator


bp = Blueprint('agente', __name__)

# ATUALIZAÇÃO PARA app/routes/agente.py

@bp.route('/')
@login_required
def dashboard():
    
    
    
    # === CAPTURAR PARÂMETROS DE PAGINAÇÃO ===
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    
    # Validar parâmetros
    page = max(1, page)
    per_page = min(max(5, per_page), 50)  # Entre 5 e 50 itens por página (menor que gestor)
    
    agente_id = session['user_id']
    
    # === MÉTRICAS GERAIS DO AGENTE ===
    query_metricas = """
    SELECT 
        COUNT(p.id) as total_pesquisas,
        SUM(CASE WHEN p.respondida = TRUE THEN 1 ELSE 0 END) as pesquisas_respondidas,
        SUM(CASE WHEN p.respondida = FALSE AND p.data_expiracao > NOW() THEN 1 ELSE 0 END) as pesquisas_pendentes,
        ROUND(
            (SUM(CASE WHEN p.respondida = TRUE THEN 1 ELSE 0 END) * 100.0) / 
            NULLIF(COUNT(p.id), 0), 1
        ) as taxa_resposta,
        -- FEEDBACK POR SENTIMENTO
        SUM(CASE WHEN as_sent.sentimento = 'negative' THEN 1 ELSE 0 END) as feedback_negativo,
        SUM(CASE WHEN as_sent.sentimento = 'positive' THEN 1 ELSE 0 END) as feedback_positivo,
        SUM(CASE WHEN as_sent.sentimento = 'neutral' THEN 1 ELSE 0 END) as feedback_neutro,
        ROUND(
            (SUM(CASE WHEN as_sent.sentimento = 'negative' THEN 1 ELSE 0 END) * 100.0) / 
            NULLIF(SUM(CASE WHEN p.respondida = TRUE THEN 1 ELSE 0 END), 0), 1
        ) as percentual_negativo,
        ROUND(
            (SUM(CASE WHEN as_sent.sentimento = 'positive' THEN 1 ELSE 0 END) * 100.0) / 
            NULLIF(SUM(CASE WHEN p.respondida = TRUE THEN 1 ELSE 0 END), 0), 1
        ) as percentual_positivo
    FROM pesquisas p
    LEFT JOIN analises_sentimento as_sent ON p.id = as_sent.pesquisa_id
    WHERE p.agente_id = %s
    """
    
    metricas_result = execute_query(query_metricas, (agente_id,), fetch=True)
    metricas = metricas_result[0] if metricas_result else {
        'total_pesquisas': 0, 'pesquisas_respondidas': 0, 'pesquisas_pendentes': 0,
        'taxa_resposta': 0, 'feedback_negativo': 0, 'feedback_positivo': 0, 
        'feedback_neutro': 0, 'percentual_negativo': 0, 'percentual_positivo': 0
    }
    
    # Garantir que valores não sejam None
    for key in metricas:
        if metricas[key] is None:
            metricas[key] = 0

    # === MÉTRICAS POR PRODUTO ===
    query_por_produto = """
    SELECT 
        tp.nome,
        COUNT(p.id) as total,
        SUM(CASE WHEN p.respondida = TRUE THEN 1 ELSE 0 END) as respondidas,
        ROUND(
            (SUM(CASE WHEN p.respondida = TRUE THEN 1 ELSE 0 END) * 100.0) / 
            NULLIF(COUNT(p.id), 0), 1
        ) as taxa,
        SUM(CASE WHEN as_sent.sentimento = 'negative' THEN 1 ELSE 0 END) as negativos,
        ROUND(
            (SUM(CASE WHEN as_sent.sentimento = 'negative' THEN 1 ELSE 0 END) * 100.0) / 
            NULLIF(SUM(CASE WHEN p.respondida = TRUE THEN 1 ELSE 0 END), 0), 1
        ) as percentual_negativo_produto
    FROM tipos_produtos tp
    LEFT JOIN pesquisas p ON tp.id = p.tipo_produto_id AND p.agente_id = %s
    LEFT JOIN analises_sentimento as_sent ON p.id = as_sent.pesquisa_id
    GROUP BY tp.id, tp.nome
    ORDER BY tp.nome
    """
    
    por_produto = execute_query(query_por_produto, (agente_id,), fetch=True) or []
    
    # === MÉTRICAS TEMPORAIS ===
    query_esta_semana = """
    SELECT 
        COUNT(*) as criadas,
        SUM(CASE WHEN p.respondida = TRUE THEN 1 ELSE 0 END) as respondidas,
        SUM(CASE WHEN as_sent.sentimento = 'negative' THEN 1 ELSE 0 END) as negativos,
        ROUND(
            (SUM(CASE WHEN as_sent.sentimento = 'negative' THEN 1 ELSE 0 END) * 100.0) / 
            NULLIF(SUM(CASE WHEN p.respondida = TRUE THEN 1 ELSE 0 END), 0), 1
        ) as percentual_negativo_semana
    FROM pesquisas p
    LEFT JOIN analises_sentimento as_sent ON p.id = as_sent.pesquisa_id
    WHERE p.agente_id = %s 
    AND YEARWEEK(p.created_at, 1) = YEARWEEK(CURDATE(), 1)
    """
    
    query_semana_passada = """
    SELECT 
        COUNT(*) as criadas,
        SUM(CASE WHEN p.respondida = TRUE THEN 1 ELSE 0 END) as respondidas,
        SUM(CASE WHEN as_sent.sentimento = 'negative' THEN 1 ELSE 0 END) as negativos,
        ROUND(
            (SUM(CASE WHEN as_sent.sentimento = 'negative' THEN 1 ELSE 0 END) * 100.0) / 
            NULLIF(SUM(CASE WHEN p.respondida = TRUE THEN 1 ELSE 0 END), 0), 1
        ) as percentual_negativo_semana
    FROM pesquisas p
    LEFT JOIN analises_sentimento as_sent ON p.id = as_sent.pesquisa_id
    WHERE p.agente_id = %s 
    AND YEARWEEK(p.created_at, 1) = YEARWEEK(CURDATE(), 1) - 1
    """
    
    query_este_mes = """
    SELECT 
        COUNT(*) as criadas,
        SUM(CASE WHEN p.respondida = TRUE THEN 1 ELSE 0 END) as respondidas,
        SUM(CASE WHEN as_sent.sentimento = 'negative' THEN 1 ELSE 0 END) as negativos,
        ROUND(
            (SUM(CASE WHEN as_sent.sentimento = 'negative' THEN 1 ELSE 0 END) * 100.0) / 
            NULLIF(SUM(CASE WHEN p.respondida = TRUE THEN 1 ELSE 0 END), 0), 1
        ) as percentual_negativo_semana
    FROM pesquisas p
    LEFT JOIN analises_sentimento as_sent ON p.id = as_sent.pesquisa_id
    WHERE p.agente_id = %s 
    AND YEAR(p.created_at) = YEAR(CURDATE()) 
    AND MONTH(p.created_at) = MONTH(CURDATE())
    """
    
    esta_semana_result = execute_query(query_esta_semana, (agente_id,), fetch=True)
    esta_semana = esta_semana_result[0] if esta_semana_result else {
        'criadas': 0, 'respondidas': 0, 'negativos': 0, 'percentual_negativo_semana': 0
    }
    
    semana_passada_result = execute_query(query_semana_passada, (agente_id,), fetch=True)
    semana_passada = semana_passada_result[0] if semana_passada_result else {
        'criadas': 0, 'respondidas': 0, 'negativos': 0, 'percentual_negativo_semana': 0
    }
    
    este_mes_result = execute_query(query_este_mes, (agente_id,), fetch=True)
    este_mes = este_mes_result[0] if este_mes_result else {
        'criadas': 0, 'respondidas': 0, 'negativos': 0, 'percentual_negativo_semana': 0
    }
    
    # Garantir que valores não sejam None
    for periodo in [esta_semana, semana_passada, este_mes]:
        for key in periodo:
            if periodo[key] is None:
                periodo[key] = 0

    # === PAGINAÇÃO: CONTAR TOTAL DE PESQUISAS DO AGENTE ===
    query_count_ultimas = """
    SELECT COUNT(*) as total
    FROM pesquisas p
    WHERE p.agente_id = %s
    """
    
    count_result = execute_query(query_count_ultimas, (agente_id,), fetch=True)
    total_ultimas_pesquisas = count_result[0]['total'] if count_result else 0
    
    # === CONFIGURAR PAGINAÇÃO ===
    paginator = Paginator(total_ultimas_pesquisas, page, per_page)
    pagination_info = paginator.get_pagination_info()

    # === ÚLTIMAS PESQUISAS COM PAGINAÇÃO ===
    query_ultimas = """
    SELECT p.*, tp.nome as tipo_produto,
           as_sent.sentimento,
           as_sent.confianca,
           as_sent.motivo_insatisfacao,
           CASE 
               WHEN p.data_expiracao < NOW() THEN 'expirada'
               WHEN p.respondida = TRUE THEN 'respondida'
               ELSE 'ativa'
           END as status_pesquisa
    FROM pesquisas p
    LEFT JOIN tipos_produtos tp ON p.tipo_produto_id = tp.id
    LEFT JOIN analises_sentimento as_sent ON p.id = as_sent.pesquisa_id
    WHERE p.agente_id = %s
    ORDER BY p.created_at DESC
    LIMIT %s OFFSET %s
    """
    
    ultimas_pesquisas = execute_query(query_ultimas, (agente_id, per_page, pagination_info['offset']), fetch=True) or []
    
    # === ANÁLISE DE PERFORMANCE DO AGENTE ===
    alertas_agente = []
    
    # Alerta de alto percentual de feedback negativo
    if metricas['percentual_negativo'] > 20:
        alertas_agente.append({
            'tipo': 'danger',
            'titulo': 'Alto Índice de Insatisfação',
            'mensagem': f'{metricas["percentual_negativo"]}% dos seus atendimentos receberam feedback negativo.'
        })
    
    # Alerta de baixa taxa de resposta
    if metricas['taxa_resposta'] < 50 and metricas['total_pesquisas'] > 5:
        alertas_agente.append({
            'tipo': 'warning',
            'titulo': 'Taxa de Resposta Baixa',
            'mensagem': f'Apenas {metricas["taxa_resposta"]}% das suas pesquisas foram respondidas.'
        })
    
    # Alerta de piora no feedback
    if (esta_semana['percentual_negativo_semana'] > 0 and 
        semana_passada['percentual_negativo_semana'] > 0 and
        esta_semana['percentual_negativo_semana'] > semana_passada['percentual_negativo_semana'] + 5):
        alertas_agente.append({
            'tipo': 'warning',
            'titulo': 'Piora no Feedback',
            'mensagem': f'Feedback negativo aumentou de {semana_passada["percentual_negativo_semana"]}% para {esta_semana["percentual_negativo_semana"]}% esta semana.'
        })

    # === ORGANIZAR DADOS ===
    metricas_completas = {
        'total_pesquisas': metricas['total_pesquisas'],
        'pesquisas_respondidas': metricas['pesquisas_respondidas'],
        'pesquisas_pendentes': metricas['pesquisas_pendentes'],
        'taxa_resposta': metricas['taxa_resposta'],
        'feedback_negativo': metricas['feedback_negativo'],
        'feedback_positivo': metricas['feedback_positivo'],
        'feedback_neutro': metricas['feedback_neutro'],
        'percentual_negativo': metricas['percentual_negativo'],
        'percentual_positivo': metricas['percentual_positivo'],
        'por_produto': por_produto,
        'esta_semana': esta_semana,
        'semana_passada': semana_passada,
        'este_mes': este_mes,
        'alertas': alertas_agente
    }
    
    return render_template('agente/dashboard.html', 
                         metricas=metricas_completas, 
                         ultimas_pesquisas=ultimas_pesquisas,
                         pagination=pagination_info)  # NOVO: DADOS DE PAGINAÇÃO

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