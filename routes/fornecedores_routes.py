import pandas as pd
from io import BytesIO
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, send_file
from database import query_one, query_all, execute

fornecedores_bp = Blueprint("fornecedores_bp", __name__)


def usuario_logado():
    return "usuario_id" in session


@fornecedores_bp.route("/fornecedores")
def fornecedores():
    if not usuario_logado():
        return redirect(url_for("auth_bp.login"))

    lista_fornecedores = query_all("SELECT * FROM fornecedores ORDER BY id DESC")
    return render_template("fornecedores.html", fornecedores=lista_fornecedores)


@fornecedores_bp.route("/fornecedores/novo", methods=["POST"])
def novo_fornecedor():
    if not usuario_logado():
        return redirect(url_for("auth_bp.login"))

    codigo = request.form.get("codigo", "").strip()
    nome = request.form.get("nome", "").strip()
    categoria = request.form.get("categoria", "").strip()
    contato = request.form.get("contato", "").strip()
    documento = request.form.get("documento", "").strip()
    prazo_medio = request.form.get("prazo_medio", "").strip()
    nota_qualidade = request.form.get("nota_qualidade", "").strip()
    nota_preco = request.form.get("nota_preco", "").strip()
    nota_prazo = request.form.get("nota_prazo", "").strip()
    observacao = request.form.get("observacao", "").strip()

    if not codigo or not nome or not categoria:
        flash("Preencha os campos obrigatórios do fornecedor.", "erro")
        return redirect(url_for("fornecedores_bp.fornecedores"))

    existe = query_one("SELECT * FROM fornecedores WHERE codigo = ?", (codigo,))
    if existe:
        flash("Já existe um fornecedor com esse código.", "erro")
        return redirect(url_for("fornecedores_bp.fornecedores"))

    execute(
        """
        INSERT INTO fornecedores (
            codigo, nome, categoria, contato, documento,
            prazo_medio, nota_qualidade, nota_preco,
            nota_prazo, observacao
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            codigo,
            nome,
            categoria,
            contato,
            documento,
            int(prazo_medio) if prazo_medio else 0,
            float(nota_qualidade) if nota_qualidade else 0,
            float(nota_preco) if nota_preco else 0,
            float(nota_prazo) if nota_prazo else 0,
            observacao
        )
    )

    flash("Fornecedor cadastrado com sucesso.", "sucesso")
    return redirect(url_for("fornecedores_bp.fornecedores"))


@fornecedores_bp.route("/fornecedores/editar/<int:fornecedor_id>", methods=["POST"])
def editar_fornecedor(fornecedor_id):
    if not usuario_logado():
        return redirect(url_for("auth_bp.login"))

    nome = request.form.get("nome", "").strip()
    categoria = request.form.get("categoria", "").strip()
    contato = request.form.get("contato", "").strip()
    documento = request.form.get("documento", "").strip()
    prazo_medio = request.form.get("prazo_medio", "").strip()
    nota_qualidade = request.form.get("nota_qualidade", "").strip()
    nota_preco = request.form.get("nota_preco", "").strip()
    nota_prazo = request.form.get("nota_prazo", "").strip()
    observacao = request.form.get("observacao", "").strip()

    execute(
        """
        UPDATE fornecedores
        SET nome = ?, categoria = ?, contato = ?, documento = ?,
            prazo_medio = ?, nota_qualidade = ?, nota_preco = ?,
            nota_prazo = ?, observacao = ?
        WHERE id = ?
        """,
        (
            nome,
            categoria,
            contato,
            documento,
            int(prazo_medio) if prazo_medio else 0,
            float(nota_qualidade) if nota_qualidade else 0,
            float(nota_preco) if nota_preco else 0,
            float(nota_prazo) if nota_prazo else 0,
            observacao,
            fornecedor_id
        )
    )

    flash("Fornecedor atualizado com sucesso.", "sucesso")
    return redirect(url_for("fornecedores_bp.fornecedores"))


@fornecedores_bp.route("/fornecedores/excluir/<int:fornecedor_id>", methods=["POST"])
def excluir_fornecedor(fornecedor_id):
    if not usuario_logado():
        return redirect(url_for("auth_bp.login"))

    execute("DELETE FROM fornecedores WHERE id = ?", (fornecedor_id,))
    flash("Fornecedor excluído com sucesso.", "sucesso")
    return redirect(url_for("fornecedores_bp.fornecedores"))


@fornecedores_bp.route("/fornecedores/exportar")
def fornecedores_exportar():
    if not usuario_logado():
        return redirect(url_for("auth_bp.login"))

    lista = query_all("SELECT * FROM fornecedores ORDER BY id DESC")

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df = pd.DataFrame([dict(x) for x in lista])
        df.to_excel(writer, index=False, sheet_name="Fornecedores")

    output.seek(0)
    return send_file(
        output,
        as_attachment=True,
        download_name="fornecedores_central_obras.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )