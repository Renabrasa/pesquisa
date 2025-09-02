from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from app.utils.database import execute_query
from app.routes.auth import login_required, gestor_required
import hashlib
import json
from app.utils.upload import save_avatar, delete_avatar, get_default_avatar
from app.utils.pagination import Paginator

bp = Blueprint('gestor', __name__)

def hash_password(password):
    """Criar hash MD5 da senha"""
    return hashlib.md5(password.encode()).hexdigest()

@bp.route('/')
@gestor_required
def dashboard():
    # === IMPORTS NECESSÁRIOS ===
    from app.utils.pagination import Paginator
    
    # === CAPTURAR PARÂMETROS DE PAGINAÇÃO ===
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    # Validar parâmetros
    page = max(1, page)
    per_page = min(max(10, per_page), 100)  # Entre 10 e 100 itens por página
    
    # Capturar filtros da URL
    data_inicio = request.args.get('data_inicio')
    data_fim = request.args.get('data_fim')
    busca = request.args.get('busca', '').strip()
    status = request.args.get('status', '')  # NOVO FILTRO
    produto_id = request.args.get('produto_id', '')  # NOVO FILTRO DE PRODUTO
    
    print(f"DEBUG - Filtros recebidos: data_inicio={data_inicio}, data_fim={data_fim}, busca='{busca}', status='{status}', produto_id='{produto_id}'")
    print(f"DEBUG - Paginação: page={page}, per_page={per_page}")
    
    # === BUSCAR PRODUTOS PARA O DROPDOWN ===
    query_produtos = "SELECT id, nome FROM tipos_produtos ORDER BY nome"
    produtos = execute_query(query_produtos, fetch=True) or []
    
    # Construir condições WHERE baseadas nos filtros
    condicoes_where = []
    params_base = []
    
    # Filtro de data
    if data_inicio:
        condicoes_where.append("DATE(p.created_at) >= %s")
        params_base.append(data_inicio)
    
    if data_fim:
        condicoes_where.append("DATE(p.created_at) <= %s")
        params_base.append(data_fim)
    
    # Filtro de busca (código, cliente, treinamento, agente)
    if busca:
        condicoes_where.append("""(
            p.codigo_cliente LIKE %s OR 
            p.nome_cliente LIKE %s OR 
            p.nome_treinamento LIKE %s OR 
            u.nome LIKE %s
        )""")
        busca_param = f"%{busca}%"
        params_base.extend([busca_param, busca_param, busca_param, busca_param])
    
    # NOVO: Filtro de status
    if status:
        if status == 'respondida':
            condicoes_where.append("p.respondida = TRUE")
        elif status == 'ativa':
            condicoes_where.append("p.respondida = FALSE AND p.data_expiracao > NOW()")
        elif status == 'expirada':
            condicoes_where.append("p.respondida = FALSE AND p.data_expiracao <= NOW()")
    
    # NOVO: Filtro de produto
    if produto_id:
        condicoes_where.append("p.tipo_produto_id = %s")
        params_base.append(produto_id)
    
    # Montar cláusula WHERE
    where_clause = " AND ".join(condicoes_where) if condicoes_where else "1=1"
    
    # === MÉTRICAS GERAIS COM FILTROS ===
    query_metricas = f"""
    SELECT 
        COUNT(*) as total_pesquisas,
        SUM(CASE WHEN p.respondida = TRUE THEN 1 ELSE 0 END) as respondidas,
        SUM(CASE WHEN p.respondida = FALSE AND p.data_expiracao > NOW() THEN 1 ELSE 0 END) as pendentes,
        SUM(CASE WHEN p.respondida = FALSE AND p.data_expiracao <= NOW() THEN 1 ELSE 0 END) as expiradas,
        ROUND(
            (SUM(CASE WHEN p.respondida = TRUE THEN 1 ELSE 0 END) * 100.0) / 
            NULLIF(COUNT(*), 0), 1
        ) as taxa_resposta,
        COUNT(DISTINCT p.codigo_cliente) as clientes_unicos,
        -- NOVO KPI: Atendimentos mal avaliados
        SUM(CASE WHEN as_sent.sentimento = 'negative' THEN 1 ELSE 0 END) as mal_avaliados,
        ROUND(
            (SUM(CASE WHEN as_sent.sentimento = 'negative' THEN 1 ELSE 0 END) * 100.0) / 
            NULLIF(SUM(CASE WHEN p.respondida = TRUE THEN 1 ELSE 0 END), 0), 1
        ) as percentual_mal_avaliados
    FROM pesquisas p
    LEFT JOIN usuarios u ON p.agente_id = u.id
    LEFT JOIN analises_sentimento as_sent ON p.id = as_sent.pesquisa_id
    WHERE {where_clause}
    """
    
    metricas_result = execute_query(query_metricas, params_base, fetch=True)
    metricas = metricas_result[0] if metricas_result else {
        'total_pesquisas': 0, 'respondidas': 0, 'pendentes': 0, 
        'expiradas': 0, 'taxa_resposta': 0, 'clientes_unicos': 0,
        'mal_avaliados': 0, 'percentual_mal_avaliados': 0
    }
    
    # Garantir que valores não sejam None
    for key in metricas:
        if metricas[key] is None:
            metricas[key] = 0
    
    # === MÉTRICAS POR PRODUTO COM FILTROS ===
    # Ajustar query para não duplicar filtro de produto nas estatísticas por produto
    where_clause_produto = where_clause
    params_produto = params_base.copy()
    
    # Se há filtro de produto, removê-lo das stats por produto para mostrar comparação
    if produto_id:
        # Remover a condição de produto da WHERE clause
        condicoes_sem_produto = [cond for cond in condicoes_where if not cond.startswith("p.tipo_produto_id")]
        where_clause_produto = " AND ".join(condicoes_sem_produto) if condicoes_sem_produto else "1=1"
        params_produto = params_base[:-1]  # Remover último parâmetro (produto_id)
    
    query_por_produto = f"""
    SELECT 
        tp.id,
        tp.nome,
        COUNT(p.id) as total,
        SUM(CASE WHEN p.respondida = TRUE THEN 1 ELSE 0 END) as respondidas,
        COALESCE(
            ROUND(
                (SUM(CASE WHEN p.respondida = TRUE THEN 1 ELSE 0 END) * 100.0) / 
                NULLIF(COUNT(p.id), 0), 1
            ), 0
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
        ), 1) as media_satisfacao,
        SUM(CASE WHEN as_sent.sentimento = 'negative' THEN 1 ELSE 0 END) as negativos
    FROM tipos_produtos tp
    LEFT JOIN pesquisas p ON tp.id = p.tipo_produto_id
    LEFT JOIN usuarios u ON p.agente_id = u.id
    LEFT JOIN respostas r ON p.id = r.pesquisa_id AND r.resposta_texto IN ('Muito Satisfeito', 'Satisfeito', 'Neutro', 'Insatisfeito', 'Muito Insatisfeito')
    LEFT JOIN analises_sentimento as_sent ON p.id = as_sent.pesquisa_id
    WHERE p.id IS NULL OR ({where_clause_produto})
    GROUP BY tp.id, tp.nome
    ORDER BY tp.nome
    """
    
    por_produto = execute_query(query_por_produto, params_produto, fetch=True) or []
    
    # === MÉTRICAS POR AGENTE COM FILTROS ===
    query_por_agente = f"""
    SELECT 
        COALESCE(u.nome, 'Agente Desconhecido') as nome,
        COUNT(p.id) as total,
        SUM(CASE WHEN p.respondida = TRUE THEN 1 ELSE 0 END) as respondidas,
        ROUND(
            (SUM(CASE WHEN p.respondida = TRUE THEN 1 ELSE 0 END) * 100.0) / 
            NULLIF(COUNT(p.id), 0), 1
        ) as taxa,
        SUM(CASE WHEN as_sent.sentimento = 'negative' THEN 1 ELSE 0 END) as negativos
    FROM pesquisas p
    LEFT JOIN usuarios u ON p.agente_id = u.id
    LEFT JOIN analises_sentimento as_sent ON p.id = as_sent.pesquisa_id
    WHERE {where_clause}
    GROUP BY p.agente_id, u.nome
    HAVING COUNT(p.id) > 0
    ORDER BY total DESC
    """
    
    por_agente = execute_query(query_por_agente, params_base, fetch=True) or []
    
    # === MÉTRICAS TEMPORAIS COM FILTROS ===
    if data_inicio and data_fim:
        # Com filtro: comparar primeira metade vs segunda metade do período
        query_periodo_1 = f"""
        SELECT 
            COUNT(*) as criadas,
            SUM(CASE WHEN p.respondida = TRUE THEN 1 ELSE 0 END) as respondidas,
            ROUND(
                (SUM(CASE WHEN p.respondida = TRUE THEN 1 ELSE 0 END) * 100.0) / 
                NULLIF(COUNT(*), 0), 1
            ) as taxa
        FROM pesquisas p
        LEFT JOIN usuarios u ON p.agente_id = u.id
        WHERE DATE(p.created_at) >= %s AND DATE(p.created_at) <= %s
        """
        
        # Calcular meio período
        from datetime import datetime, timedelta
        inicio = datetime.strptime(data_inicio, '%Y-%m-%d')
        fim = datetime.strptime(data_fim, '%Y-%m-%d')
        meio = inicio + (fim - inicio) / 2
        meio_str = meio.strftime('%Y-%m-%d')
        
        # Ajustar parâmetros para incluir outros filtros
        params_extras = []
        where_extra = ""
        
        if busca:
            where_extra += f" AND (p.codigo_cliente LIKE %s OR p.nome_cliente LIKE %s OR p.nome_treinamento LIKE %s OR u.nome LIKE %s)"
            params_extras.extend([busca_param, busca_param, busca_param, busca_param])
        
        if status:
            if status == 'respondida':
                where_extra += " AND p.respondida = TRUE"
            elif status == 'ativa':
                where_extra += " AND p.respondida = FALSE AND p.data_expiracao > NOW()"
            elif status == 'expirada':
                where_extra += " AND p.respondida = FALSE AND p.data_expiracao <= NOW()"
        
        if produto_id:
            where_extra += " AND p.tipo_produto_id = %s"
            params_extras.append(produto_id)
        
        periodo_1_params = [data_inicio, meio_str] + params_extras
        periodo_2_params = [meio_str, data_fim] + params_extras
        
        query_periodo_1 += where_extra
        query_periodo_2 = query_periodo_1.replace(f"'>= %s AND DATE(p.created_at) <= %s'", f"'>= %s AND DATE(p.created_at) <= %s'")
        
        esta_semana_result = execute_query(query_periodo_1, periodo_1_params, fetch=True)
        semana_passada_result = execute_query(query_periodo_2, periodo_2_params, fetch=True)
        
        este_mes = esta_semana_result[0] if esta_semana_result else {'criadas': 0, 'respondidas': 0, 'taxa': 0}
        mes_passado = semana_passada_result[0] if semana_passada_result else {'criadas': 0, 'respondidas': 0, 'taxa': 0}
        
    else:
        # Sem filtro de data: usar períodos relativos normais
        where_extra = ""
        params_extras = []
        
        if busca:
            where_extra += f" AND (p.codigo_cliente LIKE %s OR p.nome_cliente LIKE %s OR p.nome_treinamento LIKE %s OR u.nome LIKE %s)"
            params_extras.extend([busca_param, busca_param, busca_param, busca_param])
        
        if status:
            if status == 'respondida':
                where_extra += " AND p.respondida = TRUE"
            elif status == 'ativa':
                where_extra += " AND p.respondida = FALSE AND p.data_expiracao > NOW()"
            elif status == 'expirada':
                where_extra += " AND p.respondida = FALSE AND p.data_expiracao <= NOW()"
        
        if produto_id:
            where_extra += " AND p.tipo_produto_id = %s"
            params_extras.append(produto_id)
        
        query_esta_semana = f"""
        SELECT 
            COUNT(*) as criadas,
            SUM(CASE WHEN p.respondida = TRUE THEN 1 ELSE 0 END) as respondidas,
            ROUND(
                (SUM(CASE WHEN p.respondida = TRUE THEN 1 ELSE 0 END) * 100.0) / 
                NULLIF(COUNT(*), 0), 1
            ) as taxa
        FROM pesquisas p
        LEFT JOIN usuarios u ON p.agente_id = u.id
        WHERE YEARWEEK(p.created_at, 1) = YEARWEEK(CURDATE(), 1)
        {where_extra}
        """
        
        query_semana_passada = query_esta_semana.replace("YEARWEEK(CURDATE(), 1)", "YEARWEEK(CURDATE(), 1) - 1")
        query_este_mes = query_esta_semana.replace("YEARWEEK(p.created_at, 1) = YEARWEEK(CURDATE(), 1)", 
                                                  "YEAR(p.created_at) = YEAR(CURDATE()) AND MONTH(p.created_at) = MONTH(CURDATE())")
        query_mes_passado = query_este_mes.replace("MONTH(CURDATE())", "MONTH(CURDATE() - INTERVAL 1 MONTH)").replace("YEAR(CURDATE())", "YEAR(CURDATE() - INTERVAL 1 MONTH)")
        
        esta_semana_result = execute_query(query_esta_semana, params_extras, fetch=True)
        semana_passada_result = execute_query(query_semana_passada, params_extras, fetch=True)
        este_mes_result = execute_query(query_este_mes, params_extras, fetch=True)
        mes_passado_result = execute_query(query_mes_passado, params_extras, fetch=True)
        
        este_mes = este_mes_result[0] if este_mes_result else {'criadas': 0, 'respondidas': 0, 'taxa': 0}
        mes_passado = mes_passado_result[0] if mes_passado_result else {'criadas': 0, 'respondidas': 0, 'taxa': 0}
    
    esta_semana = esta_semana_result[0] if esta_semana_result else {'criadas': 0, 'respondidas': 0, 'taxa': 0}
    semana_passada = semana_passada_result[0] if semana_passada_result else {'criadas': 0, 'respondidas': 0, 'taxa': 0}
    
    # Garantir que valores não sejam None
    for periodo in [esta_semana, semana_passada, este_mes, mes_passado]:
        for key in periodo:
            if periodo[key] is None:
                periodo[key] = 0
    
    # === NOVA FUNCIONALIDADE: PESQUISAS PENDENTES ===
    query_pendentes = f"""
    SELECT p.*, tp.nome as tipo_produto, u.nome as agente_nome,
           TIMESTAMPDIFF(HOUR, NOW(), p.data_expiracao) as horas_restantes,
           CASE 
               WHEN TIMESTAMPDIFF(HOUR, NOW(), p.data_expiracao) <= 6 THEN 'critico'
               WHEN TIMESTAMPDIFF(HOUR, NOW(), p.data_expiracao) <= 24 THEN 'atencao'
               ELSE 'normal'
           END as urgencia
    FROM pesquisas p
    LEFT JOIN tipos_produtos tp ON p.tipo_produto_id = tp.id
    LEFT JOIN usuarios u ON p.agente_id = u.id
    WHERE p.respondida = FALSE 
    AND p.data_expiracao > NOW()
    AND ({where_clause})
    ORDER BY p.data_expiracao ASC
    LIMIT 15
    """
    
    # Ajustar parâmetros para query de pendentes
    params_pendentes = params_base if where_clause != "1=1" else []
    pesquisas_pendentes = execute_query(query_pendentes, params_pendentes, fetch=True) or []
    
    # === ESTATÍSTICAS DE PESQUISAS PENDENTES ===
    query_stats_pendentes = f"""
    SELECT 
        COUNT(*) as total_pendentes,
        SUM(CASE WHEN TIMESTAMPDIFF(HOUR, NOW(), p.data_expiracao) <= 6 THEN 1 ELSE 0 END) as criticas,
        SUM(CASE WHEN TIMESTAMPDIFF(HOUR, NOW(), p.data_expiracao) <= 24 THEN 1 ELSE 0 END) as atencao,
        AVG(TIMESTAMPDIFF(HOUR, NOW(), p.data_expiracao)) as media_horas_restantes
    FROM pesquisas p
    LEFT JOIN usuarios u ON p.agente_id = u.id
    WHERE p.respondida = FALSE 
    AND p.data_expiracao > NOW()
    AND ({where_clause})
    """
    
    stats_pendentes_result = execute_query(query_stats_pendentes, params_pendentes, fetch=True)
    stats_pendentes = stats_pendentes_result[0] if stats_pendentes_result else {
        'total_pendentes': 0, 'criticas': 0, 'atencao': 0, 'media_horas_restantes': 0
    }
    
    # Garantir que valores não sejam None
    for key in stats_pendentes:
        if stats_pendentes[key] is None:
            stats_pendentes[key] = 0
    
    # === GERAR ALERTAS ===
    alertas = []
    
    # Alerta de baixa taxa de resposta
    if (metricas.get('taxa_resposta') or 0) < 50:
        alertas.append({
            'tipo': 'warning',
            'titulo': 'Taxa de Resposta Baixa',
            'mensagem': f'Taxa atual: {metricas["taxa_resposta"]}%. Considere revisar os links.'
        })
    
    # Alerta de muitas pesquisas expiradas
    if (metricas.get('expiradas') or 0) > (metricas.get('respondidas') or 0):
        alertas.append({
            'tipo': 'danger',
            'titulo': 'Muitas Expiradas',
            'mensagem': f'{metricas["expiradas"]} pesquisas expiraram sem resposta.'
        })
    
    # NOVO ALERTA: Alto percentual de insatisfação
    if (metricas.get('percentual_mal_avaliados') or 0) > 15:
        alertas.append({
            'tipo': 'danger',
            'titulo': 'Alto Índice de Insatisfação',
            'mensagem': f'{metricas["percentual_mal_avaliados"]}% dos atendimentos foram mal avaliados.'
        })
    
    # NOVO ALERTA: Pesquisas críticas
    if (stats_pendentes.get('criticas') or 0) > 0:
        alertas.append({
            'tipo': 'danger',
            'titulo': 'Pesquisas Expirando',
            'mensagem': f'{stats_pendentes["criticas"]} pesquisa(s) expira(m) em menos de 6 horas!'
        })
    elif (stats_pendentes.get('atencao') or 0) > 3:
        alertas.append({
            'tipo': 'warning',
            'titulo': 'Muitas Pesquisas Pendentes',
            'mensagem': f'{stats_pendentes["atencao"]} pesquisa(s) expira(m) nas próximas 24 horas.'
        })
    
    # Alerta de queda na performance
    if (esta_semana.get('taxa') or 0) and (semana_passada.get('taxa') or 0) and (esta_semana.get('taxa') or 0) < (semana_passada.get('taxa') or 0) - 10:
        alertas.append({
            'tipo': 'warning',
            'titulo': 'Queda na Performance',
            'mensagem': f'Taxa caiu {semana_passada["taxa"] - esta_semana["taxa"]:.1f}% em relação ao período anterior.'
        })
    
    # === PAGINAÇÃO: CONTAR TOTAL DE PESQUISAS ===
    query_count_pesquisas = f"""
    SELECT COUNT(*) as total
    FROM pesquisas p
    LEFT JOIN usuarios u ON p.agente_id = u.id
    WHERE {where_clause}
    """
    
    count_result = execute_query(query_count_pesquisas, params_base, fetch=True)
    total_pesquisas_paginacao = count_result[0]['total'] if count_result else 0
    
    # === CONFIGURAR PAGINAÇÃO ===
    paginator = Paginator(total_pesquisas_paginacao, page, per_page)
    pagination_info = paginator.get_pagination_info()
    
    # === PESQUISAS RECENTES COM PAGINAÇÃO ===
    query_pesquisas = f"""
    SELECT p.*, tp.nome as tipo_produto, u.nome as agente_nome,
           -- LÓGICA DE STATUS CORRIGIDA
           CASE 
               WHEN p.respondida = TRUE THEN 'respondida'
               WHEN p.respondida = FALSE AND p.data_expiracao <= NOW() THEN 'expirada'
               ELSE 'ativa'
           END as status_pesquisa,
           -- Dados de sentimento
           as_sent.sentimento,
           as_sent.pontuacao_hibrida,
           as_sent.confianca,
           p.ia_processada,
           -- Dados de ações
           ai.id as acao_id,
           ai.status as acao_status,
           ai.data_registro as acao_data,
           -- Tempo até expiração
           CASE 
               WHEN p.respondida = TRUE THEN NULL
               WHEN p.data_expiracao <= NOW() THEN 0
               ELSE TIMESTAMPDIFF(HOUR, NOW(), p.data_expiracao)
           END as horas_restantes
    FROM pesquisas p
    LEFT JOIN tipos_produtos tp ON p.tipo_produto_id = tp.id
    LEFT JOIN usuarios u ON p.agente_id = u.id
    LEFT JOIN analises_sentimento as_sent ON p.id = as_sent.pesquisa_id
    LEFT JOIN acoes_insatisfacao ai ON p.id = ai.pesquisa_id
    WHERE {where_clause}
    ORDER BY p.created_at DESC
    LIMIT %s OFFSET %s
    """
    
    # Adicionar parâmetros de paginação
    params_pesquisas = params_base + [per_page, pagination_info['offset']]
    pesquisas = execute_query(query_pesquisas, params_pesquisas, fetch=True) or []
    
    # === ORGANIZAR MÉTRICAS COMPLETAS ===
    metricas_completas = {
        'total_pesquisas': metricas['total_pesquisas'],
        'respondidas': metricas['respondidas'],
        'pendentes': metricas['pendentes'],
        'expiradas': metricas['expiradas'],
        'taxa_resposta': metricas['taxa_resposta'],
        'clientes_unicos': metricas['clientes_unicos'],
        'mal_avaliados': metricas['mal_avaliados'],
        'percentual_mal_avaliados': metricas['percentual_mal_avaliados'],
        'por_produto': por_produto,
        'por_agente': por_agente,
        'esta_semana': esta_semana,
        'semana_passada': semana_passada,
        'este_mes': este_mes,
        'mes_passado': mes_passado,
        'alertas': alertas,
        # NOVAS FUNCIONALIDADES
        'pesquisas_pendentes': pesquisas_pendentes,
        'stats_pendentes': stats_pendentes
    }
    
    return render_template('gestor/dashboard.html', 
                         metricas=metricas_completas, 
                         pesquisas=pesquisas,
                         produtos=produtos,  # PASSAR PRODUTOS PARA O TEMPLATE
                         pagination=pagination_info)  # NOVO: DADOS DE PAGINAÇÃO

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
    SELECT u.foto_url, u.*, 
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
        
        # Verificar se email já existe (exceto o próprio usuário)
        query_check = "SELECT id FROM usuarios WHERE email = %s AND id != %s"
        if execute_query(query_check, (email, user_id), fetch=True):
            flash('E-mail já está sendo usado por outro usuário!', 'error')
            return redirect(url_for('gestor.editar_usuario', user_id=user_id))
        
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
                        return redirect(url_for('gestor.editar_usuario', user_id=user_id))
                        
                except Exception as e:
                    flash(f'Erro ao processar foto: {str(e)}', 'error')
                    return redirect(url_for('gestor.editar_usuario', user_id=user_id))
        
        # Preparar query de atualização (com ou sem foto)
        if foto_url:
            query_update = """
            UPDATE usuarios 
            SET nome = %s, email = %s, tipo_usuario = %s, ativo = %s, foto_url = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            """
            params = (nome, email, tipo_usuario, ativo, foto_url, user_id)
        else:
            query_update = """
            UPDATE usuarios 
            SET nome = %s, email = %s, tipo_usuario = %s, ativo = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            """
            params = (nome, email, tipo_usuario, ativo, user_id)
        
        try:
            result = execute_query(query_update, params)
            
            if result:
                flash('Usuário atualizado com sucesso!', 'success')
                return redirect(url_for('gestor.usuarios'))
            else:
                flash('Erro ao atualizar usuário!', 'error')
                
        except Exception as e:
            flash(f'Erro específico: {str(e)}', 'error')
    
    # GET - Buscar dados do usuário
    query = "SELECT * FROM usuarios WHERE id = %s"
    result = execute_query(query, (user_id,), fetch=True)
    
    if not result:
        return "Usuário não encontrado", 404
    
    usuario = result[0]
    
    # Garantir foto padrão se não tiver
    if not usuario['foto_url']:
        usuario['foto_url'] = get_default_avatar()
    
    # Buscar estatísticas do usuário (apenas para agentes)
    estatisticas = {'total_pesquisas': 0, 'pesquisas_respondidas': 0}
    
    if usuario['tipo_usuario'] == 'agente':
        query_stats = """
        SELECT 
            COUNT(p.id) as total_pesquisas,
            SUM(CASE WHEN p.respondida = TRUE THEN 1 ELSE 0 END) as pesquisas_respondidas
        FROM pesquisas p
        WHERE p.agente_id = %s
        """
        
        result_stats = execute_query(query_stats, (user_id,), fetch=True)
        
        if result_stats:
            estatisticas = {
                'total_pesquisas': result_stats[0]['total_pesquisas'] or 0,
                'pesquisas_respondidas': result_stats[0]['pesquisas_respondidas'] or 0
            }
    
    return render_template('gestor/editar_usuario.html', usuario=usuario, estatisticas=estatisticas)


@bp.route('/usuarios/<int:user_id>/resetar-senha', methods=['POST'])
@gestor_required
def resetar_senha_usuario(user_id):
    """Resetar senha do usuário (apenas para gestores)"""
    try:
        from flask import session
        import random
        import string
        
        # Verificar se o usuário existe
        query_check = "SELECT id, nome, email FROM usuarios WHERE id = %s"
        result = execute_query(query_check, (user_id,), fetch=True)
        
        if not result:
            return jsonify({'success': False, 'error': 'Usuário não encontrado'})
        
        usuario = result[0]
        
        # Verificar se não está tentando resetar a própria senha
        if user_id == session.get('user_id'):
            return jsonify({'success': False, 'error': 'Não é possível resetar sua própria senha por este método'})
        
        # Gerar nova senha temporária (8 caracteres)
        caracteres = string.ascii_letters + string.digits
        nova_senha = ''.join(random.choice(caracteres) for _ in range(8))
        
        # Hash da nova senha
        nova_senha_hash = hash_password(nova_senha)
        
        # Atualizar senha no banco
        query_update = """
        UPDATE usuarios 
        SET senha_hash = %s, updated_at = CURRENT_TIMESTAMP
        WHERE id = %s
        """
        
        resultado = execute_query(query_update, (nova_senha_hash, user_id))
        
        if resultado:
            return jsonify({
                'success': True, 
                'message': 'Senha resetada com sucesso',
                'nova_senha': nova_senha,
                'usuario_nome': usuario['nome'],
                'usuario_email': usuario['email']
            })
        else:
            return jsonify({'success': False, 'error': 'Erro ao resetar senha no banco de dados'})
            
    except Exception as e:
        print(f"Erro ao resetar senha: {str(e)}")
        return jsonify({'success': False, 'error': f'Erro interno: {str(e)}'})



# ===== ROTAS DE AÇÕES DE INSATISFAÇÃO =====

@bp.route('/acoes/<int:pesquisa_id>', methods=['GET'])
@gestor_required
def buscar_acoes(pesquisa_id):
    """Buscar ações existentes para uma pesquisa"""
    try:
        # Verificar se pesquisa existe e tem sentimento negativo
        query_verifica = """
        SELECT p.id, p.nome_cliente, as_sent.sentimento 
        FROM pesquisas p
        LEFT JOIN analises_sentimento as_sent ON p.id = as_sent.pesquisa_id
        WHERE p.id = %s
        """
        
        result_verifica = execute_query(query_verifica, (pesquisa_id,), fetch=True)
        
        if not result_verifica:
            return jsonify({'success': False, 'error': 'Pesquisa não encontrada'})
        
        pesquisa = result_verifica[0]
        
        if pesquisa['sentimento'] != 'negative':
            return jsonify({'success': False, 'error': 'Esta pesquisa não possui sentimento negativo'})
        
        # Buscar ações existentes
        query_acoes = """
        SELECT ai.*, u.nome as gestor_nome
        FROM acoes_insatisfacao ai
        LEFT JOIN usuarios u ON ai.gestor_id = u.id
        WHERE ai.pesquisa_id = %s
        ORDER BY ai.data_registro DESC
        LIMIT 1
        """
        
        result_acoes = execute_query(query_acoes, (pesquisa_id,), fetch=True)
        
        if not result_acoes:
            return jsonify({'success': False, 'error': 'Nenhuma ação encontrada para esta pesquisa'})
        
        acao = result_acoes[0]
        
        return jsonify({
            'success': True,
            'acoes_tomadas': acao['acoes_tomadas'],
            'status': acao['status'],
            'data_registro': acao['data_registro'].strftime('%d/%m/%Y %H:%M'),
            'gestor_nome': acao['gestor_nome']
        })
        
    except Exception as e:
        print(f"Erro ao buscar ações: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

@bp.route('/acoes/<int:pesquisa_id>', methods=['POST'])
@gestor_required
def salvar_acoes(pesquisa_id):
    """Salvar/atualizar ações para uma pesquisa"""
    try:
        from flask import session
        
        # Obter dados do JSON
        data = request.get_json()
        acoes_tomadas = data.get('acoes_tomadas', '').strip()
        status = data.get('status', 'pendente')
        
        if not acoes_tomadas:
            return jsonify({'success': False, 'error': 'Ações tomadas são obrigatórias'})
        
        if status not in ['pendente', 'em_andamento', 'resolvido']:
            return jsonify({'success': False, 'error': 'Status inválido'})
        
        # Verificar se pesquisa existe e tem sentimento negativo
        query_verifica = """
        SELECT p.id, p.nome_cliente, as_sent.sentimento, as_sent.id as analise_id
        FROM pesquisas p
        LEFT JOIN analises_sentimento as_sent ON p.id = as_sent.pesquisa_id
        WHERE p.id = %s
        """
        
        result_verifica = execute_query(query_verifica, (pesquisa_id,), fetch=True)
        
        if not result_verifica:
            return jsonify({'success': False, 'error': 'Pesquisa não encontrada'})
        
        pesquisa = result_verifica[0]
        
        if pesquisa['sentimento'] != 'negative':
            return jsonify({'success': False, 'error': 'Esta pesquisa não possui sentimento negativo'})
        
        # Verificar se já existe ação para esta pesquisa
        query_existe = "SELECT id FROM acoes_insatisfacao WHERE pesquisa_id = %s"
        result_existe = execute_query(query_existe, (pesquisa_id,), fetch=True)
        
        gestor_id = session['user_id']
        analise_id = pesquisa['analise_id']
        
        if result_existe:
            # Atualizar ação existente
            acao_id = result_existe[0]['id']
            
            query_update = """
            UPDATE acoes_insatisfacao 
            SET acoes_tomadas = %s, status = %s, gestor_id = %s,
                data_atualizacao = CURRENT_TIMESTAMP
            WHERE id = %s
            """
            
            result = execute_query(query_update, (acoes_tomadas, status, gestor_id, acao_id))
            
            if result:
                return jsonify({
                    'success': True, 
                    'message': 'Ações atualizadas com sucesso',
                    'acao_id': acao_id
                })
            else:
                return jsonify({'success': False, 'error': 'Erro ao atualizar ações'})
        
        else:
            # Inserir nova ação
            query_insert = """
            INSERT INTO acoes_insatisfacao 
            (pesquisa_id, analise_sentimento_id, gestor_id, acoes_tomadas, status)
            VALUES (%s, %s, %s, %s, %s)
            """
            
            result = execute_query(query_insert, (pesquisa_id, analise_id, gestor_id, acoes_tomadas, status))
            
            if result:
                # Buscar ID da ação inserida
                query_last_id = "SELECT LAST_INSERT_ID() as id"
                result_id = execute_query(query_last_id, fetch=True)
                acao_id = result_id[0]['id'] if result_id else None
                
                return jsonify({
                    'success': True, 
                    'message': 'Ações salvas com sucesso',
                    'acao_id': acao_id
                })
            else:
                return jsonify({'success': False, 'error': 'Erro ao salvar ações'})
        
    except Exception as e:
        print(f"Erro ao salvar ações: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})
    
    
    # ADICIONAR no final do arquivo app/routes/gestor.py

@bp.route('/lembrete/<int:pesquisa_id>', methods=['POST'])
@gestor_required
def enviar_lembrete(pesquisa_id):
    """Enviar lembrete ao agente sobre pesquisa pendente crítica"""
    try:
        # Buscar dados da pesquisa e agente
        query = """
        SELECT p.*, u.nome as agente_nome, u.email as agente_email,
               tp.nome as tipo_produto,
               TIMESTAMPDIFF(HOUR, NOW(), p.data_expiracao) as horas_restantes
        FROM pesquisas p
        JOIN usuarios u ON p.agente_id = u.id
        JOIN tipos_produtos tp ON p.tipo_produto_id = tp.id
        WHERE p.id = %s 
        AND p.respondida = FALSE 
        AND p.data_expiracao > NOW()
        """
        
        result = execute_query(query, (pesquisa_id,), fetch=True)
        
        if not result:
            return jsonify({
                'success': False, 
                'error': 'Pesquisa não encontrada ou já respondida/expirada'
            })
        
        pesquisa = result[0]
        
        # Verificar se é realmente crítica (menos de 6 horas)
        if pesquisa['horas_restantes'] > 6:
            return jsonify({
                'success': False,
                'error': 'Pesquisa não está em estado crítico (>6h restantes)'
            })
        
        # Verificar se já foi enviado lembrete nas últimas 2 horas
        query_check = """
        SELECT created_at FROM log_lembretes 
        WHERE pesquisa_id = %s 
        AND created_at > DATE_SUB(NOW(), INTERVAL 2 HOUR)
        ORDER BY created_at DESC LIMIT 1
        """
        
        lembrete_recente = execute_query(query_check, (pesquisa_id,), fetch=True)
        
        if lembrete_recente:
            return jsonify({
                'success': False,
                'error': 'Lembrete já enviado nas últimas 2 horas'
            })
        
        # TODO: Implementar envio real de email
        # Por enquanto, apenas simular o envio
        
        sucesso_envio = True  # Simular sucesso
        
        if sucesso_envio:
            # Registrar no log
            query_log = """
            INSERT INTO log_lembretes 
            (pesquisa_id, agente_id, gestor_id, tipo_lembrete, enviado_com_sucesso)
            VALUES (%s, %s, %s, %s, %s)
            """
            
            from flask import session
            execute_query(query_log, (
                pesquisa_id,
                pesquisa['agente_id'],
                session['user_id'],
                'pesquisa_critica',
                True
            ))
            
            return jsonify({
                'success': True,
                'message': f'Lembrete enviado para {pesquisa["agente_nome"]} ({pesquisa["agente_email"]})',
                'agente': pesquisa['agente_nome'],
                'horas_restantes': pesquisa['horas_restantes']
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Falha no envio do email'
            })
            
    except Exception as e:
        print(f"Erro ao enviar lembrete: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        })