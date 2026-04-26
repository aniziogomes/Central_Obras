from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from database import query_all, query_one, execute
from auth import verificar_senha, gerar_hash_senha, eh_admin
from services.log_service import registrar_log

auth_bp = Blueprint("auth_bp", __name__)


def usuario_logado():
    return "usuario_id" in session


@auth_bp.route("/")
def index():
    if not usuario_logado():
        return redirect(url_for("auth_bp.login"))
    return redirect(url_for("dashboard_bp.dashboard"))


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        senha = request.form.get("senha", "").strip()

        usuario = query_one(
            "SELECT * FROM usuarios WHERE username = ? AND ativo = 1",
            (username,)
        )

        if not usuario:
            flash("Usuário não encontrado.", "erro")
            return render_template("login.html")

        if verificar_senha(senha, usuario["senha_hash"]):
            session["usuario_id"] = usuario["id"]
            registrar_log(
                acao="login",
                entidade="usuario",
                entidade_id=usuario["id"],
                descricao=f"Usuário {usuario['username']} fez login")
            session["usuario_nome"] = usuario["nome"]
            session["usuario_perfil"] = usuario["perfil"]
            return redirect(url_for("dashboard_bp.dashboard"))
        else:
            flash("Senha incorreta.", "erro")

    return render_template("login.html")


@auth_bp.route("/perfil")
def perfil():
    if not usuario_logado():
        return redirect(url_for("auth_bp.login"))

    usuario = query_one("SELECT id, nome, username, perfil, ativo FROM usuarios WHERE id = ?", (session["usuario_id"],))
    if not usuario:
        session.clear()
        return redirect(url_for("auth_bp.login"))

    return render_template("perfil.html", usuario=usuario)


@auth_bp.route("/perfil/senha", methods=["POST"])
def alterar_senha():
    if not usuario_logado():
        return redirect(url_for("auth_bp.login"))

    senha_atual = request.form.get("senha_atual", "").strip()
    nova_senha = request.form.get("nova_senha", "").strip()
    confirmar_senha = request.form.get("confirmar_senha", "").strip()

    usuario = query_one("SELECT * FROM usuarios WHERE id = ?", (session["usuario_id"],))

    if not usuario or not verificar_senha(senha_atual, usuario["senha_hash"]):
        flash("Senha atual incorreta.", "erro")
        return redirect(url_for("auth_bp.perfil"))

    if len(nova_senha) < 6:
        flash("A nova senha precisa ter pelo menos 6 caracteres.", "erro")
        return redirect(url_for("auth_bp.perfil"))

    if nova_senha != confirmar_senha:
        flash("A confirmação da senha não confere.", "erro")
        return redirect(url_for("auth_bp.perfil"))

    execute("UPDATE usuarios SET senha_hash = ? WHERE id = ?", (gerar_hash_senha(nova_senha), usuario["id"]))
    registrar_log("alterar_senha", "usuario", usuario["id"], "Usuário alterou a própria senha")
    flash("Senha alterada com sucesso.", "sucesso")
    return redirect(url_for("auth_bp.perfil"))


@auth_bp.route("/usuarios")
def usuarios():
    if not usuario_logado():
        return redirect(url_for("auth_bp.login"))
    if not eh_admin():
        flash("Apenas administradores podem gerenciar usuários.", "erro")
        return redirect(url_for("dashboard_bp.dashboard"))

    lista_usuarios = query_all("SELECT id, nome, username, perfil, ativo, criado_em FROM usuarios ORDER BY nome ASC")
    return render_template("usuarios.html", usuarios=lista_usuarios)


@auth_bp.route("/usuarios/novo", methods=["POST"])
def novo_usuario():
    if not usuario_logado() or not eh_admin():
        flash("Apenas administradores podem criar usuários.", "erro")
        return redirect(url_for("auth_bp.usuarios"))

    nome = request.form.get("nome", "").strip()
    username = request.form.get("username", "").strip()
    perfil = request.form.get("perfil", "leitura").strip()
    senha = request.form.get("senha", "").strip()

    if perfil not in ["admin", "gestor", "leitura"]:
        perfil = "leitura"

    if not nome or not username or len(senha) < 6:
        flash("Informe nome, username e uma senha com pelo menos 6 caracteres.", "erro")
        return redirect(url_for("auth_bp.usuarios"))

    if query_one("SELECT id FROM usuarios WHERE username = ?", (username,)):
        flash("Já existe um usuário com esse username.", "erro")
        return redirect(url_for("auth_bp.usuarios"))

    usuario_id = execute(
        """
        INSERT INTO usuarios (nome, username, senha_hash, perfil, ativo)
        VALUES (?, ?, ?, ?, 1)
        """,
        (nome, username, gerar_hash_senha(senha), perfil)
    )
    registrar_log("criar_usuario", "usuario", usuario_id, f"Usuário {username} criado")
    flash("Usuário criado com sucesso.", "sucesso")
    return redirect(url_for("auth_bp.usuarios"))


@auth_bp.route("/usuarios/<int:usuario_id>/desativar", methods=["POST"])
def desativar_usuario(usuario_id):
    if not usuario_logado() or not eh_admin():
        flash("Apenas administradores podem desativar usuários.", "erro")
        return redirect(url_for("auth_bp.usuarios"))

    if usuario_id == session.get("usuario_id"):
        flash("Você não pode desativar seu próprio usuário.", "erro")
        return redirect(url_for("auth_bp.usuarios"))

    execute("UPDATE usuarios SET ativo = 0 WHERE id = ?", (usuario_id,))
    registrar_log("desativar_usuario", "usuario", usuario_id, "Usuário desativado")
    flash("Usuário desativado.", "sucesso")
    return redirect(url_for("auth_bp.usuarios"))


@auth_bp.route("/usuarios/<int:usuario_id>/resetar-senha", methods=["POST"])
def resetar_senha_usuario(usuario_id):
    if not usuario_logado() or not eh_admin():
        flash("Apenas administradores podem redefinir senhas.", "erro")
        return redirect(url_for("auth_bp.usuarios"))

    nova_senha = request.form.get("nova_senha", "").strip()
    if len(nova_senha) < 6:
        flash("A nova senha precisa ter pelo menos 6 caracteres.", "erro")
        return redirect(url_for("auth_bp.usuarios"))

    execute("UPDATE usuarios SET senha_hash = ? WHERE id = ?", (gerar_hash_senha(nova_senha), usuario_id))
    registrar_log("resetar_senha", "usuario", usuario_id, "Senha redefinida pelo administrador")
    flash("Senha redefinida com sucesso.", "sucesso")
    return redirect(url_for("auth_bp.usuarios"))


@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth_bp.login"))
