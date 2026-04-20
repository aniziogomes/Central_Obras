import re
import pandas as pd
from io import BytesIO
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, jsonify
from database import query_one, query_all, execute
from services.validators import parse_valor_monetario, valor_negativo, validar_intervalo_percentual
from auth import usuario_logado, eh_admin, eh_gestor, eh_leitura
from services.log_service import registrar_log
from utils import formatar_moeda, formatar_tipo_obra

obras_bp = Blueprint("obras_bp", __name__)


def gerar_codigo_obra():
    obras = query_all("SELECT codigo FROM obras WHERE codigo IS NOT NULL AND codigo != ''")

    maior_numero = 0
    padrao = re.compile(r"^OBR-(\d+)$", re.IGNORECASE)

    for obra in obras:
        codigo = (obra["codigo"] or "").strip()
        match = padrao.match(codigo)
        if match:
            numero = int(match.group(1))
            if numero > maior_numero:
                maior_numero = numero

    proximo_numero = maior_numero + 1
    return f"OBR-{proximo_numero:03d}"


def obter_filtros_obras():
    return {
        "busca": request.args.get("busca", "").strip(),
        "status": request.args.get("status", "").strip().lower(),
    }


def buscar_obras_filtradas(busca="", status=""):
    lista_obras = query_all("SELECT * FROM obras ORDER BY id DESC")

    if busca:
        termo = busca.lower()
        lista_obras = [
            o for o in lista_obras
            if termo in (
                f"{o['codigo'] or ''} "
                f"{o['nome'] or ''} "
                f"{o['tipologia'] or ''} "
                f"{o['endereco'] or ''} "
                f"{o['tipo_obra'] or ''}"
            ).lower()
        ]

    if status and status != "todas":
        lista_obras = [
            o for o in lista_obras
            if (o["status"] or "").lower() == status
        ]

    return lista_obras


def serializar_obras(lista_obras):
    return [
        {
            "id": o["id"],
            "codigo": o["codigo"] or "",
            "nome": o["nome"] or "",
            "tipo_obra": o["tipo_obra"] or "contrato",
            "tipo_obra_formatado": formatar_tipo_obra(o["tipo_obra"]),
            "tipologia": o["tipologia"] or "-",
            "area_m2": o["area_m2"] or 0,
            "orcamento": o["orcamento"] or 0,
            "orcamento_formatado": formatar_moeda(o["orcamento"] or 0),
            "receita_total": o["receita_total"] or 0,
            "receita_total_formatado": formatar_moeda(o["receita_total"] or 0),
            "progresso_percentual": o["progresso_percentual"] or 0,
            "status": o["status"] or "",
            "endereco": o["endereco"] or "",
        }
        for o in lista_obras
    ]


@obras_bp.route("/obras")
def obras():
    if not usuario_logado() or not eh_leitura():
        return redirect(url_for("auth_bp.login"))

    filtros = obter_filtros_obras()
    lista_obras = buscar_obras_filtradas(
        busca=filtros["busca"],
        status=filtros["status"]
    )
    proximo_codigo = gerar_codigo_obra()

    return render_template(
        "obras.html",
        obras=lista_obras,
        proximo_codigo=proximo_codigo,
        filtro_busca=filtros["busca"],
        filtro_status=filtros["status"]
    )


@obras_bp.route("/obras/dados")
def obras_dados():
    if not usuario_logado() or not eh_leitura():
        return jsonify({"erro": "não autorizado"}), 401

    filtros = obter_filtros_obras()
    lista_obras = buscar_obras_filtradas(
        busca=filtros["busca"],
        status=filtros["status"]
    )

    return jsonify({
        "filtros": {
            "busca": filtros["busca"],
            "status": filtros["status"] or "todas",
        },
        "total": len(lista_obras),
        "obras": serializar_obras(lista_obras),
        "pode_editar": eh_gestor(),
        "pode_excluir": eh_admin(),
    })


