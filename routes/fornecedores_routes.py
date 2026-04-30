import pandas as pd
from io import BytesIO
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file
from database import query_one, query_all, execute
from services.validators import limpar_texto, parse_int_nao_negativo, validar_nota
from auth import usuario_logado, eh_gestor, eh_leitura
from services.log_service import registrar_log
from services.tenant import empresa_id_para_insert, obter_registro_acessivel, where_empresa

fornecedores_bp = Blueprint("fornecedores_bp", __name__)


@fornecedores_bp.route("/fornecedores")
def fornecedores():
    if not usuario_logado() or not eh_leitura():
        return redirect(url_for("auth_bp.login"))

    where, params = where_empresa()
    lista_fornecedores = query_all(f"SELECT * FROM fornecedores {where} ORDER BY id DESC", params)
    return render_template("fornecedores.html", fornecedores=lista_fornecedores)


@fornecedores_bp.route("/fornecedores/novo", methods=["POST"])
def novo_fornecedor():
    if not usuario_logado() or not eh_gestor():
        flash("Você não tem permissão para cadastrar fornecedores.", "erro")
        return redirect(url_for("fornecedores_bp.fornecedores"))

    try:
        codigo = limpar_texto(request.form.get("codigo", ""), max_len=40, obrigatorio=True, campo="Codigo")
        nome = limpar_texto(request.form.get("nome", ""), max_len=160, obrigatorio=True, campo="Nome")
        categoria = limpar_texto(request.form.get("categoria", ""), max_len=80, obrigatorio=True, campo="Categoria")
        contato = limpar_texto(request.form.get("contato", ""), max_len=120)
        documento = limpar_texto(request.form.get("documento", ""), max_len=80)
        observacao = limpar_texto(request.form.get("observacao", ""), max_len=1000)
    except ValueError as e:
        flash(str(e), "erro")
        return redirect(url_for("fornecedores_bp.fornecedores"))
    prazo_medio = request.form.get("prazo_medio", "").strip()
    nota_qualidade = request.form.get("nota_qualidade", "").strip()
    nota_preco = request.form.get("nota_preco", "").strip()
    nota_prazo = request.form.get("nota_prazo", "").strip()

    if not codigo or not nome or not categoria:
        flash("Preencha os campos obrigatórios do fornecedor.", "erro")
        return redirect(url_for("fornecedores_bp.fornecedores"))

    existe = query_one("SELECT * FROM fornecedores WHERE codigo = ?", (codigo,))
    if existe:
        flash("Já existe um fornecedor com esse código.", "erro")
        return redirect(url_for("fornecedores_bp.fornecedores"))

    try:
        prazo_medio_int = parse_int_nao_negativo(prazo_medio, "Prazo medio") if prazo_medio else 0
        nota_qualidade_float = validar_nota(nota_qualidade, "Nota de qualidade")
        nota_preco_float = validar_nota(nota_preco, "Nota de preco")
        nota_prazo_float = validar_nota(nota_prazo, "Nota de prazo")
    except ValueError as e:
        flash(str(e), "erro")
        return redirect(url_for("fornecedores_bp.fornecedores"))

    empresa_id = empresa_id_para_insert()
    fornecedor_id = execute(
        """
        INSERT INTO fornecedores (
            empresa_id, codigo, nome, categoria, contato, documento,
            prazo_medio, nota_qualidade, nota_preco,
            nota_prazo, observacao
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            empresa_id,
            codigo,
            nome,
            categoria,
            contato,
            documento,
            prazo_medio_int,
            nota_qualidade_float,
            nota_preco_float,
            nota_prazo_float,
            observacao
        )
    )

    registrar_log(
        acao="criação",
        entidade="fornecedor",
        entidade_id=fornecedor_id,
        descricao=f"Fornecedor criado: {nome}"
    )

    flash("Fornecedor cadastrado com sucesso.", "sucesso")
    return redirect(url_for("fornecedores_bp.fornecedores"))


@fornecedores_bp.route("/fornecedores/editar/<int:fornecedor_id>", methods=["POST"])
def editar_fornecedor(fornecedor_id):
    if not usuario_logado() or not eh_gestor():
        flash("Você não tem permissão para editar fornecedores.", "erro")
        return redirect(url_for("fornecedores_bp.fornecedores"))

    fornecedor_atual = obter_registro_acessivel("fornecedores", fornecedor_id, campos="id")
    if not fornecedor_atual:
        flash("Fornecedor nao encontrado.", "erro")
        return redirect(url_for("fornecedores_bp.fornecedores"))

    try:
        nome = limpar_texto(request.form.get("nome", ""), max_len=160, obrigatorio=True, campo="Nome")
        categoria = limpar_texto(request.form.get("categoria", ""), max_len=80, obrigatorio=True, campo="Categoria")
        contato = limpar_texto(request.form.get("contato", ""), max_len=120)
        documento = limpar_texto(request.form.get("documento", ""), max_len=80)
        observacao = limpar_texto(request.form.get("observacao", ""), max_len=1000)
    except ValueError as e:
        flash(str(e), "erro")
        return redirect(url_for("fornecedores_bp.fornecedores"))
    prazo_medio = request.form.get("prazo_medio", "").strip()
    nota_qualidade = request.form.get("nota_qualidade", "").strip()
    nota_preco = request.form.get("nota_preco", "").strip()
    nota_prazo = request.form.get("nota_prazo", "").strip()

    try:
        prazo_medio_int = parse_int_nao_negativo(prazo_medio, "Prazo medio") if prazo_medio else 0
        nota_qualidade_float = validar_nota(nota_qualidade, "Nota de qualidade")
        nota_preco_float = validar_nota(nota_preco, "Nota de preco")
        nota_prazo_float = validar_nota(nota_prazo, "Nota de prazo")
    except ValueError as e:
        flash(str(e), "erro")
        return redirect(url_for("fornecedores_bp.fornecedores"))

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
            prazo_medio_int,
            nota_qualidade_float,
            nota_preco_float,
            nota_prazo_float,
            observacao,
            fornecedor_id
        )
    )

    registrar_log(
        acao="edição",
        entidade="fornecedor",
        entidade_id=fornecedor_id,
        descricao=f"Fornecedor editado: {nome}"
    )

    flash("Fornecedor atualizado com sucesso.", "sucesso")
    return redirect(url_for("fornecedores_bp.fornecedores"))


@fornecedores_bp.route("/fornecedores/excluir/<int:fornecedor_id>", methods=["POST"])
def excluir_fornecedor(fornecedor_id):
    if not usuario_logado() or not eh_gestor():
        flash("Você não tem permissão para excluir fornecedores.", "erro")
        return redirect(url_for("fornecedores_bp.fornecedores"))

    fornecedor = obter_registro_acessivel("fornecedores", fornecedor_id)
    if not fornecedor:
        flash("Fornecedor nao encontrado.", "erro")
        return redirect(url_for("fornecedores_bp.fornecedores"))
    nome_fornecedor = fornecedor["nome"] if fornecedor else f"ID {fornecedor_id}"

    execute("DELETE FROM fornecedores WHERE id = ?", (fornecedor_id,))

    registrar_log(
        acao="exclusão",
        entidade="fornecedor",
        entidade_id=fornecedor_id,
        descricao=f"Fornecedor excluído: {nome_fornecedor}"
    )

    flash("Fornecedor excluído com sucesso.", "sucesso")
    return redirect(url_for("fornecedores_bp.fornecedores"))


@fornecedores_bp.route("/fornecedores/exportar")
def fornecedores_exportar():
    if not usuario_logado() or not eh_leitura():
        return redirect(url_for("auth_bp.login"))

    where, params = where_empresa()
    lista = query_all(f"SELECT * FROM fornecedores {where} ORDER BY id DESC", params)

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
