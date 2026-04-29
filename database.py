import sqlite3
import os
import shutil
from pathlib import Path

DEFAULT_DB_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Canteiro"
DB_PATH = Path(os.environ.get("CENTRAL_OBRAS_DB", DEFAULT_DB_DIR / "central_obras.db"))
LEGACY_DB_PATH = Path("data/central_obras.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
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

    # usuarios.foto_perfil
    try:
        conn.execute("ALTER TABLE usuarios ADD COLUMN foto_perfil TEXT")
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
 
    # obras.token_publico (link do portal)
    try:
        conn.execute("ALTER TABLE obras ADD COLUMN token_publico TEXT")
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
                data_registro TEXT,
                criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (obra_id) REFERENCES obras(id)
            )
        """)
        conn.commit()
    except Exception:
        pass

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
                obra_id, descricao, categoria, fornecedor, data_lancamento,
                valor_total, quantidade, valor_unitario, status_entrega,
                data_entrega_prevista, origem_compra_id, observacao
            )
            SELECT
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
            LEFT JOIN fornecedores f ON c.fornecedor_id = f.id
            WHERE NOT EXISTS (
                SELECT 1 FROM custos ct WHERE ct.origem_compra_id = c.id
            )
        """)
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
