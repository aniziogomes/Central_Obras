from datetime import datetime
from pathlib import Path
from io import BytesIO
from urllib.parse import quote_plus

import pandas as pd
from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, send_file, url_for
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from auth import eh_gestor, pode_visualizar, usuario_logado
from database import execute, query_all, query_one
from services.contrato_pdf_service import (
    STATUS_CONTRATO_LABELS,
    TIPO_CONTRATO_LABELS,
    gerar_pdf_contrato,
)
from services.log_service import registrar_log
from services.tenant import aplicar_filtro_empresa, empresa_id_para_insert, listar_obras_acessiveis, obter_obra_acessivel, where_empresa
from services.validators import caminho_redirecionamento_seguro, limpar_texto, parse_int_nao_negativo, parse_int_positivo, parse_valor_monetario, valor_negativo
from utils import formatar_moeda


contratos_bp = Blueprint("contratos_bp", __name__)

TIPOS_CONTRATO_VALIDOS = set(TIPO_CONTRATO_LABELS.keys())
STATUS_CONTRATO_VALIDOS = set(STATUS_CONTRATO_LABELS.keys())
DIAS_ALERTA_ASSINATURA = 7
MAX_AGE_LINK_PDF_COMPARTILHADO = 60 * 60 * 24 * 30
CONTRATO_FIELDS = (
    "empresa_id",
    "obra_id",
    "cliente_id",
    "tipo_contrato",
    "status",
    "titulo",
    "numero_contrato",
    "valor_total",
    "forma_pagamento",
    "entrada",
    "quantidade_parcelas",
    "valor_parcela",
    "vencimento_primeira_parcela",
    "indice_reajuste",
    "multa_atraso",
    "juros_mora",
    "prazo_execucao",
    "data_inicio",
    "data_fim_prevista",
    "escopo_servico",
    "itens_inclusos",
    "itens_nao_inclusos",
    "responsabilidades_contratada",
    "responsabilidades_contratante",
    "garantias",
    "clausulas_adicionais",
    "observacoes",
    "motivo_aditivo",
    "versao",
    "contrato_origem_id",
    "data_assinatura",
    "updated_at",
)


def _agora_iso():
    return datetime.now().isoformat(timespec="seconds")


def _limpar_opcional(nome, max_len=255):
    return limpar_texto(request.form.get(nome, ""), max_len=max_len) or None


def _valor_nao_negativo(nome, campo):
    valor = parse_valor_monetario(request.form.get(nome, ""))
    if valor_negativo(valor):
        raise ValueError(f"{campo} não pode ser negativo.")
    return valor


def _empresa_atual_para_insert():
    return empresa_id_para_insert(request.form.get("empresa_id"))


def _buscar_clientes():
    where, params = where_empresa()
    return query_all(f"SELECT * FROM clientes {where} ORDER BY nome_completo ASC", params)


def _buscar_contratos_origem():
    where, params = where_empresa("c")
    return query_all(
        f"""
        SELECT c.id, c.numero_contrato, c.titulo, c.versao, cl.nome_completo AS cliente_nome
        FROM contratos c
        LEFT JOIN clientes cl ON cl.id = c.cliente_id
        {where}
        ORDER BY c.created_at DESC, c.id DESC
        """,
        params,
    )


def _obter_cliente_acessivel(cliente_id):
    if not cliente_id:
        return None
    where_extra, params = where_empresa()
    return query_one(
        f"SELECT * FROM clientes {where_extra} {'AND' if where_extra else 'WHERE'} id = ?",
        tuple(params) + (cliente_id,),
    )


def _obter_contrato_acessivel(contrato_id):
    extra, params = where_empresa("c")
    return query_one(
        f"""
        SELECT
            c.*,
            o.codigo AS obra_codigo,
            o.nome AS obra_nome,
            o.endereco AS obra_endereco,
            o.tipologia AS obra_tipologia,
            o.tipo_obra AS obra_tipo_obra,
            o.area_m2 AS obra_area_m2,
            o.data_inicio AS obra_data_inicio,
            o.data_fim_prevista AS obra_data_fim_prevista,
            o.receita_total AS obra_receita_total,
            cl.nome_completo AS cliente_nome,
            cl.cpf_cnpj AS cliente_documento
        FROM contratos c
        LEFT JOIN obras o ON o.id = c.obra_id
        LEFT JOIN clientes cl ON cl.id = c.cliente_id
        {extra}
        {'AND' if extra else 'WHERE'} c.id = ?
        """,
        tuple(params) + (contrato_id,),
    )


def _obter_contrato_por_id(contrato_id):
    return query_one("SELECT * FROM contratos WHERE id = ?", (contrato_id,))


def _gerar_numero_contrato(tipo):
    ano = datetime.now().year
    where, params = where_empresa()
    total = query_one(f"SELECT COUNT(*) AS total FROM contratos {where}", params)
    sequencial = int(total["total"] if total else 0) + 1
    prefixo = "ADT" if tipo == "aditivo" else "CTR"
    return f"{prefixo}-{ano}-{sequencial:04d}"


def _serializer_pdf_contrato():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"])


def _token_pdf_contrato(contrato):
    payload = {
        "contrato_id": int(contrato["id"]),
        "empresa_id": int(contrato["empresa_id"]),
        "updated_at": contrato["updated_at"] or "",
    }
    return _serializer_pdf_contrato().dumps(payload, salt="contrato-pdf-publico")


def _link_publico_pdf_contrato(contrato):
    if not contrato or not contrato["pdf_path"]:
        return ""
    token = _token_pdf_contrato(contrato)
    return url_for("contratos_bp.baixar_pdf_publico", token=token, _external=True)


def _link_whatsapp_pdf_contrato(contrato):
    link_pdf = _link_publico_pdf_contrato(contrato)
    if not link_pdf:
        return ""
    numero = contrato["numero_contrato"] or f"Contrato #{contrato['id']}"
    titulo = contrato["titulo"] or "Contrato"
    mensagem = f"Segue o PDF do contrato {numero} ({titulo}): {link_pdf}"
    return f"https://wa.me/?text={quote_plus(mensagem)}"


def _parse_datetime_flex(valor):
    if not valor:
        return None
    texto = str(valor).strip()
    if not texto:
        return None
    formatos = (
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    )
    for fmt in formatos:
        try:
            return datetime.strptime(texto[:19], fmt)
        except Exception:
            continue
    return None


def _dias_sem_assinatura(contrato):
    if not contrato:
        return None
    if (contrato["data_assinatura"] or "").strip():
        return None
    status = (contrato["status"] or "").strip().lower()
    if status in {"rascunho", "cancelado", "assinado"}:
        return None
    data_base = _parse_datetime_flex(contrato["data_geracao"]) or _parse_datetime_flex(contrato["created_at"])
    if not data_base:
        return None
    return max((datetime.now() - data_base).days, 0)


def _buscar_clausulas_salvas():
    where, params = where_empresa("cc")
    return query_all(
        f"""
        SELECT cc.*
        FROM clausulas_contrato cc
        {where}
        ORDER BY cc.titulo ASC, cc.id DESC
        """,
        params,
    )


def _obter_clausula_acessivel(clausula_id):
    where, params = where_empresa("cc")
    return query_one(
        f"""
        SELECT cc.*
        FROM clausulas_contrato cc
        {where}
        {'AND' if where else 'WHERE'} cc.id = ?
        """,
        tuple(params) + (clausula_id,),
    )


def _dados_cliente_form(prefixo=""):
    return {
        "nome_completo": limpar_texto(request.form.get(f"{prefixo}nome_completo", ""), max_len=180),
        "cpf_cnpj": limpar_texto(request.form.get(f"{prefixo}cpf_cnpj", ""), max_len=40),
        "rg_ie": limpar_texto(request.form.get(f"{prefixo}rg_ie", ""), max_len=40),
        "email": limpar_texto(request.form.get(f"{prefixo}email", ""), max_len=160),
        "telefone": limpar_texto(request.form.get(f"{prefixo}telefone", ""), max_len=60),
        "endereco": limpar_texto(request.form.get(f"{prefixo}endereco", ""), max_len=240),
        "cidade": limpar_texto(request.form.get(f"{prefixo}cidade", ""), max_len=120),
        "estado": limpar_texto(request.form.get(f"{prefixo}estado", ""), max_len=2).upper(),
        "cep": limpar_texto(request.form.get(f"{prefixo}cep", ""), max_len=20),
        "representante_legal": limpar_texto(request.form.get(f"{prefixo}representante_legal", ""), max_len=160),
        "observacoes": limpar_texto(request.form.get(f"{prefixo}observacoes", ""), max_len=1000),
    }


def _criar_cliente(empresa_id, dados):
    if not dados["nome_completo"]:
        return None
    return execute(
        """
        INSERT INTO clientes (
            empresa_id, nome_completo, cpf_cnpj, rg_ie, email, telefone, endereco,
            cidade, estado, cep, representante_legal, observacoes, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            empresa_id,
            dados["nome_completo"],
            dados["cpf_cnpj"] or None,
            dados["rg_ie"] or None,
            dados["email"] or None,
            dados["telefone"] or None,
            dados["endereco"] or None,
            dados["cidade"] or None,
            dados["estado"] or None,
            dados["cep"] or None,
            dados["representante_legal"] or None,
            dados["observacoes"] or None,
            _agora_iso(),
        ),
    )


def _resolver_cliente(empresa_id):
    cliente_id_texto = request.form.get("cliente_id", "").strip()
    if cliente_id_texto:
        cliente_id = parse_int_positivo(cliente_id_texto, "Cliente")
        cliente = _obter_cliente_acessivel(cliente_id)
        if not cliente:
            raise ValueError("Cliente não encontrado para este usuário.")
        return cliente_id

    dados_cliente = _dados_cliente_form("novo_cliente_")
    return _criar_cliente(empresa_id, dados_cliente)


def _payload_contrato(contrato_atual=None):
    tipo = limpar_texto(request.form.get("tipo_contrato", ""), max_len=40, obrigatorio=True, campo="Tipo do contrato")
    status = limpar_texto(request.form.get("status", "rascunho"), max_len=40, obrigatorio=True, campo="Status")

    if tipo not in TIPOS_CONTRATO_VALIDOS:
        raise ValueError("Tipo de contrato inválido.")
    if status not in STATUS_CONTRATO_VALIDOS:
        raise ValueError("Status do contrato inválido.")

    empresa_id = contrato_atual["empresa_id"] if contrato_atual else _empresa_atual_para_insert()
    obra_id = None
    obra_id_texto = request.form.get("obra_id", "").strip()
    obra = None
    if obra_id_texto:
        obra_id = parse_int_positivo(obra_id_texto, "Obra")
        obra = obter_obra_acessivel(obra_id=obra_id, campos="o.id, o.empresa_id, o.nome, o.receita_total, o.data_inicio, o.data_fim_prevista")
        if not obra:
            raise ValueError("Obra não encontrada para este usuário.")
        empresa_id = obra["empresa_id"]

    cliente_id = _resolver_cliente(empresa_id)

    contrato_origem_id = None
    origem_texto = request.form.get("contrato_origem_id", "").strip()
    versao = 1
    if origem_texto:
        contrato_origem_id = parse_int_positivo(origem_texto, "Contrato original")
        origem = _obter_contrato_acessivel(contrato_origem_id)
        if not origem:
            raise ValueError("Contrato original não encontrado.")
        versao = int(origem["versao"] or 1) + 1
        if tipo != "aditivo":
            raise ValueError("Apenas contratos do tipo aditivo podem ter contrato original.")
    elif contrato_atual:
        versao = int(contrato_atual["versao"] or 1)

    if tipo == "aditivo" and not contrato_origem_id:
        raise ValueError("Selecione o contrato original para criar o aditivo.")

    titulo = limpar_texto(request.form.get("titulo", ""), max_len=180)
    if not titulo:
        base = TIPO_CONTRATO_LABELS.get(tipo, "Contrato")
        nome_obra = obra["nome"] if obra else ""
        titulo = f"{base}{(' - ' + nome_obra) if nome_obra else ''}"

    numero = limpar_texto(request.form.get("numero_contrato", ""), max_len=80)
    if not numero and not contrato_atual:
        numero = _gerar_numero_contrato(tipo)
    elif not numero and contrato_atual:
        numero = contrato_atual["numero_contrato"]

    quantidade_parcelas = parse_int_nao_negativo(request.form.get("quantidade_parcelas", ""), "Quantidade de parcelas") if request.form.get("quantidade_parcelas", "").strip() else 0
    prazo_execucao = parse_int_nao_negativo(request.form.get("prazo_execucao", ""), "Prazo de execução") if request.form.get("prazo_execucao", "").strip() else 0
    motivo_aditivo = _limpar_opcional("motivo_aditivo", 2000)
    if tipo == "aditivo" and not motivo_aditivo:
        raise ValueError("Informe o motivo do aditivo.")

    payload = {
        "empresa_id": empresa_id,
        "obra_id": obra_id,
        "cliente_id": cliente_id,
        "tipo_contrato": tipo,
        "status": status,
        "titulo": titulo,
        "numero_contrato": numero,
        "valor_total": _valor_nao_negativo("valor_total", "Valor total"),
        "forma_pagamento": _limpar_opcional("forma_pagamento", 500),
        "entrada": _valor_nao_negativo("entrada", "Entrada"),
        "quantidade_parcelas": quantidade_parcelas,
        "valor_parcela": _valor_nao_negativo("valor_parcela", "Valor da parcela"),
        "vencimento_primeira_parcela": _limpar_opcional("vencimento_primeira_parcela", 10),
        "indice_reajuste": _limpar_opcional("indice_reajuste", 80),
        "multa_atraso": _valor_nao_negativo("multa_atraso", "Multa por atraso"),
        "juros_mora": _valor_nao_negativo("juros_mora", "Juros de mora"),
        "prazo_execucao": prazo_execucao,
        "data_inicio": _limpar_opcional("data_inicio", 10),
        "data_fim_prevista": _limpar_opcional("data_fim_prevista", 10),
        "escopo_servico": _limpar_opcional("escopo_servico", 5000),
        "itens_inclusos": _limpar_opcional("itens_inclusos", 5000),
        "itens_nao_inclusos": _limpar_opcional("itens_nao_inclusos", 5000),
        "responsabilidades_contratada": _limpar_opcional("responsabilidades_contratada", 5000),
        "responsabilidades_contratante": _limpar_opcional("responsabilidades_contratante", 5000),
        "garantias": _limpar_opcional("garantias", 5000),
        "clausulas_adicionais": _limpar_opcional("clausulas_adicionais", 5000),
        "observacoes": _limpar_opcional("observacoes", 3000),
        "motivo_aditivo": motivo_aditivo,
        "versao": versao,
        "contrato_origem_id": contrato_origem_id,
        "data_assinatura": _limpar_opcional("data_assinatura", 10),
        "updated_at": _agora_iso(),
    }
    return payload


def _contrato_vazio():
    return {
        "id": None,
        "empresa_id": None,
        "obra_id": "",
        "cliente_id": "",
        "tipo_contrato": "reforma",
        "status": "rascunho",
        "titulo": "",
        "numero_contrato": "",
        "valor_total": 0,
        "forma_pagamento": "",
        "entrada": 0,
        "quantidade_parcelas": 0,
        "valor_parcela": 0,
        "vencimento_primeira_parcela": "",
        "indice_reajuste": "",
        "multa_atraso": 0,
        "juros_mora": 0,
        "prazo_execucao": 0,
        "data_inicio": "",
        "data_fim_prevista": "",
        "escopo_servico": "",
        "itens_inclusos": "",
        "itens_nao_inclusos": "",
        "responsabilidades_contratada": "",
        "responsabilidades_contratante": "",
        "garantias": "",
        "clausulas_adicionais": "",
        "observacoes": "",
        "motivo_aditivo": "",
        "versao": 1,
        "contrato_origem_id": "",
        "data_assinatura": "",
    }


def _listas_form():
    return {
        "obras": listar_obras_acessiveis(order_by="o.nome ASC", campos="o.*"),
        "clientes": _buscar_clientes(),
        "contratos_origem": _buscar_contratos_origem(),
        "clausulas_salvas": _buscar_clausulas_salvas(),
        "tipos_contrato": TIPO_CONTRATO_LABELS,
        "status_contrato": STATUS_CONTRATO_LABELS,
    }


@contratos_bp.route("/contratos")
def contratos():
    if not usuario_logado() or not pode_visualizar():
        return redirect(url_for("auth_bp.login"))

    filtros = {
        "q": request.args.get("q", "").strip(),
        "obra_id": request.args.get("obra_id", "").strip(),
        "cliente_id": request.args.get("cliente_id", "").strip(),
        "tipo": request.args.get("tipo", "").strip(),
        "status": request.args.get("status", "").strip(),
        "data_inicio": request.args.get("data_inicio", "").strip(),
        "data_fim": request.args.get("data_fim", "").strip(),
    }

    clausulas = []
    params = []
    aplicar_filtro_empresa(clausulas, params, "c")
    if filtros["q"]:
        termo_like = f"%{filtros['q']}%"
        clausulas.append(
            "("
            "LOWER(c.numero_contrato) LIKE LOWER(?) OR "
            "LOWER(c.titulo) LIKE LOWER(?) OR "
            "LOWER(o.codigo) LIKE LOWER(?) OR "
            "LOWER(o.nome) LIKE LOWER(?) OR "
            "LOWER(cl.nome_completo) LIKE LOWER(?)"
            ")"
        )
        params.extend([termo_like, termo_like, termo_like, termo_like, termo_like])
    if filtros["obra_id"]:
        clausulas.append("c.obra_id = ?")
        params.append(filtros["obra_id"])
    if filtros["cliente_id"]:
        clausulas.append("c.cliente_id = ?")
        params.append(filtros["cliente_id"])
    if filtros["tipo"]:
        clausulas.append("c.tipo_contrato = ?")
        params.append(filtros["tipo"])
    if filtros["status"]:
        clausulas.append("c.status = ?")
        params.append(filtros["status"])
    if filtros["data_inicio"]:
        clausulas.append("date(c.created_at) >= ?")
        params.append(filtros["data_inicio"])
    if filtros["data_fim"]:
        clausulas.append("date(c.created_at) <= ?")
        params.append(filtros["data_fim"])

    where = "WHERE " + " AND ".join(clausulas) if clausulas else ""
    lista = query_all(
        f"""
        SELECT
            c.*,
            o.codigo AS obra_codigo,
            o.nome AS obra_nome,
            cl.nome_completo AS cliente_nome
        FROM contratos c
        LEFT JOIN obras o ON o.id = c.obra_id
        LEFT JOIN clientes cl ON cl.id = c.cliente_id
        {where}
        ORDER BY c.created_at DESC, c.id DESC
        """,
        tuple(params),
    )

    total_valor = sum((item["valor_total"] or 0) for item in lista)
    lista = [dict(i) for i in lista]
    for item in lista:
        item["whatsapp_pdf_url"] = _link_whatsapp_pdf_contrato(item)
        item["pdf_publico_url"] = _link_publico_pdf_contrato(item)
        item["dias_sem_assinatura"] = _dias_sem_assinatura(item)

    contratos_alerta_assinatura = [
        item for item in lista
        if item["dias_sem_assinatura"] is not None and item["dias_sem_assinatura"] >= DIAS_ALERTA_ASSINATURA
    ]

    return render_template(
        "contratos.html",
        contratos=lista,
        filtros=filtros,
        total_valor=total_valor,
        dias_alerta_assinatura=DIAS_ALERTA_ASSINATURA,
        contratos_alerta_assinatura=contratos_alerta_assinatura,
        **_listas_form(),
    )


@contratos_bp.route("/contratos/clientes/novo", methods=["POST"])
def novo_cliente():
    if not usuario_logado() or not eh_gestor():
        flash("Você não tem permissão para cadastrar clientes.", "erro")
        return redirect(url_for("contratos_bp.contratos"))
    redirect_to = caminho_redirecionamento_seguro(request.form.get("redirect_to"), url_for("contratos_bp.contratos"))
    try:
        dados = _dados_cliente_form("")
        if not dados["nome_completo"]:
            raise ValueError("Informe o nome do cliente.")
        cliente_id = _criar_cliente(_empresa_atual_para_insert(), dados)
    except ValueError as e:
        flash(str(e), "erro")
        return redirect(redirect_to)

    registrar_log("criacao", "cliente", cliente_id, f"Cliente criado: {dados['nome_completo']}")
    flash("Cliente cadastrado com sucesso.", "sucesso")
    return redirect(redirect_to)


@contratos_bp.route("/contratos/clausulas/novo", methods=["POST"])
def nova_clausula():
    if not usuario_logado() or not eh_gestor():
        flash("Você não tem permissão para salvar cláusulas.", "erro")
        return redirect(url_for("contratos_bp.contratos"))

    redirect_to = caminho_redirecionamento_seguro(
        request.form.get("redirect_to"),
        url_for("contratos_bp.novo_contrato"),
    )
    try:
        titulo = limpar_texto(request.form.get("clausula_titulo", ""), max_len=120, obrigatorio=True, campo="Título da cláusula")
        texto = limpar_texto(request.form.get("clausula_texto", ""), max_len=6000, obrigatorio=True, campo="Texto da cláusula")
        tipo_contrato = limpar_texto(request.form.get("clausula_tipo_contrato", ""), max_len=40)
        if tipo_contrato and tipo_contrato not in TIPOS_CONTRATO_VALIDOS:
            raise ValueError("Tipo da cláusula inválido.")

        clausula_id = execute(
            """
            INSERT INTO clausulas_contrato (
                empresa_id, titulo, tipo_contrato, texto, updated_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                _empresa_atual_para_insert(),
                titulo,
                tipo_contrato or None,
                texto,
                _agora_iso(),
            ),
        )
        registrar_log("criacao", "clausula_contrato", clausula_id, f"Cláusula salva: {titulo}")
        flash("Cláusula salva na biblioteca.", "sucesso")
    except ValueError as e:
        flash(str(e), "erro")
    return redirect(redirect_to)


