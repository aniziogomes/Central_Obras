import pandas as pd
from io import BytesIO
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file
from database import query_all, query_one, execute
from services.validators import parse_valor_monetario, valor_negativo
from auth import usuario_logado, eh_admin, eh_gestor, eh_leitura
from services.log_service import registrar_log

custos_bp = Blueprint("custos_bp", __name__)


@custos_bp.route("/custos")
def custos():
    if not usuario_logado() or not eh_leitura():
        return redirect(url_for("auth_bp.login"))

    lista_custos = query_all("""
        SELECT c.*, o.codigo AS codigo_obra, o.nome AS nome_obra
        FROM custos c
        JOIN obras o ON c.obra_id = o.id
        ORDER BY c.id DESC
    """)

    obras = query_all("SELECT * FROM obras ORDER BY nome ASC")
    return render_template("custos.html", custos=lista_custos, obras=obras)


@custos_bp.route("/custos/novo", methods=["POST"])
def novo_custo():
    if not usuario_logado() or not eh_gestor():
        flash("Você não tem permissão para cadastrar custos.", "erro")
        return redirect(url_for("custos_bp.custos"))

    obra_id = request.form.get("obra_id", "").strip()
    descricao = request.form.get("descricao", "").strip()
    categoria = request.form.get("categoria", "").strip()
    fornecedor = request.form.get("fornecedor", "").strip()
    data_lancamento = request.form.get("data_lancamento", "").strip()
    valor_total = request.form.get("valor_total", "").strip()
    nota_fiscal = request.form.get("nota_fiscal", "").strip()
    observacao = request.form.get("observacao", "").strip()

    if not obra_id or not descricao or not categoria or not valor_total:
        flash("Preencha os campos obrigatórios do custo.", "erro")
        return redirect(url_for("custos_bp.custos"))

    try:
        valor_total_float = parse_valor_monetario(valor_total)
        if valor_negativo(valor_total_float):
            raise ValueError("Valor do custo não pode ser negativo.")
    except ValueError as e:
        flash(str(e), "erro")
        return redirect(url_for("custos_bp.custos"))

    custo_id = execute(
        """
        INSERT INTO custos (
            obra_id, descricao, categoria, fornecedor,
            data_lancamento, valor_total, nota_fiscal, observacao
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(obra_id),
            descricao,
            categoria,
            fornecedor,
            data_lancamento,
            valor_total_float,
            nota_fiscal,
            observacao
        )
    )

    registrar_log(
        acao="criação",
        entidade="custo",
        entidade_id=custo_id,
        descricao=f"Custo criado: {descricao}"
    )

    flash("Custo lançado com sucesso.", "sucesso")
    return redirect(url_for("custos_bp.custos"))


@custos_bp.route("/custos/editar/<int:custo_id>", methods=["POST"])
def editar_custo(custo_id):
    if not usuario_logado() or not eh_gestor():
        flash("Você não tem permissão para editar custos.", "erro")
        return redirect(url_for("custos_bp.custos"))

    descricao = request.form.get("descricao", "").strip()
    categoria = request.form.get("categoria", "").strip()
    fornecedor = request.form.get("fornecedor", "").strip()
    data_lancamento = request.form.get("data_lancamento", "").strip()
    valor_total = request.form.get("valor_total", "").strip()
    nota_fiscal = request.form.get("nota_fiscal", "").strip()
    observacao = request.form.get("observacao", "").strip()

    try:
        valor_total_float = parse_valor_monetario(valor_total)
        if valor_negativo(valor_total_float):
            raise ValueError("Valor do custo não pode ser negativo.")
    except ValueError as e:
        flash(str(e), "erro")
        return redirect(url_for("custos_bp.custos"))

    execute(
        """
        UPDATE custos
        SET descricao = ?, categoria = ?, fornecedor = ?,
            data_lancamento = ?, valor_total = ?, nota_fiscal = ?, observacao = ?
        WHERE id = ?
        """,
        (
            descricao,
            categoria,
            fornecedor,
            data_lancamento,
            valor_total_float,
            nota_fiscal,
            observacao,
            custo_id
        )
    )

    registrar_log(
        acao="edição",
        entidade="custo",
        entidade_id=custo_id,
        descricao=f"Custo editado: {descricao}"
    )

    flash("Custo atualizado com sucesso.", "sucesso")
    return redirect(url_for("custos_bp.custos"))


@custos_bp.route("/custos/excluir/<int:custo_id>", methods=["POST"])
def excluir_custo(custo_id):
    if not usuario_logado() or not eh_admin():
        flash("Você não tem permissão para excluir custos.", "erro")
        return redirect(url_for("custos_bp.custos"))

    custo = query_one("SELECT * FROM custos WHERE id = ?", (custo_id,))
    descricao_custo = custo["descricao"] if custo else f"ID {custo_id}"

    execute("DELETE FROM custos WHERE id = ?", (custo_id,))

    registrar_log(
        acao="exclusão",
        entidade="custo",
        entidade_id=custo_id,
        descricao=f"Custo excluído: {descricao_custo}"
    )

    flash("Custo excluído com sucesso.", "sucesso")
    return redirect(url_for("custos_bp.custos"))


@custos_bp.route("/custos/exportar")
def custos_exportar():
    if not usuario_logado() or not eh_leitura():
        return redirect(url_for("auth_bp.login"))

    lista = query_all("""
        SELECT c.*, o.codigo AS codigo_obra, o.nome AS nome_obra
        FROM custos c
        JOIN obras o ON c.obra_id = o.id
        ORDER BY c.id DESC
    """)

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df = pd.DataFrame([dict(x) for x in lista])
        df.to_excel(writer, index=False, sheet_name="Custos")

    output.seek(0)
    return send_file(
        output,
        as_attachment=True,
        download_name="custos_central_obras.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )