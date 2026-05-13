import re
import unicodedata
import pandas as pd
from io import BytesIO
from pathlib import Path
from uuid import uuid4
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, jsonify
from werkzeug.utils import secure_filename
from database import query_one, query_all, execute
from services.validators import caminho_redirecionamento_seguro, limpar_texto, parse_valor_monetario, valor_negativo, validar_intervalo_percentual
from services.validators import CATEGORIAS_CUSTO_VALIDAS
from auth import usuario_logado, eh_admin, eh_gestor, pode_visualizar
from services.log_service import registrar_log
from services.tenant import (
    empresa_id_para_insert,
    listar_empresas,
    obter_obra_acessivel,
    sincronizar_empresa_filhos_obra,
    tem_acesso_global,
    where_empresa,
)
from utils import formatar_moeda, formatar_tipo_obra, formatar_data

obras_bp = Blueprint("obras_bp", __name__)
UPLOAD_OBRAS_DIR = Path("static/uploads/obras")
EXTENSOES_IMAGEM = {"png", "jpg", "jpeg", "webp", "gif"}
STATUS_OBRA_LABELS = {
    "planejamento": "Planejamento",
    "andamento": "Em andamento",
    "atrasada": "Atrasada",
    "concluida": "Concluída",
    "vendida": "Vendida",
}
FASE_OBRA_LABELS = {
    "planejamento": "Planejamento",
    "fundacao": "Fundação",
    "estrutura": "Estrutura",
    "alvenaria": "Alvenaria",
    "telhado": "Telhado",
    "instalacoes": "Instalações",
    "revestimento": "Revestimento",
    "acabamento": "Acabamento",
    "vistoria": "Vistoria",
    "concluida": "Concluída",
}
FASES_OBRA_PADRAO = [
    "Planejamento",
    "Fundação",
    "Estrutura",
    "Alvenaria",
    "Telhado",
    "Instalações",
    "Revestimento",
    "Acabamento",
    "Vistoria",
    "Concluída",
]


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


def _slug_texto(valor):
    texto = unicodedata.normalize("NFKD", str(valor or ""))
    return "".join(ch for ch in texto if not unicodedata.combining(ch)).strip().lower()


def formatar_status_obra(status):
    return STATUS_OBRA_LABELS.get((status or "").strip().lower(), (status or "-").strip() or "-")


def formatar_fase_obra(fase):
    if not fase:
        return "Não definida"
    return FASE_OBRA_LABELS.get(_slug_texto(fase), str(fase).strip())


def formatar_nome_obra(nome):
    texto = (nome or "").strip()
    if not texto:
        return ""
    return " ".join(parte[:1].upper() + parte[1:] if parte else "" for parte in texto.split())


def buscar_obras_filtradas(busca="", status=""):
    where, params = where_empresa("o")
    lista_obras = query_all(
        f"""
        SELECT o.*, e.nome AS empresa_nome
        FROM obras o
        LEFT JOIN empresas e ON e.id = o.empresa_id
        {where}
        ORDER BY o.id DESC
        """,
        params,
    )

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
                f"{o['observacao_responsavel'] if 'observacao_responsavel' in o.keys() and o['observacao_responsavel'] else ''} "
                f"{o['proxima_etapa_portal'] if 'proxima_etapa_portal' in o.keys() and o['proxima_etapa_portal'] else ''}"
            ).lower()
        ]

    if status and status != "todas":
        lista_obras = [
            o for o in lista_obras
            if (o["status"] or "").lower() == status
        ]

    return lista_obras


def enriquecer_resumo_financeiro_obras(lista_obras):
    if not lista_obras:
        return lista_obras

    where_custos, params_custos = where_empresa()
    totais = query_all(
        f"""
        SELECT obra_id, COALESCE(SUM(valor_total), 0) AS gasto_total
        FROM custos
        {where_custos}
        {'AND' if where_custos else 'WHERE'} obra_id IS NOT NULL
        GROUP BY obra_id
        """,
        params_custos,
    )
    gastos_por_obra = {item["obra_id"]: item["gasto_total"] or 0 for item in totais}

    obras_enriquecidas = []
    for obra in lista_obras:
        obra_dict = dict(obra)
        gasto_total = gastos_por_obra.get(obra["id"], 0)
        obra_dict["gasto_total"] = gasto_total
        obra_dict["saldo_disponivel"] = (obra["receita_total"] or 0) - gasto_total
        obra_dict["nome_formatado"] = formatar_nome_obra(obra["nome"] or "")
        obra_dict["status_formatado"] = formatar_status_obra(obra["status"] or "")
        obra_dict["fase_obra_formatada"] = formatar_fase_obra(obra["fase_obra"] if "fase_obra" in obra.keys() else "")
        obras_enriquecidas.append(obra_dict)

    return obras_enriquecidas


