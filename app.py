import os
import secrets
from datetime import timedelta

from flask import Flask, request, url_for, redirect, jsonify, session, abort, send_from_directory
from database import init_db
from utils import formatar_moeda, calcular_media_fornecedor, formatar_tipo_obra, formatar_data
from services.dashboard_service import calcular_alertas

from auth import (
    criar_usuario_admin,
    eh_admin,
    eh_gestor,
    eh_leitura,
    gerar_csrf_token,
    pode_visualizar,
    usuario_atual,
    usuario_logado,
    usuario_perfil,
    validar_csrf_token,
)
from routes.auth_routes import auth_bp
from routes.dashboard_routes import dashboard_bp
from routes.obras_routes import obras_bp
from routes.custos_routes import custos_bp
from routes.fornecedores_routes import fornecedores_bp
from routes.compras_routes import compras_bp
from routes.equipe_routes import equipe_bp
from routes.medicoes_routes import medicoes_bp
from routes.importacao_routes import importacao_bp
from routes.onboarding_routes import onboarding_bp
from routes.portal_routes import portal_bp          # ← NOVO

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv():
        return False

load_dotenv()

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY") or os.environ.get("FLASK_SECRET_KEY") or secrets.token_urlsafe(32),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE", "0") == "1",
    PERMANENT_SESSION_LIFETIME=timedelta(hours=int(os.environ.get("SESSION_HOURS", "8"))),
    MAX_CONTENT_LENGTH=int(os.environ.get("MAX_CONTENT_LENGTH", str(8 * 1024 * 1024))),
)

init_db()
criar_usuario_admin()


@app.route("/favicon.ico")
def favicon():
    return send_from_directory(
        os.path.join(app.root_path, "static", "imgLogos"),
        "logo1.png",
        mimetype="image/png",
        max_age=0,
    )


ROTAS_PUBLICAS = {
    "auth_bp.index",
    "auth_bp.login",
    "auth_bp.esqueci_senha",
    "auth_bp.redefinir_senha",
    "portal_bp.portal_obra",
    "portal_bp.pagina_nao_encontrada",
    "favicon",
    "static",
}

ROTAS_ONBOARDING = {
    "onboarding_bp.onboarding",
    "onboarding_bp.criar_primeira_obra",
    "onboarding_bp.criar_primeiro_custo",
    "onboarding_bp.pular_primeiro_custo",
    "onboarding_bp.concluir_onboarding",
    "auth_bp.usuarios",
    "auth_bp.novo_usuario",
    "auth_bp.editar_usuario",
    "auth_bp.toggle_usuario",
    "auth_bp.excluir_usuario",
    "auth_bp.resetar_senha_usuario",
}


def _resposta_nao_autorizado():
    if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.path.endswith("/dados"):
        return jsonify({"erro": "nao autorizado"}), 401
    return redirect(url_for("auth_bp.login"))


def _deve_exibir_onboarding(usuario):
    if not usuario or usuario["perfil"] != "gestor":
        return False
    return int(usuario["onboarding_pendente"] or 0) == 1


@app.before_request
def aplicar_seguranca_minima():
    endpoint = request.endpoint
    session.permanent = True

    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        token = request.form.get("csrf_token") or request.headers.get("X-CSRFToken")
        if not validar_csrf_token(token):
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return jsonify({"erro": "CSRF invalido"}), 400
            abort(400)

    if not endpoint or endpoint in ROTAS_PUBLICAS:
        return None

    usuario = usuario_atual()
    if not usuario or not usuario["ativo"]:
        session.clear()
        return _resposta_nao_autorizado()

    # Perfil cliente nunca acessa rotas internas. Cliente usa apenas /portal/<token>.
    if usuario["perfil"] == "cliente":
        session.clear()
        return _resposta_nao_autorizado()

    session["usuario_id"] = usuario["id"]
    session["usuario_nome"] = usuario["nome"]
    session["usuario_perfil"] = usuario["perfil"]
    session["empresa_id"] = usuario["empresa_id"]
    session["usuario_foto"] = usuario["foto_perfil"] if "foto_perfil" in usuario.keys() and usuario["foto_perfil"] else ""

    if not _deve_exibir_onboarding(usuario):
        session.pop("onboarding_ativo", None)
        session.pop("onboarding_obra_id", None)
        session.pop("onboarding_step", None)

    if endpoint not in ROTAS_ONBOARDING and _deve_exibir_onboarding(usuario):
        return redirect(url_for("onboarding_bp.onboarding"))

    return None


@app.after_request
def aplicar_headers_seguranca(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
    if app.config.get("SESSION_COOKIE_SECURE"):
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


@app.context_processor
def inject_helpers():
    alertas_globais = []
    if usuario_logado() and pode_visualizar():
        try:
            alertas_globais = calcular_alertas()
        except Exception:
            alertas_globais = []

    export_endpoints = {
        "dashboard_bp.dashboard": "dashboard_bp.dashboard_exportar",
        "obras_bp.obras": "obras_bp.obras_exportar",
        "custos_bp.custos": "custos_bp.custos_exportar",
        "compras_bp.compras": "compras_bp.compras_exportar",
        "fornecedores_bp.fornecedores": "fornecedores_bp.fornecedores_exportar",
        "equipe_bp.equipe": "equipe_bp.equipe_exportar",
        "medicoes_bp.medicoes": "medicoes_bp.medicoes_exportar",
    }
    menu_export_url = None
    export_endpoint = export_endpoints.get(request.endpoint)
    if usuario_logado() and export_endpoint:
        try:
            menu_export_url = url_for(export_endpoint, **request.args.to_dict(flat=True))
        except Exception:
            menu_export_url = None

    return dict(
        formatar_moeda=formatar_moeda,
        formatar_data=formatar_data,
        calcular_media_fornecedor=calcular_media_fornecedor,
        formatar_tipo_obra=formatar_tipo_obra,
        eh_admin=eh_admin,
        eh_gestor=eh_gestor,
        eh_leitura=eh_leitura,
        pode_visualizar=pode_visualizar,
        usuario_perfil=usuario_perfil,
        csrf_token=gerar_csrf_token,
        alertas_globais=alertas_globais,
        menu_export_url=menu_export_url,
    )


app.register_blueprint(auth_bp)
app.register_blueprint(dashboard_bp)
app.register_blueprint(obras_bp)
app.register_blueprint(custos_bp)
app.register_blueprint(fornecedores_bp)
app.register_blueprint(compras_bp)
app.register_blueprint(equipe_bp)
app.register_blueprint(medicoes_bp)
app.register_blueprint(importacao_bp)
app.register_blueprint(onboarding_bp)
app.register_blueprint(portal_bp)                  # ← NOVO


if __name__ == "__main__":
    app.run(debug=True)
