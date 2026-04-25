import pandas as pd
from io import BytesIO
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, jsonify
from database import query_all, query_one, execute
from services.validators import (
    parse_valor_monetario,
    valor_negativo,
    validar_categoria_custo,
    CATEGORIAS_CUSTO_VALIDAS
)
from auth import usuario_logado, eh_admin, eh_gestor, eh_leitura
from services.log_service import registrar_log
from utils import formatar_moeda

custos_bp = Blueprint("custos_bp", __name__)


def normalizar_categoria_card(categoria):
    mapa = {
        "Material": "Material",
        "Mão de Obra": "Mão de Obra",
        "Equipamento": "Equipamento",
        "Projeto/Engenharia": "Projeto/Engenharia",
        "Taxas e Impostos": "Taxas e Impostos",
        "Outros": "Outros",
    }
    return mapa.get(categoria, "Outros")


def gerar_cards_categorias(lista_custos):
    cards_base = [
        {"slug": "mao-de-obra", "titulo": "Mão de Obra", "cor": "or", "valor": 0, "quantidade": 0},
        {"slug": "projeto-engenharia", "titulo": "Projeto/Engenharia", "cor": "bl", "valor": 0, "quantidade": 0},
        {"slug": "material", "titulo": "Material", "cor": "gr", "valor": 0, "quantidade": 0},
    ]

    indice = {card["titulo"]: card for card in cards_base}

    for custo in lista_custos:
        categoria = normalizar_categoria_card(custo["categoria"])
        if categoria in indice:
            indice[categoria]["valor"] += custo["valor_total"] or 0
            indice[categoria]["quantidade"] += 1

    return cards_base


def obter_filtros_custos():
    return {
        "filtro_obra": request.args.get("obra", "").strip(),
        "data_inicio": request.args.get("data_inicio", "").strip(),
        "data_fim": request.args.get("data_fim", "").strip(),
    }


def montar_query_custos(filtro_obra, data_inicio, data_fim):
    clausulas = []
    params = []

    if filtro_obra:
        clausulas.append("o.codigo = ?")
        params.append(filtro_obra)

    if data_inicio:
        clausulas.append("(c.data_lancamento IS NOT NULL AND c.data_lancamento >= ?)")
        params.append(data_inicio)

    if data_fim:
        clausulas.append("(c.data_lancamento IS NOT NULL AND c.data_lancamento <= ?)")
        params.append(data_fim)

    where = ("WHERE " + " AND ".join(clausulas)) if clausulas else ""
    return where, tuple(params)


def buscar_custos_filtrados(filtro_obra="", data_inicio="", data_fim=""):
    where, params = montar_query_custos(filtro_obra, data_inicio, data_fim)

    return query_all(f"""
        SELECT c.*, o.codigo AS codigo_obra, o.nome AS nome_obra
        FROM custos c
        JOIN obras o ON c.obra_id = o.id
        {where}
        ORDER BY c.id DESC
    """, params)


@custos_bp.route("/custos")
def custos():
    if not usuario_logado() or not eh_leitura():
        return redirect(url_for("auth_bp.login"))

    filtros = obter_filtros_custos()

    lista_custos = buscar_custos_filtrados(
        filtro_obra=filtros["filtro_obra"],
        data_inicio=filtros["data_inicio"],
        data_fim=filtros["data_fim"]
    )

    todas_obras = query_all("SELECT * FROM obras ORDER BY nome ASC")
    obras = query_all("SELECT * FROM obras ORDER BY nome ASC")
    cards_categorias = gerar_cards_categorias(lista_custos)

    return render_template(
        "custos.html",
        custos=lista_custos,
        obras=obras,
        todas_obras=todas_obras,
        categorias_custo=CATEGORIAS_CUSTO_VALIDAS,
        cards_categorias=cards_categorias,
        filtro_obra=filtros["filtro_obra"],
        data_inicio=filtros["data_inicio"],
        data_fim=filtros["data_fim"],
    )


@custos_bp.route("/custos/dados")
def custos_dados():
    if not usuario_logado() or not eh_leitura():
        return jsonify({"erro": "não autorizado"}), 401

    filtros = obter_filtros_custos()

    lista = buscar_custos_filtrados(
        filtro_obra=filtros["filtro_obra"],
        data_inicio=filtros["data_inicio"],
        data_fim=filtros["data_fim"]
    )

    cards = gerar_cards_categorias(lista)

    return jsonify({
        "filtros": {
            "obra": filtros["filtro_obra"],
            "data_inicio": filtros["data_inicio"],
            "data_fim": filtros["data_fim"],
        },
        "total": len(lista),
        "cards": [
            {
                "titulo": c["titulo"],
                "cor": c["cor"],
                "valor": c["valor"],
                "valor_formatado": formatar_moeda(c["valor"]),
                "quantidade": c["quantidade"],
            }
            for c in cards
        ],
        "custos": [
            {
                "id": c["id"],
                "codigo_obra": c["codigo_obra"] or "",
                "nome_obra": c["nome_obra"] or "",
                "descricao": c["descricao"] or "",
                "categoria": c["categoria"] or "",
                "fornecedor": c["fornecedor"] or "-",
                "data_lancamento": c["data_lancamento"] or "-",
                "valor_total": c["valor_total"] or 0,
                "valor_formatado": formatar_moeda(c["valor_total"] or 0),
                "nota_fiscal": c["nota_fiscal"] or "-",
            }
            for c in lista
        ],
        "pode_editar": eh_gestor(),
        "pode_excluir": eh_admin(),
    })


@custos_bp.route("/custos/novo", methods=["POST"])
def novo_custo():
    redirect_to = request.form.get("redirect_to") or url_for("custos_bp.custos")
    if not usuario_logado() or not eh_gestor():
        flash("Você não tem permissão para cadastrar custos.", "erro")
        return redirect(redirect_to)

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
        return redirect(redirect_to)

    try:
        validar_categoria_custo(categoria)
        valor_total_float = parse_valor_monetario(valor_total)
        if valor_negativo(valor_total_float):
            raise ValueError("Valor do custo não pode ser negativo.")
    except ValueError as e:
        flash(str(e), "erro")
        return redirect(redirect_to)

    custo_id = execute(
        """
        INSERT INTO custos (
            obra_id, descricao, categoria, fornecedor,
            data_lancamento, valor_total, nota_fiscal, observacao
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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
    return redirect(redirect_to)


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
        validar_categoria_custo(categoria)
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

    filtros = obter_filtros_custos()

    lista = buscar_custos_filtrados(
        filtro_obra=filtros["filtro_obra"],
        data_inicio=filtros["data_inicio"],
        data_fim=filtros["data_fim"]
    )

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
