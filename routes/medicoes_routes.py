import pandas as pd
from io import BytesIO
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file
from database import query_all, query_one, execute
from services.validators import parse_valor_monetario, valor_negativo, validar_intervalo_percentual
from auth import usuario_logado, eh_admin, eh_gestor, eh_leitura
from services.log_service import registrar_log

medicoes_bp = Blueprint("medicoes_bp", __name__)


@medicoes_bp.route("/medicoes")
def medicoes():
    if not usuario_logado() or not eh_leitura():
        return redirect(url_for("auth_bp.login"))

    lista_medicoes = query_all("""
        SELECT m.*, o.codigo AS codigo_obra, o.nome AS nome_obra
        FROM medicoes m
        JOIN obras o ON m.obra_id = o.id
        ORDER BY m.id DESC
    """)

    obras = query_all("SELECT * FROM obras ORDER BY nome ASC")
    return render_template("medicoes.html", medicoes=lista_medicoes, obras=obras)


@medicoes_bp.route("/medicoes/nova", methods=["POST"])
def nova_medicao():
    if not usuario_logado() or not eh_gestor():
        flash("Você não tem permissão para cadastrar medições.", "erro")
        return redirect(url_for("medicoes_bp.medicoes"))

    obra_id = request.form.get("obra_id", "").strip()
    mes = request.form.get("mes", "").strip()
    medicao_nome = request.form.get("medicao_nome", "").strip()
    etapa = request.form.get("etapa", "").strip()
    percentual = request.form.get("percentual", "").strip()
    percentual_acumulado = request.form.get("percentual_acumulado", "").strip()
    valor_realizado = request.form.get("valor_realizado", "").strip()
    data_medicao = request.form.get("data_medicao", "").strip()
    observacao = request.form.get("observacao", "").strip()

    if not obra_id or not medicao_nome or not etapa:
        flash("Preencha os campos obrigatórios da medição.", "erro")
        return redirect(url_for("medicoes_bp.medicoes"))

    try:
        percentual_float = parse_valor_monetario(percentual)
        percentual_acumulado_float = parse_valor_monetario(percentual_acumulado)
        valor_realizado_float = parse_valor_monetario(valor_realizado)

        validar_intervalo_percentual(percentual_float, "Percentual")
        validar_intervalo_percentual(percentual_acumulado_float, "Percentual acumulado")

        if valor_negativo(valor_realizado_float):
            raise ValueError("Valor realizado não pode ser negativo.")
    except ValueError as e:
        flash(str(e), "erro")
        return redirect(url_for("medicoes_bp.medicoes"))

    medicao_id = execute(
        """
        INSERT INTO medicoes (
            obra_id, mes, medicao_nome, etapa, percentual,
            percentual_acumulado, valor_realizado, data_medicao, observacao
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(obra_id),
            mes,
            medicao_nome,
            etapa,
            percentual_float,
            percentual_acumulado_float,
            valor_realizado_float,
            data_medicao,
            observacao
        )
    )

    registrar_log(
        acao="criação",
        entidade="medicao",
        entidade_id=medicao_id,
        descricao=f"Medição criada: {medicao_nome}"
    )

    flash("Medição cadastrada com sucesso.", "sucesso")
    return redirect(url_for("medicoes_bp.medicoes"))


@medicoes_bp.route("/medicoes/editar/<int:medicao_id>", methods=["POST"])
def editar_medicao(medicao_id):
    if not usuario_logado() or not eh_gestor():
        flash("Você não tem permissão para editar medições.", "erro")
        return redirect(url_for("medicoes_bp.medicoes"))

    mes = request.form.get("mes", "").strip()
    medicao_nome = request.form.get("medicao_nome", "").strip()
    etapa = request.form.get("etapa", "").strip()
    percentual = request.form.get("percentual", "").strip()
    percentual_acumulado = request.form.get("percentual_acumulado", "").strip()
    valor_realizado = request.form.get("valor_realizado", "").strip()
    data_medicao = request.form.get("data_medicao", "").strip()
    observacao = request.form.get("observacao", "").strip()

    try:
        percentual_float = parse_valor_monetario(percentual)
        percentual_acumulado_float = parse_valor_monetario(percentual_acumulado)
        valor_realizado_float = parse_valor_monetario(valor_realizado)

        validar_intervalo_percentual(percentual_float, "Percentual")
        validar_intervalo_percentual(percentual_acumulado_float, "Percentual acumulado")

        if valor_negativo(valor_realizado_float):
            raise ValueError("Valor realizado não pode ser negativo.")
    except ValueError as e:
        flash(str(e), "erro")
        return redirect(url_for("medicoes_bp.medicoes"))

    execute(
        """
        UPDATE medicoes
        SET mes = ?, medicao_nome = ?, etapa = ?, percentual = ?,
            percentual_acumulado = ?, valor_realizado = ?, data_medicao = ?, observacao = ?
        WHERE id = ?
        """,
        (
            mes,
            medicao_nome,
            etapa,
            percentual_float,
            percentual_acumulado_float,
            valor_realizado_float,
            data_medicao,
            observacao,
            medicao_id
        )
    )

    registrar_log(
        acao="edição",
        entidade="medicao",
        entidade_id=medicao_id,
        descricao=f"Medição editada: {medicao_nome}"
    )

    flash("Medição atualizada com sucesso.", "sucesso")
    return redirect(url_for("medicoes_bp.medicoes"))


@medicoes_bp.route("/medicoes/excluir/<int:medicao_id>", methods=["POST"])
def excluir_medicao(medicao_id):
    if not usuario_logado() or not eh_admin():
        flash("Você não tem permissão para excluir medições.", "erro")
        return redirect(url_for("medicoes_bp.medicoes"))

    medicao = query_one("SELECT * FROM medicoes WHERE id = ?", (medicao_id,))
    nome_medicao = medicao["medicao_nome"] if medicao else f"ID {medicao_id}"

    execute("DELETE FROM medicoes WHERE id = ?", (medicao_id,))

    registrar_log(
        acao="exclusão",
        entidade="medicao",
        entidade_id=medicao_id,
        descricao=f"Medição excluída: {nome_medicao}"
    )

    flash("Medição excluída com sucesso.", "sucesso")
    return redirect(url_for("medicoes_bp.medicoes"))


@medicoes_bp.route("/medicoes/exportar")
def medicoes_exportar():
    if not usuario_logado() or not eh_leitura():
        return redirect(url_for("auth_bp.login"))

    lista = query_all("""
        SELECT m.*, o.codigo AS codigo_obra, o.nome AS nome_obra
        FROM medicoes m
        JOIN obras o ON m.obra_id = o.id
        ORDER BY m.id DESC
    """)

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df = pd.DataFrame([dict(x) for x in lista])
        df.to_excel(writer, index=False, sheet_name="Medicoes")

    output.seek(0)
    return send_file(
        output,
        as_attachment=True,
        download_name="medicoes_central_obras.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )