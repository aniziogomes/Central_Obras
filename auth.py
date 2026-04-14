import bcrypt
from database import query_one, execute


def gerar_hash_senha(senha: str) -> str:
    senha_bytes = senha.encode("utf-8")
    salt = bcrypt.gensalt()
    senha_hash = bcrypt.hashpw(senha_bytes, salt)
    return senha_hash.decode("utf-8")


def verificar_senha(senha: str, senha_hash: str) -> bool:
    return bcrypt.checkpw(senha.encode("utf-8"), senha_hash.encode("utf-8"))


def criar_usuario_admin():
    usuario = query_one("SELECT * FROM usuarios WHERE username = ?", ("admin",))
    if not usuario:
        senha_hash = gerar_hash_senha("123456")
        execute(
            """
            INSERT INTO usuarios (nome, username, senha_hash, perfil, ativo)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("Administrador", "admin", senha_hash, "admin", 1)
        )