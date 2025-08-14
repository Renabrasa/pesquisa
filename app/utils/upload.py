import os
import uuid
from werkzeug.utils import secure_filename
from PIL import Image
import secrets

# Configurações de upload
UPLOAD_FOLDER = 'app/static/uploads'
AVATAR_FOLDER = 'app/static/uploads/avatars'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
MAX_FILE_SIZE = 2 * 1024 * 1024  # 2MB

def allowed_file(filename):
    """Verificar se o arquivo tem extensão permitida"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def generate_filename(original_filename):
    """Gerar nome único para o arquivo"""
    ext = original_filename.rsplit('.', 1)[1].lower()
    unique_name = f"{secrets.token_hex(16)}.{ext}"
    return unique_name

def save_avatar(file, user_id):
    """
    Salvar foto de avatar
    Returns: caminho relativo da foto ou None se erro
    """
    try:
        if not file or file.filename == '':
            return None
        
        if not allowed_file(file.filename):
            raise ValueError("Formato de arquivo não permitido")
        
        # Verificar tamanho
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)
        
        if file_size > MAX_FILE_SIZE:
            raise ValueError("Arquivo muito grande (máx. 2MB)")
        
        # Gerar nome único
        filename = generate_filename(file.filename)
        
        # Criar pasta se não existir
        os.makedirs(AVATAR_FOLDER, exist_ok=True)
        
        # Caminho completo
        filepath = os.path.join(AVATAR_FOLDER, filename)
        
        # Salvar arquivo
        file.save(filepath)
        
        # Redimensionar e otimizar imagem
        optimize_avatar(filepath)
        
        # Retornar caminho relativo para o banco
        return f"/static/uploads/avatars/{filename}"
        
    except Exception as e:
        print(f"Erro ao salvar avatar: {e}")
        return None

def optimize_avatar(filepath):
    """Otimizar e redimensionar avatar"""
    try:
        with Image.open(filepath) as img:
            # Converter para RGB se necessário
            if img.mode in ('RGBA', 'LA', 'P'):
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                img = background
            
            # Redimensionar para 300x300 mantendo proporção
            img.thumbnail((300, 300), Image.Resampling.LANCZOS)
            
            # Criar imagem quadrada com fundo branco
            square_img = Image.new('RGB', (300, 300), (255, 255, 255))
            
            # Centralizar imagem
            x = (300 - img.width) // 2
            y = (300 - img.height) // 2
            square_img.paste(img, (x, y))
            
            # Salvar otimizada
            square_img.save(filepath, 'JPEG', quality=85, optimize=True)
            
    except Exception as e:
        print(f"Erro ao otimizar avatar: {e}")

def delete_avatar(filepath):
    """Deletar arquivo de avatar"""
    try:
        if filepath and os.path.exists(f"app{filepath}"):
            os.remove(f"app{filepath}")
            return True
    except Exception as e:
        print(f"Erro ao deletar avatar: {e}")
    return False

def get_default_avatar():
    """Retornar caminho do avatar padrão"""
    return "/static/uploads/avatars/default-avatar.png"

def create_default_avatar():
    """Criar avatar padrão se não existir"""
    try:
        default_path = os.path.join(AVATAR_FOLDER, 'default-avatar.png')
        
        if not os.path.exists(default_path):
            # Criar pasta se não existir
            os.makedirs(AVATAR_FOLDER, exist_ok=True)
            
            # Criar imagem padrão simples
            from PIL import Image, ImageDraw, ImageFont
            
            img = Image.new('RGB', (300, 300), (108, 117, 125))  # Cor cinza
            draw = ImageDraw.Draw(img)
            
            # Desenhar ícone de pessoa simples
            # Cabeça (círculo)
            draw.ellipse([100, 80, 200, 180], fill=(255, 255, 255))
            
            # Corpo (retângulo arredondado)
            draw.ellipse([75, 180, 225, 280], fill=(255, 255, 255))
            
            img.save(default_path, 'PNG')
            print(f"✓ Avatar padrão criado: {default_path}")
            
    except Exception as e:
        print(f"Erro ao criar avatar padrão: {e}")

# Criar avatar padrão na inicialização
create_default_avatar()