def serializar_obras(lista_obras):
    result = []
    for o in lista_obras:
        keys = o.keys()
        result.append({
            "id": o["id"],
            "codigo": o["codigo"] or "",
            "nome": o["nome"] or "",
            "nome_formatado": formatar_nome_obra(o["nome"] or ""),
            "tipo_obra": o["tipo_obra"] or "contrato",
            "tipo_obra_formatado": formatar_tipo_obra(o["tipo_obra"]),
            "tipologia": o["tipologia"] or "-",
            "area_m2": o["area_m2"] or 0,
            "orcamento": o["orcamento"] or 0,
            "orcamento_formatado": formatar_moeda(o["orcamento"] or 0),
            "receita_total": o["receita_total"] or 0,
            "receita_total_formatado": formatar_moeda(o["receita_total"] or 0),
            "gasto_total": o["gasto_total"] if "gasto_total" in keys and o["gasto_total"] else 0,
            "gasto_total_formatado": formatar_moeda((o["gasto_total"] if "gasto_total" in keys and o["gasto_total"] else 0)),
            "saldo_disponivel": o["saldo_disponivel"] if "saldo_disponivel" in keys and o["saldo_disponivel"] else 0,
            "saldo_disponivel_formatado": formatar_moeda((o["saldo_disponivel"] if "saldo_disponivel" in keys and o["saldo_disponivel"] else 0)),
            "progresso_percentual": o["progresso_percentual"] or 0,
            "status": o["status"] or "",
            "status_formatado": formatar_status_obra(o["status"] or ""),
            "endereco": o["endereco"] or "",
            "data_inicio": o["data_inicio"] or "",
            "data_inicio_formatada": formatar_data(o["data_inicio"], ""),
            "data_fim_prevista": o["data_fim_prevista"] or "",
            "data_fim_prevista_formatada": formatar_data(o["data_fim_prevista"], ""),
            # Campos do canteiro
            "fase_obra": (o["fase_obra"] if "fase_obra" in keys and o["fase_obra"] else ""),
            "fase_obra_formatada": formatar_fase_obra(o["fase_obra"] if "fase_obra" in keys and o["fase_obra"] else ""),
            "observacao_responsavel": (o["observacao_responsavel"] if "observacao_responsavel" in keys and o["observacao_responsavel"] else ""),
            "foto_capa": (o["foto_capa"] if "foto_capa" in keys and o["foto_capa"] else ""),
            "proxima_etapa_portal": (o["proxima_etapa_portal"] if "proxima_etapa_portal" in keys and o["proxima_etapa_portal"] else ""),
            "token_publico": (o["token_publico"] if "token_publico" in keys and o["token_publico"] else ""),
        })
    return result


def _data_contrato_documento(contrato):
    return contrato["data_geracao"] or contrato["created_at"] or contrato["updated_at"]


def _resumo_aditivo(aditivo, contrato_anterior):
    valor_anterior = contrato_anterior["valor_total"] or 0
    valor_atual = aditivo["valor_total"] or 0
    delta_valor = valor_atual - valor_anterior
    if delta_valor > 0:
        partes = [f"+{formatar_moeda(delta_valor)} de valor"]
    elif delta_valor < 0:
        partes = [f"-{formatar_moeda(abs(delta_valor))} de valor"]
    else:
        partes = ["sem alteração de valor"]

    prazo_anterior = contrato_anterior["prazo_execucao"] or 0
    prazo_atual = aditivo["prazo_execucao"] or 0
    delta_prazo = prazo_atual - prazo_anterior
    if delta_prazo > 0:
        partes.append(f"prazo estendido {delta_prazo} dias")
    elif delta_prazo < 0:
        partes.append(f"prazo reduzido {abs(delta_prazo)} dias")

    if aditivo["motivo_aditivo"]:
        partes.append(f"motivo: {aditivo['motivo_aditivo']}")

    return " · ".join(partes)


def _contratos_da_obra(obra):
    contrato_principal = query_one(
        """
        SELECT c.*, cl.nome_completo AS cliente_nome
        FROM contratos c
        LEFT JOIN clientes cl ON cl.id = c.cliente_id
        WHERE c.obra_id = ?
          AND c.empresa_id = ?
          AND c.tipo_contrato != 'aditivo'
          AND c.status != 'cancelado'
        ORDER BY
          CASE c.status
            WHEN 'assinado' THEN 1
            WHEN 'aguardando_assinatura' THEN 2
            WHEN 'aditivado' THEN 3
            WHEN 'rascunho' THEN 4
            ELSE 5
          END,
          c.created_at DESC,
          c.id DESC
        LIMIT 1
        """,
        (obra["id"], obra["empresa_id"]),
    )

    if not contrato_principal:
        return None, [], [], None

    aditivos = query_all(
        """
        SELECT c.*, cl.nome_completo AS cliente_nome
        FROM contratos c
        LEFT JOIN clientes cl ON cl.id = c.cliente_id
        WHERE c.contrato_origem_id = ?
          AND c.empresa_id = ?
        ORDER BY COALESCE(c.versao, 1) ASC, c.created_at ASC, c.id ASC
        """,
        (contrato_principal["id"], obra["empresa_id"]),
    )

    timeline = [
        {
            "contrato": contrato_principal,
            "rotulo": "Contrato original",
            "versao": contrato_principal["versao"] or 1,
            "resumo": formatar_moeda(contrato_principal["valor_total"] or 0),
            "data": _data_contrato_documento(contrato_principal),
            "pdf_path": contrato_principal["pdf_path"],
        }
    ]

    anterior = contrato_principal
    for indice, aditivo in enumerate(aditivos, start=1):
        timeline.append(
            {
                "contrato": aditivo,
                "rotulo": f"Aditivo {indice}",
                "versao": aditivo["versao"] or ((contrato_principal["versao"] or 1) + indice),
                "resumo": _resumo_aditivo(aditivo, anterior),
                "data": _data_contrato_documento(aditivo),
                "pdf_path": aditivo["pdf_path"],
            }
        )
        anterior = aditivo

    valor_original = contrato_principal["valor_total"] or 0
    valor_atualizado = timeline[-1]["contrato"]["valor_total"] or valor_original
    if not aditivos or valor_atualizado == valor_original:
        valor_atualizado = None

    return contrato_principal, aditivos, timeline, valor_atualizado


