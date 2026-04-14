import pandas as pd
from io import BytesIO
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, send_file
from database import query_all, execute
from services.validators import parse_valor_monetario, valor_negativo

equipe_bp = Blueprint("equipe_bp", __name__)


def usuario_logado():
    return "usuario_id" in session


@equipe_bp.route("/equipe")
def equipe():
    if not usuario_logado():
        return redirect(url_for("auth_bp.login"))

    lista_equipe = query_all("""
        SELECT e.*, o.codigo AS codigo_obra, o.nome AS nome_obra
        FROM equipe e
        JOIN obras o ON e.obra_id = o.id
        ORDER BY e.id DESC
    """)

    obras = query_all("SELECT * FROM obras ORDER BY nome ASC")
    return render_template("equipe.html", equipe=lista_equipe, obras=obras)


@equipe_bp.route("/equipe/novo", methods=["POST"])
def novo_membro_equipe():
    if not usuario_logado():
        return redirect(url_for("auth_bp.login"))

    obra_id = request.form.get("obra_id", "").strip()
    nome = request.form.get("nome", "").strip()
    funcao = request.form.get("funcao", "").strip()
    contrato = request.form.get("contrato", "").strip()
    data_inicio = request.form.get("data_inicio", "").strip()
    valor_contratado = request.form.get("valor_contratado", "").strip()
    valor_pago = request.form.get("valor_pago", "").strip()
    status_pagamento = request.form.get("status_pagamento", "").strip()
    observacao = request.form.get("observacao", "").strip()

    if not obra_id or not nome:
        flash("Preencha os campos obrigatórios da equipe.", "erro")
        return redirect(url_for("equipe_bp.equipe"))

    try:
        valor_contratado_float = parse_valor_monetario(valor_contratado)
        valor_pago_float = parse_valor_monetario(valor_pago)

        if valor_negativo(valor_contratado_float):
            raise ValueError("Valor contratado não pode ser negativo.")

        if valor_negativo(valor_pago_float):
            raise ValueError("Valor pago não pode ser negativo.")
    except ValueError as e:
        flash(str(e), "erro")
        return redirect(url_for("equipe_bp.equipe"))

    execute(
        """
        INSERT INTO equipe (
            obra_id, nome, funcao, contrato, data_inicio,
            valor_contratado, valor_pago, status_pagamento, observacao
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(obra_id),
            nome,
            funcao,
            contrato,
            data_inicio,
            valor_contratado_float,
            valor_pago_float,
            status_pagamento,
            observacao
        )
    )

    flash("Profissional cadastrado com sucesso.", "sucesso")
    return redirect(url_for("equipe_bp.equipe"))


@equipe_bp.route("/equipe/editar/<int:equipe_id>", methods=["POST"])
def editar_equipe(equipe_id):
    if not usuario_logado():
        return redirect(url_for("auth_bp.login"))

    nome = request.form.get("nome", "").strip()
    funcao = request.form.get("funcao", "").strip()
    contrato = request.form.get("contrato", "").strip()
    data_inicio = request.form.get("data_inicio", "").strip()
    valor_contratado = request.form.get("valor_contratado", "").strip()
    valor_pago = request.form.get("valor_pago", "").strip()
    status_pagamento = request.form.get("status_pagamento", "").strip()
    observacao = request.form.get("observacao", "").strip()

    try:
        valor_contratado_float = parse_valor_monetario(valor_contratado)
        valor_pago_float = parse_valor_monetario(valor_pago)

        if valor_negativo(valor_contratado_float):
            raise ValueError("Valor contratado não pode ser negativo.")

        if valor_negativo(valor_pago_float):
            raise ValueError("Valor pago não pode ser negativo.")
    except ValueError as e:
        flash(str(e), "erro")
        return redirect(url_for("equipe_bp.equipe"))

    execute(
        """
        UPDATE equipe
        SET nome = ?, funcao = ?, contrato = ?, data_inicio = ?,
            valor_contratado = ?, valor_pago = ?, status_pagamento = ?, observacao = ?
        WHERE id = ?
        """,
        (
            nome,
            funcao,
            contrato,
            data_inicio,
            valor_contratado_float,
            valor_pago_float,
            status_pagamento,
            observacao,
            equipe_id
        )
    )

    flash("Profissional atualizado com sucesso.", "sucesso")
    return redirect(url_for("equipe_bp.equipe"))


@equipe_bp.route("/equipe/excluir/<int:equipe_id>", methods=["POST"])
def excluir_equipe(equipe_id):
    if not usuario_logado():
        return redirect(url_for("auth_bp.login"))

    execute("DELETE FROM equipe WHERE id = ?", (equipe_id,))
    flash("Profissional excluído com sucesso.", "sucesso")
    return redirect(url_for("equipe_bp.equipe"))


@equipe_bp.route("/equipe/exportar")
def equipe_exportar():
    if not usuario_logado():
        return redirect(url_for("auth_bp.login"))

    lista = query_all("""
        SELECT e.*, o.codigo AS codigo_obra, o.nome AS nome_obra
        FROM equipe e
        JOIN obras o ON e.obra_id = o.id
        ORDER BY e.id DESC
    """)

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df = pd.DataFrame([dict(x) for x in lista])
        df.to_excel(writer, index=False, sheet_name="Equipe")

    output.seek(0)
    return send_file(
        output,
        as_attachment=True,
        download_name="equipe_central_obras.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )