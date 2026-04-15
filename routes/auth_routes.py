from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from database import query_one
from auth import verificar_senha
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


@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth_bp.login"))
