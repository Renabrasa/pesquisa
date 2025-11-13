# scripts/reprocessar_pesquisas_ia.py
"""
Script para reprocessar pesquisas que falharam na análise de IA
Execute este script quando a chave ZHIPU_API_KEY foi adicionada ao .env
"""

import os
import sys
from datetime import datetime
from dotenv import load_dotenv

# Adicionar o diretório raiz ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

from app.utils.database import execute_query
from app.services.sentiment_analyzer import SentimentAnalyzer
from app.services.email_service import EmailService

def buscar_pesquisas_nao_processadas():
    """Busca pesquisas que não foram processadas pela IA"""
    query = """
    SELECT p.id, p.respondida 
    FROM pesquisas p
    WHERE p.respondida = TRUE 
    AND p.ia_processada = FALSE
    ORDER BY p.data_resposta ASC
    """
    result = execute_query(query, fetch=True)
    return result if result else []

def buscar_respostas_pesquisa(pesquisa_id):
    """Busca todas as respostas de uma pesquisa"""
    query = """
    SELECT 
        r.resposta_texto,
        r.resposta_numerica,
        p.texto as pergunta
    FROM respostas r
    JOIN perguntas p ON r.pergunta_id = p.id
    WHERE r.pesquisa_id = %s
    AND (r.resposta_texto IS NOT NULL OR r.resposta_numerica IS NOT NULL)
    """
    result = execute_query(query, (pesquisa_id,), fetch=True)
    return result if result else []

def processar_pesquisa(pesquisa_id):
    """Processa uma pesquisa com IA"""
    try:
        print(f"\n{'='*60}")
        print(f"🔄 Processando pesquisa ID: {pesquisa_id}")
        print(f"{'='*60}")
        
        # ✅ MARCAR COMO PROCESSADA IMEDIATAMENTE (antes de qualquer processamento)
        query_update_imediato = """
        UPDATE pesquisas 
        SET ia_processada = TRUE
        WHERE id = %s
        """
        execute_query(query_update_imediato, (pesquisa_id,))
        print(f"   ✅ Pesquisa marcada como processada (proteção contra duplicatas)")
        
        # Buscar respostas
        respostas = buscar_respostas_pesquisa(pesquisa_id)
        
        if not respostas:
            print(f"⚠️  Nenhuma resposta encontrada para pesquisa {pesquisa_id}")
            return False
        
        print(f"✅ {len(respostas)} resposta(s) encontrada(s)")
        
        # Preparar respostas para análise
        respostas_processamento = []
        for resposta in respostas:
            if resposta['resposta_texto']:
                # Determinar tipo
                valor = resposta['resposta_texto']
                if valor in ['Muito Insatisfeito', 'Insatisfeito', 'Neutro', 'Satisfeito', 'Muito Satisfeito']:
                    tipo = 'escala_satisfacao'
                elif valor.lower() in ['sim', 'não']:
                    tipo = 'sim_nao'
                else:
                    tipo = 'texto_livre'
                
                respostas_processamento.append({
                    'tipo': tipo,
                    'valor': valor,
                    'pergunta': resposta['pergunta']
                })
            
            elif resposta['resposta_numerica']:
                respostas_processamento.append({
                    'tipo': 'escala_numerica',
                    'valor': str(resposta['resposta_numerica']),
                    'pergunta': resposta['pergunta']
                })
        
        # Analisar com IA
        analyzer = SentimentAnalyzer()
        resultado_analise = analyzer.calcular_pontuacao_hibrida(respostas_processamento)
        
        print(f"   📊 Sentimento: {resultado_analise['sentimento_geral']}")
        print(f"   💯 Pontuação: {resultado_analise['pontuacao_hibrida']}")
        print(f"   🎯 Confiança: {resultado_analise['confianca_geral']}")
        print(f"   🚨 Deve alertar: {resultado_analise['deve_alertar']}")
        
        # Salvar análise
        query_analise = """
        INSERT INTO analises_sentimento 
        (pesquisa_id, resposta_consolidada, sentimento, confianca, pontuacao_hibrida, 
         motivo_insatisfacao, modelo_usado)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        
        execute_query(query_analise, (
            pesquisa_id,
            resultado_analise['texto_consolidado'][:1000],
            resultado_analise['sentimento_geral'],
            resultado_analise['confianca_geral'],
            resultado_analise['pontuacao_hibrida'],
            resultado_analise['motivo_insatisfacao'],
            'glm-4-flash (ZHIPU AI)'
        ))
        
        print(f"   ✅ Análise salva no banco")
        
        # Enviar email se negativo
        if resultado_analise['deve_alertar']:
            print(f"   🚨 Enviando alertas...")
            email_service = EmailService()
            resultado_email = email_service.enviar_alerta_insatisfacao(
                pesquisa_id, 
                resultado_analise
            )
            
            if resultado_email['sucesso']:
                print(f"   📧 {resultado_email['emails_enviados']} email(s) enviado(s)")
            else:
                print(f"   ❌ Erro no envio de email")
        
        return True
        
    except Exception as e:
        print(f"   ❌ Erro ao processar: {str(e)}")
        # Se houve erro, marcar como NÃO processada para tentar novamente
        query_rollback = """
        UPDATE pesquisas 
        SET ia_processada = FALSE
        WHERE id = %s
        """
        try:
            execute_query(query_rollback, (pesquisa_id,))
            print(f"   🔄 Pesquisa desmarcada para reprocessamento")
        except:
            pass
        return False

def main():
    """Função principal"""
    print("\n" + "="*60)
    print("🤖 REPROCESSAMENTO DE PESQUISAS COM IA")
    print("="*60)
    print(f"⏰ Iniciado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print("="*60)
    
    # Verificar se ZHIPU_API_KEY está configurada
    if not os.getenv('ZHIPU_API_KEY'):
        print("\n❌ ERRO: ZHIPU_API_KEY não encontrada no .env")
        print("   Configure a chave antes de executar este script")
        return
    
    print("✅ ZHIPU_API_KEY detectada\n")
    
    # Buscar pesquisas não processadas
    pesquisas = buscar_pesquisas_nao_processadas()
    
    if not pesquisas:
        print("✅ Nenhuma pesquisa para processar!")
        return
    
    print(f"📋 Encontradas {len(pesquisas)} pesquisa(s) para processar\n")
    
    # Processar cada pesquisa
    sucesso = 0
    erro = 0
    
    for pesquisa in pesquisas:
        if processar_pesquisa(pesquisa['id']):
            sucesso += 1
        else:
            erro += 1
    
    # Resumo
    print("\n" + "="*60)
    print("📊 RESUMO DO REPROCESSAMENTO")
    print("="*60)
    print(f"✅ Sucesso: {sucesso}")
    print(f"❌ Erros: {erro}")
    print(f"⏰ Finalizado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print("="*60 + "\n")

if __name__ == '__main__':
    main()