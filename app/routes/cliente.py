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
    
    # PROCESSAR OPÇÕES JSON DAS PERGUNTAS
    import json
    for pergunta in perguntas:
        if pergunta['opcoes']:
            try:
                # Converter string JSON para lista Python
                pergunta['opcoes'] = json.loads(pergunta['opcoes'])
            except (json.JSONDecodeError, TypeError):
                # Se não conseguir processar, deixar como lista vazia
                pergunta['opcoes'] = []
        else:
            pergunta['opcoes'] = []
    
    # Garantir foto padrão se agente não tiver foto
    if not pesquisa['agente_foto']:
        pesquisa['agente_foto'] = '/static/uploads/avatars/default-avatar.png'
    
    return render_template('cliente/formulario.html', pesquisa=pesquisa, perguntas=perguntas)

@bp.route('/<pesquisa_uuid>/enviar', methods=['POST'])
def enviar_resposta(pesquisa_uuid):
    try:
        print(f"🔍 === DEBUG INÍCIO ===")
        print(f"📋 Processando pesquisa: {pesquisa_uuid}")
        print(f"📋 request.form: {dict(request.form)}")
        print(f"📋 request.method: {request.method}")
        print(f"📋 request.content_type: {request.content_type}")
        
        # Verificar se tem dados
        if not request.form:
            print("❌ ERRO: request.form vazio!")
            print(f"📋 request.values: {dict(request.values)}")
            print(f"📋 request.data: {request.data}")
            return "Erro: Formulário vazio", 400
        
        # Buscar pesquisa
        query = "SELECT id FROM pesquisas WHERE uuid = %s AND respondida = FALSE"
        result = execute_query(query, (pesquisa_uuid,), fetch=True)
        
        if not result:
            print("❌ Pesquisa não encontrada ou já respondida")
            return "Pesquisa não encontrada ou já respondida", 404
        
        pesquisa_id = result[0]['id']
        print(f"✅ Pesquisa ID: {pesquisa_id}")
        
        # === PROCESSAMENTO DAS RESPOSTAS ===
        respostas_processamento = []
        respostas_salvas = 0
        
        for campo, valor in request.form.items():
            print(f"🔍 Campo: '{campo}' = '{valor}'")
            
            if campo.startswith('pergunta_') and valor.strip():
                pergunta_id = campo.replace('pergunta_', '')
                print(f"   📋 Pergunta ID: {pergunta_id}")
                
                # Buscar informações da pergunta
                query_pergunta = """
                SELECT p.*, tp.nome as tipo_nome
                FROM perguntas p
                LEFT JOIN tipos_perguntas tp ON p.tipo_pergunta_id = tp.id
                WHERE p.id = %s
                """
                pergunta_info = execute_query(query_pergunta, (pergunta_id,), fetch=True)
                
                if pergunta_info:
                    pergunta_data = pergunta_info[0]
                    print(f"   📄 Pergunta: {pergunta_data['texto']}")
                    print(f"   🏷️ Tipo: {pergunta_data['tipo_pergunta_id']}")
                    
                    # === DETERMINAR TIPO E SALVAR ===
                    if valor.replace('.', '').replace(',', '').isdigit():
                        # RESPOSTA NUMÉRICA (ESCALA)
                        query_resposta = """
                        INSERT INTO respostas (pesquisa_id, pergunta_id, resposta_numerica)
                        VALUES (%s, %s, %s)
                        """
                        valor_numerico = float(valor.replace(',', '.'))
                        params = (pesquisa_id, pergunta_id, valor_numerico)
                        
                        respostas_processamento.append({
                            'tipo': 'escala_numerica',
                            'valor': str(valor_numerico),
                            'pergunta': pergunta_data['texto']
                        })
                        
                        print(f"   📊 Salvando como numérica: {valor_numerico}")
                        
                    else:
                        # RESPOSTA TEXTO
                        query_resposta = """
                        INSERT INTO respostas (pesquisa_id, pergunta_id, resposta_texto)
                        VALUES (%s, %s, %s)
                        """
                        params = (pesquisa_id, pergunta_id, valor)
                        
                        # Classificar tipo de texto para IA
                        tipo_pergunta = pergunta_data.get('tipo_nome', '').lower()
                        
                        if valor in ['Muito Satisfeito', 'Satisfeito', 'Neutro', 'Insatisfeito', 'Muito Insatisfeito']:
                            tipo_resposta = 'escala_satisfacao'
                        elif valor.lower() in ['sim', 'não', 'yes', 'no']:
                            tipo_resposta = 'sim_nao'
                        else:
                            tipo_resposta = 'texto_livre'
                        
                        respostas_processamento.append({
                            'tipo': tipo_resposta,
                            'valor': valor,
                            'pergunta': pergunta_data['texto']
                        })
                        
                        print(f"   📝 Salvando como texto ({tipo_resposta}): {valor}")
                    
                    # Executar INSERT
                    execute_query(query_resposta, params)
                    respostas_salvas += 1
                    print(f"   ✅ Resposta salva no banco!")
                    
                else:
                    print(f"   ❌ Pergunta {pergunta_id} não encontrada no banco")
            else:
                print(f"   ⭕ Campo ignorado (não é pergunta ou está vazio)")
        
        print(f"💾 TOTAL RESPOSTAS SALVAS: {respostas_salvas}")
        print(f"🤖 RESPOSTAS PARA IA: {len(respostas_processamento)}")
        
        # === MARCAR PESQUISA COMO RESPONDIDA ===
        query_update = """
        UPDATE pesquisas 
        SET respondida = TRUE, data_resposta = NOW(), ip_resposta = %s
        WHERE id = %s
        """
        
        ip_cliente = request.environ.get('HTTP_X_FORWARDED_FOR', request.environ.get('REMOTE_ADDR'))
        execute_query(query_update, (ip_cliente, pesquisa_id))
        print(f"✅ Pesquisa {pesquisa_id} marcada como respondida")
        
        # === ANÁLISE DE IA ===
        if respostas_processamento:
            print(f"🤖 === INICIANDO ANÁLISE DE IA ===")
            print(f"📋 Dados para análise: {respostas_processamento}")
            
            try:
                from app.services.sentiment_analyzer import SentimentAnalyzer
                from app.services.email_service import EmailService
                
                # Processar com IA
                analyzer = SentimentAnalyzer()
                resultado_analise = analyzer.calcular_pontuacao_hibrida(respostas_processamento)
                
                print(f"🎯 === RESULTADO DA IA ===")
                print(f"   Sentimento: {resultado_analise['sentimento_geral']}")
                print(f"   Pontuação: {resultado_analise.get('pontuacao_hibrida', 0)}")
                print(f"   Confiança: {resultado_analise.get('confianca_geral', 0.5)}")
                print(f"   Deve alertar: {resultado_analise.get('deve_alertar', False)}")
                print(f"   Motivo: {resultado_analise.get('motivo_insatisfacao', 'N/A')}")
                
                # Salvar análise no banco
                query_analise = """
                INSERT INTO analises_sentimento 
                (pesquisa_id, resposta_consolidada, sentimento, confianca, pontuacao_hibrida, motivo_insatisfacao)
                VALUES (%s, %s, %s, %s, %s, %s)
                """
                
                execute_query(query_analise, (
                    pesquisa_id,
                    resultado_analise.get('texto_consolidado', '')[:1000],
                    resultado_analise['sentimento_geral'],
                    resultado_analise.get('confianca_geral', 0.5),
                    resultado_analise.get('pontuacao_hibrida', 0),
                    resultado_analise.get('motivo_insatisfacao', '')
                ))
                
                print(f"✅ Análise IA salva no banco")
                # NOVA LINHA: Marcar como processada pela IA
                execute_query("UPDATE pesquisas SET ia_processada = TRUE WHERE id = %s", (pesquisa_id,))
                print(f"✅ Status IA atualizado para pesquisa {pesquisa_id}")
                
                # === ENVIO DE EMAIL SE NECESSÁRIO ===
                if resultado_analise.get('deve_alertar', False):
                    print(f"🚨 === INSATISFAÇÃO DETECTADA! ===")
                    
                    try:
                        email_service = EmailService()
                        resultado_email = email_service.enviar_alerta_insatisfacao(
                            pesquisa_id, 
                            resultado_analise
                        )
                        
                        if resultado_email.get('sucesso', False):
                            print(f"📧 ✅ {resultado_email.get('emails_enviados', 0)} email(s) enviado(s)!")
                        else:
                            print(f"📧 ❌ Erro no envio: {resultado_email.get('erro', 'Erro desconhecido')}")
                            
                    except Exception as e:
                        print(f"📧 ⚠️ Erro no serviço de email: {str(e)}")
                        
                else:
                    print(f"✅ Cliente satisfeito - nenhum alerta necessário")
                    
            except Exception as e:
                print(f"🤖 ⚠️ Erro na IA: {str(e)}")
                
                # Salvar erro no banco para auditoria
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
                    print(f"📋 Erro registrado no banco para auditoria")
                except:
                    print(f"📋 ⚠️ Não foi possível registrar o erro no banco")
        else:
            print(f"🤖 ⚠️ Nenhuma resposta para analisar - IA não executada")
            
            # Salvar análise vazia
            try:
                query_analise_vazia = """
                INSERT INTO analises_sentimento 
                (pesquisa_id, resposta_consolidada, sentimento, confianca, pontuacao_hibrida, motivo_insatisfacao)
                VALUES (%s, %s, %s, %s, %s, %s)
                """
                execute_query(query_analise_vazia, (
                    pesquisa_id,
                    "Nenhuma resposta processada",
                    'neutral',
                    0.0,
                    0,
                    "Formulário sem respostas válidas"
                ))
                print(f"📋 Análise vazia registrada")
                # NOVA LINHA: Marcar como processada (mesmo sendo vazia)
                execute_query("UPDATE pesquisas SET ia_processada = TRUE WHERE id = %s", (pesquisa_id,))
                print(f"✅ Status IA atualizado (análise vazia) para pesquisa {pesquisa_id}")
            except:
                pass
        
        print(f"🎉 === PROCESSAMENTO CONCLUÍDO ===")
        return render_template('cliente/sucesso.html')
        
    except Exception as e:
        print(f"❌ === ERRO GERAL ===")
        print(f"Erro: {str(e)}")
        import traceback
        print(f"Stack: {traceback.format_exc()}")
        return f"Erro interno: {str(e)}", 500