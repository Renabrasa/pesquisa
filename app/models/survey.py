from app import db
from datetime import datetime

class TipoProduto(db.Model):
    __tablename__ = 'tipos_produtos'
    
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    descricao = db.Column(db.Text)
    ativo = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Pesquisa(db.Model):
    __tablename__ = 'pesquisas'
    
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, nullable=False)
    agente_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    tipo_produto_id = db.Column(db.Integer, db.ForeignKey('tipos_produtos.id'), nullable=False)
    codigo_cliente = db.Column(db.String(50), nullable=False)
    nome_cliente = db.Column(db.String(200), nullable=False)
    nome_treinamento = db.Column(db.String(200), nullable=False)
    data_expiracao = db.Column(db.DateTime, nullable=False)
    respondida = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)