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
            corpo_html = self._gerar_corpo_email(dados_pesquisa, analise_sentimento)
            
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
                        corpo_html=corpo_html
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

    def _gerar_corpo_email(self, dados_pesquisa: Dict, analise_sentimento: Dict) -> str:
        """Gera corpo HTML do email de alerta"""
        
        sentimento = analise_sentimento.get('sentimento_geral', 'negative')
        pontuacao = analise_sentimento.get('pontuacao_hibrida', 0)
        confianca = analise_sentimento.get('confianca_geral', 0)
        motivo = analise_sentimento.get('motivo_insatisfacao', 'Não especificado')
        
        # Determinar cor baseada na gravidade
        if sentimento == 'negative' and pontuacao <= -2:
            cor_alerta = "#dc3545"  # Vermelho
            nivel_texto = "CRÍTICO"
        elif sentimento == 'negative':
            cor_alerta = "#fd7e14"  # Laranja
            nivel_texto = "ALTO"
        else:
            cor_alerta = "#ffc107"  # Amarelo
            nivel_texto = "MÉDIO"
        
        link_detalhes = f"{self.app_url}/gestor/detalhes/{dados_pesquisa['id']}"
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f8f9fa; }}
                .container {{ max-width: 600px; margin: 0 auto; background-color: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
                .header {{ background-color: {cor_alerta}; color: white; padding: 20px; text-align: center; }}
                .content {{ padding: 30px; }}
                .alert-box {{ background-color: #fff3cd; border: 1px solid #ffeaa7; border-radius: 5px; padding: 15px; margin: 20px 0; }}
                .info-table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
                .info-table td {{ padding: 10px; border-bottom: 1px solid #eee; }}
                .info-table td:first-child {{ font-weight: bold; width: 30%; background-color: #f8f9fa; }}
                .button {{ display: inline-block; padding: 12px 25px; background-color: #007bff; color: white; text-decoration: none; border-radius: 5px; margin: 20px 0; }}
                .footer {{ background-color: #f8f9fa; padding: 20px; text-align: center; font-size: 12px; color: #6c757d; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🚨 ALERTA DE INSATISFAÇÃO</h1>
                    <p>Nível: <strong>{nivel_texto}</strong></p>
                </div>
                
                <div class="content">
                    <div class="alert-box">
                        <strong>⚠️ Um cliente demonstrou insatisfação com o treinamento realizado.</strong><br>
                        É recomendado entrar em contato para resolver a situação.
                    </div>
                    
                    <h3>📋 Informações do Cliente</h3>
                    <table class="info-table">
                        <tr>
                            <td>Cliente:</td>
                            <td><strong>{dados_pesquisa['nome_cliente']}</strong></td>
                        </tr>
                        <tr>
                            <td>Código:</td>
                            <td>{dados_pesquisa['codigo_cliente']}</td>
                        </tr>
                        <tr>
                            <td>Treinamento:</td>
                            <td>{dados_pesquisa['nome_treinamento']}</td>
                        </tr>
                        <tr>
                            <td>Produto:</td>
                            <td>{dados_pesquisa['tipo_produto']}</td>
                        </tr>
                        <tr>
                            <td>Agente Responsável:</td>
                            <td>{dados_pesquisa['agente_nome']}</td>
                        </tr>
                        <tr>
                            <td>Data da Resposta:</td>
                            <td>{dados_pesquisa['data_resposta'].strftime('%d/%m/%Y %H:%M') if dados_pesquisa['data_resposta'] else 'N/A'}</td>
                        </tr>
                    </table>
                    
                    <h3>🤖 Análise de Sentimento</h3>
                    <table class="info-table">
                        <tr>
                            <td>Sentimento Detectado:</td>
                            <td><strong style="color: {cor_alerta};">{sentimento.upper()}</strong></td>
                        </tr>
                        <tr>
                            <td>Pontuação Híbrida:</td>
                            <td>{pontuacao} pontos</td>
                        </tr>
                        <tr>
                            <td>Confiança da IA:</td>
                            <td>{int(confianca * 100)}%</td>
                        </tr>
                        <tr>
                            <td>Motivo da Insatisfação:</td>
                            <td>{motivo}</td>
                        </tr>
                    </table>
                    
                    <div style="text-align: center;">
                        <a href="{link_detalhes}" class="button">
                            👁️ Ver Detalhes Completos
                        </a>
                    </div>
                    
                    <div class="alert-box">
                        <strong>💡 Próximos Passos Recomendados:</strong><br>
                        • Entre em contato com o cliente para entender melhor a situação<br>
                        • Verifique se há possibilidade de oferecer suporte adicional<br>
                        • Considere agendar uma conversa para resolver as questões levantadas<br>
                        • Documente as ações tomadas para melhoria contínua
                    </div>
                </div>
                
                <div class="footer">
                    <p>Este email foi enviado automaticamente pelo Sistema de Pesquisa de Satisfação</p>
                    <p>Data/Hora: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return html

    def _enviar_email(self, destinatario: str, nome_destinatario: str, 
                     assunto: str, corpo_html: str) -> Dict:
        """Envia email individual usando SMTP personalizado"""
        
        try:
            # Criar mensagem
            msg = MIMEMultipart('alternative')
            msg['From'] = f"{self.nome_remetente} <{self.email_remetente}>"
            msg['To'] = destinatario
            msg['Subject'] = assunto
            
            # Adicionar corpo HTML
            html_part = MIMEText(corpo_html, 'html', 'utf-8')
            msg.attach(html_part)
            
            # Conectar ao servidor SMTP
            server = smtplib.SMTP(self.smtp_server, self.smtp_port)
            
            # Login no servidor
            server.login(self.smtp_username, self.smtp_password)
            
            # Enviar email
            server.send_message(msg)
            server.quit()
            
            return {
                'sucesso': True,
                'mensagem': f'Email enviado para {destinatario}'
            }
            
        except Exception as e:
            return {
                'sucesso': False,
                'erro': str(e)
            }

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