import sqlite3
import os
import shutil
from pathlib import Path

DEFAULT_DB_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Canteiro"
DB_PATH = Path(os.environ.get("CENTRAL_OBRAS_DB", DEFAULT_DB_DIR / "central_obras.db"))
LEGACY_DB_PATH = Path("data/central_obras.db")
EMPRESA_PADRAO_NOME = "Canteiro Interno"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA encoding = 'UTF-8'")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    if not DB_PATH.exists() and LEGACY_DB_PATH.exists():
        shutil.copy2(LEGACY_DB_PATH, DB_PATH)

    conn = get_connection()

    with open("schema.sql", "r", encoding="utf-8") as f:
        conn.executescript(f.read())

    # Garantir colunas novas em bancos antigos sem quebrar nada

    def adicionar_coluna(tabela, coluna, definicao):
        try:
            conn.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {definicao}")
            conn.commit()
        except Exception:
            pass

    def executar_sem_quebrar(sql, params=()):
        try:
            conn.execute(sql, params)
            conn.commit()
        except Exception:
            pass

    executar_sem_quebrar(
        """
        CREATE TABLE IF NOT EXISTS empresas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL UNIQUE,
            documento TEXT UNIQUE,
            ativo INTEGER NOT NULL DEFAULT 1,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    adicionar_coluna("empresas", "documento", "TEXT")
    executar_sem_quebrar(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_empresas_documento_unico
        ON empresas(documento)
        WHERE documento IS NOT NULL AND documento != ''
        """
    )

    empresa_padrao = conn.execute(
        "SELECT id FROM empresas WHERE nome = ?",
        (EMPRESA_PADRAO_NOME,),
    ).fetchone()
    if empresa_padrao:
        empresa_padrao_id = empresa_padrao["id"]
    else:
        cursor_empresa = conn.execute(
            "INSERT INTO empresas (nome, ativo) VALUES (?, 1)",
            (EMPRESA_PADRAO_NOME,),
        )
        conn.commit()
        empresa_padrao_id = cursor_empresa.lastrowid

    tabelas_empresa = [
        "usuarios",
        "obras",
        "custos",
        "fornecedores",
        "compras",
        "equipe",
        "medicoes",
        "importacoes",
        "custos_importados_categoria",
        "fotos_obra",
        "clientes",
        "contratos",
        "clausulas_contrato",
        "logs",
    ]
    for tabela in tabelas_empresa:
        adicionar_coluna(tabela, "empresa_id", "INTEGER")

    tabelas_filhos_obra = [
        "custos",
        "compras",
        "equipe",
        "medicoes",
        "custos_importados_categoria",
        "fotos_obra",
    ]
    for tabela in tabelas_filhos_obra:
        executar_sem_quebrar(
            f"""
            UPDATE {tabela}
            SET empresa_id = (
                SELECT empresa_id FROM obras WHERE obras.id = {tabela}.obra_id
            )
            WHERE empresa_id IS NULL
              AND obra_id IS NOT NULL
              AND EXISTS (SELECT 1 FROM obras WHERE obras.id = {tabela}.obra_id)
            """
        )

    for tabela in tabelas_empresa:
        executar_sem_quebrar(
            f"UPDATE {tabela} SET empresa_id = ? WHERE empresa_id IS NULL",
            (empresa_padrao_id,),
        )

    for tabela in tabelas_empresa:
        executar_sem_quebrar(
            f"CREATE INDEX IF NOT EXISTS idx_{tabela}_empresa_id ON {tabela}(empresa_id)"
        )

    # usuarios.perfil
    try:
        conn.execute("ALTER TABLE usuarios ADD COLUMN perfil TEXT NOT NULL DEFAULT 'gestor'")
        conn.commit()
    except Exception:
        pass

    # usuarios.ativo
    try:
        conn.execute("ALTER TABLE usuarios ADD COLUMN ativo INTEGER NOT NULL DEFAULT 1")
        conn.commit()
    except Exception:
        pass

    # usuarios.onboarding_completo
    try:
        conn.execute("ALTER TABLE usuarios ADD COLUMN onboarding_completo INTEGER DEFAULT 0")
        conn.commit()
    except Exception:
        pass

    # usuarios.onboarding_pendente
    try:
        conn.execute("ALTER TABLE usuarios ADD COLUMN onboarding_pendente INTEGER DEFAULT 0")
        conn.commit()
    except Exception:
        pass

    executar_sem_quebrar(
        """
        UPDATE usuarios
        SET onboarding_pendente = 0,
            onboarding_completo = 1
        WHERE perfil != 'gestor'
        """
    )

    # usuarios.foto_perfil
    try:
        conn.execute("ALTER TABLE usuarios ADD COLUMN foto_perfil TEXT")
        conn.commit()
    except Exception:
        pass

    # usuarios.email
    try:
        conn.execute("ALTER TABLE usuarios ADD COLUMN email TEXT")
        conn.commit()
    except Exception:
        pass

    try:
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_usuarios_email ON usuarios(email)")
        conn.commit()
    except Exception:
        pass

    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tokens_reset_senha (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario_id INTEGER NOT NULL,
                token TEXT NOT NULL UNIQUE,
                expira_em TEXT NOT NULL,
                usado INTEGER NOT NULL DEFAULT 0,
                criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                usado_em TEXT,
                FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
            )
        """)
        conn.commit()
    except Exception:
        pass

    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tokens_reset_senha_usuario ON tokens_reset_senha(usuario_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tokens_reset_senha_expira ON tokens_reset_senha(expira_em)")
        conn.commit()
    except Exception:
        pass

    # obras.tipo_obra
    try:
        conn.execute("ALTER TABLE obras ADD COLUMN tipo_obra TEXT NOT NULL DEFAULT 'contrato'")
        conn.commit()
    except Exception:
        pass
    
    try:
        conn.execute("ALTER TABLE obras ADD COLUMN token_publico TEXT")
        conn.commit()
    except Exception:
        pass
    
    try:
        conn.execute("ALTER TABLE obras ADD COLUMN fase_obra TEXT")
        conn.commit()
    except Exception:
        pass
 
    # obras.observacao_responsavel
    try:
        conn.execute("ALTER TABLE obras ADD COLUMN observacao_responsavel TEXT")
        conn.commit()
    except Exception:
        pass
 
    # obras.foto_capa
    try:
        conn.execute("ALTER TABLE obras ADD COLUMN foto_capa TEXT")
        conn.commit()
    except Exception:
        pass

    # obras.proxima_etapa_portal
    try:
        conn.execute("ALTER TABLE obras ADD COLUMN proxima_etapa_portal TEXT")
        conn.commit()
    except Exception:
        pass
 
    # obras.token_publico (link do portal)
    try:
        conn.execute("ALTER TABLE obras ADD COLUMN token_publico TEXT")
        conn.commit()
    except Exception:
        pass

    try:
        conn.execute("ALTER TABLE obras ADD COLUMN portal_expira_em TEXT")
        conn.commit()
    except Exception:
        pass

    try:
        conn.execute("ALTER TABLE obras ADD COLUMN portal_revogado_em TEXT")
        conn.commit()
    except Exception:
        pass

    try:
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_obras_token_publico ON obras(token_publico)")
        conn.commit()
    except Exception:
        pass

    try:
        conn.execute("""
            UPDATE obras
            SET token_publico = NULL,
                portal_expira_em = NULL,
                portal_revogado_em = CURRENT_TIMESTAMP
            WHERE token_publico IS NOT NULL
              AND length(token_publico) < 32
        """)
        conn.commit()
    except Exception:
        pass
 
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS fotos_obra (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                obra_id INTEGER NOT NULL,
                caminho TEXT NOT NULL,
                titulo TEXT,
                fase TEXT,
                publicar_portal INTEGER NOT NULL DEFAULT 0,
                data_registro TEXT,
                criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (obra_id) REFERENCES obras(id)
            )
        """)
        conn.commit()
    except Exception:
        pass

    adicionar_coluna("fotos_obra", "publicar_portal", "INTEGER NOT NULL DEFAULT 0")
    executar_sem_quebrar("UPDATE fotos_obra SET publicar_portal = 0 WHERE publicar_portal IS NULL")

    executar_sem_quebrar(
        """
        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER NOT NULL,
            nome_completo TEXT NOT NULL,
            cpf_cnpj TEXT,
            rg_ie TEXT,
            email TEXT,
            telefone TEXT,
            endereco TEXT,
            cidade TEXT,
            estado TEXT,
            cep TEXT,
            representante_legal TEXT,
            observacoes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (empresa_id) REFERENCES empresas(id)
        )
        """
    )

    executar_sem_quebrar(
        """
        CREATE TABLE IF NOT EXISTS contratos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER NOT NULL,
            obra_id INTEGER,
            cliente_id INTEGER,
            tipo_contrato TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'rascunho',
            titulo TEXT NOT NULL,
            numero_contrato TEXT,
            valor_total REAL DEFAULT 0,
            forma_pagamento TEXT,
            entrada REAL DEFAULT 0,
            quantidade_parcelas INTEGER DEFAULT 0,
            valor_parcela REAL DEFAULT 0,
            vencimento_primeira_parcela TEXT,
            indice_reajuste TEXT,
            multa_atraso REAL DEFAULT 0,
            juros_mora REAL DEFAULT 0,
            prazo_execucao INTEGER DEFAULT 0,
            data_inicio TEXT,
            data_fim_prevista TEXT,
            escopo_servico TEXT,
            itens_inclusos TEXT,
            itens_nao_inclusos TEXT,
            responsabilidades_contratada TEXT,
            responsabilidades_contratante TEXT,
            garantias TEXT,
            clausulas_adicionais TEXT,
            observacoes TEXT,
            motivo_aditivo TEXT,
            versao INTEGER DEFAULT 1,
            contrato_origem_id INTEGER,
            pdf_path TEXT,
            data_geracao TEXT,
            data_assinatura TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (empresa_id) REFERENCES empresas(id),
            FOREIGN KEY (obra_id) REFERENCES obras(id),
            FOREIGN KEY (cliente_id) REFERENCES clientes(id),
            FOREIGN KEY (contrato_origem_id) REFERENCES contratos(id)
        )
        """
    )
    executar_sem_quebrar(
        """
        CREATE TABLE IF NOT EXISTS clausulas_contrato (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER NOT NULL,
            titulo TEXT NOT NULL,
            tipo_contrato TEXT,
            texto TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (empresa_id) REFERENCES empresas(id)
        )
        """
    )

    adicionar_coluna("contratos", "motivo_aditivo", "TEXT")

    for tabela in ["clientes", "contratos", "clausulas_contrato"]:
        executar_sem_quebrar(
            f"UPDATE {tabela} SET empresa_id = ? WHERE empresa_id IS NULL",
            (empresa_padrao_id,),
        )

    executar_sem_quebrar("CREATE INDEX IF NOT EXISTS idx_clientes_empresa_id ON clientes(empresa_id)")
    executar_sem_quebrar("CREATE INDEX IF NOT EXISTS idx_contratos_empresa_id ON contratos(empresa_id)")
    executar_sem_quebrar("CREATE INDEX IF NOT EXISTS idx_contratos_obra_id ON contratos(obra_id)")
    executar_sem_quebrar("CREATE INDEX IF NOT EXISTS idx_contratos_cliente_id ON contratos(cliente_id)")
    executar_sem_quebrar("CREATE INDEX IF NOT EXISTS idx_contratos_origem_id ON contratos(contrato_origem_id)")
    executar_sem_quebrar("CREATE INDEX IF NOT EXISTS idx_clausulas_contrato_empresa_id ON clausulas_contrato(empresa_id)")
    executar_sem_quebrar("CREATE INDEX IF NOT EXISTS idx_clausulas_contrato_tipo ON clausulas_contrato(tipo_contrato)")

    colunas_custos = [
        ("quantidade", "REAL DEFAULT 0"),
        ("valor_unitario", "REAL DEFAULT 0"),
        ("status_entrega", "TEXT"),
        ("data_entrega_prevista", "TEXT"),
        ("data_entrega_realizada", "TEXT"),
        ("origem_compra_id", "INTEGER"),
    ]

    for coluna, definicao in colunas_custos:
        try:
            conn.execute(f"ALTER TABLE custos ADD COLUMN {coluna} {definicao}")
            conn.commit()
        except Exception:
            pass

    try:
        conn.execute("""
            INSERT INTO custos (
                empresa_id, obra_id, descricao, categoria, fornecedor, data_lancamento,
                valor_total, quantidade, valor_unitario, status_entrega,
                data_entrega_prevista, origem_compra_id, observacao
            )
            SELECT
                COALESCE(c.empresa_id, o.empresa_id, ?),
                c.obra_id,
                c.material,
                'Material',
                f.nome,
                c.data_pedido,
                COALESCE(c.quantidade, 0) * COALESCE(c.valor_unitario, 0),
                COALESCE(c.quantidade, 0),
                COALESCE(c.valor_unitario, 0),
                c.status,
                c.data_entrega_prevista,
                c.id,
                c.observacao
            FROM compras c
            LEFT JOIN obras o ON o.id = c.obra_id
            LEFT JOIN fornecedores f ON c.fornecedor_id = f.id
            WHERE NOT EXISTS (
                SELECT 1 FROM custos ct WHERE ct.origem_compra_id = c.id
            )
        """, (empresa_padrao_id,))
        conn.commit()
    except Exception:
        pass

    try:
        conn.execute("""
            UPDATE custos
            SET status_entrega = CASE LOWER(status_entrega)
                WHEN 'pedido' THEN 'Aguardando'
                WHEN 'aguardando' THEN 'Aguardando'
                WHEN 'entregue' THEN 'Entregue no Prazo'
                WHEN 'entregue no prazo' THEN 'Entregue no Prazo'
                WHEN 'entregue com atraso' THEN 'Entregue com Atraso'
                WHEN 'cancelado' THEN 'Cancelado'
                ELSE status_entrega
            END
            WHERE status_entrega IS NOT NULL AND status_entrega != ''
        """)
        conn.commit()
    except Exception:
        pass

    for tabela in tabelas_filhos_obra:
        executar_sem_quebrar(
            f"""
            UPDATE {tabela}
            SET empresa_id = (
                SELECT empresa_id FROM obras WHERE obras.id = {tabela}.obra_id
            )
            WHERE empresa_id IS NULL
              AND obra_id IS NOT NULL
              AND EXISTS (SELECT 1 FROM obras WHERE obras.id = {tabela}.obra_id)
            """
        )

    for tabela in tabelas_empresa:
        executar_sem_quebrar(
            f"UPDATE {tabela} SET empresa_id = ? WHERE empresa_id IS NULL",
            (empresa_padrao_id,),
        )

    conn.commit()
    conn.close()


def query_all(sql, params=()):
    conn = get_connection()
    cursor = conn.execute(sql, params)
    rows = cursor.fetchall()
    conn.close()
    return rows


def query_one(sql, params=()):
    conn = get_connection()
    cursor = conn.execute(sql, params)
    row = cursor.fetchone()
    conn.close()
    return row


def execute(sql, params=()):
    conn = get_connection()
    cursor = conn.execute(sql, params)
    conn.commit()
    last_id = cursor.lastrowid
    conn.close()
    return last_id
