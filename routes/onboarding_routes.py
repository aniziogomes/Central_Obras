from urllib.parse import quote_plus

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from auth import eh_gestor, usuario_logado
from database import execute, query_one
from routes.obras_routes import gerar_codigo_obra
from routes.portal_routes import calcular_expiracao_portal, gerar_token_portal
from services.log_service import registrar_log
from services.validators import (
    CATEGORIAS_CUSTO_VALIDAS,
    limpar_texto,
    parse_valor_monetario,
    validar_categoria_custo,
    valor_negativo,
)

onboarding_bp = Blueprint("onboarding_bp", __name__)

STATUS_OBRA = [
    ("planejamento", "Planejamento"),
    ("andamento", "Em andamento"),
    ("atrasada", "Atrasada"),
    ("concluida", "Concluida"),
]

TIPOS_OBRA = [
    ("contrato", "Contrato"),
    ("venda", "Venda"),
]


def _usuario_id():
    return session.get("usuario_id")


def _usuario_onboarding_completo():
    usuario = query_one("SELECT onboarding_completo FROM usuarios WHERE id = ?", (_usuario_id(),))
    return bool(usuario and int(usuario["onboarding_completo"] or 0) == 1)


def _total_obras():
    total = query_one("SELECT COUNT(*) AS total FROM obras")
    return int(total["total"] if total else 0)


def _obra_onboarding():
    obra_id = session.get("onboarding_obra_id")
    if obra_id:
        obra = query_one("SELECT * FROM obras WHERE id = ?", (obra_id,))
        if obra:
            return obra
    return None


def _normalizar_passo(valor):
    try:
        passo = int(valor)
    except (TypeError, ValueError):
        passo = int(session.get("onboarding_step", 1) or 1)
    return min(max(passo, 1), 3)


def _garantir_token_portal(obra):
    token_atual = obra["token_publico"] if "token_publico" in obra.keys() else None
    revogado_em = obra["portal_revogado_em"] if "portal_revogado_em" in obra.keys() else None
    if token_atual and not revogado_em:
        return token_atual

    for _ in range(6):
        token = gerar_token_portal()
        if not query_one("SELECT id FROM obras WHERE token_publico = ?", (token,)):
            execute(
                "UPDATE obras SET token_publico = ?, portal_expira_em = ?, portal_revogado_em = NULL WHERE id = ?",
                (token, calcular_expiracao_portal(), obra["id"]),
            )
            registrar_log(
                acao="onboarding_portal",
                entidade="obra",
                entidade_id=obra["id"],
                descricao=f"Link do portal gerado no onboarding: {obra['nome']}",
            )
            return token

    raise RuntimeError("Nao foi possivel gerar o link do portal.")


def _renderizar_onboarding(passo):
    obra = _obra_onboarding()
    if passo > 1 and not obra:
        session["onboarding_step"] = 1
        passo = 1

    portal_url = ""
    whatsapp_url = ""
    if passo == 3 and obra:
        token = _garantir_token_portal(obra)
        portal_url = url_for("portal_bp.portal_obra", token=token, _external=True)
        mensagem = (
            "Acompanhe o progresso da sua obra pelo link: "
            f"{portal_url}"
        )
        whatsapp_url = f"https://wa.me/?text={quote_plus(mensagem)}"

    return render_template(
        "onboarding.html",
        passo=passo,
        obra=obra,
        tipos_obra=TIPOS_OBRA,
        status_obra=STATUS_OBRA,
        categorias_custo=CATEGORIAS_CUSTO_VALIDAS,
        portal_url=portal_url,
        whatsapp_url=whatsapp_url,
    )


@onboarding_bp.route("/onboarding")
def onboarding():
    if not usuario_logado():
        return redirect(url_for("auth_bp.login"))
    if not eh_gestor():
        return redirect(url_for("dashboard_bp.dashboard"))
    if _usuario_onboarding_completo() and _total_obras() > 0:
        return redirect(url_for("dashboard_bp.dashboard"))

    passo = _normalizar_passo(request.args.get("step"))
    session["onboarding_step"] = passo
    return _renderizar_onboarding(passo)


