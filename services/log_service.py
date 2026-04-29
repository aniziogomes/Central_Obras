from database import execute
from flask import session
import sqlite3
from services.tenant import empresa_id_atual, empresa_id_da_entidade, empresa_id_para_insert


def registrar_log(acao, entidade, entidade_id=None, descricao=""):
    usuario_id = session.get("usuario_id")
    empresa_id = empresa_id_da_entidade(entidade, entidade_id)
    if empresa_id is None:
        empresa_id = empresa_id_atual() or empresa_id_para_insert()

    try:
        execute(
            """
            INSERT INTO logs (empresa_id, usuario_id, acao, entidade, entidade_id, descricao)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (empresa_id, usuario_id, acao, entidade, entidade_id, descricao)
        )
    except sqlite3.Error:
        pass
