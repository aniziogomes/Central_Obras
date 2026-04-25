import re
import pandas as pd
from io import BytesIO
from pathlib import Path
from uuid import uuid4
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, jsonify
from werkzeug.utils import secure_filename
from database import query_one, query_all, execute
from services.validators import parse_valor_monetario, valor_negativo, validar_intervalo_percentual
from services.validators import CATEGORIAS_CUSTO_VALIDAS
from auth import usuario_logado, eh_admin, eh_gestor, eh_leitura
from services.log_service import registrar_log
from utils import formatar_moeda, formatar_tipo_obra

obras_bp = Blueprint("obras_bp", __name__)
UPLOAD_OBRAS_DIR = Path("static/uploads/obras")
EXTENSOES_IMAGEM = {"png", "jpg", "jpeg", "webp", "gif"}


# ─── Helpers ─────────────────────────────────────────────────────────────────

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
    return f"OBR-{maior_numero + 1:03d}"


def obter_filtros_obras():
    return {
        "busca": request.args.get("busca", "").strip(),
        "status": request.args.get("status", "").strip().lower(),
    }


def extensao_permitida(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in EXTENSOES_IMAGEM


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
                f"{o['tipo_obra'] or ''} "
                f"{o['fase_obra'] if 'fase_obra' in o.keys() and o['fase_obra'] else ''} "
                f"{o['observacao_responsavel'] if 'observacao_responsavel' in o.keys() and o['observacao_responsavel'] else ''}"
            ).lower()
        ]

    if status and status != "todas":
        lista_obras = [
            o for o in lista_obras
            if (o["status"] or "").lower() == status
        ]

    return lista_obras


def serializar_obras(lista_obras):
    result = []
    for o in lista_obras:
        keys = o.keys()
        result.append({
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
            "data_inicio": o["data_inicio"] or "",
            "data_fim_prevista": o["data_fim_prevista"] or "",
            # Campos do canteiro
            "fase_obra": (o["fase_obra"] if "fase_obra" in keys and o["fase_obra"] else ""),
            "observacao_responsavel": (o["observacao_responsavel"] if "observacao_responsavel" in keys and o["observacao_responsavel"] else ""),
            "foto_capa": (o["foto_capa"] if "foto_capa" in keys and o["foto_capa"] else ""),
            "token_publico": (o["token_publico"] if "token_publico" in keys and o["token_publico"] else ""),
        })
    return result


# ─── Listagem ─────────────────────────────────────────────────────────────────

@obras_bp.route("/obras")
def obras():
    if not usuario_logado() or not eh_leitura():
        return redirect(url_for("auth_bp.login"))

    filtros = obter_filtros_obras()
    lista_obras = buscar_obras_filtradas(busca=filtros["busca"], status=filtros["status"])
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
    lista_obras = buscar_obras_filtradas(busca=filtros["busca"], status=filtros["status"])

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


# ─── Nova obra ────────────────────────────────────────────────────────────────

@obras_bp.route("/obras/nova", methods=["POST"])
def nova_obra():
    if not usuario_logado() or not eh_gestor():
        flash("Você não tem permissão para cadastrar obras.", "erro")
        return redirect(url_for("obras_bp.obras"))

    codigo              = request.form.get("codigo", "").strip()
    nome                = request.form.get("nome", "").strip()
    endereco            = request.form.get("endereco", "").strip()
    tipologia           = request.form.get("tipologia", "").strip()
    tipo_obra           = request.form.get("tipo_obra", "contrato").strip().lower()
    fase_obra           = request.form.get("fase_obra", "").strip()
    area_m2             = request.form.get("area_m2", "").strip()
    data_inicio         = request.form.get("data_inicio", "").strip()
    data_fim_prevista   = request.form.get("data_fim_prevista", "").strip()
    orcamento           = request.form.get("orcamento", "").strip()
    receita_total       = request.form.get("receita_total", "").strip()
    progresso_percentual= request.form.get("progresso_percentual", "").strip()
    status              = request.form.get("status", "").strip()
    observacao          = request.form.get("observacao_responsavel", "").strip()
    foto_capa           = request.form.get("foto_capa", "").strip()

    if not codigo:
        codigo = gerar_codigo_obra()

    if not nome or not tipologia or not status:
        flash("Preencha os campos obrigatórios da obra.", "erro")
        return redirect(url_for("obras_bp.obras"))

    if tipo_obra not in ["venda", "contrato"]:
        tipo_obra = "contrato"

    existe = query_one("SELECT id FROM obras WHERE codigo = ?", (codigo,))
    if existe:
        flash("Já existe uma obra com esse código.", "erro")
        return redirect(url_for("obras_bp.obras"))

    try:
        area_valor       = float(area_m2) if area_m2 else 0
        orcamento_valor  = parse_valor_monetario(orcamento)
        receita_valor    = parse_valor_monetario(receita_total)
        progresso_valor  = parse_valor_monetario(progresso_percentual)

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
            codigo, nome, endereco, tipologia, tipo_obra, fase_obra, area_m2,
            data_inicio, data_fim_prevista, orcamento, receita_total,
            progresso_percentual, status, observacao_responsavel, foto_capa
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            codigo, nome, endereco, tipologia, tipo_obra, fase_obra or None,
            area_valor, data_inicio or None, data_fim_prevista or None,
            orcamento_valor, receita_valor, progresso_valor, status,
            observacao or None, foto_capa or None
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


