import pandas as pd
from io import BytesIO
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file
from database import query_all, execute
from services.validators import parse_valor_monetario, valor_negativo
from auth import usuario_logado, eh_admin, eh_gestor, eh_leitura

compras_bp = Blueprint("compras_bp", __name__)


@compras_bp.route("/compras")
def compras():
    if not usuario_logado() or not eh_leitura():
        return redirect(url_for("auth_bp.login"))

    lista_compras = query_all("""
        SELECT c.*, o.codigo AS codigo_obra, o.nome AS nome_obra,
               f.codigo AS codigo_fornecedor, f.nome AS nome_fornecedor
        FROM compras c
        JOIN obras o ON c.obra_id = o.id
        LEFT JOIN fornecedores f ON c.fornecedor_id = f.id
        ORDER BY c.id DESC
    """)

    obras = query_all("SELECT * FROM obras ORDER BY nome ASC")
    fornecedores = query_all("SELECT * FROM fornecedores ORDER BY nome ASC")

    return render_template(
        "compras.html",
        compras=lista_compras,
        obras=obras,
        fornecedores=fornecedores
    )


@compras_bp.route("/compras/nova", methods=["POST"])
def nova_compra():
    redirect_to = request.form.get("redirect_to") or url_for("compras_bp.compras")
    if not usuario_logado() or not eh_gestor():
        flash("Você não tem permissão para cadastrar compras.", "erro")
        return redirect(redirect_to)

    obra_id = request.form.get("obra_id", "").strip()
    fornecedor_id = request.form.get("fornecedor_id", "").strip()
    material = request.form.get("material", "").strip()
    data_pedido = request.form.get("data_pedido", "").strip()
    data_entrega_prevista = request.form.get("data_entrega_prevista", "").strip()
    quantidade = request.form.get("quantidade", "").strip()
    valor_unitario = request.form.get("valor_unitario", "").strip()
    status = request.form.get("status", "").strip()
    observacao = request.form.get("observacao", "").strip()

    if not obra_id or not material:
        flash("Preencha os campos obrigatórios da compra.", "erro")
        return redirect(redirect_to)

    try:
        quantidade_float = parse_valor_monetario(quantidade)
        valor_unitario_float = parse_valor_monetario(valor_unitario)

        if valor_negativo(quantidade_float):
            raise ValueError("Quantidade não pode ser negativa.")

        if valor_negativo(valor_unitario_float):
            raise ValueError("Valor unitário não pode ser negativo.")
    except ValueError as e:
        flash(str(e), "erro")
        return redirect(redirect_to)

    execute(
        """
        INSERT INTO compras (
            obra_id, fornecedor_id, material, data_pedido,
            data_entrega_prevista, quantidade, valor_unitario,
            status, observacao
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(obra_id),
            int(fornecedor_id) if fornecedor_id else None,
            material,
            data_pedido,
            data_entrega_prevista,
            quantidade_float,
            valor_unitario_float,
            status,
            observacao
        )
    )

    flash("Compra cadastrada com sucesso.", "sucesso")
    return redirect(redirect_to)


@compras_bp.route("/compras/editar/<int:compra_id>", methods=["POST"])
def editar_compra(compra_id):
    if not usuario_logado() or not eh_gestor():
        flash("Você não tem permissão para editar compras.", "erro")
        return redirect(url_for("compras_bp.compras"))

    material = request.form.get("material", "").strip()
    data_pedido = request.form.get("data_pedido", "").strip()
    data_entrega_prevista = request.form.get("data_entrega_prevista", "").strip()
    quantidade = request.form.get("quantidade", "").strip()
    valor_unitario = request.form.get("valor_unitario", "").strip()
    status = request.form.get("status", "").strip()
    observacao = request.form.get("observacao", "").strip()

    try:
        quantidade_float = parse_valor_monetario(quantidade)
        valor_unitario_float = parse_valor_monetario(valor_unitario)

        if valor_negativo(quantidade_float):
            raise ValueError("Quantidade não pode ser negativa.")

        if valor_negativo(valor_unitario_float):
            raise ValueError("Valor unitário não pode ser negativo.")
    except ValueError as e:
        flash(str(e), "erro")
        return redirect(url_for("compras_bp.compras"))

    execute(
        """
        UPDATE compras
        SET material = ?, data_pedido = ?, data_entrega_prevista = ?,
            quantidade = ?, valor_unitario = ?, status = ?, observacao = ?
        WHERE id = ?
        """,
        (
            material,
            data_pedido,
            data_entrega_prevista,
            quantidade_float,
            valor_unitario_float,
            status,
            observacao,
            compra_id
        )
    )

    flash("Compra atualizada com sucesso.", "sucesso")
    return redirect(url_for("compras_bp.compras"))


@compras_bp.route("/compras/excluir/<int:compra_id>", methods=["POST"])
def excluir_compra(compra_id):
    if not usuario_logado() or not eh_admin():
        flash("Você não tem permissão para excluir compras.", "erro")
        return redirect(url_for("compras_bp.compras"))

    execute("DELETE FROM compras WHERE id = ?", (compra_id,))
    flash("Compra excluída com sucesso.", "sucesso")
    return redirect(url_for("compras_bp.compras"))


@compras_bp.route("/compras/exportar")
def compras_exportar():
    if not usuario_logado() or not eh_leitura():
        return redirect(url_for("auth_bp.login"))

    lista = query_all("""
        SELECT c.*, o.codigo AS codigo_obra, o.nome AS nome_obra,
               f.codigo AS codigo_fornecedor, f.nome AS nome_fornecedor
        FROM compras c
        JOIN obras o ON c.obra_id = o.id
        LEFT JOIN fornecedores f ON c.fornecedor_id = f.id
        ORDER BY c.id DESC
    """)

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df = pd.DataFrame([dict(x) for x in lista])
        df.to_excel(writer, index=False, sheet_name="Compras")

    output.seek(0)

    return send_file(
        output,
        as_attachment=True,
        download_name="compras_central_obras.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
