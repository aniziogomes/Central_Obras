import pandas as pd
from io import BytesIO
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file
from database import query_all, execute
from services.validators import (
    caminho_redirecionamento_seguro,
    limpar_texto,
    parse_int_positivo,
    parse_valor_monetario,
    valor_negativo,
    validar_intervalo_percentual,
)
from auth import usuario_logado, eh_gestor, pode_visualizar
from services.log_service import registrar_log
from services.tenant import and_empresa, listar_obras_acessiveis, obter_obra_acessivel, obter_registro_acessivel

medicoes_bp = Blueprint("medicoes_bp", __name__)


@medicoes_bp.route("/medicoes")
def medicoes():
    if not usuario_logado() or not pode_visualizar():
        return redirect(url_for("auth_bp.login"))

    filtro_empresa, params_empresa = and_empresa("o")
    lista_medicoes = query_all(f"""
        SELECT m.*, o.codigo AS codigo_obra, o.nome AS nome_obra
        FROM medicoes m
        JOIN obras o ON m.obra_id = o.id
        WHERE 1 = 1 {filtro_empresa}
        ORDER BY m.id DESC
    """, params_empresa)

    obras = listar_obras_acessiveis(order_by="o.nome ASC", campos="o.*")
    return render_template("medicoes.html", medicoes=lista_medicoes, obras=obras)


@medicoes_bp.route("/medicoes/nova", methods=["POST"])
def nova_medicao():
    redirect_to = caminho_redirecionamento_seguro(request.form.get("redirect_to"), url_for("medicoes_bp.medicoes"))
    if not usuario_logado() or not eh_gestor():
        flash("Você não tem permissão para cadastrar medições.", "erro")
        return redirect(redirect_to)

    obra_id = request.form.get("obra_id", "").strip()
    try:
        mes = limpar_texto(request.form.get("mes", ""), max_len=20)
        medicao_nome = limpar_texto(request.form.get("medicao_nome", ""), max_len=120, obrigatorio=True, campo="Medicao")
        etapa = limpar_texto(request.form.get("etapa", ""), max_len=120, obrigatorio=True, campo="Etapa")
        data_medicao = limpar_texto(request.form.get("data_medicao", ""), max_len=10)
        observacao = limpar_texto(request.form.get("observacao", ""), max_len=1000)
    except ValueError as e:
        flash(str(e), "erro")
        return redirect(redirect_to)
    percentual = request.form.get("percentual", "").strip()
    percentual_acumulado = request.form.get("percentual_acumulado", "").strip()
    valor_realizado = request.form.get("valor_realizado", "").strip()

    if not obra_id or not medicao_nome or not etapa:
        flash("Preencha os campos obrigatórios da medição.", "erro")
        return redirect(redirect_to)

    try:
        percentual_float = parse_valor_monetario(percentual)
        percentual_acumulado_float = parse_valor_monetario(percentual_acumulado)
        valor_realizado_float = parse_valor_monetario(valor_realizado)
        obra_id_int = parse_int_positivo(obra_id, "Obra")
        obra = obter_obra_acessivel(obra_id=obra_id_int, campos="o.id, o.empresa_id")
        if not obra:
            raise ValueError("Obra nao encontrada para este usuario.")

        validar_intervalo_percentual(percentual_float, "Percentual")
        validar_intervalo_percentual(percentual_acumulado_float, "Percentual acumulado")

        if valor_negativo(valor_realizado_float):
            raise ValueError("Valor realizado não pode ser negativo.")
    except ValueError as e:
        flash(str(e), "erro")
        return redirect(redirect_to)

    medicao_id = execute(
        """
        INSERT INTO medicoes (
            empresa_id, obra_id, mes, medicao_nome, etapa, percentual,
            percentual_acumulado, valor_realizado, data_medicao, observacao
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            obra["empresa_id"],
            obra_id_int,
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
    return redirect(redirect_to)


@medicoes_bp.route("/medicoes/editar/<int:medicao_id>", methods=["POST"])
def editar_medicao(medicao_id):
    if not usuario_logado() or not eh_gestor():
        flash("Você não tem permissão para editar medições.", "erro")
        return redirect(url_for("medicoes_bp.medicoes"))

    medicao_atual = obter_registro_acessivel("medicoes", medicao_id, campos="id")
    if not medicao_atual:
        flash("Medicao nao encontrada.", "erro")
        return redirect(url_for("medicoes_bp.medicoes"))

    try:
        mes = limpar_texto(request.form.get("mes", ""), max_len=20)
        medicao_nome = limpar_texto(request.form.get("medicao_nome", ""), max_len=120, obrigatorio=True, campo="Medicao")
        etapa = limpar_texto(request.form.get("etapa", ""), max_len=120, obrigatorio=True, campo="Etapa")
        data_medicao = limpar_texto(request.form.get("data_medicao", ""), max_len=10)
        observacao = limpar_texto(request.form.get("observacao", ""), max_len=1000)
    except ValueError as e:
        flash(str(e), "erro")
        return redirect(url_for("medicoes_bp.medicoes"))
    percentual = request.form.get("percentual", "").strip()
    percentual_acumulado = request.form.get("percentual_acumulado", "").strip()
    valor_realizado = request.form.get("valor_realizado", "").strip()

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
    if not usuario_logado() or not eh_gestor():
        flash("Você não tem permissão para excluir medições.", "erro")
        return redirect(url_for("medicoes_bp.medicoes"))

    medicao = obter_registro_acessivel("medicoes", medicao_id)
    if not medicao:
        flash("Medicao nao encontrada.", "erro")
        return redirect(url_for("medicoes_bp.medicoes"))
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
    if not usuario_logado() or not pode_visualizar():
        return redirect(url_for("auth_bp.login"))

    filtro_empresa, params_empresa = and_empresa("o")
    lista = query_all(f"""
        SELECT m.*, o.codigo AS codigo_obra, o.nome AS nome_obra
        FROM medicoes m
        JOIN obras o ON m.obra_id = o.id
        WHERE 1 = 1 {filtro_empresa}
        ORDER BY m.id DESC
    """, params_empresa)

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
