from pathlib import Path
import time
from uuid import uuid4
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.utils import secure_filename
from database import query_all, query_one, execute
from auth import verificar_senha, gerar_hash_senha, eh_admin, gerar_csrf_token, PERFIS_VALIDOS
from services.validators import limpar_texto
from services.log_service import registrar_log

auth_bp = Blueprint("auth_bp", __name__)
UPLOAD_USUARIOS_DIR = Path("static/uploads/usuarios")
EXTENSOES_IMAGEM = {"png", "jpg", "jpeg", "webp", "gif"}
MAX_TENTATIVAS_LOGIN = 5
BLOQUEIO_LOGIN_SEGUNDOS = 15 * 60
tentativas_login = {}
PERFIS_ADMINISTRAVEIS = {"admin", "gestor", "leitura"}


def url_sistema():
    return request.url_root.rstrip("/")


def guardar_credenciais_usuario(nome, username, senha, contexto="criado"):
    session["credenciais_usuario"] = {
        "nome": nome,
        "username": username,
        "senha": senha,
        "contexto": contexto,
        "url": url_sistema(),
    }


def redirecionar_usuarios():
    return redirect(url_for("auth_bp.usuarios"))


def usuario_logado():
    return "usuario_id" in session


def chave_login(username):
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip()
    return f"{ip}:{(username or '').lower()}"


def login_bloqueado(username):
    chave = chave_login(username)
    dados = tentativas_login.get(chave)
    if not dados:
        return False
    _, bloqueado_ate = dados
    if bloqueado_ate and bloqueado_ate > time.time():
        return True
    if bloqueado_ate:
        tentativas_login.pop(chave, None)
    return False


def registrar_falha_login(username):
    chave = chave_login(username)
    tentativas, _ = tentativas_login.get(chave, (0, 0))
    tentativas += 1
    bloqueado_ate = time.time() + BLOQUEIO_LOGIN_SEGUNDOS if tentativas >= MAX_TENTATIVAS_LOGIN else 0
    tentativas_login[chave] = (tentativas, bloqueado_ate)


def limpar_falhas_login(username):
    tentativas_login.pop(chave_login(username), None)


