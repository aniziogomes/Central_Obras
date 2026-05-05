from pathlib import Path
from datetime import datetime, timedelta, timezone
from html import escape
import hashlib
import os
import secrets
import time
from uuid import uuid4
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.utils import secure_filename
from database import query_all, query_one, execute
from auth import verificar_senha, gerar_hash_senha, eh_admin, gerar_csrf_token, PERFIS_VALIDOS
from services.validators import limpar_texto
from services.email_service import enviar_email_resend
from services.log_service import registrar_log
from services.tenant import empresa_id_atual, empresa_usuario_por_form, listar_empresas, tem_acesso_global

auth_bp = Blueprint("auth_bp", __name__)
UPLOAD_USUARIOS_DIR = Path("static/uploads/usuarios")
EXTENSOES_IMAGEM = {"png", "jpg", "jpeg", "webp", "gif"}
MAX_TENTATIVAS_LOGIN = 5
BLOQUEIO_LOGIN_SEGUNDOS = 15 * 60
tentativas_login = {}
PERFIS_ADMINISTRAVEIS = {"admin", "gestor", "leitura"}
RESET_SENHA_EXPIRACAO_MINUTOS = 60


def url_sistema():
    return os.environ.get("APP_BASE_URL", "").strip().rstrip("/") or request.url_root.rstrip("/")


def normalizar_email(email):
    return (email or "").strip().lower()


