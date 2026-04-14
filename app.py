import pandas as pd
from io import BytesIO
from flask import send_file
from datetime import datetime
import os
from importar_planilha import importar_planilha
from flask import Flask, render_template, request, redirect, url_for, session, flash
from database import init_db, query_one, query_all, execute
from auth import verificar_senha
from utils import formatar_moeda, calcular_media_fornecedor

app = Flask(__name__)
app.secret_key = "chave_super_secreta_trocar_depois"

init_db()


def usuario_logado():
    return "usuario_id" in session

def data_no_periodo(data_texto, data_inicio="", data_fim=""):
    """
    Verifica se uma data string YYYY-MM-DD está dentro do período.
    """
    if not data_texto:
        return True

    try:
        data_ref = datetime.strptime(data_texto, "%Y-%m-%d").date()
    except:
        return True

    if data_inicio:
        try:
            inicio = datetime.strptime(data_inicio, "%Y-%m-%d").date()
            if data_ref < inicio:
                return False
        except:
            pass

    if data_fim:
        try:
            fim = datetime.strptime(data_fim, "%Y-%m-%d").date()
            if data_ref > fim:
                return False
        except:
            pass

    return True

def parse_valor_monetario(valor_texto):
    """
    Converte textos como:
    410000
    410.000
    410.000,50
    410000,50
    410000.50

    para float.
    """
    if valor_texto is None:
        return 0.0

    valor = str(valor_texto).strip()

    if not valor:
        return 0.0

    valor = valor.replace("R$", "").replace(" ", "")

    # Caso tenha . e , assume padrão BR: 410.000,50
    if "." in valor and "," in valor:
        valor = valor.replace(".", "").replace(",", ".")
    # Caso só tenha vírgula: 410000,50
    elif "," in valor:
        valor = valor.replace(",", ".")
    # Caso só tenha ponto, deixamos como está

    return float(valor)


def valor_negativo(valor):
    return valor < 0


def validar_intervalo_percentual(valor, campo="Percentual"):
    if valor < 0 or valor > 100:
        raise ValueError(f"{campo} deve ficar entre 0 e 100.")

def calcular_alertas(obra_ids_filtradas=None):
    obras = query_all("SELECT * FROM obras")
    equipe = query_all("SELECT * FROM equipe")

    if obra_ids_filtradas:
        obras = [o for o in obras if o["id"] in obra_ids_filtradas]

    alertas = []
    alertas_keys = set()
    hoje = datetime.today().date()

    def adicionar_alerta(tipo, codigo, nome, mensagem):
        chave = (tipo, codigo, nome, mensagem)
        if chave not in alertas_keys:
            alertas_keys.add(chave)
            alertas.append({
                "tipo": tipo,
                "codigo": codigo,
                "nome": nome,
                "mensagem": mensagem
            })

    for obra in obras:
        custo_obra = query_one(
            "SELECT COALESCE(SUM(valor_total), 0) AS total FROM custos WHERE obra_id = ?",
            (obra["id"],)
        )
        custo_total = custo_obra["total"] if custo_obra else 0
        receita = obra["receita_total"] or 0
        orcamento = obra["orcamento"] or 0
        progresso = obra["progresso_percentual"] or 0
        status = (obra["status"] or "").lower()

        if receita > 0 and custo_total > receita:
            adicionar_alerta(
                "danger",
                obra["codigo"],
                obra["nome"],
                "Margem negativa. O custo já superou a receita da obra."
            )

        if orcamento > 0 and custo_total > orcamento * 1.05:
            adicionar_alerta(
                "warn",
                obra["codigo"],
                obra["nome"],
                "Custo realizado acima do orçamento previsto."
            )

        if receita > 0 and custo_total >= receita * 0.90:
            adicionar_alerta(
                "warn",
                obra["codigo"],
                obra["nome"],
                "Custo já consumiu 90% ou mais da receita prevista."
            )

        if status == "atrasada":
            adicionar_alerta(
                "danger",
                obra["codigo"],
                obra["nome"],
                "Obra marcada como atrasada. Verifique cronograma."
            )

        if status == "andamento" and progresso == 0:
            adicionar_alerta(
                "warn",
                obra["codigo"],
                obra["nome"],
                "Obra em andamento, mas com execução física zerada."
            )

        data_fim_prevista = obra["data_fim_prevista"]
        if data_fim_prevista and status not in ["concluida", "vendida"]:
            try:
                data_final = datetime.strptime(data_fim_prevista, "%Y-%m-%d").date()
                dias_restantes = (data_final - hoje).days

                if 0 <= dias_restantes <= 7:
                    adicionar_alerta(
                        "warn",
                        obra["codigo"],
                        obra["nome"],
                        f"Obra próxima do prazo final. Restam {dias_restantes} dia(s)."
                    )

                if dias_restantes < 0:
                    adicionar_alerta(
                        "danger",
                        obra["codigo"],
                        obra["nome"],
                        "Data final prevista já foi ultrapassada."
                    )
            except:
                pass

    if obra_ids_filtradas:
        equipe = [p for p in equipe if p["obra_id"] in obra_ids_filtradas]

    for profissional in equipe:
        if (profissional["status_pagamento"] or "").lower() == "pendente":
            adicionar_alerta(
                "warn",
                "EQUIPE",
                profissional["nome"],
                f"Pagamento pendente para {profissional['nome']}."
            )

    return alertas


