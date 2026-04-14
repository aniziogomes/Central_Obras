from database import init_db
from auth import criar_usuario_admin

if __name__ == "__main__":
    init_db()
    criar_usuario_admin()
    print("Banco criado com sucesso.")
    print("Usuário: admin")
    print("Senha: 123456")