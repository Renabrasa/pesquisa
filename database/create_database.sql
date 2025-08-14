-- ===================================
-- SISTEMA DE PESQUISA DE SATISFAÇÃO
-- Script de Criação do Banco de Dados
-- ===================================

-- Criar o banco de dados
CREATE DATABASE IF NOT EXISTS sistema_pesquisa 
CHARACTER SET utf8mb4 
COLLATE utf8mb4_unicode_ci;

USE sistema_pesquisa;

-- ===================================
-- TABELAS PRINCIPAIS
-- ===================================

-- Tipos de produtos
CREATE TABLE tipos_produtos (
    id INT PRIMARY KEY AUTO_INCREMENT,
    nome VARCHAR(100) NOT NULL UNIQUE,
    descricao TEXT,
    ativo BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- Usuários do sistema (Agentes e Gestores)
CREATE TABLE usuarios (
    id INT PRIMARY KEY AUTO_INCREMENT,
    nome VARCHAR(100) NOT NULL,
    email VARCHAR(150) NOT NULL UNIQUE,
    senha_hash VARCHAR(255) NOT NULL,
    tipo_usuario ENUM('agente', 'gestor') NOT NULL,
    ativo BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- Tipos de perguntas
CREATE TABLE tipos_perguntas (
    id INT PRIMARY KEY AUTO_INCREMENT,
    nome VARCHAR(50) NOT NULL UNIQUE,
    descricao VARCHAR(200)
);

-- Perguntas para as pesquisas
CREATE TABLE perguntas (
    id INT PRIMARY KEY AUTO_INCREMENT,
    tipo_produto_id INT NOT NULL,
    tipo_pergunta_id INT NOT NULL,
    texto TEXT NOT NULL,
    obrigatoria BOOLEAN DEFAULT TRUE,
    ordem INT NOT NULL,
    opcoes JSON NULL,
    ativa BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (tipo_produto_id) REFERENCES tipos_produtos(id),
    FOREIGN KEY (tipo_pergunta_id) REFERENCES tipos_perguntas(id),
    INDEX idx_tipo_produto_ordem (tipo_produto_id, ordem)
);

-- Pesquisas geradas pelos agentes
CREATE TABLE pesquisas (
    id INT PRIMARY KEY AUTO_INCREMENT,
    uuid VARCHAR(36) NOT NULL UNIQUE,
    agente_id INT NOT NULL,
    tipo_produto_id INT NOT NULL,
    codigo_cliente VARCHAR(50) NOT NULL,
    nome_cliente VARCHAR(200) NOT NULL,
    nome_treinamento VARCHAR(200) NOT NULL,
    data_treinamento DATE,
    descricao_treinamento TEXT,
    data_expiracao DATETIME NOT NULL,
    respondida BOOLEAN DEFAULT FALSE,
    data_resposta DATETIME NULL,
    ip_resposta VARCHAR(45) NULL,
    user_agent TEXT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (agente_id) REFERENCES usuarios(id),
    FOREIGN KEY (tipo_produto_id) REFERENCES tipos_produtos(id),
    INDEX idx_uuid (uuid),
    INDEX idx_codigo_cliente (codigo_cliente),
    INDEX idx_data_expiracao (data_expiracao),
    INDEX idx_respondida (respondida)
);

-- Respostas das pesquisas
CREATE TABLE respostas (
    id INT PRIMARY KEY AUTO_INCREMENT,
    pesquisa_id INT NOT NULL,
    pergunta_id INT NOT NULL,
    resposta_texto TEXT NULL,
    resposta_numerica DECIMAL(5,2) NULL,
    resposta_opcao VARCHAR(200) NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (pesquisa_id) REFERENCES pesquisas(id) ON DELETE CASCADE,
    FOREIGN KEY (pergunta_id) REFERENCES perguntas(id),
    UNIQUE KEY unique_resposta (pesquisa_id, pergunta_id)
);

-- ===================================
-- DADOS INICIAIS
-- ===================================

-- Inserir tipos de produtos
INSERT INTO tipos_produtos (nome, descricao) VALUES 
('Servidor na Nuvem', 'Treinamentos e consultorias sobre servidores em nuvem'),
('Time is Money', 'Treinamentos sobre gestão de tempo e produtividade');

-- Inserir tipos de perguntas
INSERT INTO tipos_perguntas (nome, descricao) VALUES 
('texto_livre', 'Pergunta de resposta livre em texto'),
('multipla_escolha', 'Pergunta de múltipla escolha'),
('escala_numerica', 'Pergunta com escala numérica (ex: 1-10)'),
('sim_nao', 'Pergunta de sim ou não'),
('escala_satisfacao', 'Escala de satisfação (ex: Muito Insatisfeito a Muito Satisfeito)');

-- Inserir usuário agente padrão (senha: 123456)
INSERT INTO usuarios (nome, email, senha_hash, tipo_usuario) VALUES 
('Agente Demo', 'agente@empresa.com', 'e10adc3949ba59abbe56e057f20f883e', 'agente'),
('Gestor Demo', 'gestor@empresa.com', 'e10adc3949ba59abbe56e057f20f883e', 'gestor');

-- Inserir perguntas padrão para Servidor na Nuvem
INSERT INTO perguntas (tipo_produto_id, tipo_pergunta_id, texto, ordem, opcoes) VALUES 
(1, 5, 'Como você avalia o treinamento sobre Servidor na Nuvem de forma geral?', 1, 
 '["Muito Insatisfeito", "Insatisfeito", "Neutro", "Satisfeito", "Muito Satisfeito"]'),
(1, 3, 'Em uma escala de 1 a 10, qual nota você daria para o instrutor?', 2, NULL),
(1, 2, 'O conteúdo atendeu às suas expectativas?', 3, 
 '["Superou", "Atendeu", "Atendeu parcialmente", "Não atendeu"]'),
(1, 1, 'Deixe seus comentários e sugestões sobre o treinamento:', 4, NULL);

-- Inserir perguntas padrão para Time is Money
INSERT INTO perguntas (tipo_produto_id, tipo_pergunta_id, texto, ordem, opcoes) VALUES 
(2, 5, 'Como você avalia o treinamento Time is Money de forma geral?', 1, 
 '["Muito Insatisfeito", "Insatisfeito", "Neutro", "Satisfeito", "Muito Satisfeito"]'),
(2, 3, 'Em uma escala de 1 a 10, quanto você recomendaria este treinamento?', 2, NULL),
(2, 4, 'Você aplicou as técnicas aprendidas no seu dia a dia?', 3, '["Sim", "Não"]'),
(2, 1, 'Que melhorias você sugere para o treinamento?', 4, NULL);

-- ===================================
-- VIEWS ÚTEIS
-- ===================================

-- View para pesquisas com informações completas
CREATE VIEW vw_pesquisas_completas AS
SELECT 
    p.id,
    p.uuid,
    p.codigo_cliente,
    p.nome_cliente,
    p.nome_treinamento,
    p.data_treinamento,
    p.respondida,
    p.data_resposta,
    p.data_expiracao,
    p.created_at as data_criacao,
    u.nome as agente_nome,
    tp.nome as tipo_produto,
    CASE 
        WHEN p.data_expiracao < NOW() THEN 'expirada'
        WHEN p.respondida = TRUE THEN 'respondida'
        ELSE 'ativa'
    END as status_pesquisa
FROM pesquisas p
JOIN usuarios u ON p.agente_id = u.id
JOIN tipos_produtos tp ON p.tipo_produto_id = tp.id;

-- View para dashboard do gestor
CREATE VIEW vw_dashboard_gestor AS
SELECT 
    tp.nome as produto,
    COUNT(p.id) as total_pesquisas,
    SUM(CASE WHEN p.respondida = TRUE THEN 1 ELSE 0 END) as respondidas,
    SUM(CASE WHEN p.data_expiracao < NOW() AND p.respondida = FALSE THEN 1 ELSE 0 END) as expiradas,
    SUM(CASE WHEN p.data_expiracao >= NOW() AND p.respondida = FALSE THEN 1 ELSE 0 END) as pendentes,
    ROUND(
        (SUM(CASE WHEN p.respondida = TRUE THEN 1 ELSE 0 END) * 100.0) / 
        NULLIF(COUNT(p.id), 0), 2
    ) as taxa_resposta_percent
FROM tipos_produtos tp
LEFT JOIN pesquisas p ON tp.id = p.tipo_produto_id
GROUP BY tp.id, tp.nome;

-- ===================================
-- ÍNDICES PARA PERFORMANCE
-- ===================================

CREATE INDEX idx_pesquisas_status ON pesquisas(respondida, data_expiracao);
CREATE INDEX idx_respostas_pesquisa ON respostas(pesquisa_id);
CREATE INDEX idx_usuarios_tipo ON usuarios(tipo_usuario, ativo);

-- ===================================
-- PROCEDURES ÚTEIS
-- ===================================

DELIMITER //

-- Procedure para verificar se link ainda é válido
CREATE PROCEDURE VerificarLinkValido(IN p_uuid VARCHAR(36))
BEGIN
    SELECT 
        p.*,
        CASE 
            WHEN p.data_expiracao < NOW() THEN FALSE
            WHEN p.respondida = TRUE THEN FALSE
            ELSE TRUE
        END as link_valido
    FROM pesquisas p 
    WHERE p.uuid = p_uuid;
END //

-- Procedure para limpar pesquisas expiradas antigas (30 dias)
CREATE PROCEDURE LimparPesquisasAntigas()
BEGIN
    DELETE FROM pesquisas 
    WHERE data_expiracao < DATE_SUB(NOW(), INTERVAL 30 DAY)
    AND respondida = FALSE;
END //

DELIMITER ;

-- ===================================
-- DADOS DE TESTE (OPCIONAL)
-- ===================================

-- Inserir algumas pesquisas de exemplo para teste
INSERT INTO pesquisas (uuid, agente_id, tipo_produto_id, codigo_cliente, nome_cliente, nome_treinamento, data_expiracao) VALUES 
(UUID(), 1, 1, '12345', 'Empresa ABC Ltda', 'Migração para Cloud AWS', DATE_ADD(NOW(), INTERVAL 48 HOUR)),
(UUID(), 1, 2, '67890', 'Consultoria XYZ', 'Gestão de Tempo para Equipes', DATE_ADD(NOW(), INTERVAL 24 HOUR)),
(UUID(), 1, 1, '54321', 'Tech Solutions', 'Segurança em Servidores', DATE_ADD(NOW(), INTERVAL 72 HOUR));

-- ===================================
-- VERIFICAÇÕES FINAIS
-- ===================================

-- Mostrar estatísticas das tabelas criadas
SELECT 'Tipos de Produtos' as Tabela, COUNT(*) as Registros FROM tipos_produtos
UNION ALL
SELECT 'Usuários', COUNT(*) FROM usuarios
UNION ALL
SELECT 'Tipos de Perguntas', COUNT(*) FROM tipos_perguntas
UNION ALL
SELECT 'Perguntas', COUNT(*) FROM perguntas
UNION ALL
SELECT 'Pesquisas', COUNT(*) FROM pesquisas;

-- Mostrar estrutura das tabelas principais
SHOW TABLES;

-- Mensagem de sucesso
SELECT 'Banco de dados criado com sucesso!' as Status;