def calcular_kpis_dashboard(filtro_obra="", filtro_categoria="", filtro_status="", data_inicio="", data_fim=""):
    obras = query_all("SELECT * FROM obras ORDER BY id DESC")
    custos = query_all("SELECT * FROM custos ORDER BY id DESC")
    fornecedores = query_all("SELECT * FROM fornecedores ORDER BY id DESC")
    medicoes = query_all("SELECT * FROM medicoes ORDER BY id DESC")
    custos_importados = query_all("SELECT * FROM custos_importados_categoria ORDER BY id DESC")

    # ----------------------------------------
    # FILTRAR OBRAS
    # ----------------------------------------
    if filtro_obra:
        obras = [o for o in obras if o["codigo"] == filtro_obra]

    if filtro_status:
        obras = [o for o in obras if (o["status"] or "") == filtro_status]

    obra_ids_filtradas = [o["id"] for o in obras]

    # ----------------------------------------
    # FILTRAR CUSTOS
    # ----------------------------------------
    custos = [c for c in custos if c["obra_id"] in obra_ids_filtradas] if obra_ids_filtradas else []

    if filtro_categoria:
        custos = [c for c in custos if (c["categoria"] or "") == filtro_categoria]

    custos = [
    c for c in custos
    if data_no_periodo(c["data_lancamento"] if c["data_lancamento"] else "", data_inicio, data_fim)]
    
    # ----------------------------------------
    # FILTRAR MEDIÇÕES
    # ----------------------------------------
    medicoes = [m for m in medicoes if m["obra_id"] in obra_ids_filtradas] if obra_ids_filtradas else []

    medicoes = [
    m for m in medicoes
    if data_no_periodo(m["data_medicao"] if m["data_medicao"] else "", data_inicio, data_fim)]
    # ----------------------------------------
    # FILTRAR CUSTOS IMPORTADOS
    # ----------------------------------------
    custos_importados = [ci for ci in custos_importados if ci["obra_id"] in obra_ids_filtradas] if obra_ids_filtradas else []

    if filtro_categoria:
        custos_importados = [ci for ci in custos_importados if (ci["categoria"] or "") == filtro_categoria]

    total_receita = sum((obra["receita_total"] or 0) for obra in obras)
    total_custo = 0

    custos_por_categoria = {}
    custos_importados_por_categoria = {}
    comparativo_categorias = []
    margem_por_obra = []
    tipologia_count = {}

    # ----------------------------------------
    # Custos lançados
    # ----------------------------------------
    for custo in custos:
        cat = custo["categoria"] or "Sem categoria"
        valor = custo["valor_total"] or 0
        custos_por_categoria[cat] = custos_por_categoria.get(cat, 0) + valor

    # ----------------------------------------
    # Custos importados
    # ----------------------------------------
    for item in custos_importados:
        cat = item["categoria"] or "Sem categoria"
        valor = item["valor_total"] or 0
        custos_importados_por_categoria[cat] = custos_importados_por_categoria.get(cat, 0) + valor

    todas_categorias = sorted(set(list(custos_por_categoria.keys()) + list(custos_importados_por_categoria.keys())))

    for categoria in todas_categorias:
        valor_importado = custos_importados_por_categoria.get(categoria, 0)
        valor_lancado = custos_por_categoria.get(categoria, 0)
        diferenca = valor_lancado - valor_importado

        if valor_importado > 0:
            desvio_percentual = (diferenca / valor_importado) * 100
        else:
            desvio_percentual = 0

        comparativo_categorias.append({
            "categoria": categoria,
            "importado": valor_importado,
            "lancado": valor_lancado,
            "diferenca": diferenca,
            "desvio_percentual": desvio_percentual
        })

    # ----------------------------------------
    # Margem por obra
    # ----------------------------------------
    for obra in obras:
        custo_obra = sum((c["valor_total"] or 0) for c in custos if c["obra_id"] == obra["id"])
        total_custo += custo_obra

        margem_por_obra.append({
            "codigo": obra["codigo"],
            "nome": obra["nome"],
            "tipologia": obra["tipologia"],
            "status": obra["status"],
            "execucao": obra["progresso_percentual"] or 0,
            "margem_valor": (obra["receita_total"] or 0) - custo_obra
        })

        tipo = obra["tipologia"] or "Não informado"
        tipologia_count[tipo] = tipologia_count.get(tipo, 0) + 1

    margem = total_receita - total_custo
    obras_atrasadas = len([o for o in obras if o["status"] == "atrasada"])
    obras_ativas = len([o for o in obras if o["status"] == "andamento"])
    total_medicoes = len(medicoes)
    total_importado = sum(custos_importados_por_categoria.values())

    margem_percentual = (margem / total_receita * 100) if total_receita > 0 else 0
    custo_percentual_receita = (total_custo / total_receita * 100) if total_receita > 0 else 0
    execucao_media = (
        sum((obra["progresso_percentual"] or 0) for obra in obras) / len(obras)
        if obras else 0
    )

    ranking_fornecedores = []
    for f in fornecedores:
        media = calcular_media_fornecedor(
            f["nota_qualidade"],
            f["nota_preco"],
            f["nota_prazo"]
        )
        ranking_fornecedores.append({
            "codigo": f["codigo"],
            "nome": f["nome"],
            "categoria": f["categoria"],
            "media": media
        })

    ranking_fornecedores = sorted(
        ranking_fornecedores,
        key=lambda x: x["media"],
        reverse=True
    )[:5]

    alertas = calcular_alertas(obra_ids_filtradas)

    chart_comparativo_labels = [item["categoria"] for item in comparativo_categorias]
    chart_comparativo_importado = [item["importado"] for item in comparativo_categorias]
    chart_comparativo_lancado = [item["lancado"] for item in comparativo_categorias]

    chart_progresso_labels = [item["codigo"] for item in margem_por_obra]
    chart_progresso_valores = [item["execucao"] for item in margem_por_obra]

    chart_pizza_labels = list(custos_por_categoria.keys())
    chart_pizza_valores = list(custos_por_categoria.values())

    return {
        "obras": obras,
        "custos": custos,
        "fornecedores": fornecedores,
        "medicoes": medicoes,
        "total_receita": total_receita,
        "total_custo": total_custo,
        "margem": margem,
        "obras_atrasadas": obras_atrasadas,
        "obras_ativas": obras_ativas,
        "ranking_fornecedores": ranking_fornecedores,
        "custos_por_categoria": custos_por_categoria,
        "custos_importados_por_categoria": custos_importados_por_categoria,
        "comparativo_categorias": comparativo_categorias,
        "margem_por_obra": margem_por_obra,
        "tipologia_count": tipologia_count,
        "alertas": alertas,
        "total_medicoes": total_medicoes,
        "total_importado": total_importado,
        "chart_comparativo_labels": chart_comparativo_labels,
        "chart_comparativo_importado": chart_comparativo_importado,
        "chart_comparativo_lancado": chart_comparativo_lancado,
        "chart_progresso_labels": chart_progresso_labels,
        "chart_progresso_valores": chart_progresso_valores,
        "chart_pizza_labels": chart_pizza_labels,
        "chart_pizza_valores": chart_pizza_valores,
        "margem_percentual": margem_percentual,
        "custo_percentual_receita": custo_percentual_receita,
        "execucao_media": execucao_media,
    }

