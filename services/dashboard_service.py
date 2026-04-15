from datetime import datetime
from database import query_all, query_one
from utils import calcular_media_fornecedor
from services.validators import data_no_periodo


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
        custo_previsto = obra["orcamento"] or 0
        progresso = obra["progresso_percentual"] or 0
        status = (obra["status"] or "").lower()

        if receita > 0 and custo_total > receita:
            adicionar_alerta("danger", obra["codigo"], obra["nome"], "Resultado negativo. O custo já superou a receita prevista da obra.")

        if custo_previsto > 0 and custo_total > custo_previsto * 1.05:
            adicionar_alerta("warn", obra["codigo"], obra["nome"], "Custo realizado acima do custo previsto.")

        if receita > 0 and custo_total >= receita * 0.90:
            adicionar_alerta("warn", obra["codigo"], obra["nome"], "Custo já consumiu 90% ou mais da receita prevista.")

        if status == "atrasada":
            adicionar_alerta("danger", obra["codigo"], obra["nome"], "Obra marcada como atrasada. Verifique cronograma.")

        if status == "andamento" and progresso == 0:
            adicionar_alerta("warn", obra["codigo"], obra["nome"], "Obra em andamento, mas com execução física zerada.")

        data_fim_prevista = obra["data_fim_prevista"]
        if data_fim_prevista and status not in ["concluida", "vendida"]:
            try:
                data_final = datetime.strptime(data_fim_prevista, "%Y-%m-%d").date()
                dias_restantes = (data_final - hoje).days

                if 0 <= dias_restantes <= 7:
                    adicionar_alerta("warn", obra["codigo"], obra["nome"], f"Obra próxima do prazo final. Restam {dias_restantes} dia(s).")

                if dias_restantes < 0:
                    adicionar_alerta("danger", obra["codigo"], obra["nome"], "Data final prevista já foi ultrapassada.")
            except Exception:
                pass

    if obra_ids_filtradas:
        equipe = [p for p in equipe if p["obra_id"] in obra_ids_filtradas]

    for profissional in equipe:
        if (profissional["status_pagamento"] or "").lower() == "pendente":
            adicionar_alerta("warn", "EQUIPE", profissional["nome"], f"Pagamento pendente para {profissional['nome']}.")

    return alertas


def calcular_kpis_dashboard(filtro_obra="", filtro_categoria="", filtro_status="", filtro_tipo_obra="", data_inicio="", data_fim=""):
    obras = query_all("SELECT * FROM obras ORDER BY id DESC")
    custos = query_all("SELECT * FROM custos ORDER BY id DESC")
    fornecedores = query_all("SELECT * FROM fornecedores ORDER BY id DESC")
    medicoes = query_all("SELECT * FROM medicoes ORDER BY id DESC")
    custos_importados = query_all("SELECT * FROM custos_importados_categoria ORDER BY id DESC")

    if filtro_obra:
        obras = [o for o in obras if o["codigo"] == filtro_obra]

    if filtro_status:
        obras = [o for o in obras if (o["status"] or "") == filtro_status]

    if filtro_tipo_obra:
        obras = [o for o in obras if (o["tipo_obra"] or "contrato") == filtro_tipo_obra]

    obra_ids_filtradas = [o["id"] for o in obras]

    custos = [c for c in custos if c["obra_id"] in obra_ids_filtradas] if obra_ids_filtradas else []

    if filtro_categoria:
        custos = [c for c in custos if (c["categoria"] or "") == filtro_categoria]

    custos = [
        c for c in custos
        if data_no_periodo(c["data_lancamento"] if c["data_lancamento"] else "", data_inicio, data_fim)
    ]

    medicoes = [m for m in medicoes if m["obra_id"] in obra_ids_filtradas] if obra_ids_filtradas else []

    medicoes = [
        m for m in medicoes
        if data_no_periodo(m["data_medicao"] if m["data_medicao"] else "", data_inicio, data_fim)
    ]

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
    tipo_obra_count = {}

    for custo in custos:
        cat = custo["categoria"] or "Sem categoria"
        valor = custo["valor_total"] or 0
        custos_por_categoria[cat] = custos_por_categoria.get(cat, 0) + valor

    for item in custos_importados:
        cat = item["categoria"] or "Sem categoria"
        valor = item["valor_total"] or 0
        custos_importados_por_categoria[cat] = custos_importados_por_categoria.get(cat, 0) + valor

    todas_categorias = sorted(set(list(custos_por_categoria.keys()) + list(custos_importados_por_categoria.keys())))

    for categoria in todas_categorias:
        valor_importado = custos_importados_por_categoria.get(categoria, 0)
        valor_lancado = custos_por_categoria.get(categoria, 0)
        diferenca = valor_lancado - valor_importado

        desvio_percentual = (diferenca / valor_importado * 100) if valor_importado > 0 else 0

        comparativo_categorias.append({
            "categoria": categoria,
            "importado": valor_importado,
            "lancado": valor_lancado,
            "diferenca": diferenca,
            "desvio_percentual": desvio_percentual
        })

    for obra in obras:
        custo_obra = sum((c["valor_total"] or 0) for c in custos if c["obra_id"] == obra["id"])
        total_custo += custo_obra

        tipo_obra = obra["tipo_obra"] or "contrato"
        receita_contexto = "Venda prevista" if tipo_obra == "venda" else "Contrato previsto"

        margem_por_obra.append({
            "codigo": obra["codigo"],
            "nome": obra["nome"],
            "tipologia": obra["tipologia"],
            "tipo_obra": tipo_obra,
            "receita_contexto": receita_contexto,
            "status": obra["status"],
            "execucao": obra["progresso_percentual"] or 0,
            "margem_valor": (obra["receita_total"] or 0) - custo_obra,
            "lucro_previsto": (obra["receita_total"] or 0) - (obra["orcamento"] or 0)
        })

        tipo = obra["tipologia"] or "Não informado"
        tipologia_count[tipo] = tipologia_count.get(tipo, 0) + 1

        tipo_obra_count[tipo_obra] = tipo_obra_count.get(tipo_obra, 0) + 1

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
        "tipo_obra_count": tipo_obra_count,
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