@contratos_bp.route("/contratos/clausulas/excluir", methods=["POST"])
def excluir_clausula():
    if not usuario_logado() or not eh_gestor():
        flash("Você não tem permissão para excluir cláusulas.", "erro")
        return redirect(url_for("contratos_bp.contratos"))

    redirect_to = caminho_redirecionamento_seguro(
        request.form.get("redirect_to"),
        url_for("contratos_bp.novo_contrato"),
    )
    try:
        clausula_id = parse_int_positivo(request.form.get("clausula_id", ""), "Cláusula")
    except ValueError as e:
        flash(str(e), "erro")
        return redirect(redirect_to)
    clausula = _obter_clausula_acessivel(clausula_id)
    if not clausula:
        flash("Cláusula não encontrada.", "erro")
        return redirect(redirect_to)

    execute("DELETE FROM clausulas_contrato WHERE id = ? AND empresa_id = ?", (clausula_id, clausula["empresa_id"]))
    registrar_log("exclusao", "clausula_contrato", clausula_id, f"Cláusula excluída: {clausula['titulo']}")
    flash("Cláusula excluída.", "sucesso")
    return redirect(redirect_to)


@contratos_bp.route("/contratos/novo", methods=["GET", "POST"])
def novo_contrato():
    if not usuario_logado() or not eh_gestor():
        flash("Você não tem permissão para criar contratos.", "erro")
        return redirect(url_for("contratos_bp.contratos"))

    if request.method == "POST":
        try:
            payload = _payload_contrato()
            contrato_id = execute(
                """
                INSERT INTO contratos (
                    empresa_id, obra_id, cliente_id, tipo_contrato, status, titulo,
                    numero_contrato, valor_total, forma_pagamento, entrada,
                    quantidade_parcelas, valor_parcela, vencimento_primeira_parcela,
                    indice_reajuste, multa_atraso, juros_mora, prazo_execucao,
                    data_inicio, data_fim_prevista, escopo_servico, itens_inclusos,
                    itens_nao_inclusos, responsabilidades_contratada,
                    responsabilidades_contratante, garantias, clausulas_adicionais,
                    observacoes, motivo_aditivo, versao, contrato_origem_id,
                    data_assinatura, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                tuple(payload[campo] for campo in CONTRATO_FIELDS),
            )
            if payload["contrato_origem_id"]:
                execute("UPDATE contratos SET status = 'aditivado', updated_at = ? WHERE id = ?", (_agora_iso(), payload["contrato_origem_id"]))
                registrar_log(
                    "aditivo",
                    "contrato",
                    contrato_id,
                    f"Aditivo criado para contrato #{payload['contrato_origem_id']}: {payload['titulo']}",
                )
            registrar_log("criacao", "contrato", contrato_id, f"Contrato criado: {payload['titulo']}")
            flash("Contrato salvo como rascunho.", "sucesso")
            return redirect(url_for("contratos_bp.ver_contrato", contrato_id=contrato_id))
        except ValueError as e:
            flash(str(e), "erro")

    contrato = _contrato_vazio()
    origem_id = request.args.get("origem", "").strip()
    obra_id = request.args.get("obra_id", "").strip()
    tipo = request.args.get("tipo", "").strip()
    if tipo in TIPOS_CONTRATO_VALIDOS:
        contrato["tipo_contrato"] = tipo
    if obra_id:
        contrato["obra_id"] = obra_id
    if origem_id:
        origem = _obter_contrato_acessivel(int(origem_id)) if origem_id.isdigit() else None
        if origem:
            contrato.update(dict(origem))
            contrato["id"] = None
            contrato["tipo_contrato"] = "aditivo"
            contrato["status"] = "rascunho"
            contrato["titulo"] = f"Aditivo - {origem['titulo']}"
            contrato["numero_contrato"] = ""
            contrato["contrato_origem_id"] = origem["id"]
            contrato["versao"] = int(origem["versao"] or 1) + 1
            contrato["motivo_aditivo"] = ""
            contrato["pdf_path"] = ""
            contrato["data_geracao"] = ""
            contrato["data_assinatura"] = ""

    return render_template("contrato_form.html", contrato=contrato, is_edit=False, **_listas_form())


@contratos_bp.route("/contratos/<int:contrato_id>")
def ver_contrato(contrato_id):
    if not usuario_logado() or not pode_visualizar():
        return redirect(url_for("auth_bp.login"))

    contrato = _obter_contrato_acessivel(contrato_id)
    if not contrato:
        flash("Contrato não encontrado.", "erro")
        return redirect(url_for("contratos_bp.contratos"))

    aditivos = query_all(
        """
        SELECT c.*, cl.nome_completo AS cliente_nome
        FROM contratos c
        LEFT JOIN clientes cl ON cl.id = c.cliente_id
        WHERE c.contrato_origem_id = ? AND c.empresa_id = ?
        ORDER BY c.created_at DESC, c.id DESC
        """,
        (contrato_id, contrato["empresa_id"]),
    )
    origem = _obter_contrato_acessivel(contrato["contrato_origem_id"]) if contrato["contrato_origem_id"] else None
    contrato = dict(contrato)
    contrato["whatsapp_pdf_url"] = _link_whatsapp_pdf_contrato(contrato)
    contrato["pdf_publico_url"] = _link_publico_pdf_contrato(contrato)
    contrato["dias_sem_assinatura"] = _dias_sem_assinatura(contrato)
    return render_template(
        "contrato_detalhe.html",
        contrato=contrato,
        aditivos=aditivos,
        origem=origem,
        dias_alerta_assinatura=DIAS_ALERTA_ASSINATURA,
        tipos_contrato=TIPO_CONTRATO_LABELS,
        status_contrato=STATUS_CONTRATO_LABELS,
    )


@contratos_bp.route("/contratos/<int:contrato_id>/editar", methods=["GET", "POST"])
def editar_contrato(contrato_id):
    if not usuario_logado() or not eh_gestor():
        flash("Você não tem permissão para editar contratos.", "erro")
        return redirect(url_for("contratos_bp.contratos"))

    contrato = _obter_contrato_acessivel(contrato_id)
    if not contrato:
        flash("Contrato não encontrado.", "erro")
        return redirect(url_for("contratos_bp.contratos"))

    if request.method == "POST":
        try:
            payload = _payload_contrato(contrato_atual=contrato)
            execute(
                """
                UPDATE contratos
                SET empresa_id = ?, obra_id = ?, cliente_id = ?, tipo_contrato = ?, status = ?,
                    titulo = ?, numero_contrato = ?, valor_total = ?, forma_pagamento = ?,
                    entrada = ?, quantidade_parcelas = ?, valor_parcela = ?,
                    vencimento_primeira_parcela = ?, indice_reajuste = ?, multa_atraso = ?,
                    juros_mora = ?, prazo_execucao = ?, data_inicio = ?, data_fim_prevista = ?,
                    escopo_servico = ?, itens_inclusos = ?, itens_nao_inclusos = ?,
                    responsabilidades_contratada = ?, responsabilidades_contratante = ?,
                    garantias = ?, clausulas_adicionais = ?, observacoes = ?,
                    motivo_aditivo = ?, versao = ?, contrato_origem_id = ?,
                    data_assinatura = ?, updated_at = ?
                WHERE id = ? AND empresa_id = ?
                """,
                tuple(payload[campo] for campo in CONTRATO_FIELDS) + (contrato_id, contrato["empresa_id"]),
            )
            registrar_log("edicao", "contrato", contrato_id, f"Contrato editado: {payload['titulo']}")
            flash("Contrato atualizado com sucesso.", "sucesso")
            return redirect(url_for("contratos_bp.ver_contrato", contrato_id=contrato_id))
        except ValueError as e:
            flash(str(e), "erro")

    return render_template("contrato_form.html", contrato=contrato, is_edit=True, **_listas_form())


def _dados_pdf(contrato):
    cliente = _obter_cliente_acessivel(contrato["cliente_id"]) if contrato["cliente_id"] else None
    obra = obter_obra_acessivel(obra_id=contrato["obra_id"]) if contrato["obra_id"] else None
    empresa = query_one("SELECT * FROM empresas WHERE id = ?", (contrato["empresa_id"],))
    origem = _obter_contrato_acessivel(contrato["contrato_origem_id"]) if contrato["contrato_origem_id"] else None
    return cliente, obra, empresa, origem


@contratos_bp.route("/contratos/<int:contrato_id>/pdf", methods=["POST"])
def gerar_pdf(contrato_id):
    if not usuario_logado() or not eh_gestor():
        flash("Você não tem permissão para gerar PDF de contratos.", "erro")
        return redirect(url_for("contratos_bp.ver_contrato", contrato_id=contrato_id))

    contrato = _obter_contrato_acessivel(contrato_id)
    if not contrato:
        flash("Contrato não encontrado.", "erro")
        return redirect(url_for("contratos_bp.contratos"))

    cliente, obra, empresa, origem = _dados_pdf(contrato)
    pdf_path = gerar_pdf_contrato(contrato, cliente=cliente, obra=obra, empresa=empresa, origem=origem)
    execute(
        "UPDATE contratos SET pdf_path = ?, data_geracao = ?, updated_at = ? WHERE id = ? AND empresa_id = ?",
        (pdf_path, _agora_iso(), _agora_iso(), contrato_id, contrato["empresa_id"]),
    )
    registrar_log("geracao_pdf", "contrato", contrato_id, f"PDF gerado para contrato: {contrato['titulo']}")
    flash("PDF gerado com sucesso.", "sucesso")
    return redirect(url_for("contratos_bp.ver_contrato", contrato_id=contrato_id))


@contratos_bp.route("/contratos/<int:contrato_id>/download")
def baixar_pdf(contrato_id):
    if not usuario_logado() or not pode_visualizar():
        return redirect(url_for("auth_bp.login"))

    contrato = _obter_contrato_acessivel(contrato_id)
    if not contrato:
        flash("Contrato não encontrado.", "erro")
        return redirect(url_for("contratos_bp.contratos"))

    if not contrato["pdf_path"] or not Path(contrato["pdf_path"]).exists():
        flash("Este contrato ainda não possui PDF gerado.", "erro")
        return redirect(url_for("contratos_bp.ver_contrato", contrato_id=contrato_id))

    nome = f"{contrato['numero_contrato'] or 'contrato'}.pdf".replace("/", "-")
    return send_file(Path(contrato["pdf_path"]).resolve(), as_attachment=True, download_name=nome, mimetype="application/pdf")


@contratos_bp.route("/contratos/publico/pdf/<token>")
def baixar_pdf_publico(token):
    try:
        payload = _serializer_pdf_contrato().loads(
            token,
            max_age=MAX_AGE_LINK_PDF_COMPARTILHADO,
            salt="contrato-pdf-publico",
        )
    except SignatureExpired:
        abort(410)
    except BadSignature:
        abort(404)

    contrato_id = payload.get("contrato_id")
    empresa_id = payload.get("empresa_id")
    updated_at = payload.get("updated_at") or ""
    if not contrato_id or not empresa_id:
        abort(404)

    contrato = _obter_contrato_por_id(contrato_id)
    if not contrato:
        abort(404)
    if int(contrato["empresa_id"]) != int(empresa_id):
        abort(403)
    if (contrato["updated_at"] or "") != updated_at:
        abort(410)
    if not contrato["pdf_path"] or not Path(contrato["pdf_path"]).exists():
        abort(404)

    nome = f"{contrato['numero_contrato'] or 'contrato'}.pdf".replace("/", "-")
    return send_file(
        Path(contrato["pdf_path"]).resolve(),
        as_attachment=True,
        download_name=nome,
        mimetype="application/pdf",
    )


@contratos_bp.route("/contratos/<int:contrato_id>/aditivo")
def criar_aditivo(contrato_id):
    if not usuario_logado() or not eh_gestor():
        flash("Você não tem permissão para criar aditivos.", "erro")
        return redirect(url_for("contratos_bp.contratos"))
    contrato = _obter_contrato_acessivel(contrato_id)
    if not contrato:
        flash("Contrato original não encontrado.", "erro")
        return redirect(url_for("contratos_bp.contratos"))
    return redirect(url_for("contratos_bp.novo_contrato", origem=contrato_id, tipo="aditivo"))


@contratos_bp.route("/contratos/<int:contrato_id>/excluir", methods=["POST"])
def excluir_contrato(contrato_id):
    if not usuario_logado() or not eh_gestor():
        flash("Você não tem permissão para excluir contratos.", "erro")
        return redirect(url_for("contratos_bp.contratos"))

    contrato = _obter_contrato_acessivel(contrato_id)
    if not contrato:
        flash("Contrato não encontrado.", "erro")
        return redirect(url_for("contratos_bp.contratos"))

    execute("DELETE FROM contratos WHERE id = ? AND empresa_id = ?", (contrato_id, contrato["empresa_id"]))
    registrar_log("exclusao", "contrato", contrato_id, f"Contrato excluído: {contrato['titulo']}")
    flash("Contrato excluído com sucesso.", "sucesso")
    return redirect(url_for("contratos_bp.contratos"))


@contratos_bp.route("/contratos/exportar")
def contratos_exportar():
    if not usuario_logado() or not pode_visualizar():
        return redirect(url_for("auth_bp.login"))

    where, params = where_empresa("c")
    lista = query_all(
        f"""
        SELECT
            c.numero_contrato AS numero,
            c.titulo,
            c.tipo_contrato AS tipo,
            c.status,
            c.valor_total,
            c.created_at,
            o.codigo AS obra_codigo,
            o.nome AS obra_nome,
            cl.nome_completo AS cliente
        FROM contratos c
        LEFT JOIN obras o ON o.id = c.obra_id
        LEFT JOIN clientes cl ON cl.id = c.cliente_id
        {where}
        ORDER BY c.created_at DESC
        """,
        params,
    )
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        pd.DataFrame([dict(item) for item in lista]).to_excel(writer, index=False, sheet_name="Contratos")
    output.seek(0)
    return send_file(
        output,
        as_attachment=True,
        download_name="contratos_canteiro.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