@onboarding_bp.route("/onboarding/obra", methods=["POST"])
def criar_primeira_obra():
    if not usuario_logado() or not eh_gestor():
        return redirect(url_for("auth_bp.login"))

    try:
        nome = limpar_texto(request.form.get("nome", ""), max_len=140, obrigatorio=True, campo="Nome da obra")
        tipo_obra = limpar_texto(request.form.get("tipo_obra", "contrato"), max_len=30).lower()
        status = limpar_texto(request.form.get("status", "planejamento"), max_len=60, obrigatorio=True, campo="Status")
    except ValueError as e:
        flash(str(e), "erro")
        return redirect(url_for("onboarding_bp.onboarding", step=1))

    if tipo_obra not in {tipo for tipo, _ in TIPOS_OBRA}:
        tipo_obra = "contrato"
    if status not in {valor for valor, _ in STATUS_OBRA}:
        status = "planejamento"

    codigo = gerar_codigo_obra()
    obra_id = execute(
        """
        INSERT INTO obras (codigo, nome, tipo_obra, status, progresso_percentual)
        VALUES (?, ?, ?, ?, 0)
        """,
        (codigo, nome, tipo_obra, status),
    )

    registrar_log(
        acao="onboarding_obra",
        entidade="obra",
        entidade_id=obra_id,
        descricao=f"Primeira obra criada no onboarding: {nome} ({codigo})",
    )

    session["onboarding_ativo"] = True
    session["onboarding_obra_id"] = obra_id
    session["onboarding_step"] = 2
    return redirect(url_for("onboarding_bp.onboarding", step=2))


@onboarding_bp.route("/onboarding/custo", methods=["POST"])
def criar_primeiro_custo():
    if not usuario_logado() or not eh_gestor():
        return redirect(url_for("auth_bp.login"))

    obra = _obra_onboarding()
    if not obra:
        flash("Crie sua primeira obra antes de registrar um custo.", "erro")
        return redirect(url_for("onboarding_bp.onboarding", step=1))

    try:
        descricao = limpar_texto(request.form.get("descricao", ""), max_len=180, obrigatorio=True, campo="Descricao")
        categoria = limpar_texto(request.form.get("categoria", ""), max_len=60, obrigatorio=True, campo="Categoria")
        validar_categoria_custo(categoria)
        valor_total = parse_valor_monetario(request.form.get("valor", ""))
        if valor_negativo(valor_total) or valor_total <= 0:
            raise ValueError("Informe um valor maior que zero.")
    except ValueError as e:
        flash(str(e), "erro")
        return redirect(url_for("onboarding_bp.onboarding", step=2))

    custo_id = execute(
        """
        INSERT INTO custos (obra_id, descricao, categoria, valor_total)
        VALUES (?, ?, ?, ?)
        """,
        (obra["id"], descricao, categoria, valor_total),
    )

    registrar_log(
        acao="onboarding_custo",
        entidade="custo",
        entidade_id=custo_id,
        descricao=f"Primeiro custo criado no onboarding: {descricao}",
    )

    session["onboarding_step"] = 3
    return redirect(url_for("onboarding_bp.onboarding", step=3))


@onboarding_bp.route("/onboarding/custo/pular", methods=["POST"])
def pular_primeiro_custo():
    if not usuario_logado() or not eh_gestor():
        return redirect(url_for("auth_bp.login"))
    if not _obra_onboarding():
        return redirect(url_for("onboarding_bp.onboarding", step=1))

    session["onboarding_ativo"] = True
    session["onboarding_step"] = 3
    return redirect(url_for("onboarding_bp.onboarding", step=3))


@onboarding_bp.route("/onboarding/concluir", methods=["POST"])
def concluir_onboarding():
    if not usuario_logado() or not eh_gestor():
        return redirect(url_for("auth_bp.login"))

    execute("UPDATE usuarios SET onboarding_completo = 1 WHERE id = ?", (_usuario_id(),))
    session.pop("onboarding_ativo", None)
    session.pop("onboarding_obra_id", None)
    session.pop("onboarding_step", None)
    flash("Onboarding concluido. Seu canteiro inicial esta pronto.", "sucesso")
    return redirect(url_for("dashboard_bp.dashboard"))
