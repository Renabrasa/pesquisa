# app/services/email_service.py

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import os
from datetime import datetime
from typing import Dict, List, Optional
from app.utils.database import execute_query
import ssl

class EmailService:
    """
    Serviço de envio de emails para alertas de insatisfação
    Usa SMTP personalizado da empresa
    """
    
    def __init__(self):
        # Carregar configurações SMTP do .env
        self.smtp_server = os.getenv('SMTP_SERVER')
        self.smtp_port = int(os.getenv('SMTP_PORT', 587))
        self.smtp_username = os.getenv('SMTP_USERNAME')
        self.smtp_password = os.getenv('SMTP_PASSWORD')
        self.email_remetente = os.getenv('EMAIL_REMETENTE')
        self.nome_remetente = os.getenv('NOME_REMETENTE', 'Sistema de Pesquisa de Satisfação')
        
        # Verificar se todas as configurações obrigatórias estão presentes
        required_configs = [
            ('SMTP_SERVER', self.smtp_server),
            ('SMTP_USERNAME', self.smtp_username), 
            ('SMTP_PASSWORD', self.smtp_password),
            ('EMAIL_REMETENTE', self.email_remetente)
        ]
        
        missing_configs = [name for name, value in required_configs if not value]
        if missing_configs:
            raise ValueError(f"Configurações SMTP obrigatórias não encontradas no .env: {', '.join(missing_configs)}")
        
        # URL base da aplicação (para links no email)
        self.app_url = os.getenv('APP_URL', 'http://localhost:5000')

    # SUBSTITUIR o método enviar_alerta_insatisfacao() no arquivo: app/services/email_service.py
