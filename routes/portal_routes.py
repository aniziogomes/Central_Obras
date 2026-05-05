import os
import re
import secrets
import unicodedata
from datetime import datetime, timedelta
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from database import query_one, query_all, execute
from auth import usuario_logado, eh_gestor
from services.log_service import registrar_log
from services.tenant import obter_obra_acessivel

portal_bp = Blueprint("portal_bp", __name__)
TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{32,128}$")
PORTAL_FASES = [
    "Planejamento",
    "Fundacao",
    "Estrutura",
    "Alvenaria",
    "Telhado",
    "Instalacoes",
    "Revestimento",
    "Acabamento",
    "Vistoria",
    "Concluida",
]


def gerar_token_portal():
    return secrets.token_urlsafe(32)


def calcular_expiracao_portal():
    dias = int(os.environ.get("PORTAL_TOKEN_DAYS", "0") or 0)
    if dias <= 0:
        return None
    return (datetime.utcnow() + timedelta(days=dias)).isoformat(timespec="seconds")


def token_portal_valido(token):
    return bool(token and TOKEN_RE.fullmatch(token))


def _slug_fase(valor):
    texto = unicodedata.normalize("NFKD", str(valor or ""))
    texto = "".join(ch for ch in texto if not unicodedata.combining(ch))
    return texto.strip().lower()


def _indice_fase_atual(fase_atual):
    fase_slug = _slug_fase(fase_atual)
    for indice, fase in enumerate(PORTAL_FASES):
        if _slug_fase(fase) == fase_slug:
            return indice
    return 0


def _proxima_etapa(fase_atual, status):
    if (status or "").lower() in {"concluida", "vendida"}:
        return "Obra concluida"
    indice = _indice_fase_atual(fase_atual)
    if indice >= len(PORTAL_FASES) - 1:
        return "Entrega final"
    return PORTAL_FASES[indice + 1]


def _ultima_atualizacao(obra, atualizacoes, fotos_obra):
    candidatos = []
    if atualizacoes and atualizacoes[0]["data_hora"]:
        candidatos.append(atualizacoes[0]["data_hora"])
    if fotos_obra and fotos_obra[0]["data_registro"]:
        candidatos.append(fotos_obra[0]["data_registro"])
    if "criado_em" in obra.keys() and obra["criado_em"]:
        candidatos.append(obra["criado_em"])
    return max(candidatos) if candidatos else None


def _montar_timeline_portal(obra, fase_atual, proxima_etapa, ultima_atualizacao):
    status = (obra["status"] or "").lower()
    etapa_entrega = "Concluida" if status in {"concluida", "vendida"} else "Entrega prevista"
    return [
        {
            "titulo": "Inicio da obra",
            "status": "done" if obra["data_inicio"] else "upcoming",
            "data": obra["data_inicio"],
            "descricao": "Marco inicial do cronograma.",
        },
        {
            "titulo": fase_atual,
            "status": "current",
            "data": ultima_atualizacao,
            "descricao": "Fase atualmente em acompanhamento.",
        },
        {
            "titulo": proxima_etapa,
            "status": "upcoming" if status not in {"concluida", "vendida"} else "done",
            "data": obra["data_fim_prevista"],
            "descricao": "Proximo passo previsto pela equipe responsavel.",
        },
        {
            "titulo": etapa_entrega,
            "status": "done" if status in {"concluida", "vendida"} else "upcoming",
            "data": obra["data_fim_prevista"],
            "descricao": "Previsao consolidada de encerramento da obra.",
        },
    ]


# ─── Rota pública — sem login ────────────────────────────────────────────────

@portal_bp.route("/portal/<token>")
def portal_obra(token):
    if not token_portal_valido(token):
        abort(404)

    obra = query_one("""
        SELECT
            id, codigo, nome, endereco, tipologia, area_m2, data_inicio, criado_em,
            data_fim_prevista, progresso_percentual, status, fase_obra,
            observacao_responsavel, foto_capa, proxima_etapa_portal, token_publico, portal_expira_em,
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

    foto_principal = obra["foto_capa"] if "foto_capa" in obra.keys() and obra["foto_capa"] else ""
    if not foto_principal and fotos_obra:
        foto_principal = fotos_obra[0]["caminho"]

    galeria_portal = [foto for foto in fotos_obra if foto["caminho"] != foto_principal]
    fase_portal = obra["fase_obra"] if obra["fase_obra"] else "Atualizacao em breve"
    proxima_etapa = obra["proxima_etapa_portal"] if obra["proxima_etapa_portal"] else _proxima_etapa(fase_portal, obra["status"])
    ultima_atualizacao = _ultima_atualizacao(obra, atualizacoes, fotos_obra)
    timeline_portal = _montar_timeline_portal(obra, fase_portal, proxima_etapa, ultima_atualizacao)

    return render_template(
        "portal_obra.html",
        obra=obra,
        atualizacoes=atualizacoes,
        fotos_obra=fotos_obra,
        foto_principal=foto_principal,
        galeria_portal=galeria_portal,
        fase_portal=fase_portal,
        proxima_etapa=proxima_etapa,
        ultima_atualizacao=ultima_atualizacao,
        timeline_portal=timeline_portal,
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
