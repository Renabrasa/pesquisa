-- Adicionar coluna foto_url na tabela usuarios
USE sistema_pesquisa;

ALTER TABLE usuarios 
ADD COLUMN foto_url VARCHAR(500) NULL AFTER email;

-- Comentário da coluna
ALTER TABLE usuarios 
MODIFY COLUMN foto_url VARCHAR(500) NULL COMMENT 'Caminho da foto de perfil do usuário';

-- Verificar se foi adicionado
DESCRIBE usuarios;