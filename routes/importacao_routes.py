import os
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from database import query_all
from importar_planilha import importar_planilha

importacao_bp = Blueprint("importacao_bp", __name__)


def usuario_logado():
    return "usuario_id" in session


@importacao_bp.route("/importacao")
def importacao():
    if not usuario_logado():
        return redirect(url_for("auth_bp.login"))

    obras = query_all("SELECT * FROM obras ORDER BY id DESC")
    importacoes = query_all("SELECT * FROM importacoes ORDER BY id DESC")
    return render_template("importacao.html", obras=obras, importacoes=importacoes)


@importacao_bp.route("/importacao/planilha", methods=["POST"])
def importar_planilha_route():
    if not usuario_logado():
        return redirect(url_for("auth_bp.login"))

    arquivo = request.files.get("arquivo_planilha")
    codigo_obra = request.form.get("codigo_obra", "").strip()
    nome_obra = request.form.get("nome_obra", "").strip()

    if not arquivo or not codigo_obra or not nome_obra:
        flash("Envie a planilha e preencha código e nome da obra.", "erro")
        return redirect(url_for("importacao_bp.importacao"))

    os.makedirs("uploads", exist_ok=True)
    caminho = os.path.join("uploads", arquivo.filename)
    arquivo.save(caminho)

    try:
        importar_planilha(caminho, codigo_obra, nome_obra)
        flash("Planilha importada com sucesso.", "sucesso")
    except Exception as e:
        flash(f"Erro ao importar planilha: {str(e)}", "erro")

    return redirect(url_for("importacao_bp.importacao"))


@importacao_bp.route("/orcamento-importado")
def orcamento_importado():
    if not usuario_logado():
        return redirect(url_for("auth_bp.login"))

    obras = query_all("SELECT * FROM obras ORDER BY id DESC")
    categorias_importadas = query_all("""
        SELECT cic.*, o.codigo AS codigo_obra, o.nome AS nome_obra
        FROM custos_importados_categoria cic
        JOIN obras o ON cic.obra_id = o.id
        ORDER BY o.id DESC, cic.categoria ASC
    """)

    return render_template(
        "orcamento_importado.html",
        obras=obras,
        categorias_importadas=categorias_importadas
    )