def hash_token_reset(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def agora_utc():
    return datetime.now(timezone.utc)


def data_iso(dt):
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def apagar_tokens_reset_expirados():
    execute(
        "DELETE FROM tokens_reset_senha WHERE usado = 1 OR expira_em <= ?",
        (data_iso(agora_utc()),)
    )


def gerar_token_reset(usuario_id):
    apagar_tokens_reset_expirados()
    execute(
        "UPDATE tokens_reset_senha SET usado = 1, usado_em = ? WHERE usuario_id = ? AND usado = 0",
        (data_iso(agora_utc()), usuario_id)
    )
    token = secrets.token_urlsafe(48)
    expira_em = agora_utc() + timedelta(minutes=RESET_SENHA_EXPIRACAO_MINUTOS)
    execute(
        """
        INSERT INTO tokens_reset_senha (usuario_id, token, expira_em, usado)
        VALUES (?, ?, ?, 0)
        """,
        (usuario_id, hash_token_reset(token), data_iso(expira_em))
    )
    return token


def enviar_email_reset_senha(usuario, link_reset):
    nome = escape(usuario["nome"] or "usuario")
    link = escape(link_reset)
    assunto = "Redefinicao de senha - Canteiro"
    texto = (
        f"Ola, {usuario['nome']}.\n\n"
        "Recebemos uma solicitacao para redefinir sua senha no Canteiro.\n"
        f"Acesse este link em ate {RESET_SENHA_EXPIRACAO_MINUTOS} minutos:\n{link_reset}\n\n"
        "Se voce nao solicitou essa redefinicao, ignore este email."
    )
    html = f"""
    <div style="font-family:Arial,sans-serif;line-height:1.5;color:#20232a">
      <h2>Redefinicao de senha</h2>
      <p>Ola, {nome}.</p>
      <p>Recebemos uma solicitacao para redefinir sua senha no Canteiro.</p>
      <p><a href="{link}" style="display:inline-block;background:#e8621a;color:#fff;padding:12px 18px;border-radius:8px;text-decoration:none;font-weight:700">Criar nova senha</a></p>
      <p>Este link expira em {RESET_SENHA_EXPIRACAO_MINUTOS} minutos.</p>
      <p>Se voce nao solicitou essa redefinicao, ignore este email.</p>
    </div>
    """
    return enviar_email_resend(usuario["email"], assunto, html, texto)


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


def obter_usuario_administravel(usuario_id, campos="id"):
    filtro_empresa = "" if tem_acesso_global() else "AND empresa_id = ?"
    params = (usuario_id,) if tem_acesso_global() else (usuario_id, empresa_id_atual())
    return query_one(
        f"SELECT {campos} FROM usuarios WHERE id = ? AND perfil != 'cliente' {filtro_empresa}",
        params,
    )


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
    if request.method == "GET" and usuario_logado():
        return redirect(url_for("dashboard_bp.dashboard"))

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
            session["empresa_id"] = usuario["empresa_id"] if "empresa_id" in usuario.keys() else None
            session["usuario_foto"] = usuario["foto_perfil"] if "foto_perfil" in usuario.keys() and usuario["foto_perfil"] else ""
            limpar_falhas_login(username)
            return redirect(url_for("dashboard_bp.dashboard"))

        registrar_falha_login(username)
        flash("Usuário ou senha inválidos.", "erro")

    return render_template("login.html")


@auth_bp.route("/esqueci-senha", methods=["GET", "POST"])
def esqueci_senha():
    if request.method == "POST":
        email = normalizar_email(request.form.get("email", ""))
        usuario = None
        if email:
            usuario = query_one(
                "SELECT id, nome, email, ativo FROM usuarios WHERE lower(email) = ?",
                (email,)
            )

        if usuario and usuario["ativo"]:
            token = gerar_token_reset(usuario["id"])
            link_reset = f"{url_sistema()}{url_for('auth_bp.redefinir_senha', token=token)}"
            enviado = enviar_email_reset_senha(usuario, link_reset)
            if not enviado and os.environ.get("FLASK_DEBUG", "0") == "1":
                print(f"Link de redefinicao de senha para desenvolvimento: {link_reset}")

        flash("Se o email estiver cadastrado, enviaremos um link para redefinir sua senha.", "sucesso")
        return redirect(url_for("auth_bp.login"))

    return render_template("esqueci_senha.html")


@auth_bp.route("/redefinir-senha/<token>", methods=["GET", "POST"])
def redefinir_senha(token):
    apagar_tokens_reset_expirados()
    token_hash = hash_token_reset(token or "")
    registro = query_one(
        """
        SELECT t.id, t.usuario_id, t.expira_em, t.usado, u.nome, u.email, u.ativo
        FROM tokens_reset_senha t
        JOIN usuarios u ON u.id = t.usuario_id
        WHERE t.token = ?
        """,
        (token_hash,)
    )

    token_valido = bool(
        registro
        and not registro["usado"]
        and registro["ativo"]
        and registro["expira_em"] > data_iso(agora_utc())
    )

    if not token_valido:
        flash("Link de redefinicao invalido ou expirado. Solicite um novo link.", "erro")
        return redirect(url_for("auth_bp.esqueci_senha"))

    if request.method == "POST":
        nova_senha = request.form.get("nova_senha", "")
        confirmar_senha = request.form.get("confirmar_senha", "")

        if len(nova_senha) < 8:
            flash("A nova senha precisa ter pelo menos 8 caracteres.", "erro")
            return render_template("redefinir_senha.html", token=token)

        if nova_senha != confirmar_senha:
            flash("A confirmacao da senha nao confere.", "erro")
            return render_template("redefinir_senha.html", token=token)

        execute(
            "UPDATE usuarios SET senha_hash = ? WHERE id = ?",
            (gerar_hash_senha(nova_senha), registro["usuario_id"])
        )
        execute(
            "UPDATE tokens_reset_senha SET usado = 1, usado_em = ? WHERE id = ?",
            (data_iso(agora_utc()), registro["id"])
        )
        apagar_tokens_reset_expirados()
        registrar_log("resetar_senha_publico", "usuario", registro["usuario_id"], "Senha redefinida por link de email")
        flash("Senha redefinida com sucesso. Entre com sua nova senha.", "sucesso")
        return redirect(url_for("auth_bp.login"))

    return render_template("redefinir_senha.html", token=token)


@auth_bp.route("/perfil")
def perfil():
    if not usuario_logado():
        return redirect(url_for("auth_bp.login"))

    usuario = query_one("SELECT id, empresa_id, nome, username, email, perfil, ativo, foto_perfil FROM usuarios WHERE id = ?", (session["usuario_id"],))
    if not usuario:
        session.clear()
        return redirect(url_for("auth_bp.login"))

    usuarios = []
    if eh_admin():
        if tem_acesso_global():
            usuarios = query_all("SELECT id, empresa_id, nome, username, email, perfil, ativo, foto_perfil, criado_em FROM usuarios ORDER BY nome ASC")
        else:
            usuarios = query_all(
                "SELECT id, empresa_id, nome, username, email, perfil, ativo, foto_perfil, criado_em FROM usuarios WHERE empresa_id = ? ORDER BY nome ASC",
                (empresa_id_atual(),),
            )

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

    filtro_empresa = ""
    params_empresa = ()
    if not tem_acesso_global():
        filtro_empresa = "AND u.empresa_id = ?"
        params_empresa = (empresa_id_atual(),)

    usuarios_lista = query_all(f"""
        SELECT
            u.id, u.empresa_id, u.nome, u.username, u.email, u.perfil, u.ativo,
            u.foto_perfil, u.criado_em, e.nome AS empresa_nome
        FROM usuarios u
        LEFT JOIN empresas e ON e.id = u.empresa_id
        WHERE u.perfil != 'cliente'
          {filtro_empresa}
        ORDER BY u.ativo DESC, u.nome ASC
    """, params_empresa)
    kpis = {
        "total": len(usuarios_lista),
        "ativos": sum(1 for usuario in usuarios_lista if usuario["ativo"]),
        "admins": sum(1 for usuario in usuarios_lista if usuario["perfil"] == "admin"),
    }
    credenciais_usuario = session.pop("credenciais_usuario", None)
    empresas = listar_empresas() if tem_acesso_global() else []

    return render_template(
        "usuarios.html",
        usuarios=usuarios_lista,
        empresas=empresas,
        kpis=kpis,
        credenciais_usuario=credenciais_usuario,
        sistema_url=url_sistema(),
        admin_global=tem_acesso_global(),
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
        email = normalizar_email(limpar_texto(request.form.get("email", ""), max_len=160))
    except ValueError as e:
        flash(str(e), "erro")
        return redirecionar_usuarios()

    perfil = request.form.get("perfil", "leitura").strip()
    senha = request.form.get("senha", "")
    confirmar_senha = request.form.get("confirmar_senha", "")
    ativo = 1 if request.form.get("ativo", "1") == "1" else 0

    if perfil not in PERFIS_ADMINISTRAVEIS:
        perfil = "leitura"

    try:
        if tem_acesso_global():
            empresa_id = empresa_usuario_por_form(
                perfil,
                request.form.get("empresa_id", ""),
                request.form.get("empresa_nome", ""),
            )
        else:
            empresa_id = empresa_id_atual()
            if not empresa_id:
                raise ValueError("Administrador sem empresa nao pode criar usuarios de empresa.")
    except ValueError as e:
        flash(str(e), "erro")
        return redirecionar_usuarios()

    if not nome or not username or len(senha) < 6:
        flash("Informe nome, username e uma senha com pelo menos 6 caracteres.", "erro")
        return redirecionar_usuarios()

    if senha != confirmar_senha:
        flash("A confirmacao da senha nao confere.", "erro")
        return redirecionar_usuarios()

    if query_one("SELECT id FROM usuarios WHERE username = ?", (username,)):
        flash("Ja existe um usuario com esse username.", "erro")
        return redirecionar_usuarios()

    if email and query_one("SELECT id FROM usuarios WHERE lower(email) = ?", (email,)):
        flash("Ja existe um usuario com esse email.", "erro")
        return redirecionar_usuarios()

    onboarding_pendente = 1 if perfil == "gestor" else 0
    onboarding_completo = 0 if onboarding_pendente else 1

    usuario_id = execute(
        """
        INSERT INTO usuarios (
            empresa_id, nome, username, email, senha_hash, perfil, ativo,
            onboarding_completo, onboarding_pendente
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            empresa_id,
            nome,
            username,
            email or None,
            gerar_hash_senha(senha),
            perfil,
            ativo,
            onboarding_completo,
            onboarding_pendente,
        )
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

    onboarding_pendente = 1 if perfil == "gestor" else 0
    onboarding_completo = 0 if onboarding_pendente else 1

    usuario_id = execute(
        """
        INSERT INTO usuarios (nome, username, senha_hash, perfil, ativo, onboarding_completo, onboarding_pendente)
        VALUES (?, ?, ?, ?, 1, ?, ?)
        """,
        (nome, username, gerar_hash_senha(senha), perfil, onboarding_completo, onboarding_pendente)
    )
    registrar_log("criar_usuario", "usuario", usuario_id, f"Usuário {username} criado")
    flash("Usuário criado com sucesso.", "sucesso")
    return redirect(url_for("auth_bp.perfil") + "#usuarios")


@auth_bp.route("/usuarios/editar/<int:usuario_id>", methods=["POST"])
def editar_usuario(usuario_id):
    if not usuario_logado() or not eh_admin():
        flash("Apenas administradores podem editar usuarios.", "erro")
        return redirecionar_usuarios()

    usuario = obter_usuario_administravel(usuario_id)
    if not usuario:
        flash("Usuario nao encontrado.", "erro")
        return redirecionar_usuarios()

    try:
        nome = limpar_texto(request.form.get("nome", ""), max_len=120, obrigatorio=True, campo="Nome completo")
        username = limpar_texto(request.form.get("username", ""), max_len=80, obrigatorio=True, campo="Username")
        email = normalizar_email(limpar_texto(request.form.get("email", ""), max_len=160))
    except ValueError as e:
        flash(str(e), "erro")
        return redirecionar_usuarios()

    perfil = request.form.get("perfil", "leitura").strip()
    ativo = 1 if request.form.get("ativo", "1") == "1" else 0

    if perfil not in PERFIS_ADMINISTRAVEIS:
        perfil = "leitura"

    try:
        if tem_acesso_global():
            empresa_id = empresa_usuario_por_form(
                perfil,
                request.form.get("empresa_id", ""),
                request.form.get("empresa_nome", ""),
            )
        else:
            empresa_id = empresa_id_atual()
            if not empresa_id:
                raise ValueError("Administrador sem empresa nao pode editar usuarios de empresa.")
    except ValueError as e:
        flash(str(e), "erro")
        return redirecionar_usuarios()

    if usuario_id == session.get("usuario_id") and ativo == 0:
        flash("Voce nao pode desativar sua propria conta.", "erro")
        return redirecionar_usuarios()

    if query_one("SELECT id FROM usuarios WHERE username = ? AND id != ?", (username, usuario_id)):
        flash("Ja existe um usuario com esse username.", "erro")
        return redirecionar_usuarios()

    if email and query_one("SELECT id FROM usuarios WHERE lower(email) = ? AND id != ?", (email, usuario_id)):
        flash("Ja existe um usuario com esse email.", "erro")
        return redirecionar_usuarios()

    onboarding_pendente = None
    onboarding_completo = None
    if perfil != "gestor":
        onboarding_pendente = 0
        onboarding_completo = 1

    if onboarding_pendente is None:
        execute(
            "UPDATE usuarios SET empresa_id = ?, nome = ?, username = ?, email = ?, perfil = ?, ativo = ? WHERE id = ?",
            (empresa_id, nome, username, email or None, perfil, ativo, usuario_id)
        )
    else:
        execute(
            """
            UPDATE usuarios
            SET empresa_id = ?, nome = ?, username = ?, email = ?, perfil = ?, ativo = ?,
                onboarding_completo = ?, onboarding_pendente = ?
            WHERE id = ?
            """,
            (empresa_id, nome, username, email or None, perfil, ativo, onboarding_completo, onboarding_pendente, usuario_id)
        )
    if usuario_id == session.get("usuario_id"):
        session["usuario_nome"] = nome
        session["usuario_perfil"] = perfil
        session["empresa_id"] = empresa_id

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

    usuario = obter_usuario_administravel(usuario_id, "id, ativo")
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

    usuario = obter_usuario_administravel(usuario_id, "id, username")
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

    usuario = obter_usuario_administravel(usuario_id, "id, ativo")
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

    usuario = obter_usuario_administravel(usuario_id)
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

    usuario = obter_usuario_administravel(usuario_id, "id, nome, username")
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

    usuario = obter_usuario_administravel(usuario_id)
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
