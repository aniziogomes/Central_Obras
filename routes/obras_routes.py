import pandas as pd
from io import BytesIO
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, send_file
from database import query_one, query_all, execute
from services.validators import parse_valor_monetario, valor_negativo, validar_intervalo_percentual

obras_bp = Blueprint("obras_bp", __name__)


def usuario_logado():
    return "usuario_id" in session


@obras_bp.route("/obras")
def obras():
    if not usuario_logado():
        return redirect(url_for("auth_bp.login"))

    lista_obras = query_all("SELECT * FROM obras ORDER BY id DESC")
    return render_template("obras.html", obras=lista_obras)


@obras_bp.route("/obras/nova", methods=["POST"])
def nova_obra():
    if not usuario_logado():
        return redirect(url_for("auth_bp.login"))

    codigo = request.form.get("codigo", "").strip()
    nome = request.form.get("nome", "").strip()
    endereco = request.form.get("endereco", "").strip()
    tipologia = request.form.get("tipologia", "").strip()
    area_m2 = request.form.get("area_m2", "").strip()
    data_inicio = request.form.get("data_inicio", "").strip()
    data_fim_prevista = request.form.get("data_fim_prevista", "").strip()
    orcamento = request.form.get("orcamento", "").strip()
    receita_total = request.form.get("receita_total", "").strip()
    progresso_percentual = request.form.get("progresso_percentual", "").strip()
    status = request.form.get("status", "").strip()

    if not codigo or not nome or not tipologia or not status:
        flash("Preencha os campos obrigatórios da obra.", "erro")
        return redirect(url_for("obras_bp.obras"))

    existe = query_one("SELECT * FROM obras WHERE codigo = ?", (codigo,))
    if existe:
        flash("Já existe uma obra com esse código.", "erro")
        return redirect(url_for("obras_bp.obras"))

    try:
        area_valor = float(area_m2) if area_m2 else 0
        orcamento_valor = parse_valor_monetario(orcamento)
        receita_valor = parse_valor_monetario(receita_total)
        progresso_valor = parse_valor_monetario(progresso_percentual)

        if valor_negativo(area_valor):
            raise ValueError("Área não pode ser negativa.")

        if valor_negativo(orcamento_valor):
            raise ValueError("Orçamento não pode ser negativo.")

        if valor_negativo(receita_valor):
            raise ValueError("Receita total não pode ser negativa.")

        validar_intervalo_percentual(progresso_valor, "Execução (%)")
    except ValueError as e:
        flash(str(e), "erro")
        return redirect(url_for("obras_bp.obras"))

    execute(
        """
        INSERT INTO obras (
            codigo, nome, endereco, tipologia, area_m2,
            data_inicio, data_fim_prevista, orcamento,
            receita_total, progresso_percentual, status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            codigo,
            nome,
            endereco,
            tipologia,
            area_valor,
            data_inicio,
            data_fim_prevista,
            orcamento_valor,
            receita_valor,
            progresso_valor,
            status
        )
    )

    flash("Obra cadastrada com sucesso.", "sucesso")
    return redirect(url_for("obras_bp.obras"))


@obras_bp.route("/obras/exportar")
def obras_exportar():
    if not usuario_logado():
        return redirect(url_for("auth_bp.login"))

    obras = query_all("SELECT * FROM obras ORDER BY id DESC")

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df = pd.DataFrame([dict(o) for o in obras])
        df.to_excel(writer, index=False, sheet_name="Obras")

    output.seek(0)

    return send_file(
        output,
        as_attachment=True,
        download_name="obras_central_obras.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


@obras_bp.route("/obra/<codigo>")
def obra_detalhe(codigo):
    if not usuario_logado():
        return redirect(url_for("auth_bp.login"))

    obra = query_one("SELECT * FROM obras WHERE codigo = ?", (codigo,))
    if not obra:
        flash("Obra não encontrada.", "erro")
        return redirect(url_for("obras_bp.obras"))

    custos = query_all("SELECT * FROM custos WHERE obra_id = ? ORDER BY id DESC", (obra["id"],))
    medicoes = query_all("SELECT * FROM medicoes WHERE obra_id = ? ORDER BY id DESC", (obra["id"],))
    equipe = query_all("SELECT * FROM equipe WHERE obra_id = ? ORDER BY id DESC", (obra["id"],))
    compras = query_all("SELECT * FROM compras WHERE obra_id = ? ORDER BY id DESC", (obra["id"],))
    custos_importados = query_all(
        "SELECT * FROM custos_importados_categoria WHERE obra_id = ? ORDER BY categoria ASC",
        (obra["id"],)
    )

    custo_total = sum((c["valor_total"] or 0) for c in custos)
    margem = (obra["receita_total"] or 0) - custo_total

    return render_template(
        "obra_detalhe.html",
        obra=obra,
        custos=custos,
        medicoes=medicoes,
        equipe=equipe,
        compras=compras,
        custos_importados=custos_importados,
        custo_total=custo_total,
        margem=margem
    )


@obras_bp.route("/obras/editar/<int:obra_id>", methods=["POST"])
def editar_obra(obra_id):
    if not usuario_logado():
        return redirect(url_for("auth_bp.login"))

    nome = request.form.get("nome", "").strip()
    endereco = request.form.get("endereco", "").strip()
    tipologia = request.form.get("tipologia", "").strip()
    area_m2 = request.form.get("area_m2", "").strip()
    data_inicio = request.form.get("data_inicio", "").strip()
    data_fim_prevista = request.form.get("data_fim_prevista", "").strip()
    orcamento = request.form.get("orcamento", "").strip()
    receita_total = request.form.get("receita_total", "").strip()
    progresso_percentual = request.form.get("progresso_percentual", "").strip()
    status = request.form.get("status", "").strip()

    try:
        area_valor = float(area_m2) if area_m2 else 0
        orcamento_valor = parse_valor_monetario(orcamento)
        receita_valor = parse_valor_monetario(receita_total)
        progresso_valor = parse_valor_monetario(progresso_percentual)

        if valor_negativo(area_valor):
            raise ValueError("Área não pode ser negativa.")

        if valor_negativo(orcamento_valor):
            raise ValueError("Orçamento não pode ser negativo.")

        if valor_negativo(receita_valor):
            raise ValueError("Receita total não pode ser negativa.")

        validar_intervalo_percentual(progresso_valor, "Execução (%)")
    except ValueError as e:
        flash(str(e), "erro")
        return redirect(url_for("obras_bp.obras"))

    execute(
        """
        UPDATE obras
        SET nome = ?, endereco = ?, tipologia = ?, area_m2 = ?,
            data_inicio = ?, data_fim_prevista = ?, orcamento = ?,
            receita_total = ?, progresso_percentual = ?, status = ?
        WHERE id = ?
        """,
        (
            nome,
            endereco,
            tipologia,
            area_valor,
            data_inicio,
            data_fim_prevista,
            orcamento_valor,
            receita_valor,
            progresso_valor,
            status,
            obra_id
        )
    )

    flash("Obra atualizada com sucesso.", "sucesso")
    return redirect(url_for("obras_bp.obras"))


@obras_bp.route("/obras/excluir/<int:obra_id>", methods=["POST"])
def excluir_obra(obra_id):
    if not usuario_logado():
        return redirect(url_for("auth_bp.login"))

    execute("DELETE FROM custos WHERE obra_id = ?", (obra_id,))
    execute("DELETE FROM medicoes WHERE obra_id = ?", (obra_id,))
    execute("DELETE FROM equipe WHERE obra_id = ?", (obra_id,))
    execute("DELETE FROM compras WHERE obra_id = ?", (obra_id,))
    execute("DELETE FROM custos_importados_categoria WHERE obra_id = ?", (obra_id,))
    execute("DELETE FROM obras WHERE id = ?", (obra_id,))

    flash("Obra excluída com sucesso.", "sucesso")
    return redirect(url_for("obras_bp.obras"))