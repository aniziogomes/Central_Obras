import pandas as pd
from io import BytesIO
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, jsonify
from database import query_all, execute
from services.validators import (
    parse_valor_monetario,
    valor_negativo,
    validar_categoria_custo,
    caminho_redirecionamento_seguro,
    limpar_texto,
    parse_int_positivo,
    CATEGORIAS_CUSTO_VALIDAS
)
from auth import usuario_logado, eh_admin, eh_gestor, eh_leitura
from services.log_service import registrar_log
from services.tenant import aplicar_filtro_empresa, listar_obras_acessiveis, obter_obra_acessivel, obter_registro_acessivel
from utils import formatar_moeda, formatar_data

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
        {"slug": "material", "titulo": "Material", "cor": "pu", "valor": 0, "quantidade": 0},
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
        "filtro_categoria": request.args.get("categoria", "").strip(),
        "data_inicio": request.args.get("data_inicio", "").strip(),
        "data_fim": request.args.get("data_fim", "").strip(),
    }


def montar_query_custos(filtro_obra, data_inicio, data_fim, filtro_categoria=""):
    clausulas = []
    params = []
    aplicar_filtro_empresa(clausulas, params, "o")

    if filtro_obra:
        clausulas.append("o.codigo = ?")
        params.append(filtro_obra)

    if filtro_categoria:
        clausulas.append("c.categoria = ?")
        params.append(filtro_categoria)

    if data_inicio:
        clausulas.append("(c.data_lancamento IS NOT NULL AND c.data_lancamento >= ?)")
        params.append(data_inicio)

    if data_fim:
        clausulas.append("(c.data_lancamento IS NOT NULL AND c.data_lancamento <= ?)")
        params.append(data_fim)

    where = ("WHERE " + " AND ".join(clausulas)) if clausulas else ""
    return where, tuple(params)


def buscar_custos_filtrados(filtro_obra="", data_inicio="", data_fim="", filtro_categoria=""):
    where, params = montar_query_custos(filtro_obra, data_inicio, data_fim, filtro_categoria)

    return query_all(f"""
        SELECT c.*, o.codigo AS codigo_obra, o.nome AS nome_obra
        FROM custos c
        JOIN obras o ON c.obra_id = o.id
        {where}
        ORDER BY c.id DESC
    """, params)


def buscar_obras_com_custos(data_inicio="", data_fim="", filtro_categoria="", filtro_obra=""):
    where, params = montar_query_custos("", data_inicio, data_fim, filtro_categoria)

    obras = query_all(f"""
        SELECT DISTINCT o.*
        FROM obras o
        JOIN custos c ON c.obra_id = o.id
        {where}
        ORDER BY o.nome ASC
    """, params)

    if filtro_obra and not any(obra["codigo"] == filtro_obra for obra in obras):
        obra_atual = obter_obra_acessivel(codigo=filtro_obra)
        if obra_atual:
            obras = [obra_atual] + list(obras)

    return obras


def normalizar_status_entrega(status):
    mapa = {
        "pedido": "Aguardando",
        "aguardando": "Aguardando",
        "entregue": "Entregue no Prazo",
        "entregue no prazo": "Entregue no Prazo",
        "entregue com atraso": "Entregue com Atraso",
        "cancelado": "Cancelado",
    }
    chave = (status or "").strip().lower()
    return mapa.get(chave, (status or "").strip())


def calcular_valores_custo(valor_total, quantidade, valor_unitario):
    valor_total_float = parse_valor_monetario(valor_total)
    quantidade_float = parse_valor_monetario(quantidade)
    valor_unitario_float = parse_valor_monetario(valor_unitario)

    if not valor_total and quantidade_float and valor_unitario_float:
        valor_total_float = quantidade_float * valor_unitario_float

    return valor_total_float, quantidade_float, valor_unitario_float


