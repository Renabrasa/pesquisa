# app/services/sentiment_analyzer.py

import requests
import json
import os
import re
from typing import Dict, List, Tuple, Optional
from datetime import datetime

class SentimentAnalyzer:
    """
    Serviço de análise de sentimento usando RoBERTa via Hugging Face
    Implementa sistema híbrido: texto livre + escalas numéricas
    """
    
    def __init__(self):
        self.model_name = "cardiffnlp/twitter-xlm-roberta-base-sentiment"
        self.api_url = f"https://api-inference.huggingface.co/models/{self.model_name}"
        self.token = os.getenv('HUGGING_FACE_TOKEN')
        
        if not self.token:
            raise ValueError("HUGGING_FACE_TOKEN não encontrado no .env")
        
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
        
        # Palavras-chave para detectar insatisfação
        self.palavras_insatisfacao = [
            'confuso', 'difícil', 'não entendi', 'perdido', 'mal explicado',
            'desorganizado', 'ruim', 'péssimo', 'horrível', 'terrível',
            'perdi tempo', 'decepcionante', 'frustante', 'chato',
            'não recomendo', 'muito técnico', 'muito rápido', 'muito lento',
            'não consegui', 'não aprendi', 'inútil', 'fraco'
        ]
        
        # Palavras-chave para detectar satisfação
        self.palavras_satisfacao = [
            'excelente', 'ótimo', 'muito bom', 'perfeito', 'maravilhoso',
            'claro', 'útil', 'aprendi', 'recomendo', 'fantástico',
            'didático', 'objetivo', 'prático', 'esclarecedor',
            'valeu a pena', 'superou expectativas', 'adorei'
        ]

    def analisar_sentimento_texto(self, texto: str) -> Dict:
        """
        Analisa sentimento de um texto usando RoBERTa
        Com retry logic para timeout
        """
        import time
        
        max_tentativas = 3
        delay_entre_tentativas = 5  # segundos
        
        for tentativa in range(max_tentativas):
            try:
                # Limpar e preparar texto
                texto_limpo = self._limpar_texto(texto)
                
                if not texto_limpo or len(texto_limpo.strip()) < 3:
                    return {
                        'sentimento': 'neutral',
                        'confianca': 0.5,
                        'detalhes': {'erro': 'Texto muito curto ou vazio'}
                    }
                
                # Fazer requisição para Hugging Face
                payload = {"inputs": texto_limpo}
                
                print(f"🤖 Tentativa {tentativa + 1}/{max_tentativas} - Analisando sentimento...")
                
                response = requests.post(
                    self.api_url,
                    headers=self.headers,
                    json=payload,
                    timeout=60  # Aumentado para 60 segundos
                )
                
                if response.status_code == 200:
                    result = response.json()
                    print(f"✅ Análise de sentimento concluída com sucesso!")
                    return self._processar_resposta_roberta(result, texto_limpo)
                else:
                    raise Exception(f"Erro API: {response.status_code} - {response.text}")
                    
            except requests.exceptions.Timeout:
                print(f"⏰ Timeout na tentativa {tentativa + 1}/{max_tentativas}")
                if tentativa < max_tentativas - 1:  # Não é a última tentativa
                    print(f"🔄 Aguardando {delay_entre_tentativas}s antes da próxima tentativa...")
                    time.sleep(delay_entre_tentativas)
                    continue
                else:
                    print(f"❌ Todas as tentativas falharam por timeout")
                    return {
                        'sentimento': 'neutral',
                        'confianca': 0.0,
                        'detalhes': {'erro': f'Timeout após {max_tentativas} tentativas'}
                    }
            except Exception as e:
                print(f"❌ Erro na análise de sentimento (tentativa {tentativa + 1}): {str(e)}")
                if tentativa < max_tentativas - 1:
                    print(f"🔄 Tentando novamente em {delay_entre_tentativas}s...")
                    time.sleep(delay_entre_tentativas)
                    continue
                else:
                    return {
                        'sentimento': 'neutral',
                        'confianca': 0.0,
                        'detalhes': {'erro': str(e)}
                    }

    def _processar_resposta_roberta(self, result: List, texto: str) -> Dict:
        """Processa resposta da API RoBERTa e adiciona análise de palavras-chave"""
        
        if not result or not isinstance(result, list) or len(result) == 0:
            return {
                'sentimento': 'neutral',
                'confianca': 0.0,
                'detalhes': {'erro': 'Resposta inválida da API'}
            }
        
        # Pegar classificações da API
        classificacoes = result[0] if isinstance(result[0], list) else result
        
        # Encontrar sentimento com maior score
        melhor_resultado = max(classificacoes, key=lambda x: x.get('score', 0))
        
        # Mapear labels para português
        label_map = {
            'LABEL_0': 'negative',   # Negativo
            'LABEL_1': 'neutral',    # Neutro  
            'LABEL_2': 'positive',   # Positivo
            'negative': 'negative',
            'neutral': 'neutral',
            'positive': 'positive'
        }
        
        sentimento_api = label_map.get(melhor_resultado.get('label', ''), 'neutral')
        confianca_api = melhor_resultado.get('score', 0.0)
        
        # Análise de palavras-chave para melhorar precisão
        palavras_encontradas = self._analisar_palavras_chave(texto)
        
        # Combinar resultado da API com análise de palavras
        sentimento_final, confianca_final = self._combinar_analises(
            sentimento_api, confianca_api, palavras_encontradas
        )
        
        return {
            'sentimento': sentimento_final,
            'confianca': round(confianca_final, 3),
            'detalhes': {
                'api_sentimento': sentimento_api,
                'api_confianca': round(confianca_api, 3),
                'palavras_positivas': palavras_encontradas['positivas'],
                'palavras_negativas': palavras_encontradas['negativas'],
                'classificacoes_completas': classificacoes
            }
        }

    def _analisar_palavras_chave(self, texto: str) -> Dict:
        """Analisa palavras-chave de satisfação/insatisfação no texto"""
        
        texto_lower = texto.lower()
        
        palavras_positivas = []
        palavras_negativas = []
        
        # Buscar palavras de insatisfação
        for palavra in self.palavras_insatisfacao:
            if palavra.lower() in texto_lower:
                palavras_negativas.append(palavra)
        
        # Buscar palavras de satisfação
        for palavra in self.palavras_satisfacao:
            if palavra.lower() in texto_lower:
                palavras_positivas.append(palavra)
        
        return {
            'positivas': palavras_positivas,
            'negativas': palavras_negativas,
            'score_palavras': len(palavras_positivas) - len(palavras_negativas)
        }

    def _combinar_analises(self, sentimento_api: str, confianca_api: float, 
                          palavras: Dict) -> Tuple[str, float]:
        """Combina resultado da API com análise de palavras-chave"""
        
        score_palavras = palavras['score_palavras']
        
        # Se palavras-chave são muito claras, dar mais peso a elas
        if abs(score_palavras) >= 2:  # 2+ palavras positivas ou negativas
            if score_palavras >= 2:
                return 'positive', min(0.95, confianca_api + 0.1)
            elif score_palavras <= -2:
                return 'negative', min(0.95, confianca_api + 0.1)
        
        # Se há conflito entre API e palavras, analisar contexto
        if score_palavras > 0 and sentimento_api == 'negative':
            if confianca_api < 0.7:  # API pouco confiante
                return 'neutral', 0.6
        elif score_palavras < 0 and sentimento_api == 'positive':
            if confianca_api < 0.7:  # API pouco confiante
                return 'neutral', 0.6
        
        # Usar resultado da API por padrão
        return sentimento_api, confianca_api

    def calcular_pontuacao_hibrida(self, respostas_dados: List[Dict]) -> Dict:
        """
        Calcula pontuação híbrida baseada em todos os tipos de resposta
        
        Args:
            respostas_dados: Lista de dicts com respostas formatadas
            
        Returns:
            dict: Análise completa com pontuação híbrida
        """
        
        pontos_totais = 0
        textos_para_analise = []
        detalhes_analise = {
            'respostas_texto': [],
            'respostas_numericas': [],
            'respostas_satisfacao': [],
            'respostas_sim_nao': []
        }
        
        # Processar cada resposta
        for resposta in respostas_dados:
            tipo = resposta.get('tipo', 'texto')
            valor = resposta.get('valor', '')
            pergunta = resposta.get('pergunta', '')
            
            if tipo == 'texto_livre' and valor and len(valor.strip()) > 3:
                # Analisar sentimento do texto
                analise_texto = self.analisar_sentimento_texto(valor)
                
                # Converter para pontos
                if analise_texto['sentimento'] == 'positive':
                    pontos = 1
                elif analise_texto['sentimento'] == 'negative':
                    pontos = -1
                else:
                    pontos = 0
                
                pontos_totais += pontos
                textos_para_analise.append(valor)
                
                detalhes_analise['respostas_texto'].append({
                    'pergunta': pergunta,
                    'texto': valor,
                    'sentimento': analise_texto['sentimento'],
                    'confianca': analise_texto['confianca'],
                    'pontos': pontos
                })
            
            elif tipo == 'escala_numerica':
                # Converter escala para pontos
                try:
                    nota = float(valor)
                    if nota <= 4:
                        pontos = -1
                    elif nota >= 8:
                        pontos = 1
                    else:
                        pontos = 0
                    
                    pontos_totais += pontos
                    
                    detalhes_analise['respostas_numericas'].append({
                        'pergunta': pergunta,
                        'nota': nota,
                        'pontos': pontos
                    })
                except (ValueError, TypeError):
                    pass
            
            elif tipo == 'escala_satisfacao':
                # Converter satisfação para pontos
                pontos = 0
                if valor in ['Muito Insatisfeito', 'Insatisfeito']:
                    pontos = -1
                elif valor in ['Satisfeito', 'Muito Satisfeito']:
                    pontos = 1
                
                pontos_totais += pontos
                
                detalhes_analise['respostas_satisfacao'].append({
                    'pergunta': pergunta,
                    'resposta': valor,
                    'pontos': pontos
                })
            
            elif tipo == 'sim_nao':
                # Sim/Não depende do contexto da pergunta
                pontos = self._analisar_sim_nao(pergunta, valor)
                pontos_totais += pontos
                
                detalhes_analise['respostas_sim_nao'].append({
                    'pergunta': pergunta,
                    'resposta': valor,
                    'pontos': pontos
                })
        
        # Análise consolidada dos textos
        texto_consolidado = " ".join(textos_para_analise)
        sentimento_geral = 'neutral'
        confianca_geral = 0.5
        motivo_insatisfacao = None
        
        if texto_consolidado.strip():
            analise_consolidada = self.analisar_sentimento_texto(texto_consolidado)
            sentimento_geral = analise_consolidada['sentimento']
            confianca_geral = analise_consolidada['confianca']
            
            # Gerar motivo de insatisfação se necessário
            if sentimento_geral == 'negative':
                motivo_insatisfacao = self._gerar_motivo_insatisfacao(
                    detalhes_analise, analise_consolidada
                )
        
        return {
            'sentimento_geral': sentimento_geral,
            'confianca_geral': confianca_geral,
            'pontuacao_hibrida': pontos_totais,
            'texto_consolidado': texto_consolidado,
            'motivo_insatisfacao': motivo_insatisfacao,
            'detalhes_completos': detalhes_analise,
            'deve_alertar': (sentimento_geral == 'negative' or pontos_totais <= -1)
        }

    def _analisar_sim_nao(self, pergunta: str, resposta: str) -> int:
        """Analisa resposta Sim/Não baseada no contexto da pergunta"""
        
        pergunta_lower = pergunta.lower()
        
        # Perguntas onde "Não" é negativo
        contextos_negativos = [
            'recomenda', 'satisfeito', 'atendeu', 'gostou', 'aprovou',
            'valeu', 'útil', 'claro', 'entendeu'
        ]
        
        # Perguntas onde "Sim" é negativo  
        contextos_positivos_inversos = [
            'dificuldade', 'problema', 'confuso', 'difícil'
        ]
        
        if resposta.lower() == 'sim':
            # Verificar se é contexto inverso
            for contexto in contextos_positivos_inversos:
                if contexto in pergunta_lower:
                    return -1  # "Sim" para problemas = negativo
            
            # Por padrão, "Sim" é positivo
            return 1
        
        elif resposta.lower() == 'não':
            # Verificar se é contexto normal
            for contexto in contextos_negativos:
                if contexto in pergunta_lower:
                    return -1  # "Não" para coisas boas = negativo
            
            # Para contextos inversos, "Não" é positivo
            for contexto in contextos_positivos_inversos:
                if contexto in pergunta_lower:
                    return 1  # "Não" para problemas = positivo
        
        return 0  # Neutro se não conseguir determinar

    def _gerar_motivo_insatisfacao(self, detalhes: Dict, analise_consolidada: Dict) -> str:
        """Gera resumo do motivo da insatisfação"""
        
        motivos = []
        
        # Verificar textos negativos
        for resposta_texto in detalhes['respostas_texto']:
            if resposta_texto['sentimento'] == 'negative':
                # Pegar palavras-chave negativas se disponível
                palavras_neg = analise_consolidada.get('detalhes', {}).get('palavras_negativas', [])
                if palavras_neg:
                    motivos.append(f"Mencionou: {', '.join(palavras_neg[:3])}")
                else:
                    motivos.append("Comentário com sentimento negativo")
        
        # Verificar notas baixas
        notas_baixas = [r for r in detalhes['respostas_numericas'] if r['pontos'] == -1]
        if notas_baixas:
            notas = [str(r['nota']) for r in notas_baixas[:2]]
            motivos.append(f"Notas baixas: {', '.join(notas)}")
        
        # Verificar escalas de insatisfação
        insatisfacoes = [r for r in detalhes['respostas_satisfacao'] if r['pontos'] == -1]
        if insatisfacoes:
            respostas = [r['resposta'] for r in insatisfacoes[:2]]
            motivos.append(f"Avaliou como: {', '.join(respostas)}")
        
        return "; ".join(motivos) if motivos else "Sentimento negativo detectado"

    def _limpar_texto(self, texto: str) -> str:
        """Remove caracteres especiais e limpa o texto"""
        if not texto:
            return ""
        
        # Remover HTML tags se houver
        texto = re.sub(r'<[^>]+>', '', texto)
        
        # Remover caracteres especiais excessivos
        texto = re.sub(r'[^\w\s\.\,\!\?\;\:\-\(\)]', ' ', texto)
        
        # Remover espaços extras
        texto = re.sub(r'\s+', ' ', texto)
        
        return texto.strip()

    def testar_conexao(self) -> Dict:
        """Testa conexão com a API Hugging Face"""
        
        try:
            resultado = self.analisar_sentimento_texto("Este é um teste de conexão.")
            return {
                'sucesso': True,
                'modelo': self.model_name,
                'resultado_teste': resultado
            }
        except Exception as e:
            return {
                'sucesso': False,
                'erro': str(e),
                'modelo': self.model_name
            }