# Sistema de Pesquisa de Satisfação

Sistema para coleta de feedback de clientes sobre treinamentos.

## Como executar:

1. Instalar dependências:
```
pip install -r requirements.txt
```

2. Configurar banco MySQL e editar .env

3. Executar:
```
python run.py
```

## Estrutura:
- `/` - Página inicial
- `/agente` - Dashboard do agente
- `/gestor` - Dashboard do gestor  
- `/pesquisa/<uuid>` - Formulário para cliente