@custos_bp.route("/custos")
def custos():
    if not usuario_logado() or not eh_leitura():
        return redirect(url_for("auth_bp.login"))

    filtros = obter_filtros_custos()

    lista_custos = buscar_custos_filtrados(
        filtro_obra=filtros["filtro_obra"],
        filtro_categoria=filtros["filtro_categoria"],
        data_inicio=filtros["data_inicio"],
        data_fim=filtros["data_fim"]
    )

    todas_obras = buscar_obras_com_custos(
        filtro_categoria=filtros["filtro_categoria"],
        data_inicio=filtros["data_inicio"],
        data_fim=filtros["data_fim"],
        filtro_obra=filtros["filtro_obra"],
    )
    obras = listar_obras_acessiveis(order_by="o.nome ASC", campos="o.*")
    cards_categorias = gerar_cards_categorias(lista_custos)

    return render_template(
        "custos.html",
        custos=lista_custos,
        obras=obras,
        todas_obras=todas_obras,
        categorias_custo=CATEGORIAS_CUSTO_VALIDAS,
        cards_categorias=cards_categorias,
        filtro_obra=filtros["filtro_obra"],
        filtro_categoria=filtros["filtro_categoria"],
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
        filtro_categoria=filtros["filtro_categoria"],
        data_inicio=filtros["data_inicio"],
        data_fim=filtros["data_fim"]
    )

    cards = gerar_cards_categorias(lista)

    return jsonify({
        "filtros": {
            "obra": filtros["filtro_obra"],
            "categoria": filtros["filtro_categoria"],
            "data_inicio": filtros["data_inicio"],
            "data_fim": filtros["data_fim"],
            "data_inicio_formatada": formatar_data(filtros["data_inicio"], ""),
            "data_fim_formatada": formatar_data(filtros["data_fim"], ""),
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
                "data_lancamento_formatada": formatar_data(c["data_lancamento"]),
                "quantidade": c["quantidade"] or 0,
                "valor_unitario": c["valor_unitario"] or 0,
                "status_entrega": c["status_entrega"] or "",
                "data_entrega_prevista": c["data_entrega_prevista"] or "",
                "data_entrega_prevista_formatada": formatar_data(c["data_entrega_prevista"], ""),
                "data_entrega_realizada": c["data_entrega_realizada"] or "",
                "data_entrega_realizada_formatada": formatar_data(c["data_entrega_realizada"], ""),
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
    redirect_to = caminho_redirecionamento_seguro(request.form.get("redirect_to"), url_for("custos_bp.custos"))
    if not usuario_logado() or not eh_gestor():
        flash("Você não tem permissão para cadastrar custos.", "erro")
        return redirect(redirect_to)

    obra_id = request.form.get("obra_id", "").strip()
    try:
        descricao = limpar_texto(request.form.get("descricao", ""), max_len=180, obrigatorio=True, campo="Descricao")
        categoria = limpar_texto(request.form.get("categoria", ""), max_len=60, obrigatorio=True, campo="Categoria")
        fornecedor = limpar_texto(request.form.get("fornecedor", ""), max_len=140)
        data_lancamento = limpar_texto(request.form.get("data_lancamento", ""), max_len=10)
        status_entrega = normalizar_status_entrega(limpar_texto(request.form.get("status_entrega", ""), max_len=60))
        data_entrega_prevista = limpar_texto(request.form.get("data_entrega_prevista", ""), max_len=10)
        data_entrega_realizada = limpar_texto(request.form.get("data_entrega_realizada", ""), max_len=10)
        nota_fiscal = limpar_texto(request.form.get("nota_fiscal", ""), max_len=80)
        observacao = limpar_texto(request.form.get("observacao", ""), max_len=1000)
    except ValueError as e:
        flash(str(e), "erro")
        return redirect(redirect_to)
    valor_total = request.form.get("valor_total", "").strip()
    quantidade = request.form.get("quantidade", "").strip()
    valor_unitario = request.form.get("valor_unitario", "").strip()

    if not obra_id or not descricao or not categoria:
        flash("Preencha os campos obrigatórios do custo.", "erro")
        return redirect(redirect_to)

    try:
        obra_id_int = parse_int_positivo(obra_id, "Obra")
        validar_categoria_custo(categoria)
        valor_total_float, quantidade_float, valor_unitario_float = calcular_valores_custo(valor_total, quantidade, valor_unitario)
        obra = obter_obra_acessivel(obra_id=obra_id_int, campos="o.id, o.empresa_id")
        if not obra:
            raise ValueError("Obra nao encontrada para este usuario.")
        if valor_negativo(valor_total_float):
            raise ValueError("Valor do custo não pode ser negativo.")
        if valor_negativo(quantidade_float):
            raise ValueError("Quantidade nao pode ser negativa.")
        if valor_negativo(valor_unitario_float):
            raise ValueError("Valor unitario nao pode ser negativo.")
        if valor_total_float <= 0:
            raise ValueError("Informe o valor total ou quantidade e valor unitario.")
    except ValueError as e:
        flash(str(e), "erro")
        return redirect(redirect_to)

    custo_id = execute(
        """
        INSERT INTO custos (
            empresa_id, obra_id, descricao, categoria, fornecedor,
            data_lancamento, valor_total, quantidade, valor_unitario,
            status_entrega, data_entrega_prevista, data_entrega_realizada,
            nota_fiscal, observacao
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            obra["empresa_id"],
            obra_id_int,
            descricao,
            categoria,
            fornecedor,
            data_lancamento,
            valor_total_float,
            quantidade_float,
            valor_unitario_float,
            status_entrega,
            data_entrega_prevista,
            data_entrega_realizada,
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

    custo_atual = obter_registro_acessivel("custos", custo_id, campos="id")
    if not custo_atual:
        flash("Custo nao encontrado.", "erro")
        return redirect(url_for("custos_bp.custos"))

    try:
        descricao = limpar_texto(request.form.get("descricao", ""), max_len=180, obrigatorio=True, campo="Descricao")
        categoria = limpar_texto(request.form.get("categoria", ""), max_len=60, obrigatorio=True, campo="Categoria")
        fornecedor = limpar_texto(request.form.get("fornecedor", ""), max_len=140)
        data_lancamento = limpar_texto(request.form.get("data_lancamento", ""), max_len=10)
        status_entrega = normalizar_status_entrega(limpar_texto(request.form.get("status_entrega", ""), max_len=60))
        data_entrega_prevista = limpar_texto(request.form.get("data_entrega_prevista", ""), max_len=10)
        data_entrega_realizada = limpar_texto(request.form.get("data_entrega_realizada", ""), max_len=10)
        nota_fiscal = limpar_texto(request.form.get("nota_fiscal", ""), max_len=80)
        observacao = limpar_texto(request.form.get("observacao", ""), max_len=1000)
    except ValueError as e:
        flash(str(e), "erro")
        return redirect(url_for("custos_bp.custos"))
    valor_total = request.form.get("valor_total", "").strip()
    quantidade = request.form.get("quantidade", "").strip()
    valor_unitario = request.form.get("valor_unitario", "").strip()

    try:
        validar_categoria_custo(categoria)
        valor_total_float, quantidade_float, valor_unitario_float = calcular_valores_custo(valor_total, quantidade, valor_unitario)
        if valor_negativo(valor_total_float):
            raise ValueError("Valor do custo não pode ser negativo.")
        if valor_negativo(quantidade_float):
            raise ValueError("Quantidade nao pode ser negativa.")
        if valor_negativo(valor_unitario_float):
            raise ValueError("Valor unitario nao pode ser negativo.")
        if valor_total_float <= 0:
            raise ValueError("Informe o valor total ou quantidade e valor unitario.")
    except ValueError as e:
        flash(str(e), "erro")
        return redirect(url_for("custos_bp.custos"))

    execute(
        """
        UPDATE custos
        SET descricao = ?, categoria = ?, fornecedor = ?,
            data_lancamento = ?, valor_total = ?, quantidade = ?, valor_unitario = ?,
            status_entrega = ?, data_entrega_prevista = ?, data_entrega_realizada = ?,
            nota_fiscal = ?, observacao = ?
        WHERE id = ?
        """,
        (
            descricao,
            categoria,
            fornecedor,
            data_lancamento,
            valor_total_float,
            quantidade_float,
            valor_unitario_float,
            status_entrega,
            data_entrega_prevista,
            data_entrega_realizada,
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

    custo = obter_registro_acessivel("custos", custo_id)
    if not custo:
        flash("Custo nao encontrado.", "erro")
        return redirect(url_for("custos_bp.custos"))
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
        filtro_categoria=filtros["filtro_categoria"],
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
