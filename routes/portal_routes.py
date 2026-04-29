import os
import re
import secrets
from datetime import datetime, timedelta
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from database import query_one, query_all, execute
from auth import usuario_logado, eh_gestor
from services.log_service import registrar_log
from services.tenant import obter_obra_acessivel

portal_bp = Blueprint("portal_bp", __name__)
TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{32,128}$")


def gerar_token_portal():
    return secrets.token_urlsafe(32)


def calcular_expiracao_portal():
    dias = int(os.environ.get("PORTAL_TOKEN_DAYS", "0") or 0)
    if dias <= 0:
        return None
    return (datetime.utcnow() + timedelta(days=dias)).isoformat(timespec="seconds")


def token_portal_valido(token):
    return bool(token and TOKEN_RE.fullmatch(token))


# ─── Rota pública — sem login ────────────────────────────────────────────────

@portal_bp.route("/portal/<token>")
def portal_obra(token):
    if not token_portal_valido(token):
        abort(404)

    obra = query_one("""
        SELECT
            id, codigo, nome, tipologia, area_m2, data_inicio,
            data_fim_prevista, progresso_percentual, status, fase_obra,
            observacao_responsavel, foto_capa, token_publico, portal_expira_em,
            portal_revogado_em
        FROM obras
        WHERE token_publico = ?
          AND token_publico IS NOT NULL
          AND portal_revogado_em IS NULL
    """, (token,))
    if not obra:
        abort(404)

    if obra["portal_expira_em"]:
        try:
            if datetime.fromisoformat(obra["portal_expira_em"]) < datetime.utcnow():
                abort(404)
        except ValueError:
            abort(404)

    # LGPD: o portal publico recebe apenas atualizacoes e fotos publicadas ao cliente.
    # Custos, fornecedores, equipe, documentos e valores internos nao sao consultados aqui.
    atualizacoes = query_all("""
        SELECT l.descricao, l.data_hora, u.nome AS autor
        FROM logs l
        LEFT JOIN usuarios u ON l.usuario_id = u.id
        WHERE l.entidade = 'obra'
          AND l.entidade_id = ?
          AND l.acao = 'atualizacao_canteiro'
          AND l.descricao LIKE 'Atualização para o cliente:%'
        ORDER BY l.data_hora DESC
    """, (obra["id"],))

    fotos_obra = query_all("""
        SELECT caminho, titulo, fase, data_registro
        FROM fotos_obra
        WHERE obra_id = ?
        ORDER BY id DESC
        LIMIT 12
    """, (obra["id"],))

    return render_template(
        "portal_obra.html",
        obra=obra,
        atualizacoes=atualizacoes,
        fotos_obra=fotos_obra,
    )


# ─── Página 404 do portal ────────────────────────────────────────────────────

@portal_bp.app_errorhandler(404)
def pagina_nao_encontrada(e):
    return render_template("portal_404.html"), 404


# ─── Gerar link público ──────────────────────────────────────────────────────

@portal_bp.route("/obras/gerar-link/<int:obra_id>", methods=["POST"])
def gerar_link(obra_id):
    if not usuario_logado() or not eh_gestor():
        flash("Você não tem permissão para gerar links.", "erro")
        return redirect(url_for("obras_bp.obras"))

    obra = obter_obra_acessivel(obra_id=obra_id)
    if not obra:
        flash("Obra não encontrada.", "erro")
        return redirect(url_for("obras_bp.obras"))

    novo_token = gerar_token_portal()
    expira_em = calcular_expiracao_portal()
    execute(
        "UPDATE obras SET token_publico = ?, portal_expira_em = ?, portal_revogado_em = NULL WHERE id = ?",
        (novo_token, expira_em, obra_id)
    )

    registrar_log(
        acao="gerar_link",
        entidade="obra",
        entidade_id=obra_id,
        descricao=f"Link público gerado para a Visão do Canteiro: {obra['nome']}"
    )

    flash("Link da Visão do Canteiro gerado com sucesso!", "sucesso")
    return redirect(request.referrer or url_for("obras_bp.obra_detalhe", codigo=obra["codigo"]))


# ─── Revogar link público ────────────────────────────────────────────────────

@portal_bp.route("/obras/revogar-link/<int:obra_id>", methods=["POST"])
def revogar_link(obra_id):
    if not usuario_logado() or not eh_gestor():
        flash("Você não tem permissão.", "erro")
        return redirect(url_for("obras_bp.obras"))

    obra = obter_obra_acessivel(obra_id=obra_id)
    if not obra:
        flash("Obra não encontrada.", "erro")
        return redirect(url_for("obras_bp.obras"))

    execute(
        "UPDATE obras SET token_publico = NULL, portal_expira_em = NULL, portal_revogado_em = CURRENT_TIMESTAMP WHERE id = ?",
        (obra_id,)
    )

    registrar_log(
        acao="revogar_link",
        entidade="obra",
        entidade_id=obra_id,
        descricao=f"Link público revogado: {obra['nome']}"
    )

    flash("Link revogado. O cliente não consegue mais acessar.", "sucesso")
    return redirect(request.referrer or url_for("obras_bp.obra_detalhe", codigo=obra["codigo"]))