def extensao_permitida(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in EXTENSOES_IMAGEM


def salvar_foto_usuario(arquivo, usuario_id):
    if not arquivo or not arquivo.filename:
        raise ValueError("Selecione uma foto para enviar.")
    if not extensao_permitida(arquivo.filename):
        raise ValueError("Use uma imagem PNG, JPG, JPEG, WEBP ou GIF.")

    UPLOAD_USUARIOS_DIR.mkdir(parents=True, exist_ok=True)
    filename = secure_filename(arquivo.filename)
    extensao = filename.rsplit(".", 1)[1].lower()
    nome_arquivo = f"usuario-{usuario_id}-{uuid4().hex[:10]}.{extensao}"
    destino = UPLOAD_USUARIOS_DIR / nome_arquivo
    arquivo.save(destino)
    return "/" + destino.as_posix()


@auth_bp.route("/")
def index():
    if not usuario_logado():
        return redirect(url_for("auth_bp.login"))
    return redirect(url_for("dashboard_bp.dashboard"))


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        try:
            username = limpar_texto(request.form.get("username", ""), max_len=80)
        except ValueError:
            username = ""
        senha = request.form.get("senha", "")

        usuario = query_one("SELECT * FROM usuarios WHERE username = ?", (username,))
        senha_correta = bool(usuario and verificar_senha(senha, usuario["senha_hash"]))

        if login_bloqueado(username) and not senha_correta:
            flash("Muitas tentativas. Aguarde alguns minutos e tente novamente.", "erro")
            return render_template("login.html"), 429

        if senha_correta:
            if not usuario["ativo"]:
                flash("Sua conta está desativada. Entre em contato com o administrador.", "erro")
                return render_template("login.html"), 403
            if usuario["perfil"] == "cliente":
                flash("Acesso de cliente deve ser feito pelo link do portal.", "erro")
                return render_template("login.html"), 403
            session.clear()
            gerar_csrf_token()
            session["usuario_id"] = usuario["id"]
            registrar_log(
                acao="login",
                entidade="usuario",
                entidade_id=usuario["id"],
                descricao=f"Usuário {usuario['username']} fez login")
            session["usuario_nome"] = usuario["nome"]
            session["usuario_perfil"] = usuario["perfil"]
            session["usuario_foto"] = usuario["foto_perfil"] if "foto_perfil" in usuario.keys() and usuario["foto_perfil"] else ""
            limpar_falhas_login(username)
            return redirect(url_for("dashboard_bp.dashboard"))

        registrar_falha_login(username)
        flash("Usuário ou senha inválidos.", "erro")

    return render_template("login.html")


@auth_bp.route("/perfil")
def perfil():
    if not usuario_logado():
        return redirect(url_for("auth_bp.login"))

    usuario = query_one("SELECT id, nome, username, perfil, ativo, foto_perfil FROM usuarios WHERE id = ?", (session["usuario_id"],))
    if not usuario:
        session.clear()
        return redirect(url_for("auth_bp.login"))

    usuarios = []
    if eh_admin():
        usuarios = query_all("SELECT id, nome, username, perfil, ativo, foto_perfil, criado_em FROM usuarios ORDER BY nome ASC")

    return render_template("perfil.html", usuario=usuario, usuarios=usuarios)


@auth_bp.route("/perfil/senha", methods=["POST"])
def alterar_senha():
    if not usuario_logado():
        return redirect(url_for("auth_bp.login"))

    senha_atual = request.form.get("senha_atual", "")
    nova_senha = request.form.get("nova_senha", "")
    confirmar_senha = request.form.get("confirmar_senha", "")

    usuario = query_one("SELECT * FROM usuarios WHERE id = ?", (session["usuario_id"],))

    if not usuario or not verificar_senha(senha_atual, usuario["senha_hash"]):
        flash("Senha atual incorreta.", "erro")
        return redirect(url_for("auth_bp.perfil"))

    if len(nova_senha) < 8:
        flash("A nova senha precisa ter pelo menos 8 caracteres.", "erro")
        return redirect(url_for("auth_bp.perfil"))

    if nova_senha != confirmar_senha:
        flash("A confirmação da senha não confere.", "erro")
        return redirect(url_for("auth_bp.perfil"))

    execute("UPDATE usuarios SET senha_hash = ? WHERE id = ?", (gerar_hash_senha(nova_senha), usuario["id"]))
    registrar_log("alterar_senha", "usuario", usuario["id"], "Usuário alterou a própria senha")
    flash("Senha alterada com sucesso.", "sucesso")
    return redirect(url_for("auth_bp.perfil"))


@auth_bp.route("/perfil/foto", methods=["POST"])
def atualizar_foto_perfil():
    if not usuario_logado():
        return redirect(url_for("auth_bp.login"))

    try:
        caminho = salvar_foto_usuario(request.files.get("foto_perfil"), session["usuario_id"])
    except ValueError as e:
        flash(str(e), "erro")
        return redirect(url_for("auth_bp.perfil"))

    execute("UPDATE usuarios SET foto_perfil = ? WHERE id = ?", (caminho, session["usuario_id"]))
    session["usuario_foto"] = caminho
    registrar_log("atualizar_foto", "usuario", session["usuario_id"], "Usuario atualizou a foto de perfil")
    flash("Foto de perfil atualizada.", "sucesso")
    return redirect(url_for("auth_bp.perfil"))


@auth_bp.route("/usuarios")
def usuarios():
    if not usuario_logado():
        return redirect(url_for("auth_bp.login"))
    if not eh_admin():
        flash("Apenas administradores podem gerenciar usuarios.", "erro")
        return redirect(url_for("dashboard_bp.dashboard"))

    usuarios_lista = query_all("""
        SELECT id, nome, username, perfil, ativo, foto_perfil, criado_em
        FROM usuarios
        WHERE perfil != 'cliente'
        ORDER BY ativo DESC, nome ASC
    """)
    kpis = {
        "total": len(usuarios_lista),
        "ativos": sum(1 for usuario in usuarios_lista if usuario["ativo"]),
        "admins": sum(1 for usuario in usuarios_lista if usuario["perfil"] == "admin"),
    }
    credenciais_usuario = session.pop("credenciais_usuario", None)

    return render_template(
        "usuarios.html",
        usuarios=usuarios_lista,
        kpis=kpis,
        credenciais_usuario=credenciais_usuario,
        sistema_url=url_sistema(),
    )


def usuarios_antigo():
    if not usuario_logado():
        return redirect(url_for("auth_bp.login"))
    if not eh_admin():
        flash("Apenas administradores podem gerenciar usuários.", "erro")
        return redirect(url_for("dashboard_bp.dashboard"))

    return redirect(url_for("auth_bp.perfil") + "#usuarios")


@auth_bp.route("/usuarios/novo", methods=["POST"])
def novo_usuario():
    if not usuario_logado() or not eh_admin():
        flash("Apenas administradores podem criar usuarios.", "erro")
        return redirecionar_usuarios()

    try:
        nome = limpar_texto(request.form.get("nome", ""), max_len=120, obrigatorio=True, campo="Nome completo")
        username = limpar_texto(request.form.get("username", ""), max_len=80, obrigatorio=True, campo="Username")
    except ValueError as e:
        flash(str(e), "erro")
        return redirecionar_usuarios()

    perfil = request.form.get("perfil", "leitura").strip()
    senha = request.form.get("senha", "")
    confirmar_senha = request.form.get("confirmar_senha", "")
    ativo = 1 if request.form.get("ativo", "1") == "1" else 0

    if perfil not in PERFIS_ADMINISTRAVEIS:
        perfil = "leitura"

    if not nome or not username or len(senha) < 6:
        flash("Informe nome, username e uma senha com pelo menos 6 caracteres.", "erro")
        return redirecionar_usuarios()

    if senha != confirmar_senha:
        flash("A confirmacao da senha nao confere.", "erro")
        return redirecionar_usuarios()

    if query_one("SELECT id FROM usuarios WHERE username = ?", (username,)):
        flash("Ja existe um usuario com esse username.", "erro")
        return redirecionar_usuarios()

    usuario_id = execute(
        """
        INSERT INTO usuarios (nome, username, senha_hash, perfil, ativo)
        VALUES (?, ?, ?, ?, ?)
        """,
        (nome, username, gerar_hash_senha(senha), perfil, ativo)
    )
    registrar_log("criar_usuario", "usuario", usuario_id, f"Usuario {username} criado")
    guardar_credenciais_usuario(nome, username, senha, "criado")
    flash("Usuario criado com sucesso.", "sucesso")
    return redirecionar_usuarios()


def novo_usuario_antigo():
    if not usuario_logado() or not eh_admin():
        flash("Apenas administradores podem criar usuários.", "erro")
        return redirect(url_for("auth_bp.perfil") + "#usuarios")

    try:
        nome = limpar_texto(request.form.get("nome", ""), max_len=120, obrigatorio=True, campo="Nome")
        username = limpar_texto(request.form.get("username", ""), max_len=80, obrigatorio=True, campo="Username")
    except ValueError as e:
        flash(str(e), "erro")
        return redirect(url_for("auth_bp.perfil") + "#usuarios")
    perfil = request.form.get("perfil", "leitura").strip()
    senha = request.form.get("senha", "")

    if perfil not in PERFIS_VALIDOS:
        perfil = "leitura"

    if not nome or not username or len(senha) < 8:
        flash("Informe nome, username e uma senha com pelo menos 8 caracteres.", "erro")
        return redirect(url_for("auth_bp.perfil") + "#usuarios")

    if query_one("SELECT id FROM usuarios WHERE username = ?", (username,)):
        flash("Já existe um usuário com esse username.", "erro")
        return redirect(url_for("auth_bp.perfil") + "#usuarios")

    usuario_id = execute(
        """
        INSERT INTO usuarios (nome, username, senha_hash, perfil, ativo)
        VALUES (?, ?, ?, ?, 1)
        """,
        (nome, username, gerar_hash_senha(senha), perfil)
    )
    registrar_log("criar_usuario", "usuario", usuario_id, f"Usuário {username} criado")
    flash("Usuário criado com sucesso.", "sucesso")
    return redirect(url_for("auth_bp.perfil") + "#usuarios")


@auth_bp.route("/usuarios/editar/<int:usuario_id>", methods=["POST"])
def editar_usuario(usuario_id):
    if not usuario_logado() or not eh_admin():
        flash("Apenas administradores podem editar usuarios.", "erro")
        return redirecionar_usuarios()

    usuario = query_one("SELECT id FROM usuarios WHERE id = ? AND perfil != 'cliente'", (usuario_id,))
    if not usuario:
        flash("Usuario nao encontrado.", "erro")
        return redirecionar_usuarios()

    try:
        nome = limpar_texto(request.form.get("nome", ""), max_len=120, obrigatorio=True, campo="Nome completo")
        username = limpar_texto(request.form.get("username", ""), max_len=80, obrigatorio=True, campo="Username")
    except ValueError as e:
        flash(str(e), "erro")
        return redirecionar_usuarios()

    perfil = request.form.get("perfil", "leitura").strip()
    ativo = 1 if request.form.get("ativo", "1") == "1" else 0

    if perfil not in PERFIS_ADMINISTRAVEIS:
        perfil = "leitura"

    if usuario_id == session.get("usuario_id") and ativo == 0:
        flash("Voce nao pode desativar sua propria conta.", "erro")
        return redirecionar_usuarios()

    if query_one("SELECT id FROM usuarios WHERE username = ? AND id != ?", (username, usuario_id)):
        flash("Ja existe um usuario com esse username.", "erro")
        return redirecionar_usuarios()

    execute(
        "UPDATE usuarios SET nome = ?, username = ?, perfil = ?, ativo = ? WHERE id = ?",
        (nome, username, perfil, ativo, usuario_id)
    )
    if usuario_id == session.get("usuario_id"):
        session["usuario_nome"] = nome
        session["usuario_perfil"] = perfil

    registrar_log("editar_usuario", "usuario", usuario_id, f"Usuario atualizado: {username}")
    flash("Usuario atualizado com sucesso.", "sucesso")
    return redirecionar_usuarios()


@auth_bp.route("/usuarios/toggle/<int:usuario_id>", methods=["POST"])
def toggle_usuario(usuario_id):
    requisicao_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"

    if not usuario_logado() or not eh_admin():
        if requisicao_ajax:
            return jsonify({"ok": False, "message": "Nao autorizado."}), 403
        flash("Apenas administradores podem alterar usuarios.", "erro")
        return redirecionar_usuarios()

    if usuario_id == session.get("usuario_id"):
        if requisicao_ajax:
            return jsonify({"ok": False, "message": "Voce nao pode desativar sua propria conta."}), 400
        flash("Voce nao pode desativar sua propria conta.", "erro")
        return redirecionar_usuarios()

    usuario = query_one("SELECT id, ativo FROM usuarios WHERE id = ? AND perfil != 'cliente'", (usuario_id,))
    if not usuario:
        if requisicao_ajax:
            return jsonify({"ok": False, "message": "Usuario nao encontrado."}), 404
        flash("Usuario nao encontrado.", "erro")
        return redirecionar_usuarios()

    novo_status = 0 if usuario["ativo"] else 1
    execute("UPDATE usuarios SET ativo = ? WHERE id = ?", (novo_status, usuario_id))
    registrar_log("toggle_usuario", "usuario", usuario_id, "Usuario ativado" if novo_status else "Usuario desativado")

    if requisicao_ajax:
        return jsonify({"ok": True, "ativo": bool(novo_status)})
    flash("Usuario ativado." if novo_status else "Usuario desativado.", "sucesso")
    return redirecionar_usuarios()


@auth_bp.route("/usuarios/excluir/<int:usuario_id>", methods=["POST"])
def excluir_usuario(usuario_id):
    if not usuario_logado() or not eh_admin():
        flash("Apenas administradores podem excluir usuarios.", "erro")
        return redirecionar_usuarios()

    if usuario_id == session.get("usuario_id"):
        flash("Voce nao pode excluir sua propria conta.", "erro")
        return redirecionar_usuarios()

    usuario = query_one("SELECT id, username FROM usuarios WHERE id = ? AND perfil != 'cliente'", (usuario_id,))
    if not usuario:
        flash("Usuario nao encontrado.", "erro")
        return redirecionar_usuarios()

    execute("DELETE FROM usuarios WHERE id = ?", (usuario_id,))
    registrar_log("excluir_usuario", "usuario", usuario_id, f"Usuario excluido: {usuario['username']}")
    flash("Usuario excluido com sucesso.", "sucesso")
    return redirecionar_usuarios()


@auth_bp.route("/usuarios/<int:usuario_id>/desativar", methods=["POST"])
def desativar_usuario(usuario_id):
    requisicao_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"

    if not usuario_logado() or not eh_admin():
        flash("Apenas administradores podem desativar usuários.", "erro")
        return redirect(url_for("auth_bp.perfil") + "#usuarios")

    if usuario_id == session.get("usuario_id"):
        flash("Você não pode desativar seu próprio usuário.", "erro")
        return redirect(url_for("auth_bp.perfil") + "#usuarios")

    usuario = query_one("SELECT id, ativo FROM usuarios WHERE id = ?", (usuario_id,))
    if not usuario:
        if requisicao_ajax:
            return jsonify({"ok": False, "message": "Usuario nao encontrado."}), 404
        flash("Usuario nao encontrado.", "erro")
        return redirect(url_for("auth_bp.perfil") + "#usuarios")

    if not usuario["ativo"]:
        if requisicao_ajax:
            return jsonify({"ok": True, "message": "Usuario ja estava inativo."})
        flash("Usuario ja estava inativo.", "sucesso")
        return redirect(url_for("auth_bp.perfil") + "#usuarios")

    execute("UPDATE usuarios SET ativo = 0 WHERE id = ? AND ativo = 1", (usuario_id,))
    registrar_log("desativar_usuario", "usuario", usuario_id, "Usuário desativado")
    flash("Usuário desativado.", "sucesso")
    return redirect(url_for("auth_bp.perfil") + "#usuarios")


@auth_bp.route("/usuarios/<int:usuario_id>/reativar", methods=["POST"])
def reativar_usuario(usuario_id):
    if not usuario_logado() or not eh_admin():
        flash("Apenas administradores podem reativar usuarios.", "erro")
        return redirect(url_for("auth_bp.perfil") + "#usuarios")

    usuario = query_one("SELECT id FROM usuarios WHERE id = ?", (usuario_id,))
    if not usuario:
        flash("Usuario nao encontrado.", "erro")
        return redirect(url_for("auth_bp.perfil") + "#usuarios")

    execute("UPDATE usuarios SET ativo = 1 WHERE id = ?", (usuario_id,))
    registrar_log("reativar_usuario", "usuario", usuario_id, "Usuario reativado")
    flash("Usuario reativado.", "sucesso")
    return redirect(url_for("auth_bp.perfil") + "#usuarios")


@auth_bp.route("/usuarios/<int:usuario_id>/resetar-senha", methods=["POST"])
def resetar_senha_usuario(usuario_id):
    if not usuario_logado() or not eh_admin():
        flash("Apenas administradores podem redefinir senhas.", "erro")
        return redirecionar_usuarios()

    nova_senha = request.form.get("nova_senha", "")
    confirmar_senha = request.form.get("confirmar_senha", "")
    if len(nova_senha) < 6:
        flash("A nova senha precisa ter pelo menos 6 caracteres.", "erro")
        return redirecionar_usuarios()

    if confirmar_senha and nova_senha != confirmar_senha:
        flash("A confirmacao da senha nao confere.", "erro")
        return redirecionar_usuarios()

    usuario = query_one("SELECT id, nome, username FROM usuarios WHERE id = ? AND perfil != 'cliente'", (usuario_id,))
    if not usuario:
        flash("Usuario nao encontrado.", "erro")
        return redirecionar_usuarios()

    execute("UPDATE usuarios SET senha_hash = ? WHERE id = ?", (gerar_hash_senha(nova_senha), usuario_id))
    registrar_log("resetar_senha", "usuario", usuario_id, "Senha redefinida pelo administrador")
    guardar_credenciais_usuario(usuario["nome"], usuario["username"], nova_senha, "senha_resetada")
    flash("Senha redefinida com sucesso.", "sucesso")
    return redirecionar_usuarios()


@auth_bp.route("/usuarios/<int:usuario_id>/foto", methods=["POST"])
def atualizar_foto_usuario(usuario_id):
    if not usuario_logado() or not eh_admin():
        flash("Apenas administradores podem alterar fotos de usuarios.", "erro")
        return redirect(url_for("auth_bp.perfil") + "#usuarios")

    usuario = query_one("SELECT id FROM usuarios WHERE id = ?", (usuario_id,))
    if not usuario:
        flash("Usuario nao encontrado.", "erro")
        return redirect(url_for("auth_bp.perfil") + "#usuarios")

    try:
        caminho = salvar_foto_usuario(request.files.get("foto_perfil"), usuario_id)
    except ValueError as e:
        flash(str(e), "erro")
        return redirect(url_for("auth_bp.perfil") + "#usuarios")

    execute("UPDATE usuarios SET foto_perfil = ? WHERE id = ?", (caminho, usuario_id))
    if usuario_id == session.get("usuario_id"):
        session["usuario_foto"] = caminho
    registrar_log("atualizar_foto_usuario", "usuario", usuario_id, "Foto de usuario atualizada pelo administrador")
    flash("Foto do usuario atualizada.", "sucesso")
    return redirect(url_for("auth_bp.perfil") + "#usuarios")


@auth_bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("auth_bp.login"))
