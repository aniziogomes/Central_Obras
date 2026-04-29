import uuid
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from database import query_one, query_all, execute
from auth import usuario_logado, eh_gestor
from services.log_service import registrar_log

portal_bp = Blueprint("portal_bp", __name__)


# ─── Rota pública — sem login ────────────────────────────────────────────────

@portal_bp.route("/portal/<token>")
def portal_obra(token):
    obra = query_one(
        "SELECT * FROM obras WHERE token_publico = ?", (token,)
    )
    if not obra:
        abort(404)

    # Atualizacoes publicadas para o cliente.
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

    obra = query_one("SELECT * FROM obras WHERE id = ?", (obra_id,))
    if not obra:
        flash("Obra não encontrada.", "erro")
        return redirect(url_for("obras_bp.obras"))

    novo_token = uuid.uuid4().hex[:16]
    execute(
        "UPDATE obras SET token_publico = ? WHERE id = ?",
        (novo_token, obra_id)
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

    obra = query_one("SELECT * FROM obras WHERE id = ?", (obra_id,))
    if not obra:
        flash("Obra não encontrada.", "erro")
        return redirect(url_for("obras_bp.obras"))

    execute(
        "UPDATE obras SET token_publico = NULL WHERE id = ?",
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