# Adicionar logs detalhados para debug

    def enviar_alerta_insatisfacao(self, pesquisa_id: int, analise_sentimento: Dict) -> Dict:
        """
        Envia alerta de insatisfação para gestores configurados
        
        Args:
            pesquisa_id (int): ID da pesquisa
            analise_sentimento (dict): Resultado da análise de sentimento
            
        Returns:
            dict: Resultado do envio com status e detalhes
        """
        
        try:
            print(f"📧 [DEBUG] Iniciando envio de alerta para pesquisa {pesquisa_id}")
            
            # Buscar dados da pesquisa
            dados_pesquisa = self._buscar_dados_pesquisa(pesquisa_id)
            if not dados_pesquisa:
                print(f"❌ [DEBUG] Pesquisa {pesquisa_id} não encontrada")
                return {
                    'sucesso': False,
                    'erro': 'Pesquisa não encontrada',
                    'emails_enviados': 0
                }
            
            print(f"✅ [DEBUG] Pesquisa encontrada: {dados_pesquisa['nome_cliente']} - Produto: {dados_pesquisa['tipo_produto']}")
            
            # Buscar gestores que devem receber o alerta
            gestores = self._buscar_gestores_para_alerta(dados_pesquisa['tipo_produto'])
            if not gestores:
                print(f"⚠️ [DEBUG] Nenhum gestor configurado para produto: {dados_pesquisa['tipo_produto']}")
                return {
                    'sucesso': True,
                    'mensagem': 'Nenhum gestor configurado para receber alertas deste produto',
                    'emails_enviados': 0
                }
            
            print(f"👥 [DEBUG] {len(gestores)} gestor(es) encontrado(s)")
            
            # Preparar dados do email
            assunto = self._gerar_assunto(dados_pesquisa, analise_sentimento)
            dados_email = self._gerar_corpo_email(dados_pesquisa, analise_sentimento)

            
            print(f"📝 [DEBUG] Assunto: {assunto}")
            
            emails_enviados = 0
            erros = []
            
            # Enviar para cada gestor
            for i, gestor in enumerate(gestores, 1):
                try:
                    print(f"📮 [DEBUG] Enviando email {i}/{len(gestores)} para: {gestor['email']}")
                    
                    resultado_envio = self._enviar_email(
                        destinatario=gestor['email'],
                        nome_destinatario=gestor['nome'],
                        assunto=assunto,
                        dados_email=dados_email
                    )
                    
                    if resultado_envio['sucesso']:
                        emails_enviados += 1
                        print(f"✅ [DEBUG] Email enviado com sucesso para {gestor['email']}")
                        
                        # Registrar no log
                        self._registrar_log_email(
                            pesquisa_id=pesquisa_id,
                            email_destinatario=gestor['email'],
                            assunto=assunto,
                            sucesso=True,
                            erro=None,
                            analise_sentimento_id=None
                        )
                    else:
                        erro_msg = f"{gestor['email']}: {resultado_envio['erro']}"
                        erros.append(erro_msg)
                        print(f"❌ [DEBUG] Falha no envio para {gestor['email']}: {resultado_envio['erro']}")
                        
                        # Registrar erro no log
                        self._registrar_log_email(
                            pesquisa_id=pesquisa_id,
                            email_destinatario=gestor['email'],
                            assunto=assunto,
                            sucesso=False,
                            erro=resultado_envio['erro'],
                            analise_sentimento_id=None
                        )
                        
                except Exception as e:
                    erro_msg = f"Erro ao enviar para {gestor['email']}: {str(e)}"
                    erros.append(erro_msg)
                    print(f"💥 [DEBUG] Exceção no envio para {gestor['email']}: {str(e)}")
                    
                    # Registrar erro no log
                    self._registrar_log_email(
                        pesquisa_id=pesquisa_id,
                        email_destinatario=gestor['email'],
                        assunto=assunto,
                        sucesso=False,
                        erro=str(e),
                        analise_sentimento_id=None
                    )
            
            resultado_final = {
                'sucesso': emails_enviados > 0,
                'emails_enviados': emails_enviados,
                'total_gestores': len(gestores),
                'erros': erros if erros else None
            }
            
            print(f"🎯 [DEBUG] Resultado final: {resultado_final}")
            
            return resultado_final
            
        except Exception as e:
            print(f"💥 [DEBUG] Erro geral no envio de alertas: {str(e)}")
            return {
                'sucesso': False,
                'erro': f"Erro geral no envio: {str(e)}",
                'emails_enviados': 0
            }


    def enviar_senha_temporaria(self, nome_usuario: str, email_destinatario: str, 
                          senha_temporaria: str, gestor_nome: str) -> Dict:
        """
        Envia email com senha temporária para usuário
        
        Args:
            nome_usuario (str): Nome do usuário que terá a senha resetada
            email_destinatario (str): Email do usuário
            senha_temporaria (str): Nova senha temporária gerada
            gestor_nome (str): Nome do gestor que resetou a senha
            
        Returns:
            dict: Resultado do envio com status e detalhes
        """
        
        try:
            print(f"📧 [DEBUG] Enviando senha temporária para {email_destinatario}")
            
            # === CRIAR CONTEÚDO DO EMAIL ===
            
            assunto = f"Nova Senha Temporária - Sistema de Pesquisa"
            
            # Versão HTML
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <style>
                    body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                    .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                    .header {{ background-color: #f8f9fa; padding: 20px; text-align: center; border-radius: 8px 8px 0 0; }}
                    .content {{ background-color: white; padding: 30px; border: 1px solid #dee2e6; }}
                    .password-box {{ background-color: #e9ecef; padding: 15px; border-radius: 5px; text-align: center; margin: 20px 0; }}
                    .password {{ font-size: 24px; font-weight: bold; color: #007bff; letter-spacing: 2px; }}
                    .alert {{ background-color: #fff3cd; border: 1px solid #ffeaa7; padding: 15px; border-radius: 5px; margin: 20px 0; }}
                    .footer {{ background-color: #f8f9fa; padding: 15px; text-align: center; font-size: 12px; color: #6c757d; border-radius: 0 0 8px 8px; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>🔑 Nova Senha Temporária</h1>
                    </div>
                    
                    <div class="content">
                        <p>Olá <strong>{nome_usuario}</strong>,</p>
                        
                        <p>Sua senha foi resetada pelo gestor <strong>{gestor_nome}</strong> no Sistema de Pesquisa de Satisfação.</p>
                        
                        <div class="password-box">
                            <p><strong>Sua nova senha temporária é:</strong></p>
                            <div class="password">{senha_temporaria}</div>
                        </div>
                        
                        <div class="alert">
                            <strong>⚠️ IMPORTANTE:</strong>
                            <ul>
                                <li>Esta é uma senha temporária</li>
                                <li>Altere sua senha após o primeiro login</li>
                                <li>Esta senha expira em 30 dias</li>
                                <li>Use as credenciais: <strong>{email_destinatario}</strong> e a senha acima</li>
                            </ul>
                        </div>
                        
                        <p>Para acessar o sistema: <a href="{self.app_url}/auth/login">{self.app_url}/auth/login</a></p>
                        
                        <p>Se você não solicitou esta alteração, entre em contato com o administrador imediatamente.</p>
                    </div>
                    
                    <div class="footer">
                        Sistema de Pesquisa de Satisfação<br>
                        Email enviado automaticamente em {datetime.now().strftime('%d/%m/%Y às %H:%M:%S')}
                    </div>
                </div>
            </body>
            </html>
            """
            
            # Versão texto simples
            texto_content = f"""
            Nova Senha Temporária - Sistema de Pesquisa
            
            Olá {nome_usuario},
            
            Sua senha foi resetada pelo gestor {gestor_nome} no Sistema de Pesquisa de Satisfação.
            
            Sua nova senha temporária é: {senha_temporaria}
            
            IMPORTANTE:
            - Esta é uma senha temporária
            - Altere sua senha após o primeiro login  
            - Esta senha expira em 30 dias
            - Use as credenciais: {email_destinatario} e a senha acima
            
            Para acessar o sistema: {self.app_url}/auth/login
            
            Se você não solicitou esta alteração, entre em contato com o administrador imediatamente.
            
            ────────────────────────────────────────
            Sistema de Pesquisa de Satisfação
            Email enviado automaticamente em {datetime.now().strftime('%d/%m/%Y às %H:%M:%S')}
            """
            
            # === ENVIAR EMAIL ===
            
            resultado_envio = self._enviar_email(
                destinatario=email_destinatario,
                nome_destinatario=nome_usuario,
                assunto=assunto,
                corpo_html=html_content,
                corpo_texto=texto_content
            )
            
            if resultado_envio['sucesso']:
                print(f"✅ [DEBUG] Senha temporária enviada com sucesso!")
                
                # Registrar no log (opcional - se você tiver tabela de log)
                # self._registrar_log_email(
                #     pesquisa_id=None,
                #     email_destinatario=email_destinatario,
                #     assunto=assunto,
                #     sucesso=True,
                #     erro=None
                # )
                
                return {
                    'sucesso': True,
                    'email_enviado': email_destinatario,
                    'mensagem': 'Senha temporária enviada com sucesso'
                }
            else:
                return {
                    'sucesso': False,
                    'erro': resultado_envio.get('erro', 'Erro desconhecido no envio')
                }
                
        except Exception as e:
            print(f"💥 [DEBUG] Erro ao enviar senha temporária: {str(e)}")
            return {
                'sucesso': False,
                'erro': f'Erro interno: {str(e)}'
            }




    def _buscar_dados_pesquisa(self, pesquisa_id: int) -> Optional[Dict]:
        """Busca dados completos da pesquisa"""
        
        query = """
        SELECT 
            p.id,
            p.uuid,
            p.codigo_cliente,
            p.nome_cliente,
            p.nome_treinamento,
            p.data_resposta,
            p.created_at,
            u.nome as agente_nome,
            u.email as agente_email,
            tp.id as tipo_produto_id,
            tp.nome as tipo_produto
        FROM pesquisas p
        JOIN usuarios u ON p.agente_id = u.id
        JOIN tipos_produtos tp ON p.tipo_produto_id = tp.id
        WHERE p.id = %s
        """
        
        result = execute_query(query, (pesquisa_id,), fetch=True)
        return result[0] if result else None

    def _buscar_gestores_para_alerta(self, tipo_produto: str) -> List[Dict]:
        """Busca gestores que devem receber alertas para o produto específico"""
        
        # Mapear nome do produto para campo do banco
        campo_alerta = None
        if 'Time is Money' in tipo_produto or 'time' in tipo_produto.lower():
            campo_alerta = 'alerta_time_is_money'
        elif 'Servidor' in tipo_produto or 'servidor' in tipo_produto.lower() or 'nuvem' in tipo_produto.lower():
            campo_alerta = 'alerta_servidor_nuvem'
        elif 'Alterdata' in tipo_produto or 'alterdata' in tipo_produto.lower():
            campo_alerta = 'alerta_alterdata'

        if not campo_alerta:
            print(f"⚠️ Produto não mapeado para alertas: {tipo_produto}")
            return []
        
        query = f"""
        SELECT 
            id,
            nome,
            email
        FROM usuarios
        WHERE tipo_usuario = 'gestor'
        AND ativo = TRUE
        AND {campo_alerta} = TRUE
        """
        
        result = execute_query(query, fetch=True)
        gestores_encontrados = result if result else []
        
        print(f"📧 Gestores encontrados para '{tipo_produto}': {len(gestores_encontrados)}")
        for gestor in gestores_encontrados:
            print(f"   - {gestor['nome']} ({gestor['email']})")
        
        return gestores_encontrados

    def _gerar_assunto(self, dados_pesquisa: Dict, analise_sentimento: Dict) -> str:
        """Gera assunto do email de alerta"""
        
        sentimento = analise_sentimento.get('sentimento_geral', 'negative')
        pontuacao = analise_sentimento.get('pontuacao_hibrida', 0)
        
        if sentimento == 'negative' and pontuacao <= -1:
            nivel = "CRÍTICO"
        elif sentimento == 'negative':
            nivel = "ALTO"
        else:
            nivel = "MÉDIO"
        
        return f"🚨 ALERTA [{nivel}] - Cliente Insatisfeito: {dados_pesquisa['nome_cliente']}"

    def _gerar_corpo_email(self, dados_pesquisa: Dict, analise_sentimento: Dict) -> Dict:
        """Gera dados estruturados profissionais para o email"""
        
        sentimento = analise_sentimento.get('sentimento_geral', 'negative')
        pontuacao = analise_sentimento.get('pontuacao_hibrida', 0)
        confianca = analise_sentimento.get('confianca_geral', 0)
        motivo = analise_sentimento.get('motivo_insatisfacao', 'Não especificado')
        detalhes = analise_sentimento.get('detalhes_completos', {})
        
        # Determinar nível e cor baseada na gravidade
        if sentimento == 'negative' and pontuacao <= -2:
            nivel = "CRÍTICO"
            cor_nivel = "#dc3545"
            urgencia = "Intervenção imediata necessária"
        elif sentimento == 'negative':
            nivel = "ALTO"
            cor_nivel = "#fd7e14"
            urgencia = "Ação recomendada em 24h"
        else:
            nivel = "MÉDIO"
            cor_nivel = "#ffc107"
            urgencia = "Monitoramento recomendado"
        
        # Extrair trechos críticos das respostas de texto
        trechos_criticos = []
        if 'respostas_texto' in detalhes:
            for resposta in detalhes['respostas_texto']:
                if resposta.get('sentimento') == 'negative' and resposta.get('confianca', 0) > 0.7:
                    # Pegar palavras negativas detectadas
                    palavras_negativas = []
                    if 'detalhes' in resposta:
                        palavras_negativas = resposta['detalhes'].get('palavras_negativas', [])
                    
                    # Interpretar o motivo baseado nas palavras
                    interpretacao = "Crítica geral ao serviço"
                    texto = resposta['texto'].lower()
                    
                    if any(palavra in texto for palavra in ['confuso', 'difícil', 'complicado', 'não entendi']):
                        interpretacao = "Dificuldade de compreensão do conteúdo"
                    elif any(palavra in texto for palavra in ['perdi tempo', 'inútil', 'não aprendi']):
                        interpretacao = "Percepção de tempo perdido e baixo aproveitamento"
                    elif any(palavra in texto for palavra in ['mal explicado', 'ruim', 'péssimo']):
                        interpretacao = "Crítica direta à qualidade da apresentação"
                    elif any(palavra in texto for palavra in ['não recomendo', 'decepcionante']):
                        interpretacao = "Insatisfação que pode afetar reputação"
                    
                    trechos_criticos.append({
                        'texto': resposta['texto'][:150] + ('...' if len(resposta['texto']) > 150 else ''),
                        'interpretacao': interpretacao,
                        'confianca': resposta.get('confianca', 0)
                    })
        
        # Analisar notas baixas
        notas_baixas = []
        if 'respostas_numericas' in detalhes:
            for resposta in detalhes['respostas_numericas']:
                if resposta.get('pontos', 0) == -1:  # Nota baixa
                    contexto = "Avaliação geral"
                    if 'instrutor' in resposta['pergunta'].lower():
                        contexto = "Qualidade do instrutor"
                    elif 'conteúdo' in resposta['pergunta'].lower():
                        contexto = "Conteúdo do treinamento"
                    elif 'recomend' in resposta['pergunta'].lower():
                        contexto = "Disposição para recomendar"
                    
                    notas_baixas.append({
                        'nota': resposta['nota'],
                        'contexto': contexto,
                        'pergunta': resposta['pergunta']
                    })
        
        # Gerar resumo inteligente
        resumo_ia = f"Este cliente demonstrou {nivel.lower()} nível de insatisfação. "
        
        if trechos_criticos:
            if len(trechos_criticos) > 1:
                resumo_ia += f"Múltiplos aspectos foram criticados, indicando problemas sistêmicos. "
            else:
                resumo_ia += f"O principal problema identificado relaciona-se à {trechos_criticos[0]['interpretacao'].lower()}. "
        
        if notas_baixas:
            resumo_ia += f"As avaliações numéricas confirmam a insatisfação expressa no texto. "
        
        resumo_ia += f"A confiabilidade desta análise é de {int(confianca * 100)}%, indicando alta precisão na detecção."
        
        return {
            'nivel_alerta': nivel,
            'cor_nivel': cor_nivel,
            'urgencia': urgencia,
            'cliente': {
                'nome': dados_pesquisa['nome_cliente'],
                'codigo': dados_pesquisa['codigo_cliente'],
                'treinamento': dados_pesquisa['nome_treinamento'],
                'produto': dados_pesquisa['tipo_produto'],
                'agente': dados_pesquisa['agente_nome'],
                'data_resposta': dados_pesquisa['data_resposta'].strftime('%d/%m/%Y %H:%M') if dados_pesquisa['data_resposta'] else 'N/A'
            },
            'analise': {
                'sentimento': sentimento,
                'confianca': int(confianca * 100),
                'trechos_criticos': trechos_criticos[:3],  # Máximo 3 trechos
                'notas_baixas': notas_baixas,
                'resumo_ia': resumo_ia,
                'pontuacao': pontuacao
            },
            'link_detalhes': f"{self.app_url}/gestor/detalhes/{dados_pesquisa['id']}"
        }

    def _enviar_email(self, destinatario: str, nome_destinatario: str, 
                assunto: str, dados_email: Dict = None, 
                corpo_html: str = None, corpo_texto: str = None) -> Dict:
        """Envia email profissional com análise detalhada OU email simples"""
        
        print(f"[DEBUG] === INICIANDO ENVIO DE EMAIL ===")
        print(f"[DEBUG] Destinatário: {destinatario}")
        print(f"[DEBUG] Assunto: {assunto}")
        print(f"[DEBUG] Tipo: {'Alerta' if dados_email else 'Simples'}")
        
        # Validar configurações SMTP
        print(f"[DEBUG] === CONFIGURAÇÕES SMTP ===")
        print(f"[DEBUG] Servidor: {self.smtp_server}")
        print(f"[DEBUG] Porta: {self.smtp_port}")
        print(f"[DEBUG] Username: {self.smtp_username}")
        print(f"[DEBUG] Remetente: {self.email_remetente}")
        print(f"[DEBUG] Senha definida: {'SIM' if self.smtp_password else 'NÃO'}")
        print(f"[DEBUG] Senha length: {len(self.smtp_password) if self.smtp_password else 0}")
        
        if not all([self.smtp_server, self.smtp_port, self.smtp_username, self.smtp_password, self.email_remetente]):
            return {
                'sucesso': False,
                'erro': 'Configurações SMTP incompletas no .env'
            }
        
        try:
            # MODO ORIGINAL: Email de alerta (mantém todo código existente)
            if dados_email:
                print(f"[DEBUG] Criando email profissional...")
                print(f"[DEBUG] Nível: {dados_email['nivel_alerta']}")
                
                # === HTML PROFISSIONAL (código existente inalterado) ===
                html_profissional = f"""
        <!DOCTYPE html>
        <html lang="pt-BR">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Alerta de Insatisfação - Sistema de Pesquisa</title>
            <style>
                * {{ margin: 0; padding: 0; box-sizing: border-box; }}
                
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Helvetica Neue', Arial, sans-serif;
                    line-height: 1.6;
                    color: #2c3e50;
                    background: #ecf0f1;
                }}
                
                .email-container {{
                    max-width: 650px;
                    margin: 0 auto;
                    background: #ffffff;
                    border-radius: 8px;
                    overflow: hidden;
                    box-shadow: 0 4px 20px rgba(0,0,0,0.08);
                }}
                
                .header {{
                    background: linear-gradient(135deg, {dados_email['cor_nivel']} 0%, #8b0000 100%);
                    color: #ffffff;
                    padding: 25px 30px;
                    text-align: center;
                    border-bottom: 3px solid rgba(255,255,255,0.2);
                }}
                
                .header h1 {{
                    font-size: 24px;
                    font-weight: 600;
                    margin-bottom: 8px;
                    letter-spacing: 0.5px;
                }}
                
                .nivel-badge {{
                    display: inline-block;
                    background: rgba(255,255,255,0.15);
                    padding: 6px 16px;
                    border-radius: 20px;
                    font-size: 13px;
                    font-weight: 500;
                    border: 1px solid rgba(255,255,255,0.3);
                    backdrop-filter: blur(10px);
                }}
                
                .urgencia {{
                    font-size: 12px;
                    margin-top: 8px;
                    opacity: 0.9;
                    font-style: italic;
                }}
                
                .content {{
                    padding: 30px;
                }}
                
                .alert-section {{
                    background: linear-gradient(135deg, #fff8e1 0%, #ffecb3 100%);
                    border-left: 4px solid #ff8f00;
                    padding: 18px 20px;
                    border-radius: 6px;
                    margin-bottom: 25px;
                }}
                
                .alert-section strong {{
                    color: #e65100;
                    font-weight: 600;
                }}
                
                .info-section {{
                    margin-bottom: 25px;
                }}
                
                .section-title {{
                    font-size: 16px;
                    font-weight: 600;
                    color: #34495e;
                    margin-bottom: 15px;
                    padding-bottom: 8px;
                    border-bottom: 2px solid #ecf0f1;
                    display: flex;
                    align-items: center;
                }}
                
                .section-title::before {{
                    content: '';
                    width: 4px;
                    height: 16px;
                    background: {dados_email['cor_nivel']};
                    margin-right: 10px;
                    border-radius: 2px;
                }}
                
                .client-info {{
                    background: #f8f9fa;
                    padding: 20px;
                    border-radius: 6px;
                    border: 1px solid #e9ecef;
                }}
                
                .info-grid {{
                    display: grid;
                    grid-template-columns: 1fr 1fr;
                    gap: 12px;
                    margin-bottom: 10px;
                }}
                
                .info-item {{
                    display: flex;
                    align-items: center;
                }}
                
                .info-label {{
                    font-weight: 600;
                    color: #495057;
                    min-width: 80px;
                    font-size: 13px;
                }}
                
                .info-value {{
                    color: #212529;
                    font-size: 13px;
                    margin-left: 5px;
                }}
                
                .ai-analysis {{
                    background: linear-gradient(135deg, #f0f7ff 0%, #e3f2fd 100%);
                    border: 1px solid #bbdefb;
                    border-radius: 8px;
                    padding: 20px;
                    margin: 20px 0;
                }}
                
                .confidence-bar {{
                    background: #e0e0e0;
                    height: 6px;
                    border-radius: 3px;
                    overflow: hidden;
                    margin: 8px 0;
                }}
                
                .confidence-fill {{
                    background: linear-gradient(90deg, #4caf50 0%, #2e7d32 100%);
                    height: 100%;
                    width: {dados_email['analise']['confianca']}%;
                    transition: width 0.3s ease;
                }}
                
                .excerpt {{
                    background: #ffffff;
                    border: 1px solid #dee2e6;
                    border-left: 3px solid {dados_email['cor_nivel']};
                    padding: 15px;
                    margin: 10px 0;
                    border-radius: 4px;
                }}
                
                .excerpt-text {{
                    font-style: italic;
                    color: #495057;
                    margin-bottom: 8px;
                    line-height: 1.5;
                }}
                
                .excerpt-interpretation {{
                    font-size: 12px;
                    color: #6c757d;
                    font-weight: 500;
                }}
                
                .summary-box {{
                    background: linear-gradient(135deg, #fff3e0 0%, #ffe0b2 100%);
                    border: 1px solid #ffcc02;
                    border-radius: 6px;
                    padding: 18px;
                    margin: 15px 0;
                }}
                
                .summary-title {{
                    font-weight: 600;
                    color: #ef6c00;
                    margin-bottom: 8px;
                    font-size: 14px;
                }}
                
                .summary-text {{
                    color: #bf360c;
                    font-size: 13px;
                    line-height: 1.5;
                }}
                
                .recommendations {{
                    background: linear-gradient(135deg, #e8f5e8 0%, #c8e6c9 100%);
                    border: 1px solid #81c784;
                    border-radius: 6px;
                    padding: 20px;
                    margin: 20px 0;
                }}
                
                .rec-list {{
                    list-style: none;
                    padding: 0;
                }}
                
                .rec-list li {{
                    padding: 6px 0;
                    color: #2e7d32;
                    font-size: 13px;
                    display: flex;
                    align-items: flex-start;
                }}
                
                .rec-list li::before {{
                    content: '▶';
                    color: #4caf50;
                    margin-right: 8px;
                    margin-top: 1px;
                    font-size: 10px;
                }}
                
                .action-button {{
                    display: inline-block;
                    background: linear-gradient(135deg, #1976d2 0%, #0d47a1 100%);
                    color: #ffffff !important;
                    padding: 12px 24px;
                    text-decoration: none !important;
                    border-radius: 6px;
                    font-weight: 500;
                    font-size: 13px;
                    margin: 15px 0;
                    box-shadow: 0 2px 8px rgba(25,118,210,0.3);
                    transition: all 0.2s ease;
                }}
                
                .action-button:hover {{
                    transform: translateY(-1px);
                    box-shadow: 0 4px 12px rgba(25,118,210,0.4);
                }}
                
                .divider {{
                    height: 1px;
                    background: linear-gradient(90deg, transparent 0%, #bdc3c7 50%, transparent 100%);
                    margin: 25px 0;
                }}
                
                .footer {{
                    background: linear-gradient(135deg, #263238 0%, #37474f 100%);
                    color: #eceff1;
                    padding: 20px 30px;
                    text-align: center;
                    border-top: 1px solid #455a64;
                }}
                
                .footer-main {{
                    font-size: 13px;
                    margin-bottom: 8px;
                    font-weight: 500;
                }}
                
                .footer-timestamp {{
                    font-size: 11px;
                    color: #b0bec5;
                    margin-bottom: 12px;
                }}
                
                .ai-credit {{
                    background: rgba(255,255,255,0.05);
                    border-radius: 20px;
                    padding: 8px 16px;
                    display: inline-block;
                    border: 1px solid rgba(255,255,255,0.1);
                }}
                
                .ai-credit-text {{
                    font-size: 11px;
                    color: #cfd8dc;
                    margin: 0;
                }}
                
                @media (max-width: 600px) {{
                    .email-container {{ margin: 10px; }}
                    .content {{ padding: 20px; }}
                    .info-grid {{ grid-template-columns: 1fr; }}
                    .header {{ padding: 20px; }}
                }}
            </style>
        </head>
        <body>
            <div class="email-container">
                <div class="header">
                    <h1>ALERTA DE INSATISFAÇÃO</h1>
                    <div class="nivel-badge">NÍVEL: {dados_email['nivel_alerta']}</div>
                    <div class="urgencia">{dados_email['urgencia']}</div>
                </div>
                
                <div class="content">
                    <div class="alert-section">
                        <strong>Situação Detectada:</strong> Um cliente demonstrou insatisfação significativa com o treinamento realizado. 
                        Recomenda-se análise imediata e contato direto para resolução.
                    </div>
                    
                    <div class="info-section">
                        <div class="section-title">Informações do Cliente</div>
                        <div class="client-info">
                            <div class="info-grid">
                                <div class="info-item">
                                    <span class="info-label">Cliente:</span>
                                    <span class="info-value"><strong>{dados_email['cliente']['nome']}</strong></span>
                                </div>
                                <div class="info-item">
                                    <span class="info-label">Código:</span>
                                    <span class="info-value">{dados_email['cliente']['codigo']}</span>
                                </div>
                                <div class="info-item">
                                    <span class="info-label">Treinamento:</span>
                                    <span class="info-value">{dados_email['cliente']['treinamento']}</span>
                                </div>
                                <div class="info-item">
                                    <span class="info-label">Produto:</span>
                                    <span class="info-value">{dados_email['cliente']['produto']}</span>
                                </div>
                                <div class="info-item">
                                    <span class="info-label">Agente:</span>
                                    <span class="info-value">{dados_email['cliente']['agente']}</span>
                                </div>
                                <div class="info-item">
                                    <span class="info-label">Data:</span>
                                    <span class="info-value">{dados_email['cliente']['data_resposta']}</span>
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <div class="info-section">
                        <div class="section-title">Análise de Inteligência Artificial</div>
                        <div class="ai-analysis">
                            <p><strong>Confiabilidade da Análise:</strong> {dados_email['analise']['confianca']}%</p>
                            <div class="confidence-bar">
                                <div class="confidence-fill"></div>
                            </div>
                            
                            {self._gerar_trechos_html(dados_email['analise']['trechos_criticos'])}
                            
                            {self._gerar_notas_html(dados_email['analise']['notas_baixas'])}
                            
                            <div class="summary-box">
                                <div class="summary-title">Interpretação da IA:</div>
                                <div class="summary-text">{dados_email['analise']['resumo_ia']}</div>
                            </div>
                        </div>
                    </div>
                    
                    <div class="divider"></div>
                    
                    <div style="text-align: center;">
                        <a href="{dados_email['link_detalhes']}" class="action-button">
                            Ver Análise Completa no Sistema
                        </a>
                    </div>
                    
                    <div class="recommendations">
                        <div class="section-title" style="border: none; margin-bottom: 10px;">Recomendações Estratégicas</div>
                        <ul class="rec-list">
                            <li>Contatar cliente nas próximas 4 horas para demonstrar proatividade</li>
                            <li>Preparar plano de ação específico baseado nos pontos críticos identificados</li>
                            <li>Oferecer sessão de follow-up personalizada sem custo adicional</li>
                            <li>Documentar feedback para melhoria dos processos de treinamento</li>
                            <li>Analisar padrões similares em outras avaliações do mesmo instrutor/produto</li>
                        </ul>
                    </div>
                </div>
                
                <div class="footer">
                    <div class="footer-main">Sistema de Pesquisa de Satisfação</div>
                    <div class="footer-timestamp">
                        Email enviado automaticamente em {datetime.now().strftime('%d/%m/%Y às %H:%M:%S')}
                    </div>
                    <div class="ai-credit">
                        <p class="ai-credit-text">
                            🧠 Análise realizada por: RoBERTa (BERT)<br>
                            IA de última geração especializada em compreensão de linguagem natural
                        </p>
                    </div>
                </div>
            </div>
        </body>
        </html>
                """.strip()
                
                # === VERSÃO TEXTO ===
                texto_profissional = f"""
        ALERTA DE INSATISFACAO - NIVEL {dados_email['nivel_alerta']}
        {dados_email['urgencia']}

        SITUACAO DETECTADA:
        Um cliente demonstrou insatisfacao significativa com o treinamento realizado.
        Recomenda-se analise imediata e contato direto para resolucao.

        INFORMACOES DO CLIENTE:
        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        Cliente: {dados_email['cliente']['nome']}              Codigo: {dados_email['cliente']['codigo']}
        Treinamento: {dados_email['cliente']['treinamento']}
        Produto: {dados_email['cliente']['produto']}           Agente: {dados_email['cliente']['agente']}
        Data da Resposta: {dados_email['cliente']['data_resposta']}

        ANALISE DE INTELIGENCIA ARTIFICIAL:
        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        Confiabilidade: {dados_email['analise']['confianca']}% (alta precisao)

        PRINCIPAIS PROBLEMAS IDENTIFICADOS:
        {self._gerar_trechos_texto(dados_email['analise']['trechos_criticos'])}

        INTERPRETACAO DA IA:
        {dados_email['analise']['resumo_ia']}

        RECOMENDACOES ESTRATEGICAS:
        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        • Contatar cliente nas proximas 4 horas para demonstrar proatividade
        • Preparar plano de acao especifico baseado nos pontos criticos identificados
        • Oferecer sessao de follow-up personalizada sem custo adicional
        • Documentar feedback para melhoria dos processos de treinamento
        • Analisar padroes similares em outras avaliacoes do mesmo instrutor/produto

        ACESSO COMPLETO: {dados_email['link_detalhes']}

        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        Sistema de Pesquisa de Satisfacao
        Email enviado automaticamente em {datetime.now().strftime('%d/%m/%Y as %H:%M:%S')}

        Analise realizada por: RoBERTa (BERT)
        IA de ultima geracao especializada em compreensao de linguagem natural
                """.strip()
                
                subject_line = f"ALERTA [{dados_email['nivel_alerta']}] - Insatisfação Detectada: {dados_email['cliente']['nome']}"
                from_header = f"Sistema de Pesquisa <{self.email_remetente}>"
                
                print(f"[DEBUG] Email de alerta criado")
                print(f"[DEBUG] Confiança IA: {dados_email['analise']['confianca']}%")
                print(f"[DEBUG] Trechos críticos: {len(dados_email['analise']['trechos_criticos'])}")
                
            # MODO NOVO: Email simples (apenas para senhas)
            else:
                print(f"[DEBUG] Criando email simples")
                html_profissional = corpo_html
                texto_profissional = corpo_texto or "Versão texto não disponível"
                subject_line = assunto
                from_header = f"{self.nome_remetente} <{self.email_remetente}>"
            
            print(f"[DEBUG] Subject: {subject_line}")
            print(f"[DEBUG] From: {from_header}")
            print(f"[DEBUG] HTML length: {len(html_profissional) if html_profissional else 0}")
            print(f"[DEBUG] Text length: {len(texto_profissional) if texto_profissional else 0}")
            
            # === CRIAÇÃO DA MENSAGEM ===
            print(f"[DEBUG] === CRIANDO MENSAGEM EMAIL ===")
            
            from email.mime.multipart import MIMEMultipart
            from email.mime.text import MIMEText
            
            msg = MIMEMultipart('alternative')
            msg['From'] = from_header
            msg['To'] = destinatario
            msg['Subject'] = subject_line
            msg['Message-ID'] = f"<{hash(subject_line + destinatario)}@{self.smtp_server}>"
            msg['Date'] = datetime.now().strftime('%a, %d %b %Y %H:%M:%S %z')
            
            print(f"[DEBUG] Headers configurados")
            print(f"[DEBUG] Message-ID: {msg['Message-ID']}")
            
            # Anexar conteúdo
            if texto_profissional:
                parte_texto = MIMEText(texto_profissional, 'plain', 'utf-8')
                msg.attach(parte_texto)
                print(f"[DEBUG] Parte texto anexada")
                
            if html_profissional:
                parte_html = MIMEText(html_profissional, 'html', 'utf-8')
                msg.attach(parte_html)
                print(f"[DEBUG] Parte HTML anexada")
            
            # === CONEXÃO E ENVIO SMTP ===
            print(f"[DEBUG] === INICIANDO CONEXÃO SMTP ===")
            
            import smtplib
            import ssl
            import socket
            
            # Testar resolução DNS primeiro
            try:
                print(f"[DEBUG] Testando resolução DNS para {self.smtp_server}")
                ip = socket.gethostbyname(self.smtp_server)
                print(f"[DEBUG] DNS OK - IP: {ip}")
            except Exception as dns_error:
                print(f"[ERROR] Falha na resolução DNS: {dns_error}")
                return {
                    'sucesso': False,
                    'erro': f'Falha DNS: {dns_error}'
                }
            
            # Configurar SSL
            context = ssl.create_default_context()
            # Algumas configurações específicas para provedores brasileiros
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            
            try:
                print(f"[DEBUG] Conectando ao servidor SMTP {self.smtp_server}:{self.smtp_port}")
                
                with smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=30) as server:
                    print(f"[DEBUG] Conexão estabelecida")
                    
                    # Ativar debug do SMTP
                    server.set_debuglevel(1)
                    
                    print(f"[DEBUG] Iniciando STARTTLS")
                    try:
                        server.starttls(context=context)
                        print(f"[DEBUG] STARTTLS OK")
                    except Exception as tls_error:
                        print(f"[WARNING] STARTTLS falhou: {tls_error}")
                        print(f"[DEBUG] Tentando sem TLS")
                    
                    print(f"[DEBUG] Fazendo login")
                    print(f"[DEBUG] Username: {self.smtp_username}")
                    print(f"[DEBUG] Password: {'*' * len(self.smtp_password)}")
                    
                    try:
                        server.login(self.smtp_username, self.smtp_password)
                        print(f"[DEBUG] Login bem-sucedido")
                    except smtplib.SMTPAuthenticationError as auth_error:
                        print(f"[ERROR] Falha na autenticação: {auth_error}")
                        return {
                            'sucesso': False,
                            'erro': f'Falha na autenticação SMTP: {auth_error}'
                        }
                    except Exception as login_error:
                        print(f"[ERROR] Erro no login: {login_error}")
                        return {
                            'sucesso': False,
                            'erro': f'Erro no login: {login_error}'
                        }
                    
                    print(f"[DEBUG] Enviando mensagem")
                    print(f"[DEBUG] De: {self.email_remetente}")
                    print(f"[DEBUG] Para: {destinatario}")
                    
                    try:
                        result = server.send_message(msg)
                        print(f"[DEBUG] send_message() concluído")
                        print(f"[DEBUG] Resultado SMTP: {result}")
                        
                        if not result:
                            print(f"[DEBUG] Email aceito pelo servidor sem problemas")
                        else:
                            print(f"[WARNING] Alguns destinatários foram rejeitados: {result}")
                            return {
                                'sucesso': False,
                                'erro': f'Destinatários rejeitados: {result}'
                            }
                            
                    except smtplib.SMTPRecipientsRefused as recip_error:
                        print(f"[ERROR] Destinatário recusado: {recip_error}")
                        return {
                            'sucesso': False,
                            'erro': f'Destinatário recusado: {recip_error}'
                        }
                    except smtplib.SMTPDataError as data_error:
                        print(f"[ERROR] Erro nos dados do email: {data_error}")
                        return {
                            'sucesso': False,
                            'erro': f'Erro nos dados: {data_error}'
                        }
                    except Exception as send_error:
                        print(f"[ERROR] Erro no envio: {send_error}")
                        return {
                            'sucesso': False,
                            'erro': f'Erro no envio: {send_error}'
                        }
                    
                    print(f"[DEBUG] Desconectando do servidor")
                    
            except smtplib.SMTPConnectError as conn_error:
                print(f"[ERROR] Falha na conexão: {conn_error}")
                return {
                    'sucesso': False,
                    'erro': f'Falha na conexão SMTP: {conn_error}'
                }
            except smtplib.SMTPServerDisconnected as disc_error:
                print(f"[ERROR] Servidor desconectou: {disc_error}")
                return {
                    'sucesso': False,
                    'erro': f'Servidor desconectou: {disc_error}'
                }
            except socket.timeout as timeout_error:
                print(f"[ERROR] Timeout na conexão: {timeout_error}")
                return {
                    'sucesso': False,
                    'erro': f'Timeout na conexão: {timeout_error}'
                }
            except Exception as general_error:
                print(f"[ERROR] Erro geral: {general_error}")
                print(f"[ERROR] Tipo do erro: {type(general_error)}")
                return {
                    'sucesso': False,
                    'erro': f'Erro geral: {general_error}'
                }
            
            print(f"[DEBUG] === EMAIL ENVIADO COM SUCESSO ===")
            
            return {
                'sucesso': True,
                'mensagem': f'Email enviado para {destinatario}'
            }
            
        except Exception as e:
            print(f"[ERROR] === EXCEÇÃO GERAL ===")
            print(f"[ERROR] {type(e).__name__}: {str(e)}")
            import traceback
            print(f"[ERROR] Traceback:")
            traceback.print_exc()
            
            return {
                'sucesso': False,
                'erro': f'Exceção geral: {str(e)}'
            }
            
    def _gerar_trechos_html(self, trechos_criticos):
        """Gera HTML para trechos críticos"""
        if not trechos_criticos:
            return '<p><em>Nenhum trecho crítico específico identificado no texto.</em></p>'
        
        html = '<div style="margin: 15px 0;"><strong>Principais Problemas Identificados:</strong></div>'
        
        for trecho in trechos_criticos:
            confianca_pct = int(trecho['confianca'] * 100)
            html += f'''
            <div class="excerpt">
                <div class="excerpt-text">"{trecho['texto']}"</div>
                <div class="excerpt-interpretation">
                    → IA identificou: {trecho['interpretacao']} (confiança: {confianca_pct}%)
                </div>
            </div>
            '''
        
        return html

    def _gerar_notas_html(self, notas_baixas):
        """Gera HTML para notas baixas"""
        if not notas_baixas:
            return ''
        
        html = '<div style="margin: 15px 0;"><strong>Avaliações Numéricas Críticas:</strong></div>'
        
        for nota in notas_baixas:
            html += f'''
            <div class="excerpt">
                <div class="excerpt-text">Nota atribuída: {nota['nota']}/10</div>
                <div class="excerpt-interpretation">
                    → Contexto: {nota['contexto']} - Indica insatisfação significativa
                </div>
            </div>
            '''
        
        return html

    def _gerar_trechos_texto(self, trechos_criticos):
        """Gera versão texto para trechos críticos"""
        if not trechos_criticos:
            return 'Nenhum trecho critico especifico identificado no texto.'
        
        texto = ''
        for i, trecho in enumerate(trechos_criticos, 1):
            confianca_pct = int(trecho['confianca'] * 100)
            texto += f'''
    {i}. "{trecho['texto']}"
    → IA identificou: {trecho['interpretacao']} (confianca: {confianca_pct}%)
    '''
        
        return texto.strip()        

    def _registrar_log_email(self, pesquisa_id: int, email_destinatario: str, 
                           assunto: str, sucesso: bool, erro: Optional[str],
                           analise_sentimento_id: Optional[int] = None) -> None:
        """Registra log do envio de email"""
        
        try:
            query = """
            INSERT INTO log_emails_enviados 
            (pesquisa_id, analise_sentimento_id, email_destinatario, assunto, enviado_com_sucesso, erro_envio)
            VALUES (%s, %s, %s, %s, %s, %s)
            """
            
            execute_query(query, (
                pesquisa_id,
                analise_sentimento_id,
                email_destinatario,
                assunto,
                sucesso,
                erro
            ))
            
        except Exception as e:
            print(f"Erro ao registrar log de email: {str(e)}")

    def testar_envio(self, email_teste: str = "teste@exemplo.com") -> Dict:
        """Testa envio de email com dados fictícios"""
        
        dados_teste = {
            'id': 999,
            'nome_cliente': 'Cliente Teste',
            'codigo_cliente': 'TEST123',
            'nome_treinamento': 'Teste de Email',
            'tipo_produto': 'Time is Money',
            'agente_nome': 'Agente Teste',
            'data_resposta': datetime.now()
        }
        
        analise_teste = {
            'sentimento_geral': 'negative',
            'pontuacao_hibrida': -2,
            'confianca_geral': 0.85,
            'motivo_insatisfacao': 'Este é um teste do sistema de alertas'
        }
        
        try:
            assunto = self._gerar_assunto(dados_teste, analise_teste)
            corpo_html = self._gerar_corpo_email(dados_teste, analise_teste)
            
            resultado = self._enviar_email(
                destinatario=email_teste,
                nome_destinatario="Teste",
                assunto=f"[TESTE] {assunto}",
                corpo_html=corpo_html
            )
            
            return resultado
            
        except Exception as e:
            return {
                'sucesso': False,
                'erro': f"Erro no teste: {str(e)}"
            }