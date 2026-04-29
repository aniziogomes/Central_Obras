import os
import secrets

import bcrypt
from flask import session
from database import query_one, execute


PERFIS_VALIDOS = {"admin", "gestor", "leitura", "cliente"}
PERFIS_INTERNOS = {"admin", "gestor", "leitura"}


def gerar_hash_senha(senha: str) -> str:
    senha_bytes = senha.encode("utf-8")
    salt = bcrypt.gensalt()
    senha_hash = bcrypt.hashpw(senha_bytes, salt)
    return senha_hash.decode("utf-8")


def verificar_senha(senha: str, senha_hash: str) -> bool:
    if not senha or not senha_hash:
        return False
    try:
        return bcrypt.checkpw(senha.encode("utf-8"), senha_hash.encode("utf-8"))
    except (TypeError, ValueError):
        return False


def criar_usuario_admin():
    usuario = query_one("SELECT * FROM usuarios WHERE username = ?", ("admin",))
    precisa_criar = not usuario
    precisa_trocar_senha_padrao = bool(usuario and verificar_senha("123456", usuario["senha_hash"]))
    if not precisa_criar and not precisa_trocar_senha_padrao:
        return

    senha_inicial = os.environ.get("ADMIN_PASSWORD")
    if not senha_inicial:
        senha_inicial = secrets.token_urlsafe(18)
        print(
            "AVISO DE SEGURANCA: ADMIN_PASSWORD nao definido. "
            f"Senha inicial temporaria do admin: {senha_inicial}"
        )
    if len(senha_inicial) < 8:
        raise RuntimeError("ADMIN_PASSWORD precisa ter pelo menos 8 caracteres.")

    senha_hash = gerar_hash_senha(senha_inicial)
    if precisa_criar:
        execute(
            """
            INSERT INTO usuarios (nome, username, senha_hash, perfil, ativo)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("Administrador", "admin", senha_hash, "admin", 1)
        )
    else:
        execute(
            "UPDATE usuarios SET senha_hash = ?, perfil = 'admin', ativo = 1 WHERE id = ?",
            (senha_hash, usuario["id"])
        )
        print("AVISO DE SEGURANCA: senha padrao antiga do admin foi substituida.")


def usuario_logado():
    return "usuario_id" in session


def usuario_atual():
    usuario_id = session.get("usuario_id")
    if not usuario_id:
        return None
    return query_one(
        """
        SELECT id, empresa_id, nome, username, perfil, ativo, onboarding_completo, foto_perfil
        FROM usuarios
        WHERE id = ?
        """,
        (usuario_id,)
    )


def gerar_csrf_token():
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return token


def validar_csrf_token(token: str) -> bool:
    token_sessao = session.get("_csrf_token")
    return bool(token and token_sessao and secrets.compare_digest(token, token_sessao))


def usuario_perfil():
    return session.get("usuario_perfil", "")


def eh_admin():
    return usuario_perfil() == "admin"


def eh_gestor():
    return usuario_perfil() in ["admin", "gestor"]


def eh_leitura():
    return usuario_perfil() in PERFIS_INTERNOS


def eh_cliente():
    return usuario_perfil() == "cliente"
