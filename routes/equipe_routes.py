import pandas as pd
from io import BytesIO
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file
from database import query_all, execute
from services.validators import parse_valor_monetario, valor_negativo
from auth import usuario_logado, eh_admin, eh_gestor, eh_leitura

equipe_bp = Blueprint("equipe_bp", __name__)


@equipe_bp.route("/equipe")
def equipe():
    if not usuario_logado() or not eh_leitura():
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
    redirect_to = request.form.get("redirect_to") or url_for("equipe_bp.equipe")
    if not usuario_logado() or not eh_gestor():
        flash("Você não tem permissão para cadastrar equipe.", "erro")
        return redirect(redirect_to)

    obra_id = request.form.get("obra_id", "").strip()
    nome = request.form.get("nome", "").strip()
    funcao = request.form.get("funcao", "").strip()

    if not obra_id or not nome:
        flash("Preencha os campos obrigatórios da equipe.", "erro")
        return redirect(redirect_to)

    valor_contratado = request.form.get("valor_contratado", "").strip()
    valor_pago = request.form.get("valor_pago", "").strip()

    try:
        valor_contratado_float = parse_valor_monetario(valor_contratado)
        valor_pago_float = parse_valor_monetario(valor_pago)

        if valor_negativo(valor_contratado_float):
            raise ValueError("Valor contratado não pode ser negativo.")

        if valor_negativo(valor_pago_float):
            raise ValueError("Valor pago não pode ser negativo.")
    except ValueError as e:
        flash(str(e), "erro")
        return redirect(redirect_to)

    execute(
        """
        INSERT INTO equipe (
            obra_id, nome, funcao, valor_contratado, valor_pago
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            int(obra_id),
            nome,
            funcao,
            valor_contratado_float,
            valor_pago_float
        )
    )

    flash("Profissional cadastrado com sucesso.", "sucesso")
    return redirect(redirect_to)


@equipe_bp.route("/equipe/editar/<int:equipe_id>", methods=["POST"])
def editar_equipe(equipe_id):
    if not usuario_logado() or not eh_gestor():
        flash("Você não tem permissão para editar equipe.", "erro")
        return redirect(url_for("equipe_bp.equipe"))

    nome = request.form.get("nome", "").strip()
    funcao = request.form.get("funcao", "").strip()

    execute(
        """
        UPDATE equipe
        SET nome = ?, funcao = ?
        WHERE id = ?
        """,
        (
            nome,
            funcao,
            equipe_id
        )
    )

    flash("Profissional atualizado com sucesso.", "sucesso")
    return redirect(url_for("equipe_bp.equipe"))


@equipe_bp.route("/equipe/excluir/<int:equipe_id>", methods=["POST"])
def excluir_equipe(equipe_id):
    if not usuario_logado() or not eh_admin():
        flash("Você não tem permissão para excluir equipe.", "erro")
        return redirect(url_for("equipe_bp.equipe"))

    execute("DELETE FROM equipe WHERE id = ?", (equipe_id,))
    flash("Profissional excluído com sucesso.", "sucesso")
    return redirect(url_for("equipe_bp.equipe"))


@equipe_bp.route("/equipe/exportar")
def equipe_exportar():
    if not usuario_logado() or not eh_leitura():
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