# ─── Detalhe ─────────────────────────────────────────────────────────────────

@obras_bp.route("/obra/<codigo>")
def obra_detalhe(codigo):
    if not usuario_logado() or not eh_leitura():
        return redirect(url_for("auth_bp.login"))

    obra = query_one("SELECT * FROM obras WHERE codigo = ?", (codigo,))
    if not obra:
        flash("Obra não encontrada.", "erro")
        return redirect(url_for("obras_bp.obras"))

    custos           = query_all("SELECT * FROM custos WHERE obra_id = ? ORDER BY id DESC", (obra["id"],))
    medicoes         = query_all("SELECT * FROM medicoes WHERE obra_id = ? ORDER BY id DESC", (obra["id"],))
    equipe           = query_all("SELECT * FROM equipe WHERE obra_id = ? ORDER BY id DESC", (obra["id"],))
    compras          = [
        c for c in custos
        if (c["categoria"] or "") == "Material"
        and (c["status_entrega"] or c["data_entrega_prevista"] or c["quantidade"] or c["valor_unitario"])
    ]
    fotos_obra       = query_all("SELECT * FROM fotos_obra WHERE obra_id = ? ORDER BY id DESC", (obra["id"],))
    custos_importados = query_all(
        "SELECT * FROM custos_importados_categoria WHERE obra_id = ? ORDER BY categoria ASC",
        (obra["id"],)
    )

    custo_total   = sum((c["valor_total"] or 0) for c in custos)
    margem        = (obra["receita_total"] or 0) - custo_total
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
        lucro_previsto=lucro_previsto,
        fotos_obra=fotos_obra,
    )


@obras_bp.route("/obra/<codigo>/detalhes")
def obra_detalhes(codigo):
    if not usuario_logado() or not eh_leitura():
        return redirect(url_for("auth_bp.login"))

    obra = query_one("SELECT * FROM obras WHERE codigo = ?", (codigo,))
    if not obra:
        flash("Obra nao encontrada.", "erro")
        return redirect(url_for("obras_bp.obras"))

    custos = query_all("SELECT * FROM custos WHERE obra_id = ? ORDER BY id DESC", (obra["id"],))
    medicoes = query_all("SELECT * FROM medicoes WHERE obra_id = ? ORDER BY id DESC", (obra["id"],))
    equipe = query_all("SELECT * FROM equipe WHERE obra_id = ? ORDER BY id DESC", (obra["id"],))
    compras = [
        c for c in custos
        if (c["categoria"] or "") == "Material"
        and (c["status_entrega"] or c["data_entrega_prevista"] or c["quantidade"] or c["valor_unitario"])
    ]
    fornecedores = query_all("SELECT * FROM fornecedores ORDER BY nome ASC")
    fotos_obra = query_all("SELECT * FROM fotos_obra WHERE obra_id = ? ORDER BY id DESC", (obra["id"],))
    custos_importados = query_all(
        "SELECT * FROM custos_importados_categoria WHERE obra_id = ? ORDER BY categoria ASC",
        (obra["id"],)
    )

    custo_total = sum((c["valor_total"] or 0) for c in custos)
    margem = (obra["receita_total"] or 0) - custo_total
    lucro_previsto = (obra["receita_total"] or 0) - (obra["orcamento"] or 0)
    custos_por_categoria = {}
    for custo in custos:
        categoria = custo["categoria"] or "Sem categoria"
        custos_por_categoria[categoria] = custos_por_categoria.get(categoria, 0) + (custo["valor_total"] or 0)

    medicoes_ordenadas = sorted(
        medicoes,
        key=lambda m: (m["data_medicao"] or "", m["id"] or 0)
    )
    medicao_labels = [
        m["medicao_nome"] or m["etapa"] or m["data_medicao"] or f"Medicao {i + 1}"
        for i, m in enumerate(medicoes_ordenadas)
    ]
    medicao_percentuais = [m["percentual_acumulado"] or m["percentual"] or 0 for m in medicoes_ordenadas]
    medicao_valores = [m["valor_realizado"] or 0 for m in medicoes_ordenadas]

    return render_template(
        "obra_detalhes.html",
        obra=obra,
        custos=custos,
        medicoes=medicoes,
        equipe=equipe,
        compras=compras,
        fornecedores=fornecedores,
        categorias_custo=CATEGORIAS_CUSTO_VALIDAS,
        custos_importados=custos_importados,
        fotos_obra=fotos_obra,
        custo_total=custo_total,
        margem=margem,
        lucro_previsto=lucro_previsto,
        chart_custo_cat_labels=list(custos_por_categoria.keys()),
        chart_custo_cat_valores=list(custos_por_categoria.values()),
        chart_medicao_labels=medicao_labels,
        chart_medicao_percentuais=medicao_percentuais,
        chart_medicao_valores=medicao_valores,
    )


@obras_bp.route("/obras/<int:obra_id>/fotos/nova", methods=["POST"])
def nova_foto_obra(obra_id):
    if not usuario_logado() or not eh_gestor():
        flash("Voce nao tem permissao para adicionar fotos.", "erro")
        return redirect(url_for("obras_bp.obras"))

    obra = query_one("SELECT id, codigo, nome FROM obras WHERE id = ?", (obra_id,))
    if not obra:
        flash("Obra nao encontrada.", "erro")
        return redirect(url_for("obras_bp.obras"))

    arquivo = request.files.get("foto_arquivo")
    caminho = request.form.get("caminho", "").strip()
    titulo = request.form.get("titulo", "").strip()
    fase = request.form.get("fase", "").strip()
    data_registro = request.form.get("data_registro", "").strip()
    usar_como_capa = request.form.get("usar_como_capa") == "1"

    if arquivo and arquivo.filename:
        if not extensao_permitida(arquivo.filename):
            flash("Envie uma imagem nos formatos PNG, JPG, JPEG, WEBP ou GIF.", "erro")
            return redirect(url_for("obras_bp.obra_detalhe", codigo=obra["codigo"]))

        UPLOAD_OBRAS_DIR.mkdir(parents=True, exist_ok=True)
        nome_seguro = secure_filename(arquivo.filename)
        nome_arquivo = f"obra-{obra_id}-{uuid4().hex[:8]}-{nome_seguro}"
        destino = UPLOAD_OBRAS_DIR / nome_arquivo
        arquivo.save(destino)
        caminho = f"/static/uploads/obras/{nome_arquivo}"

    if not caminho:
        flash("Selecione uma foto do seu dispositivo para adicionar a galeria.", "erro")
        return redirect(url_for("obras_bp.obra_detalhe", codigo=obra["codigo"]))

    foto_id = execute(
        """
        INSERT INTO fotos_obra (obra_id, caminho, titulo, fase, data_registro)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            obra_id,
            caminho,
            titulo or None,
            fase or None,
            data_registro or None,
        )
    )

    registrar_log(
        acao="foto_galeria",
        entidade="obra",
        entidade_id=obra_id,
        descricao=f"Foto adicionada a galeria da obra: {obra['nome']}"
    )

    if usar_como_capa:
        execute(
            "UPDATE obras SET foto_capa = ? WHERE id = ?",
            (caminho, obra_id)
        )

    flash("Foto adicionada a galeria com sucesso.", "sucesso")
    return redirect(url_for("obras_bp.obra_detalhe", codigo=obra["codigo"]))


@obras_bp.route("/obras/<int:obra_id>/fotos/<int:foto_id>/capa", methods=["POST"])
def usar_foto_como_capa(obra_id, foto_id):
    if not usuario_logado() or not eh_gestor():
        flash("Voce nao tem permissao para alterar a capa.", "erro")
        return redirect(url_for("obras_bp.obras"))

    obra = query_one("SELECT id, codigo, nome FROM obras WHERE id = ?", (obra_id,))
    if not obra:
        flash("Obra nao encontrada.", "erro")
        return redirect(url_for("obras_bp.obras"))

    foto = query_one(
        "SELECT caminho FROM fotos_obra WHERE id = ? AND obra_id = ?",
        (foto_id, obra_id)
    )
    if not foto:
        flash("Foto nao encontrada na galeria.", "erro")
        return redirect(url_for("obras_bp.obra_detalhe", codigo=obra["codigo"]))

    execute("UPDATE obras SET foto_capa = ? WHERE id = ?", (foto["caminho"], obra_id))
    registrar_log(
        acao="foto_capa",
        entidade="obra",
        entidade_id=obra_id,
        descricao=f"Foto da galeria definida como capa da obra: {obra['nome']}"
    )

    flash("Foto definida como capa da Visao do Canteiro.", "sucesso")
    return redirect(url_for("obras_bp.obra_detalhe", codigo=obra["codigo"]))


# ─── Editar ──────────────────────────────────────────────────────────────────

@obras_bp.route("/obras/<int:obra_id>/fotos/<int:foto_id>/excluir", methods=["POST"])
def excluir_foto_obra(obra_id, foto_id):
    if not usuario_logado() or not eh_gestor():
        flash("Voce nao tem permissao para excluir fotos.", "erro")
        return redirect(url_for("obras_bp.obras"))

    obra = query_one("SELECT id, codigo, nome, foto_capa FROM obras WHERE id = ?", (obra_id,))
    if not obra:
        flash("Obra nao encontrada.", "erro")
        return redirect(url_for("obras_bp.obras"))

    foto = query_one(
        "SELECT id, caminho FROM fotos_obra WHERE id = ? AND obra_id = ?",
        (foto_id, obra_id)
    )
    if not foto:
        flash("Foto nao encontrada na galeria.", "erro")
        return redirect(url_for("obras_bp.obra_detalhe", codigo=obra["codigo"]))

    execute("DELETE FROM fotos_obra WHERE id = ? AND obra_id = ?", (foto_id, obra_id))

    if obra["foto_capa"] == foto["caminho"]:
        execute("UPDATE obras SET foto_capa = NULL WHERE id = ?", (obra_id,))

    caminho = foto["caminho"] or ""
    if caminho.startswith("/static/uploads/obras/"):
        arquivo = Path(caminho.lstrip("/"))
        try:
            if arquivo.exists() and arquivo.is_file():
                arquivo.unlink()
        except OSError:
            pass

    registrar_log(
        acao="foto_excluida",
        entidade="obra",
        entidade_id=obra_id,
        descricao=f"Foto removida da galeria da obra: {obra['nome']}"
    )

    flash("Foto excluida da galeria.", "sucesso")
    return redirect(url_for("obras_bp.obra_detalhe", codigo=obra["codigo"]))


@obras_bp.route("/obras/<int:obra_id>/canteiro", methods=["POST"])
def atualizar_canteiro_obra(obra_id):
    if not usuario_logado() or not eh_gestor():
        flash("Voce nao tem permissao para atualizar o canteiro.", "erro")
        return redirect(url_for("obras_bp.obras"))

    obra = query_one("SELECT id, codigo, nome FROM obras WHERE id = ?", (obra_id,))
    if not obra:
        flash("Obra nao encontrada.", "erro")
        return redirect(url_for("obras_bp.obras"))

    fase_obra = request.form.get("fase_obra", "").strip()
    progresso_percentual = request.form.get("progresso_percentual", "").strip()
    observacao = request.form.get("observacao_responsavel", "").strip()

    try:
        progresso_valor = parse_valor_monetario(progresso_percentual)
        validar_intervalo_percentual(progresso_valor, "Conclusao (%)")
    except ValueError as e:
        flash(str(e), "erro")
        return redirect(url_for("obras_bp.obra_detalhe", codigo=obra["codigo"]))

    execute(
        """
        UPDATE obras
        SET fase_obra = ?, progresso_percentual = ?, observacao_responsavel = ?
        WHERE id = ?
        """,
        (
            fase_obra or None,
            progresso_valor,
            observacao or None,
            obra_id,
        )
    )

    registrar_log(
        acao="atualizacao_canteiro",
        entidade="obra",
        entidade_id=obra_id,
        descricao=f"Canteiro atualizado: {obra['nome']}"
    )

    flash("Avanco do canteiro salvo com sucesso.", "sucesso")
    return redirect(url_for("obras_bp.obra_detalhe", codigo=obra["codigo"]))


@obras_bp.route("/obras/editar/<int:obra_id>", methods=["POST"])
def editar_obra(obra_id):
    if not usuario_logado() or not eh_gestor():
        flash("Você não tem permissão para editar obras.", "erro")
        return redirect(url_for("obras_bp.obras"))

    # Busca a obra para saber o codigo (para redirecionar de volta)
    obra = query_one("SELECT codigo FROM obras WHERE id = ?", (obra_id,))

    nome                = request.form.get("nome", "").strip()
    endereco            = request.form.get("endereco", "").strip()
    tipologia           = request.form.get("tipologia", "").strip()
    tipo_obra           = request.form.get("tipo_obra", "contrato").strip().lower()
    fase_obra           = request.form.get("fase_obra", "").strip()
    area_m2             = request.form.get("area_m2", "").strip()
    data_inicio         = request.form.get("data_inicio", "").strip()
    data_fim_prevista   = request.form.get("data_fim_prevista", "").strip()
    orcamento           = request.form.get("orcamento", "").strip()
    receita_total       = request.form.get("receita_total", "").strip()
    progresso_percentual= request.form.get("progresso_percentual", "").strip()
    status              = request.form.get("status", "").strip()
    observacao          = request.form.get("observacao_responsavel", "").strip()
    foto_capa           = request.form.get("foto_capa", "").strip()

    # Descobre de onde veio o request para redirecionar corretamente
    veio_do_detalhe = obra and (
        "obra_detalhe" in (request.referrer or "") or
        f"/obra/" in (request.referrer or "")
    )

    if tipo_obra not in ["venda", "contrato"]:
        tipo_obra = "contrato"

    try:
        area_valor       = float(area_m2) if area_m2 else 0
        orcamento_valor  = parse_valor_monetario(orcamento)
        receita_valor    = parse_valor_monetario(receita_total)
        progresso_valor  = parse_valor_monetario(progresso_percentual)

        if valor_negativo(area_valor):
            raise ValueError("Área não pode ser negativa.")
        if valor_negativo(orcamento_valor):
            raise ValueError("Custo previsto não pode ser negativo.")
        if valor_negativo(receita_valor):
            raise ValueError("Receita prevista não pode ser negativa.")
        validar_intervalo_percentual(progresso_valor, "Execução (%)")
    except ValueError as e:
        flash(str(e), "erro")
        if obra and veio_do_detalhe:
            return redirect(url_for("obras_bp.obra_detalhe", codigo=obra["codigo"]))
        return redirect(url_for("obras_bp.obras"))

    execute(
        """
        UPDATE obras
        SET nome = ?, endereco = ?, tipologia = ?, tipo_obra = ?, fase_obra = ?,
            area_m2 = ?, data_inicio = ?, data_fim_prevista = ?,
            orcamento = ?, receita_total = ?, progresso_percentual = ?,
            status = ?, observacao_responsavel = ?, foto_capa = ?
        WHERE id = ?
        """,
        (
            nome, endereco, tipologia, tipo_obra, fase_obra or None,
            area_valor, data_inicio or None, data_fim_prevista or None,
            orcamento_valor, receita_valor, progresso_valor,
            status, observacao or None, foto_capa or None,
            obra_id
        )
    )

    registrar_log(
        acao="edição",
        entidade="obra",
        entidade_id=obra_id,
        descricao=f"Obra atualizada: {nome}"
    )

    flash("Obra atualizada com sucesso.", "sucesso")

    # Redireciona de volta para a ficha se veio de lá, senão vai para a lista
    if obra and veio_do_detalhe:
        return redirect(url_for("obras_bp.obra_detalhe", codigo=obra["codigo"]))
    return redirect(url_for("obras_bp.obras"))


# ─── Exportar ────────────────────────────────────────────────────────────────

@obras_bp.route("/obras/exportar")
def obras_exportar():
    if not usuario_logado() or not eh_leitura():
        return redirect(url_for("auth_bp.login"))

    filtros = obter_filtros_obras()
    lista = buscar_obras_filtradas(busca=filtros["busca"], status=filtros["status"])

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df = pd.DataFrame([dict(o) for o in lista])
        df.to_excel(writer, index=False, sheet_name="Obras")
    output.seek(0)

    return send_file(
        output,
        as_attachment=True,
        download_name="obras_central_obras.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


# ─── Excluir ─────────────────────────────────────────────────────────────────

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