@app.context_processor
def inject_helpers():
    return dict(
        formatar_moeda=formatar_moeda,
        calcular_media_fornecedor=calcular_media_fornecedor
    )


@app.route("/")
def index():
    if not usuario_logado():
        return redirect(url_for("login"))
    return redirect(url_for("dashboard"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        senha = request.form.get("senha", "").strip()

        usuario = query_one(
            "SELECT * FROM usuarios WHERE username = ? AND ativo = 1",
            (username,)
        )

        if not usuario:
            flash("Usuário não encontrado.", "erro")
            return render_template("login.html")

        if verificar_senha(senha, usuario["senha_hash"]):
            session["usuario_id"] = usuario["id"]
            session["usuario_nome"] = usuario["nome"]
            session["usuario_perfil"] = usuario["perfil"]
            return redirect(url_for("dashboard"))
        else:
            flash("Senha incorreta.", "erro")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/dashboard")
def dashboard():
    if not usuario_logado():
        return redirect(url_for("login"))

    filtro_obra = request.args.get("obra", "").strip()
    filtro_categoria = request.args.get("categoria", "").strip()
    filtro_status = request.args.get("status", "").strip()
    data_inicio = request.args.get("data_inicio", "").strip()
    data_fim = request.args.get("data_fim", "").strip()

    dados = calcular_kpis_dashboard(
        filtro_obra=filtro_obra,
        filtro_categoria=filtro_categoria,
        filtro_status=filtro_status,
        data_inicio=data_inicio,
        data_fim=data_fim
    )

    todas_obras = query_all("SELECT * FROM obras ORDER BY codigo ASC")
    todas_categorias_rows = query_all(
        "SELECT DISTINCT categoria FROM custos WHERE categoria IS NOT NULL AND categoria != '' ORDER BY categoria ASC"
    )
    todas_categorias = [row["categoria"] for row in todas_categorias_rows]

    return render_template(
        "dashboard.html",
        **dados,
        filtro_obra=filtro_obra,
        filtro_categoria=filtro_categoria,
        filtro_status=filtro_status,
        data_inicio=data_inicio,
        data_fim=data_fim,
        todas_obras=todas_obras,
        todas_categorias=todas_categorias
    )

@app.route("/obras")
def obras():
    if not usuario_logado():
        return redirect(url_for("login"))

    lista_obras = query_all("SELECT * FROM obras ORDER BY id DESC")
    return render_template("obras.html", obras=lista_obras)


@app.route("/obras/nova", methods=["POST"])
def nova_obra():
    if not usuario_logado():
        return redirect(url_for("login"))

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
        return redirect(url_for("obras"))

    existe = query_one("SELECT * FROM obras WHERE codigo = ?", (codigo,))
    if existe:
        flash("Já existe uma obra com esse código.", "erro")
        return redirect(url_for("obras"))

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
        return redirect(url_for("obras"))

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
    return redirect(url_for("obras"))


@app.route("/custos")
def custos():
    if not usuario_logado():
        return redirect(url_for("login"))

    lista_custos = query_all("""
        SELECT c.*, o.codigo AS codigo_obra, o.nome AS nome_obra
        FROM custos c
        JOIN obras o ON c.obra_id = o.id
        ORDER BY c.id DESC
    """)

    obras = query_all("SELECT * FROM obras ORDER BY nome ASC")
    return render_template("custos.html", custos=lista_custos, obras=obras)


@app.route("/custos/novo", methods=["POST"])
def novo_custo():
    if not usuario_logado():
        return redirect(url_for("login"))

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
        return redirect(url_for("custos"))

    try:
        valor_total_float = parse_valor_monetario(valor_total)
        if valor_negativo(valor_total_float):
            raise ValueError("Valor do custo não pode ser negativo.")
    except ValueError as e:
        flash(str(e), "erro")
        return redirect(url_for("custos"))

    execute(
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

    flash("Custo lançado com sucesso.", "sucesso")
    return redirect(url_for("custos"))


@app.route("/fornecedores")
def fornecedores():
    if not usuario_logado():
        return redirect(url_for("login"))

    lista_fornecedores = query_all("SELECT * FROM fornecedores ORDER BY id DESC")
    return render_template("fornecedores.html", fornecedores=lista_fornecedores)


@app.route("/fornecedores/novo", methods=["POST"])
def novo_fornecedor():
    if not usuario_logado():
        return redirect(url_for("login"))

    codigo = request.form.get("codigo", "").strip()
    nome = request.form.get("nome", "").strip()
    categoria = request.form.get("categoria", "").strip()
    contato = request.form.get("contato", "").strip()
    documento = request.form.get("documento", "").strip()
    prazo_medio = request.form.get("prazo_medio", "").strip()
    nota_qualidade = request.form.get("nota_qualidade", "").strip()
    nota_preco = request.form.get("nota_preco", "").strip()
    nota_prazo = request.form.get("nota_prazo", "").strip()
    observacao = request.form.get("observacao", "").strip()

    if not codigo or not nome or not categoria:
        flash("Preencha os campos obrigatórios do fornecedor.", "erro")
        return redirect(url_for("fornecedores"))

    existe = query_one("SELECT * FROM fornecedores WHERE codigo = ?", (codigo,))
    if existe:
        flash("Já existe um fornecedor com esse código.", "erro")
        return redirect(url_for("fornecedores"))

    execute(
        """
        INSERT INTO fornecedores (
            codigo, nome, categoria, contato, documento,
            prazo_medio, nota_qualidade, nota_preco,
            nota_prazo, observacao
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            codigo,
            nome,
            categoria,
            contato,
            documento,
            int(prazo_medio) if prazo_medio else 0,
            float(nota_qualidade) if nota_qualidade else 0,
            float(nota_preco) if nota_preco else 0,
            float(nota_prazo) if nota_prazo else 0,
            observacao
        )
    )

    flash("Fornecedor cadastrado com sucesso.", "sucesso")
    return redirect(url_for("fornecedores"))


@app.route("/compras")
def compras():
    if not usuario_logado():
        return redirect(url_for("login"))

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


@app.route("/compras/nova", methods=["POST"])
def nova_compra():
    if not usuario_logado():
        return redirect(url_for("login"))

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
        return redirect(url_for("compras"))

    try:
        quantidade_float = parse_valor_monetario(quantidade)
        valor_unitario_float = parse_valor_monetario(valor_unitario)

        if valor_negativo(quantidade_float):
            raise ValueError("Quantidade não pode ser negativa.")

        if valor_negativo(valor_unitario_float):
            raise ValueError("Valor unitário não pode ser negativo.")
    except ValueError as e:
        flash(str(e), "erro")
        return redirect(url_for("compras"))

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
    return redirect(url_for("compras"))


@app.route("/equipe")
def equipe():
    if not usuario_logado():
        return redirect(url_for("login"))

    lista_equipe = query_all("""
        SELECT e.*, o.codigo AS codigo_obra, o.nome AS nome_obra
        FROM equipe e
        JOIN obras o ON e.obra_id = o.id
        ORDER BY e.id DESC
    """)

    obras = query_all("SELECT * FROM obras ORDER BY nome ASC")
    return render_template("equipe.html", equipe=lista_equipe, obras=obras)


@app.route("/equipe/novo", methods=["POST"])
def novo_membro_equipe():
    if not usuario_logado():
        return redirect(url_for("login"))

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
        return redirect(url_for("equipe"))

    try:
        valor_contratado_float = parse_valor_monetario(valor_contratado)
        valor_pago_float = parse_valor_monetario(valor_pago)

        if valor_negativo(valor_contratado_float):
            raise ValueError("Valor contratado não pode ser negativo.")

        if valor_negativo(valor_pago_float):
            raise ValueError("Valor pago não pode ser negativo.")
    except ValueError as e:
        flash(str(e), "erro")
        return redirect(url_for("equipe"))

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
    return redirect(url_for("equipe"))


@app.route("/medicoes")
def medicoes():
    if not usuario_logado():
        return redirect(url_for("login"))

    lista_medicoes = query_all("""
        SELECT m.*, o.codigo AS codigo_obra, o.nome AS nome_obra
        FROM medicoes m
        JOIN obras o ON m.obra_id = o.id
        ORDER BY m.id DESC
    """)

    obras = query_all("SELECT * FROM obras ORDER BY nome ASC")
    return render_template("medicoes.html", medicoes=lista_medicoes, obras=obras)


@app.route("/medicoes/nova", methods=["POST"])
def nova_medicao():
    if not usuario_logado():
        return redirect(url_for("login"))

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
        return redirect(url_for("medicoes"))

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
        return redirect(url_for("medicoes"))

    execute(
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

    flash("Medição cadastrada com sucesso.", "sucesso")
    return redirect(url_for("medicoes"))


@app.route("/importacao")
def importacao():
    if not usuario_logado():
        return redirect(url_for("login"))

    obras = query_all("SELECT * FROM obras ORDER BY id DESC")
    importacoes = query_all("SELECT * FROM importacoes ORDER BY id DESC")
    return render_template("importacao.html", obras=obras, importacoes=importacoes)


@app.route("/importacao/planilha", methods=["POST"])
def importar_planilha_route():
    if not usuario_logado():
        return redirect(url_for("login"))

    arquivo = request.files.get("arquivo_planilha")
    codigo_obra = request.form.get("codigo_obra", "").strip()
    nome_obra = request.form.get("nome_obra", "").strip()

    if not arquivo or not codigo_obra or not nome_obra:
        flash("Envie a planilha e preencha código e nome da obra.", "erro")
        return redirect(url_for("importacao"))

    os.makedirs("uploads", exist_ok=True)
    caminho = os.path.join("uploads", arquivo.filename)
    arquivo.save(caminho)

    try:
        importar_planilha(caminho, codigo_obra, nome_obra)
        flash("Planilha importada com sucesso.", "sucesso")
    except Exception as e:
        flash(f"Erro ao importar planilha: {str(e)}", "erro")

    return redirect(url_for("importacao"))
@app.route("/orcamento-importado")
def orcamento_importado():
    if not usuario_logado():
        return redirect(url_for("login"))

    obras = query_all("SELECT * FROM obras ORDER BY id DESC")
    categorias_importadas = query_all("""
        SELECT cic.*, o.codigo AS codigo_obra, o.nome AS nome_obra
        FROM custos_importados_categoria cic
        JOIN obras o ON cic.obra_id = o.id
        ORDER BY o.id DESC, cic.categoria ASC
    """)

    return render_template(
        "orcamento_importado.html",
        obras=obras,
        categorias_importadas=categorias_importadas
    )

@app.route("/dashboard/exportar")
def dashboard_exportar():
    if not usuario_logado():
        return redirect(url_for("login"))

    filtro_obra = request.args.get("obra", "").strip()
    filtro_categoria = request.args.get("categoria", "").strip()
    filtro_status = request.args.get("status", "").strip()
    data_inicio = request.args.get("data_inicio", "").strip()
    data_fim = request.args.get("data_fim", "").strip()

    dados = calcular_kpis_dashboard(
        filtro_obra=filtro_obra,
        filtro_categoria=filtro_categoria,
        filtro_status=filtro_status,
        data_inicio=data_inicio,
        data_fim=data_fim
    )

    output = BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df_kpis = pd.DataFrame([{
            "Receita Total": dados["total_receita"],
            "Custo Total": dados["total_custo"],
            "Margem": dados["margem"],
            "Obras em Atenção": len(dados["alertas"]),
            "Medições": dados["total_medicoes"],
            "Total Importado": dados["total_importado"]
        }])
        df_kpis.to_excel(writer, index=False, sheet_name="KPIs")

        df_comparativo = pd.DataFrame(dados["comparativo_categorias"])
        df_comparativo.to_excel(writer, index=False, sheet_name="Comparativo")

        df_obras = pd.DataFrame(dados["margem_por_obra"])
        df_obras.to_excel(writer, index=False, sheet_name="Obras")

    output.seek(0)

    return send_file(
        output,
        as_attachment=True,
        download_name="dashboard_central_obras.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

@app.route("/obra/<codigo>")
def obra_detalhe(codigo):
    if not usuario_logado():
        return redirect(url_for("login"))

    obra = query_one("SELECT * FROM obras WHERE codigo = ?", (codigo,))
    if not obra:
        flash("Obra não encontrada.", "erro")
        return redirect(url_for("obras"))

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

@app.route("/obras/exportar")
def obras_exportar():
    if not usuario_logado():
        return redirect(url_for("login"))

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

@app.route("/obras/editar/<int:obra_id>", methods=["POST"])
def editar_obra(obra_id):
    if not usuario_logado():
        return redirect(url_for("login"))

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
        return redirect(url_for("obras"))

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
    return redirect(url_for("obras"))

@app.route("/obras/excluir/<int:obra_id>", methods=["POST"])
def excluir_obra(obra_id):
    if not usuario_logado():
        return redirect(url_for("login"))

    execute("DELETE FROM custos WHERE obra_id = ?", (obra_id,))
    execute("DELETE FROM medicoes WHERE obra_id = ?", (obra_id,))
    execute("DELETE FROM equipe WHERE obra_id = ?", (obra_id,))
    execute("DELETE FROM compras WHERE obra_id = ?", (obra_id,))
    execute("DELETE FROM custos_importados_categoria WHERE obra_id = ?", (obra_id,))
    execute("DELETE FROM obras WHERE id = ?", (obra_id,))

    flash("Obra excluída com sucesso.", "sucesso")
    return redirect(url_for("obras"))

@app.route("/alertas")
def alertas():
    if not usuario_logado():
        return redirect(url_for("login"))

    lista_alertas = calcular_alertas()
    return render_template("alertas.html", alertas=lista_alertas)

@app.route("/custos/editar/<int:custo_id>", methods=["POST"])
def editar_custo(custo_id):
    if not usuario_logado():
        return redirect(url_for("login"))

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
        return redirect(url_for("custos"))

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

    flash("Custo atualizado com sucesso.", "sucesso")
    return redirect(url_for("custos"))


@app.route("/custos/excluir/<int:custo_id>", methods=["POST"])
def excluir_custo(custo_id):
    if not usuario_logado():
        return redirect(url_for("login"))

    execute("DELETE FROM custos WHERE id = ?", (custo_id,))
    flash("Custo excluído com sucesso.", "sucesso")
    return redirect(url_for("custos"))

@app.route("/fornecedores/editar/<int:fornecedor_id>", methods=["POST"])
def editar_fornecedor(fornecedor_id):
    if not usuario_logado():
        return redirect(url_for("login"))

    nome = request.form.get("nome", "").strip()
    categoria = request.form.get("categoria", "").strip()
    contato = request.form.get("contato", "").strip()
    documento = request.form.get("documento", "").strip()
    prazo_medio = request.form.get("prazo_medio", "").strip()
    nota_qualidade = request.form.get("nota_qualidade", "").strip()
    nota_preco = request.form.get("nota_preco", "").strip()
    nota_prazo = request.form.get("nota_prazo", "").strip()
    observacao = request.form.get("observacao", "").strip()

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
            int(prazo_medio) if prazo_medio else 0,
            float(nota_qualidade) if nota_qualidade else 0,
            float(nota_preco) if nota_preco else 0,
            float(nota_prazo) if nota_prazo else 0,
            observacao,
            fornecedor_id
        )
    )

    flash("Fornecedor atualizado com sucesso.", "sucesso")
    return redirect(url_for("fornecedores"))

@app.route("/fornecedores/excluir/<int:fornecedor_id>", methods=["POST"])
def excluir_fornecedor(fornecedor_id):
    if not usuario_logado():
        return redirect(url_for("login"))

    execute("DELETE FROM fornecedores WHERE id = ?", (fornecedor_id,))
    flash("Fornecedor excluído com sucesso.", "sucesso")
    return redirect(url_for("fornecedores"))

@app.route("/compras/editar/<int:compra_id>", methods=["POST"])
def editar_compra(compra_id):
    if not usuario_logado():
        return redirect(url_for("login"))

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
        return redirect(url_for("compras"))

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
    return redirect(url_for("compras"))


@app.route("/compras/excluir/<int:compra_id>", methods=["POST"])
def excluir_compra(compra_id):
    if not usuario_logado():
        return redirect(url_for("login"))

    execute("DELETE FROM compras WHERE id = ?", (compra_id,))
    flash("Compra excluída com sucesso.", "sucesso")
    return redirect(url_for("compras"))

@app.route("/equipe/editar/<int:equipe_id>", methods=["POST"])
def editar_equipe(equipe_id):
    if not usuario_logado():
        return redirect(url_for("login"))

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
        return redirect(url_for("equipe"))

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
    return redirect(url_for("equipe"))


@app.route("/equipe/excluir/<int:equipe_id>", methods=["POST"])
def excluir_equipe(equipe_id):
    if not usuario_logado():
        return redirect(url_for("login"))

    execute("DELETE FROM equipe WHERE id = ?", (equipe_id,))
    flash("Profissional excluído com sucesso.", "sucesso")
    return redirect(url_for("equipe"))
@app.route("/medicoes/editar/<int:medicao_id>", methods=["POST"])
def editar_medicao(medicao_id):
    if not usuario_logado():
        return redirect(url_for("login"))

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
        return redirect(url_for("medicoes"))

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

    flash("Medição atualizada com sucesso.", "sucesso")
    return redirect(url_for("medicoes"))


@app.route("/medicoes/excluir/<int:medicao_id>", methods=["POST"])
def excluir_medicao(medicao_id):
    if not usuario_logado():
        return redirect(url_for("login"))

    execute("DELETE FROM medicoes WHERE id = ?", (medicao_id,))
    flash("Medição excluída com sucesso.", "sucesso")
    return redirect(url_for("medicoes"))

@app.route("/custos/exportar")
def custos_exportar():
    if not usuario_logado():
        return redirect(url_for("login"))

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


@app.route("/fornecedores/exportar")
def fornecedores_exportar():
    if not usuario_logado():
        return redirect(url_for("login"))

    lista = query_all("SELECT * FROM fornecedores ORDER BY id DESC")

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


@app.route("/compras/exportar")
def compras_exportar():
    if not usuario_logado():
        return redirect(url_for("login"))

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


@app.route("/equipe/exportar")
def equipe_exportar():
    if not usuario_logado():
        return redirect(url_for("login"))

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


@app.route("/medicoes/exportar")
def medicoes_exportar():
    if not usuario_logado():
        return redirect(url_for("login"))

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

if __name__ == "__main__":
    app.run(debug=True)