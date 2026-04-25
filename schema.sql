CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    username TEXT NOT NULL UNIQUE,
    senha_hash TEXT NOT NULL,
    perfil TEXT NOT NULL DEFAULT 'admin',
    ativo INTEGER NOT NULL DEFAULT 1,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS obras (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo TEXT NOT NULL UNIQUE,
    nome TEXT NOT NULL,
    endereco TEXT,
    tipologia TEXT,
    tipo_obra TEXT NOT NULL DEFAULT 'contrato',
    area_m2 REAL,
    data_inicio TEXT,
    data_fim_prevista TEXT,
    orcamento REAL DEFAULT 0,
    receita_total REAL DEFAULT 0,
    progresso_percentual REAL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'planejamento',
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS custos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    obra_id INTEGER NOT NULL,
    descricao TEXT NOT NULL,
    categoria TEXT NOT NULL,
    fornecedor TEXT,
    data_lancamento TEXT,
    valor_total REAL DEFAULT 0,
    nota_fiscal TEXT,
    observacao TEXT,
    FOREIGN KEY (obra_id) REFERENCES obras(id)
);

CREATE TABLE IF NOT EXISTS fornecedores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo TEXT NOT NULL UNIQUE,
    nome TEXT NOT NULL,
    categoria TEXT,
    contato TEXT,
    documento TEXT,
    prazo_medio INTEGER DEFAULT 0,
    nota_qualidade REAL DEFAULT 0,
    nota_preco REAL DEFAULT 0,
    nota_prazo REAL DEFAULT 0,
    observacao TEXT
);

CREATE TABLE IF NOT EXISTS compras (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    obra_id INTEGER NOT NULL,
    fornecedor_id INTEGER,
    material TEXT NOT NULL,
    data_pedido TEXT,
    data_entrega_prevista TEXT,
    quantidade REAL DEFAULT 0,
    valor_unitario REAL DEFAULT 0,
    status TEXT,
    observacao TEXT,
    FOREIGN KEY (obra_id) REFERENCES obras(id),
    FOREIGN KEY (fornecedor_id) REFERENCES fornecedores(id)
);

CREATE TABLE IF NOT EXISTS equipe (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    obra_id INTEGER NOT NULL,
    nome TEXT NOT NULL,
    funcao TEXT,
    contrato TEXT,
    data_inicio TEXT,
    valor_contratado REAL DEFAULT 0,
    valor_pago REAL DEFAULT 0,
    status_pagamento TEXT,
    observacao TEXT,
    FOREIGN KEY (obra_id) REFERENCES obras(id)
);

CREATE TABLE IF NOT EXISTS medicoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    obra_id INTEGER NOT NULL,
    mes TEXT,
    medicao_nome TEXT,
    etapa TEXT,
    percentual REAL DEFAULT 0,
    percentual_acumulado REAL DEFAULT 0,
    valor_realizado REAL DEFAULT 0,
    data_medicao TEXT,
    observacao TEXT,
    FOREIGN KEY (obra_id) REFERENCES obras(id)
);

CREATE TABLE IF NOT EXISTS importacoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome_arquivo TEXT NOT NULL,
    data_importacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    observacao TEXT
);

CREATE TABLE IF NOT EXISTS custos_importados_categoria (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    obra_id INTEGER NOT NULL,
    categoria TEXT NOT NULL,
    valor_total REAL DEFAULT 0,
    origem TEXT DEFAULT 'planilha',
    FOREIGN KEY (obra_id) REFERENCES obras(id)
);

CREATE TABLE IF NOT EXISTS fotos_obra (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    obra_id INTEGER NOT NULL,
    caminho TEXT NOT NULL,
    titulo TEXT,
    fase TEXT,
    data_registro TEXT,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (obra_id) REFERENCES obras(id)
);

CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id INTEGER,
    acao TEXT,
    entidade TEXT,
    entidade_id INTEGER,
    descricao TEXT,
    data_hora DATETIME DEFAULT CURRENT_TIMESTAMP
);
