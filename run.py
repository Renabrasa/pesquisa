import os
from app import create_app
from dotenv import load_dotenv

load_dotenv()

app = create_app()

if __name__ == '__main__':
    print("=" * 50)
    print("SISTEMA DE PESQUISA DE SATISFACAO")
    print("=" * 50)
    print(f"Acesse: http://localhost:5000")
    print(f"Teste conexao: http://localhost:5000/teste-conexao")
    print("=" * 50)
    
    app.run(
        host=os.getenv('APP_HOST', '0.0.0.0'),
        port=int(os.getenv('APP_PORT', 5000)),
        debug=True
    )