@obras_bp.route("/obras/nova", methods=["POST"])
def nova_obra():
    if not usuario_logado() or not eh_gestor():
        flash("Você não tem permissão para cadastrar obras.", "erro")
        return redirect(url_for("obras_bp.obras"))

    codigo = request.form.get("codigo", "").strip()
    nome = request.form.get("nome", "").strip()
    endereco = request.form.get("endereco", "").strip()
    tipologia = request.form.get("tipologia", "").strip()
    tipo_obra = request.form.get("tipo_obra", "contrato").strip().lower()
    area_m2 = request.form.get("area_m2", "").strip()
    data_inicio = request.form.get("data_inicio", "").strip()
    data_fim_prevista = request.form.get("data_fim_prevista", "").strip()
    orcamento = request.form.get("orcamento", "").strip()
    receita_total = request.form.get("receita_total", "").strip()
    progresso_percentual = request.form.get("progresso_percentual", "").strip()
    status = request.form.get("status", "").strip()

    if not codigo:
        codigo = gerar_codigo_obra()

    if not nome or not tipologia or not status:
        flash("Preencha os campos obrigatórios da obra.", "erro")
        return redirect(url_for("obras_bp.obras"))

    if tipo_obra not in ["venda", "contrato"]:
        tipo_obra = "contrato"

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
            raise ValueError("Custo previsto não pode ser negativo.")

        if valor_negativo(receita_valor):
            raise ValueError("Receita prevista não pode ser negativa.")

        validar_intervalo_percentual(progresso_valor, "Execução (%)")
    except ValueError as e:
        flash(str(e), "erro")
        return redirect(url_for("obras_bp.obras"))

    obra_id = execute(
        """
        INSERT INTO obras (
            codigo, nome, endereco, tipologia, tipo_obra, area_m2,
            data_inicio, data_fim_prevista, orcamento,
            receita_total, progresso_percentual, status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            codigo,
            nome,
            endereco,
            tipologia,
            tipo_obra,
            area_valor,
            data_inicio,
            data_fim_prevista,
            orcamento_valor,
            receita_valor,
            progresso_valor,
            status
        )
    )

    registrar_log(
        acao="criação",
        entidade="obra",
        entidade_id=obra_id,
        descricao=f"Obra criada: {nome} ({codigo})"
    )

    flash("Obra cadastrada com sucesso.", "sucesso")
    return redirect(url_for("obras_bp.obras"))


@obras_bp.route("/obras/exportar")
def obras_exportar():
    if not usuario_logado() or not eh_leitura():
        return redirect(url_for("auth_bp.login"))

    filtros = obter_filtros_obras()
    obras = buscar_obras_filtradas(
        busca=filtros["busca"],
        status=filtros["status"]
    )

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
    if not usuario_logado() or not eh_leitura():
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
    lucro_previsto = (obra["receita_total"] or 0) - (obra["orcamento"] or 0)

    return render_template(
        "obra_detalhe.html",
        obra=obra,
        custos=custos,
        medicoes=medicoes,
        equipe=equipe,
        compras=compras,
        custos_importados=custos_importados,
        custo_total=custo_total,
        margem=margem,
        lucro_previsto=lucro_previsto
    )


@obras_bp.route("/obras/editar/<int:obra_id>", methods=["POST"])
def editar_obra(obra_id):
    if not usuario_logado() or not eh_gestor():
        flash("Você não tem permissão para editar obras.", "erro")
        return redirect(url_for("obras_bp.obras"))

    nome = request.form.get("nome", "").strip()
    endereco = request.form.get("endereco", "").strip()
    tipologia = request.form.get("tipologia", "").strip()
    tipo_obra = request.form.get("tipo_obra", "contrato").strip().lower()
    area_m2 = request.form.get("area_m2", "").strip()
    data_inicio = request.form.get("data_inicio", "").strip()
    data_fim_prevista = request.form.get("data_fim_prevista", "").strip()
    orcamento = request.form.get("orcamento", "").strip()
    receita_total = request.form.get("receita_total", "").strip()
    progresso_percentual = request.form.get("progresso_percentual", "").strip()
    status = request.form.get("status", "").strip()

    if tipo_obra not in ["venda", "contrato"]:
        tipo_obra = "contrato"

    try:
        area_valor = float(area_m2) if area_m2 else 0
        orcamento_valor = parse_valor_monetario(orcamento)
        receita_valor = parse_valor_monetario(receita_total)
        progresso_valor = parse_valor_monetario(progresso_percentual)

        if valor_negativo(area_valor):
            raise ValueError("Área não pode ser negativa.")

        if valor_negativo(orcamento_valor):
            raise ValueError("Custo previsto não pode ser negativo.")

        if valor_negativo(receita_valor):
            raise ValueError("Receita prevista não pode ser negativa.")

        validar_intervalo_percentual(progresso_valor, "Execução (%)")
    except ValueError as e:
        flash(str(e), "erro")
        return redirect(url_for("obras_bp.obras"))

    execute(
        """
        UPDATE obras
        SET nome = ?, endereco = ?, tipologia = ?, tipo_obra = ?, area_m2 = ?,
            data_inicio = ?, data_fim_prevista = ?, orcamento = ?,
            receita_total = ?, progresso_percentual = ?, status = ?
        WHERE id = ?
        """,
        (
            nome,
            endereco,
            tipologia,
            tipo_obra,
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

    registrar_log(
        acao="edição",
        entidade="obra",
        entidade_id=obra_id,
        descricao=f"Obra editada: {nome}"
    )

    flash("Obra atualizada com sucesso.", "sucesso")
    return redirect(url_for("obras_bp.obras"))


@obras_bp.route("/obras/excluir/<int:obra_id>", methods=["POST"])
def excluir_obra(obra_id):
    if not usuario_logado() or not eh_admin():
        flash("Você não tem permissão para excluir obras.", "erro")
        return redirect(url_for("obras_bp.obras"))

    execute("DELETE FROM custos WHERE obra_id = ?", (obra_id,))
    execute("DELETE FROM medicoes WHERE obra_id = ?", (obra_id,))
    execute("DELETE FROM equipe WHERE obra_id = ?", (obra_id,))
    execute("DELETE FROM compras WHERE obra_id = ?", (obra_id,))
    execute("DELETE FROM custos_importados_categoria WHERE obra_id = ?", (obra_id,))
    execute("DELETE FROM obras WHERE id = ?", (obra_id,))

    registrar_log(
        acao="exclusão",
        entidade="obra",
        entidade_id=obra_id,
        descricao="Obra excluída"
    )

    flash("Obra excluída com sucesso.", "sucesso")
    return redirect(url_for("obras_bp.obras"))