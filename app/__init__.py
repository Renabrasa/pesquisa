from flask import Flask
import os
from dotenv import load_dotenv

load_dotenv()

def create_app():
    """Factory function para criar a aplicação Flask"""
    
    app = Flask(__name__, 
                template_folder='templates',
                static_folder='static')
    
    # Configurações
    app.secret_key = os.getenv('SECRET_KEY', 'dev-key')
    
    # Registrar blueprints (rotas)
    register_blueprints(app)
    
    return app

def register_blueprints(app):
    """Registra todos os blueprints da aplicação"""
    
    from app.routes.main import bp as main_bp
    from app.routes.auth import bp as auth_bp
    from app.routes.agente import bp as agente_bp
    from app.routes.gestor import bp as gestor_bp
    from app.routes.cliente import bp as cliente_bp
    
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(agente_bp, url_prefix='/agente')
    app.register_blueprint(gestor_bp, url_prefix='/gestor')
    app.register_blueprint(cliente_bp, url_prefix='/pesquisa')