# ─── Listagem ─────────────────────────────────────────────────────────────────

@obras_bp.route("/obras")
def obras():
    if not usuario_logado() or not pode_visualizar():
        return redirect(url_for("auth_bp.login"))

    filtros = obter_filtros_obras()
    lista_obras = enriquecer_resumo_financeiro_obras(
        buscar_obras_filtradas(busca=filtros["busca"], status=filtros["status"])
    )
    proximo_codigo = gerar_codigo_obra()
    empresas = listar_empresas(apenas_ativas=True) if tem_acesso_global() else []

    return render_template(
        "obras.html",
        obras=lista_obras,
        empresas=empresas,
        proximo_codigo=proximo_codigo,
        filtro_busca=filtros["busca"],
        filtro_status=filtros["status"]
    )


@obras_bp.route("/obras/dados")
def obras_dados():
    if not usuario_logado() or not pode_visualizar():
        return jsonify({"erro": "não autorizado"}), 401

    filtros = obter_filtros_obras()
    lista_obras = enriquecer_resumo_financeiro_obras(
        buscar_obras_filtradas(busca=filtros["busca"], status=filtros["status"])
    )

    return jsonify({
        "filtros": {
            "busca": filtros["busca"],
            "status": filtros["status"] or "todas",
        },
        "total": len(lista_obras),
        "obras": serializar_obras(lista_obras),
        "pode_editar": eh_gestor(),
        "pode_excluir": eh_gestor(),
    })


# ─── Nova obra ────────────────────────────────────────────────────────────────

@obras_bp.route("/obras/nova", methods=["POST"])
def nova_obra():
    if not usuario_logado() or not eh_gestor():
        flash("Você não tem permissão para cadastrar obras.", "erro")
        return redirect(url_for("obras_bp.obras"))

    try:
        codigo              = limpar_texto(request.form.get("codigo", ""), max_len=40)
        nome                = limpar_texto(request.form.get("nome", ""), max_len=140, obrigatorio=True, campo="Nome")
        tipologia           = limpar_texto(request.form.get("tipologia", ""), max_len=100, obrigatorio=True, campo="Tipologia")
        tipo_obra           = limpar_texto(request.form.get("tipo_obra", "contrato"), max_len=30).lower()
        data_inicio         = limpar_texto(request.form.get("data_inicio", ""), max_len=10)
        data_fim_prevista   = limpar_texto(request.form.get("data_fim_prevista", ""), max_len=10)
        status              = limpar_texto(request.form.get("status", ""), max_len=60, obrigatorio=True, campo="Status")
    except ValueError as e:
        flash(str(e), "erro")
        return redirect(url_for("obras_bp.obras"))
    area_m2             = request.form.get("area_m2", "").strip()
    orcamento           = request.form.get("orcamento", "").strip()
    receita_total       = request.form.get("receita_total", "").strip()

    if not codigo:
        codigo = gerar_codigo_obra()

    if not nome or not tipologia or not status:
        flash("Preencha os campos obrigatórios da obra.", "erro")
        return redirect(url_for("obras_bp.obras"))

    if tipo_obra not in ["venda", "contrato"]:
        tipo_obra = "contrato"

    empresa_id = empresa_id_para_insert(request.form.get("empresa_id"))

    existe = query_one("SELECT id FROM obras WHERE codigo = ?", (codigo,))
    if existe:
        flash("Já existe uma obra com esse código.", "erro")
        return redirect(url_for("obras_bp.obras"))

    try:
        area_valor       = float(area_m2) if area_m2 else 0
        orcamento_valor  = parse_valor_monetario(orcamento)
        receita_valor    = parse_valor_monetario(receita_total)
        progresso_valor  = 0

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
            empresa_id, codigo, nome, endereco, tipologia, tipo_obra, fase_obra, area_m2,
            data_inicio, data_fim_prevista, orcamento, receita_total,
            progresso_percentual, status, observacao_responsavel, foto_capa
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            empresa_id, codigo, nome, None, tipologia, tipo_obra, None,
            area_valor, data_inicio or None, data_fim_prevista or None,
            orcamento_valor, receita_valor, progresso_valor, status,
            None, None
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
    if not usuario_logado() or not pode_visualizar():
        return redirect(url_for("auth_bp.login"))

    obra = obter_obra_acessivel(codigo=codigo, campos="o.*, e.nome AS empresa_nome")
    if not obra:
        flash("Obra não encontrada.", "erro")
        return redirect(url_for("obras_bp.obras"))

    custos           = query_all("SELECT * FROM custos WHERE obra_id = ? AND empresa_id = ? ORDER BY id DESC", (obra["id"], obra["empresa_id"]))
    medicoes         = query_all("SELECT * FROM medicoes WHERE obra_id = ? AND empresa_id = ? ORDER BY id DESC", (obra["id"], obra["empresa_id"]))
    equipe           = query_all("SELECT * FROM equipe WHERE obra_id = ? AND empresa_id = ? ORDER BY id DESC", (obra["id"], obra["empresa_id"]))
    compras          = [
        c for c in custos
        if (c["categoria"] or "") == "Material"
        and (c["status_entrega"] or c["data_entrega_prevista"] or c["quantidade"] or c["valor_unitario"])
    ]
    fotos_obra       = query_all("SELECT * FROM fotos_obra WHERE obra_id = ? AND empresa_id = ? ORDER BY id DESC", (obra["id"], obra["empresa_id"]))
    atualizacoes_cliente = query_all("""
        SELECT l.id, l.descricao, l.data_hora, u.nome AS autor
        FROM logs l
        LEFT JOIN usuarios u ON l.usuario_id = u.id
        WHERE l.entidade = 'obra'
          AND l.entidade_id = ?
          AND l.empresa_id = ?
          AND l.acao = 'atualizacao_canteiro'
          AND l.descricao LIKE 'Atualização para o cliente:%'
        ORDER BY l.data_hora DESC
    """, (obra["id"], obra["empresa_id"]))
    custos_importados = query_all(
        "SELECT * FROM custos_importados_categoria WHERE obra_id = ? AND empresa_id = ? ORDER BY categoria ASC",
        (obra["id"], obra["empresa_id"])
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
        fases_obra_opcoes=FASES_OBRA_PADRAO,
        fotos_obra=fotos_obra,
        atualizacoes_cliente=atualizacoes_cliente,
    )


