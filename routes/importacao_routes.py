from pathlib import Path
from uuid import uuid4
from flask import Blueprint, render_template, request, redirect, url_for, flash
from werkzeug.utils import secure_filename
from database import query_all
from importar_planilha import importar_planilha
from auth import usuario_logado, eh_gestor, eh_leitura
from services.validators import limpar_texto
from services.log_service import registrar_log

importacao_bp = Blueprint("importacao_bp", __name__)
UPLOAD_IMPORTACAO_DIR = Path("uploads")
EXTENSOES_PLANILHA = {"xlsx", "xls", "csv"}


def extensao_planilha_permitida(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in EXTENSOES_PLANILHA


@importacao_bp.route("/importacao")
def importacao():
    if not usuario_logado() or not eh_leitura():
        return redirect(url_for("auth_bp.login"))

    obras = query_all("SELECT * FROM obras ORDER BY id DESC")
    importacoes = query_all("SELECT * FROM importacoes ORDER BY id DESC")

    return render_template(
        "importacao.html",
        obras=obras,
        importacoes=importacoes
    )


@importacao_bp.route("/importacao/planilha", methods=["POST"])
def importar_planilha_route():
    if not usuario_logado() or not eh_gestor():
        flash("Você não tem permissão para importar planilhas.", "erro")
        return redirect(url_for("importacao_bp.importacao"))

    arquivo = request.files.get("arquivo_planilha")
    try:
        codigo_obra = limpar_texto(request.form.get("codigo_obra", ""), max_len=40, obrigatorio=True, campo="Codigo da obra")
        nome_obra = limpar_texto(request.form.get("nome_obra", ""), max_len=140, obrigatorio=True, campo="Nome da obra")
    except ValueError as e:
        flash(str(e), "erro")
        return redirect(url_for("importacao_bp.importacao"))

    if not arquivo or not codigo_obra or not nome_obra:
        flash("Envie a planilha e preencha código e nome da obra.", "erro")
        return redirect(url_for("importacao_bp.importacao"))

    filename = secure_filename(arquivo.filename or "")
    if not filename or not extensao_planilha_permitida(filename):
        flash("Envie uma planilha XLSX, XLS ou CSV.", "erro")
        return redirect(url_for("importacao_bp.importacao"))

    UPLOAD_IMPORTACAO_DIR.mkdir(parents=True, exist_ok=True)
    nome_arquivo = f"importacao-{uuid4().hex[:10]}-{filename}"
    caminho = UPLOAD_IMPORTACAO_DIR / nome_arquivo
    arquivo.save(caminho)

    try:
        importar_planilha(str(caminho), codigo_obra, nome_obra)

        # LOG
        registrar_log(
            "importação",
            "planilha",
            None,
            f"Planilha importada: {filename}"
        )

        flash("Planilha importada com sucesso.", "sucesso")

    except Exception as e:
        flash(f"Erro ao importar planilha: {str(e)}", "erro")

    return redirect(url_for("importacao_bp.importacao"))


@importacao_bp.route("/orcamento-importado")
def orcamento_importado():
    if not usuario_logado() or not eh_leitura():
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
