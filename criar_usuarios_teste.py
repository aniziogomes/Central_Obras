from auth import gerar_hash_senha
from database import execute, query_one, init_db

init_db()

usuarios = [
    ("Gestor Teste", "gestor", "123456", "gestor", 1),
    ("Leitura Teste", "leitura", "123456", "leitura", 1),
]

for nome, username, senha, perfil, ativo in usuarios:
    existe = query_one("SELECT * FROM usuarios WHERE username = ?", (username,))
    if not existe:
        senha_hash = gerar_hash_senha(senha)
        execute(
            """
            INSERT INTO usuarios (nome, username, senha_hash, perfil, ativo)
            VALUES (?, ?, ?, ?, ?)
            """,
            (nome, username, senha_hash, perfil, ativo)
        )
        print(f"Usuário criado: {username}")
    else:
        print(f"Usuário já existe: {username}")