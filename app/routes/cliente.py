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

# SUBSTITUIR a função enviar_resposta() no arquivo: app/routes/cliente.py
# Localizar a função atual e substituir por esta versão com IA integrada

@bp.route('/<pesquisa_uuid>/enviar', methods=['POST'])
def enviar_resposta(pesquisa_uuid):
    try:
        # Buscar pesquisa
        query = "SELECT id FROM pesquisas WHERE uuid = %s AND respondida = FALSE"
        result = execute_query(query, (pesquisa_uuid,), fetch=True)
        
        if not result:
            return "Pesquisa não encontrada ou já respondida", 404
        
        pesquisa_id = result[0]['id']
        
        # Coletar e salvar respostas
        respostas_processamento = []  # Para análise de IA
        
        for campo, valor in request.form.items():
            if campo.startswith('pergunta_') and valor.strip():
                pergunta_id = campo.replace('pergunta_', '')
                
                # Buscar informações da pergunta para classificação
                query_pergunta = """
                SELECT p.*, tp.nome as tipo_nome
                FROM perguntas p
                LEFT JOIN tipos_perguntas tp ON p.tipo_pergunta_id = tp.id
                WHERE p.id = %s
                """
                pergunta_info = execute_query(query_pergunta, (pergunta_id,), fetch=True)
                
                if pergunta_info:
                    pergunta_data = pergunta_info[0]
                    
                    # Determinar tipo de resposta
                    if valor.replace('.', '').replace(',', '').isdigit():
                        # Resposta numérica (escala)
                        query_resposta = """
                        INSERT INTO respostas (pesquisa_id, pergunta_id, resposta_numerica)
                        VALUES (%s, %s, %s)
                        """
                        params = (pesquisa_id, pergunta_id, float(valor.replace(',', '.')))
                        
                        # Adicionar para processamento IA
                        respostas_processamento.append({
                            'tipo': 'escala_numerica',
                            'valor': valor,
                            'pergunta': pergunta_data['texto']
                        })
                        
                    else:
                        # Resposta texto
                        query_resposta = """
                        INSERT INTO respostas (pesquisa_id, pergunta_id, resposta_texto)
                        VALUES (%s, %s, %s)
                        """
                        params = (pesquisa_id, pergunta_id, valor)
                        
                        # Classificar tipo de texto para IA
                        tipo_pergunta = pergunta_data.get('tipo_nome', '').lower()
                        
                        if 'satisfacao' in tipo_pergunta or valor in ['Muito Satisfeito', 'Satisfeito', 'Neutro', 'Insatisfeito', 'Muito Insatisfeito']:
                            tipo_resposta = 'escala_satisfacao'
                        elif valor.lower() in ['sim', 'não', 'yes', 'no']:
                            tipo_resposta = 'sim_nao'
                        else:
                            tipo_resposta = 'texto_livre'
                        
                        # Adicionar para processamento IA
                        respostas_processamento.append({
                            'tipo': tipo_resposta,
                            'valor': valor,
                            'pergunta': pergunta_data['texto']
                        })
                
                    execute_query(query_resposta, params)
        
        # Marcar pesquisa como respondida
        query_update = """
        UPDATE pesquisas 
        SET respondida = TRUE, data_resposta = NOW(), ip_resposta = %s
        WHERE id = %s
        """
        
        ip_cliente = request.environ.get('HTTP_X_FORWARDED_FOR', request.environ.get('REMOTE_ADDR'))
        execute_query(query_update, (ip_cliente, pesquisa_id))
        
        # === NOVA FUNCIONALIDADE: ANÁLISE DE IA ===
        try:
            print(f"🤖 Iniciando análise de IA para pesquisa {pesquisa_id}...")
            
            # Importar serviços
            from app.services.sentiment_analyzer import SentimentAnalyzer
            from app.services.email_service import EmailService
            
            # Processar com IA
            analyzer = SentimentAnalyzer()
            resultado_analise = analyzer.calcular_pontuacao_hibrida(respostas_processamento)
            
            print(f"   Sentimento: {resultado_analise['sentimento_geral']}")
            print(f"   Pontuação: {resultado_analise['pontuacao_hibrida']}")
            print(f"   Deve alertar: {resultado_analise['deve_alertar']}")
            
            # Salvar análise no banco
            query_analise = """
            INSERT INTO analises_sentimento 
            (pesquisa_id, resposta_consolidada, sentimento, confianca, pontuacao_hibrida, 
             motivo_insatisfacao, modelo_usado)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
            
            execute_query(query_analise, (
                pesquisa_id,
                resultado_analise['texto_consolidado'][:1000],  # Limitar tamanho
                resultado_analise['sentimento_geral'],
                resultado_analise['confianca_geral'],
                resultado_analise['pontuacao_hibrida'],
                resultado_analise['motivo_insatisfacao'],
                'cardiffnlp/twitter-xlm-roberta-base-sentiment'
            ))
            
            print(f"✅ Análise salva no banco")
            
            # Enviar email se detectar insatisfação
            if resultado_analise['deve_alertar']:
                print(f"🚨 Insatisfação detectada! Enviando alertas...")
                
                email_service = EmailService()
                resultado_email = email_service.enviar_alerta_insatisfacao(
                    pesquisa_id, 
                    resultado_analise
                )
                
                if resultado_email['sucesso']:
                    print(f"📧 {resultado_email['emails_enviados']} email(s) enviado(s) com sucesso!")
                else:
                    print(f"❌ Erro no envio de emails: {resultado_email.get('erro', 'Erro desconhecido')}")
            else:
                print(f"✅ Cliente satisfeito - nenhum alerta necessário")
                
        except Exception as e:
            # Se a IA falhar, não quebrar o fluxo principal
            print(f"⚠️ Erro na análise de IA (pesquisa salva normalmente): {str(e)}")
            
            # Registrar erro no log (opcional)
            try:
                error_query = """
                INSERT INTO analises_sentimento 
                (pesquisa_id, resposta_consolidada, sentimento, confianca, pontuacao_hibrida, motivo_insatisfacao)
                VALUES (%s, %s, %s, %s, %s, %s)
                """
                execute_query(error_query, (
                    pesquisa_id,
                    f"Erro na análise: {str(e)}",
                    'neutral',
                    0.0,
                    0,
                    f"Erro no processamento: {str(e)}"
                ))
            except:
                pass  # Se nem o log der certo, ignorar
        
        return render_template('cliente/sucesso.html')
        
    except Exception as e:
        print(f"❌ Erro geral ao processar resposta: {str(e)}")
        return f"Erro ao processar resposta: {str(e)}", 500