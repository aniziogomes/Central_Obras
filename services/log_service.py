from database import execute
from flask import session


def registrar_log(acao, entidade, entidade_id=None, descricao=""):
    usuario_id = session.get("usuario_id")

    execute(
        """
        INSERT INTO logs (usuario_id, acao, entidade, entidade_id, descricao)
        VALUES (?, ?, ?, ?, ?)
        """,
        (usuario_id, acao, entidade, entidade_id, descricao)
    )