@obras_bp.route("/obra/<codigo>/detalhes")
def obra_detalhes(codigo):
    if not usuario_logado() or not pode_visualizar():
        return redirect(url_for("auth_bp.login"))

    obra = obter_obra_acessivel(codigo=codigo, campos="o.*, e.nome AS empresa_nome")
    if not obra:
        flash("Obra não encontrada.", "erro")
        return redirect(url_for("obras_bp.obras"))

    custos = query_all("SELECT * FROM custos WHERE obra_id = ? AND empresa_id = ? ORDER BY id DESC", (obra["id"], obra["empresa_id"]))
    medicoes = query_all("SELECT * FROM medicoes WHERE obra_id = ? AND empresa_id = ? ORDER BY id DESC", (obra["id"], obra["empresa_id"]))
    equipe = query_all("SELECT * FROM equipe WHERE obra_id = ? AND empresa_id = ? ORDER BY id DESC", (obra["id"], obra["empresa_id"]))
    compras = [
        c for c in custos
        if (c["categoria"] or "") == "Material"
        and (c["status_entrega"] or c["data_entrega_prevista"] or c["quantidade"] or c["valor_unitario"])
    ]
    fornecedores_where, fornecedores_params = where_empresa()
    fornecedores = query_all(
        f"SELECT * FROM fornecedores {fornecedores_where} ORDER BY nome ASC",
        fornecedores_params,
    )
    empresas = listar_empresas(apenas_ativas=True) if tem_acesso_global() else []
    fotos_obra = query_all("SELECT * FROM fotos_obra WHERE obra_id = ? AND empresa_id = ? ORDER BY id DESC", (obra["id"], obra["empresa_id"]))
    custos_importados = query_all(
        "SELECT * FROM custos_importados_categoria WHERE obra_id = ? AND empresa_id = ? ORDER BY categoria ASC",
        (obra["id"], obra["empresa_id"])
    )

    custo_total = sum((c["valor_total"] or 0) for c in custos)
    margem = (obra["receita_total"] or 0) - custo_total
    lucro_previsto = (obra["receita_total"] or 0) - (obra["orcamento"] or 0)
    custos_por_categoria = {}
    for custo in custos:
        categoria = custo["categoria"] or "Sem categoria"
        custos_por_categoria[categoria] = custos_por_categoria.get(categoria, 0) + (custo["valor_total"] or 0)

    contrato_ativo, aditivos_contrato, historico_contratos, valor_contrato_atualizado = _contratos_da_obra(obra)
    fase_logs = query_all(
        """
        SELECT l.id, l.data_hora, l.descricao, u.nome AS autor
        FROM logs l
        LEFT JOIN usuarios u ON l.usuario_id = u.id
        WHERE l.entidade = 'obra'
          AND l.entidade_id = ?
          AND l.empresa_id = ?
          AND l.acao = 'fase_obra_atualizada'
        ORDER BY COALESCE(l.data_hora, '') ASC, l.id ASC
        """,
        (obra["id"], obra["empresa_id"]),
    )

    fase_timeline = []
    for item in fase_logs:
        descricao = (item["descricao"] or "").strip()
        fase = descricao.split(":", 1)[1].strip() if ":" in descricao else descricao
        fase_timeline.append(
            {
                "fase": fase or "Fase atualizada",
                "data_hora": item["data_hora"],
                "autor": item["autor"] or "Sistema",
            }
        )

    if not fase_timeline:
        logs_legado = query_all(
            """
            SELECT l.id, l.data_hora, l.descricao, u.nome AS autor
            FROM logs l
            LEFT JOIN usuarios u ON l.usuario_id = u.id
            WHERE l.entidade = 'obra'
              AND l.entidade_id = ?
              AND l.empresa_id = ?
              AND l.acao = 'atualizacao_canteiro'
            ORDER BY COALESCE(l.data_hora, '') ASC, l.id ASC
            """,
            (obra["id"], obra["empresa_id"]),
        )
        for item in logs_legado:
            descricao = (item["descricao"] or "").strip()
            marcador = "Fase atual:"
            if marcador not in descricao:
                continue
            fase = descricao.split(marcador, 1)[1].split(".", 1)[0].strip()
            if not fase:
                continue
            fase_timeline.append(
                {
                    "fase": fase,
                    "data_hora": item["data_hora"],
                    "autor": item["autor"] or "Sistema",
                }
            )

    medicoes_ordenadas = sorted(
        medicoes,
        key=lambda m: (m["data_medicao"] or "", m["id"] or 0)
    )
    medicao_labels = [
        m["medicao_nome"] or m["etapa"] or m["data_medicao"] or f"Medição {i + 1}"
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
        empresas=empresas,
        categorias_custo=CATEGORIAS_CUSTO_VALIDAS,
        custos_importados=custos_importados,
        fotos_obra=fotos_obra,
        custo_total=custo_total,
        margem=margem,
        lucro_previsto=lucro_previsto,
        fases_obra_opcoes=FASES_OBRA_PADRAO,
        contrato_ativo=contrato_ativo,
        aditivos_contrato=aditivos_contrato,
        historico_contratos=historico_contratos,
        valor_contrato_atualizado=valor_contrato_atualizado,
        fase_timeline=fase_timeline,
        chart_custo_cat_labels=list(custos_por_categoria.keys()),
        chart_custo_cat_valores=list(custos_por_categoria.values()),
        chart_medicao_labels=medicao_labels,
        chart_medicao_percentuais=medicao_percentuais,
        chart_medicao_valores=medicao_valores,
    )


@obras_bp.route("/obras/<int:obra_id>/fotos/nova", methods=["POST"])
def nova_foto_obra(obra_id):
    redirect_to = caminho_redirecionamento_seguro(request.form.get("redirect_to"), "")
    if not usuario_logado() or not eh_gestor():
        flash("Você não tem permissão para adicionar fotos.", "erro")
        return redirect(redirect_to or url_for("obras_bp.obras"))

    obra = obter_obra_acessivel(
        obra_id=obra_id,
        campos="o.id, o.codigo, o.nome, o.empresa_id, o.proxima_etapa_portal",
    )
    if not obra:
        flash("Obra não encontrada.", "erro")
        return redirect(redirect_to or url_for("obras_bp.obras"))

    arquivo = request.files.get("foto_arquivo")
    try:
        caminho = limpar_texto(request.form.get("caminho", ""), max_len=500)
        titulo = limpar_texto(request.form.get("titulo", ""), max_len=140)
        fase = limpar_texto(request.form.get("fase", ""), max_len=120)
        data_registro = limpar_texto(request.form.get("data_registro", ""), max_len=10)
    except ValueError as e:
        flash(str(e), "erro")
        return redirect(redirect_to or url_for("obras_bp.obra_detalhe", codigo=obra["codigo"]))
    usar_como_capa = request.form.get("usar_como_capa") == "1"
    publicar_portal = 1 if "1" in request.form.getlist("publicar_portal") else 0

    if arquivo and arquivo.filename:
        if not extensao_permitida(arquivo.filename):
            flash("Envie uma imagem nos formatos PNG, JPG, JPEG, WEBP ou GIF.", "erro")
            return redirect(redirect_to or url_for("obras_bp.obra_detalhe", codigo=obra["codigo"]))

        UPLOAD_OBRAS_DIR.mkdir(parents=True, exist_ok=True)
        nome_seguro = secure_filename(arquivo.filename)
        nome_arquivo = f"obra-{obra_id}-{uuid4().hex[:8]}-{nome_seguro}"
        destino = UPLOAD_OBRAS_DIR / nome_arquivo
        arquivo.save(destino)
        caminho = f"/static/uploads/obras/{nome_arquivo}"

    if not caminho:
        flash("Selecione uma foto do seu dispositivo para adicionar à galeria.", "erro")
        return redirect(redirect_to or url_for("obras_bp.obra_detalhe", codigo=obra["codigo"]))

    foto_id = execute(
        """
        INSERT INTO fotos_obra (empresa_id, obra_id, caminho, titulo, fase, publicar_portal, data_registro)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            obra["empresa_id"],
            obra_id,
            caminho,
            titulo or None,
            fase or None,
            publicar_portal,
            data_registro or None,
        )
    )

    registrar_log(
        acao="foto_galeria",
        entidade="obra",
        entidade_id=obra_id,
        descricao=f"Foto adicionada à galeria da obra: {obra['nome']}"
    )

    if usar_como_capa:
        execute(
            "UPDATE obras SET foto_capa = ? WHERE id = ? AND empresa_id = ?",
            (caminho, obra_id, obra["empresa_id"])
        )

    flash("Foto adicionada à galeria com sucesso.", "sucesso")
    return redirect(redirect_to or url_for("obras_bp.obra_detalhe", codigo=obra["codigo"]))


@obras_bp.route("/obras/<int:obra_id>/fotos/<int:foto_id>/capa", methods=["POST"])
def usar_foto_como_capa(obra_id, foto_id):
    redirect_to = caminho_redirecionamento_seguro(request.form.get("redirect_to"), "")
    if not usuario_logado() or not eh_gestor():
        flash("Você não tem permissão para alterar a capa.", "erro")
        return redirect(redirect_to or url_for("obras_bp.obras"))

    obra = obter_obra_acessivel(
        obra_id=obra_id,
        campos="o.id, o.codigo, o.nome, o.empresa_id, o.proxima_etapa_portal",
    )
    if not obra:
        flash("Obra não encontrada.", "erro")
        return redirect(redirect_to or url_for("obras_bp.obras"))

    foto = query_one(
        "SELECT caminho FROM fotos_obra WHERE id = ? AND obra_id = ? AND empresa_id = ?",
        (foto_id, obra_id, obra["empresa_id"])
    )
    if not foto:
        flash("Foto não encontrada na galeria.", "erro")
        return redirect(redirect_to or url_for("obras_bp.obra_detalhe", codigo=obra["codigo"]))

    execute("UPDATE obras SET foto_capa = ? WHERE id = ? AND empresa_id = ?", (foto["caminho"], obra_id, obra["empresa_id"]))
    registrar_log(
        acao="foto_capa",
        entidade="obra",
        entidade_id=obra_id,
        descricao=f"Foto da galeria definida como capa da obra: {obra['nome']}"
    )

    flash("Foto definida como capa da Visão do Canteiro.", "sucesso")
    return redirect(redirect_to or url_for("obras_bp.obra_detalhe", codigo=obra["codigo"]))


# ─── Editar ──────────────────────────────────────────────────────────────────

@obras_bp.route("/obras/<int:obra_id>/fotos/<int:foto_id>/publicacao", methods=["POST"])
def atualizar_publicacao_foto_obra(obra_id, foto_id):
    redirect_to = caminho_redirecionamento_seguro(request.form.get("redirect_to"), "")
    if not usuario_logado() or not eh_gestor():
        flash("Você não tem permissão para alterar a publicação de fotos.", "erro")
        return redirect(redirect_to or url_for("obras_bp.obras"))

    obra = obter_obra_acessivel(obra_id=obra_id, campos="o.id, o.codigo, o.nome, o.empresa_id, o.proxima_etapa_portal")
    if not obra:
        flash("Obra não encontrada.", "erro")
        return redirect(redirect_to or url_for("obras_bp.obras"))

    foto = query_one(
        "SELECT id FROM fotos_obra WHERE id = ? AND obra_id = ? AND empresa_id = ?",
        (foto_id, obra_id, obra["empresa_id"])
    )
    if not foto:
        flash("Foto não encontrada na galeria.", "erro")
        return redirect(redirect_to or url_for("obras_bp.obra_detalhe", codigo=obra["codigo"]))

    publicar_portal = 1 if "1" in request.form.getlist("publicar_portal") else 0
    execute(
        "UPDATE fotos_obra SET publicar_portal = ? WHERE id = ? AND obra_id = ? AND empresa_id = ?",
        (publicar_portal, foto_id, obra_id, obra["empresa_id"])
    )

    registrar_log(
        acao="foto_publicacao_portal",
        entidade="obra",
        entidade_id=obra_id,
        descricao=f"Publicação da foto no portal {'ativada' if publicar_portal else 'desativada'}: {obra['nome']}"
    )

    flash(
        "Foto publicada no portal do cliente." if publicar_portal else "Foto mantida apenas para uso interno.",
        "sucesso",
    )
    return redirect(redirect_to or url_for("obras_bp.obra_detalhe", codigo=obra["codigo"]))


@obras_bp.route("/obras/<int:obra_id>/fotos/<int:foto_id>/excluir", methods=["POST"])
def excluir_foto_obra(obra_id, foto_id):
    redirect_to = caminho_redirecionamento_seguro(request.form.get("redirect_to"), "")
    if not usuario_logado() or not eh_gestor():
        flash("Você não tem permissão para excluir fotos.", "erro")
        return redirect(redirect_to or url_for("obras_bp.obras"))

    obra = obter_obra_acessivel(obra_id=obra_id, campos="o.id, o.codigo, o.nome, o.foto_capa, o.empresa_id")
    if not obra:
        flash("Obra não encontrada.", "erro")
        return redirect(redirect_to or url_for("obras_bp.obras"))

    foto = query_one(
        "SELECT id, caminho FROM fotos_obra WHERE id = ? AND obra_id = ? AND empresa_id = ?",
        (foto_id, obra_id, obra["empresa_id"])
    )
    if not foto:
        flash("Foto não encontrada na galeria.", "erro")
        return redirect(redirect_to or url_for("obras_bp.obra_detalhe", codigo=obra["codigo"]))

    execute("DELETE FROM fotos_obra WHERE id = ? AND obra_id = ? AND empresa_id = ?", (foto_id, obra_id, obra["empresa_id"]))

    if obra["foto_capa"] == foto["caminho"]:
        execute("UPDATE obras SET foto_capa = NULL WHERE id = ? AND empresa_id = ?", (obra_id, obra["empresa_id"]))

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

    flash("Foto excluída da galeria.", "sucesso")
    return redirect(redirect_to or url_for("obras_bp.obra_detalhe", codigo=obra["codigo"]))


@obras_bp.route("/obras/<int:obra_id>/canteiro", methods=["POST"])
def atualizar_canteiro_obra(obra_id):
    redirect_to = caminho_redirecionamento_seguro(request.form.get("redirect_to"), "")
    if not usuario_logado() or not eh_gestor():
        flash("Você não tem permissão para atualizar o canteiro.", "erro")
        return redirect(redirect_to or url_for("obras_bp.obras"))

    obra = obter_obra_acessivel(
        obra_id=obra_id,
        campos="o.id, o.codigo, o.nome, o.empresa_id, o.fase_obra, o.proxima_etapa_portal",
    )
    if not obra:
        flash("Obra não encontrada.", "erro")
        return redirect(redirect_to or url_for("obras_bp.obras"))

    try:
        fase_obra = limpar_texto(request.form.get("fase_obra", ""), max_len=120)
        observacao = limpar_texto(request.form.get("observacao_responsavel", ""), max_len=1000)
        if "proxima_etapa_portal" in request.form:
            proxima_etapa_portal = limpar_texto(request.form.get("proxima_etapa_portal", ""), max_len=160)
        else:
            proxima_etapa_portal = obra["proxima_etapa_portal"] if "proxima_etapa_portal" in obra.keys() else None
    except ValueError as e:
        flash(str(e), "erro")
        return redirect(redirect_to or url_for("obras_bp.obra_detalhe", codigo=obra["codigo"]))
    progresso_percentual = request.form.get("progresso_percentual", "").strip()
    atualizar_status_concluida = (request.form.get("atualizar_status_concluida", "0") or "").strip() == "1"

    try:
        progresso_valor = parse_valor_monetario(progresso_percentual)
        validar_intervalo_percentual(progresso_valor, "Conclusão (%)")
    except ValueError as e:
        flash(str(e), "erro")
        return redirect(redirect_to or url_for("obras_bp.obra_detalhe", codigo=obra["codigo"]))

    fase_slug = _slug_texto(fase_obra)
    fase_anterior_slug = _slug_texto(obra["fase_obra"] if "fase_obra" in obra.keys() else "")
    deve_atualizar_status = fase_slug == "concluida" and atualizar_status_concluida

    if deve_atualizar_status:
        execute(
            """
            UPDATE obras
            SET fase_obra = ?, progresso_percentual = ?, observacao_responsavel = ?, proxima_etapa_portal = ?, status = ?
            WHERE id = ? AND empresa_id = ?
            """,
            (
                fase_obra or None,
                progresso_valor,
                observacao or None,
                proxima_etapa_portal or None,
                "concluida",
                obra_id,
                obra["empresa_id"],
            )
        )
    else:
        execute(
            """
            UPDATE obras
            SET fase_obra = ?, progresso_percentual = ?, observacao_responsavel = ?, proxima_etapa_portal = ?
            WHERE id = ? AND empresa_id = ?
            """,
            (
                fase_obra or None,
                progresso_valor,
                observacao or None,
                proxima_etapa_portal or None,
                obra_id,
                obra["empresa_id"],
            )
        )

    mensagem_cliente = observacao or f"Fase atual: {fase_obra or 'Atualização em breve'}."
    registrar_log(
        acao="atualizacao_canteiro",
        entidade="obra",
        entidade_id=obra_id,
        descricao=f"Atualização para o cliente: {mensagem_cliente}"
    )
    if fase_obra and fase_slug != fase_anterior_slug:
        registrar_log(
            acao="fase_obra_atualizada",
            entidade="obra",
            entidade_id=obra_id,
            descricao=f"Fase da obra atualizada para: {fase_obra}",
        )

    flash("Avanço do canteiro salvo com sucesso.", "sucesso")
    return redirect(redirect_to or url_for("obras_bp.obra_detalhe", codigo=obra["codigo"]))


@obras_bp.route("/obras/<int:obra_id>/canteiro/atualizacao/<int:log_id>", methods=["POST"])
def editar_atualizacao_canteiro(obra_id, log_id):
    if not usuario_logado() or not eh_gestor():
        flash("Você não tem permissão para editar atualizações do portal.", "erro")
        return redirect(url_for("obras_bp.obras"))

    obra = obter_obra_acessivel(obra_id=obra_id, campos="o.id, o.codigo, o.empresa_id")
    if not obra:
        flash("Obra não encontrada.", "erro")
        return redirect(url_for("obras_bp.obras"))

    try:
        mensagem_cliente = limpar_texto(
            request.form.get("mensagem_cliente", ""),
            max_len=1000,
            obrigatorio=True,
            campo="Atualização do cliente",
        )
    except ValueError as e:
        flash(str(e), "erro")
        return redirect(url_for("obras_bp.obra_detalhe", codigo=obra["codigo"]))

    atualizacao = query_one("""
        SELECT id
        FROM logs
        WHERE id = ?
          AND entidade = 'obra'
          AND entidade_id = ?
          AND empresa_id = ?
          AND acao = 'atualizacao_canteiro'
          AND descricao LIKE 'Atualização para o cliente:%'
    """, (log_id, obra_id, obra["empresa_id"]))
    if not atualizacao:
        flash("Atualização não encontrada.", "erro")
        return redirect(url_for("obras_bp.obra_detalhe", codigo=obra["codigo"]))

    execute(
        "UPDATE logs SET descricao = ? WHERE id = ? AND empresa_id = ?",
        (f"Atualização para o cliente: {mensagem_cliente}", log_id, obra["empresa_id"])
    )

    flash("Atualização do portal editada com sucesso.", "sucesso")
    return redirect(url_for("obras_bp.obra_detalhe", codigo=obra["codigo"]))


@obras_bp.route("/obras/editar/<int:obra_id>", methods=["POST"])
def editar_obra(obra_id):
    redirect_to = caminho_redirecionamento_seguro(request.form.get("redirect_to"), "")
    if not usuario_logado() or not eh_gestor():
        flash("Você não tem permissão para editar obras.", "erro")
        return redirect(redirect_to or url_for("obras_bp.obras"))

    obra = obter_obra_acessivel(obra_id=obra_id, campos="o.*")
    if not obra:
        flash("Obra não encontrada.", "erro")
        return redirect(redirect_to or url_for("obras_bp.obras"))

    veio_do_detalhe = obra and (
        "obra_detalhe" in (request.referrer or "") or
        f"/obra/" in (request.referrer or "")
    )

    try:
        nome = limpar_texto(request.form.get("nome", ""), max_len=140, obrigatorio=True, campo="Nome")
        endereco = limpar_texto(request.form.get("endereco", ""), max_len=240)
        tipologia = limpar_texto(request.form.get("tipologia", ""), max_len=100, obrigatorio=True, campo="Tipologia")
        tipo_obra = limpar_texto(request.form.get("tipo_obra", "contrato"), max_len=30).lower()
        data_inicio = limpar_texto(request.form.get("data_inicio", ""), max_len=10)
        data_fim_prevista = limpar_texto(request.form.get("data_fim_prevista", ""), max_len=10)
        status = limpar_texto(request.form.get("status", ""), max_len=60, obrigatorio=True, campo="Status")
    except ValueError as e:
        flash(str(e), "erro")
        if redirect_to:
            return redirect(redirect_to)
        if obra and veio_do_detalhe:
            return redirect(url_for("obras_bp.obra_detalhe", codigo=obra["codigo"]))
        return redirect(url_for("obras_bp.obras"))

    area_m2 = request.form.get("area_m2", "").strip()
    orcamento = request.form.get("orcamento", "").strip()
    receita_total = request.form.get("receita_total", "").strip()

    if tipo_obra not in ["venda", "contrato"]:
        tipo_obra = "contrato"

    empresa_id = empresa_id_para_insert(request.form.get("empresa_id")) if eh_admin() else obra["empresa_id"]

    try:
        area_valor = float(area_m2) if area_m2 else 0
        orcamento_valor = parse_valor_monetario(orcamento)
        receita_valor = parse_valor_monetario(receita_total)

        if valor_negativo(area_valor):
            raise ValueError("Área não pode ser negativa.")
        if valor_negativo(orcamento_valor):
            raise ValueError("Custo previsto não pode ser negativo.")
        if valor_negativo(receita_valor):
            raise ValueError("Receita prevista não pode ser negativa.")
    except ValueError as e:
        flash(str(e), "erro")
        if redirect_to:
            return redirect(redirect_to)
        if obra and veio_do_detalhe:
            return redirect(url_for("obras_bp.obra_detalhe", codigo=obra["codigo"]))
        return redirect(url_for("obras_bp.obras"))

    execute(
        """
        UPDATE obras
        SET empresa_id = ?, nome = ?, endereco = ?, tipologia = ?, tipo_obra = ?,
            area_m2 = ?, data_inicio = ?, data_fim_prevista = ?,
            orcamento = ?, receita_total = ?, status = ?
        WHERE id = ? AND empresa_id = ?
        """,
        (
            empresa_id, nome, endereco or None, tipologia, tipo_obra,
            area_valor, data_inicio or None, data_fim_prevista or None,
            orcamento_valor, receita_valor, status, obra_id, obra["empresa_id"]
        )
    )

    if empresa_id != obra["empresa_id"]:
        sincronizar_empresa_filhos_obra(obra_id, empresa_id)

    registrar_log(
        acao="edicao",
        entidade="obra",
        entidade_id=obra_id,
        descricao=f"Obra atualizada: {nome}"
    )

    flash("Obra atualizada com sucesso.", "sucesso")

    if redirect_to:
        return redirect(redirect_to)
    if obra and veio_do_detalhe:
        return redirect(url_for("obras_bp.obra_detalhe", codigo=obra["codigo"]))
    return redirect(url_for("obras_bp.obras"))

# ─── Exportar ────────────────────────────────────────────────────────────────

@obras_bp.route("/obras/exportar")
def obras_exportar():
    if not usuario_logado() or not pode_visualizar():
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
    if not usuario_logado() or not eh_gestor():
        flash("Você não tem permissão para excluir obras.", "erro")
        return redirect(url_for("obras_bp.obras"))

    obra = obter_obra_acessivel(obra_id=obra_id, campos="o.id, o.empresa_id")
    if not obra:
        flash("Obra não encontrada.", "erro")
        return redirect(url_for("obras_bp.obras"))

    execute("DELETE FROM custos WHERE obra_id = ? AND empresa_id = ?", (obra_id, obra["empresa_id"]))
    execute("DELETE FROM medicoes WHERE obra_id = ? AND empresa_id = ?", (obra_id, obra["empresa_id"]))
    execute("DELETE FROM equipe WHERE obra_id = ? AND empresa_id = ?", (obra_id, obra["empresa_id"]))
    execute("DELETE FROM compras WHERE obra_id = ? AND empresa_id = ?", (obra_id, obra["empresa_id"]))
    execute("DELETE FROM custos_importados_categoria WHERE obra_id = ? AND empresa_id = ?", (obra_id, obra["empresa_id"]))
    execute("DELETE FROM fotos_obra WHERE obra_id = ? AND empresa_id = ?", (obra_id, obra["empresa_id"]))
    execute("DELETE FROM obras WHERE id = ? AND empresa_id = ?", (obra_id, obra["empresa_id"]))

    registrar_log(
        acao="exclusão",
        entidade="obra",
        entidade_id=obra_id,
        descricao="Obra excluída"
    )

    flash("Obra excluída com sucesso.", "sucesso")
    return redirect(url_for("obras_bp.obras"))
