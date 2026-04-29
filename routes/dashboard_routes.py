import pandas as pd
from io import BytesIO
from flask import Blueprint, render_template, request, redirect, url_for, send_file, jsonify
from database import query_all
from services.dashboard_service import calcular_kpis_dashboard, calcular_alertas, serializar_dashboard_json
from auth import usuario_logado, eh_leitura
from services.tenant import where_empresa

dashboard_bp = Blueprint("dashboard_bp", __name__)


def obter_filtros_dashboard():
    return {
        "filtro_obra": request.args.get("obra", "").strip(),
        "filtro_categoria": request.args.get("categoria", "").strip(),
        "filtro_status": request.args.get("status", "").strip(),
        "filtro_tipo_obra": request.args.get("tipo_obra", "").strip(),
        "data_inicio": request.args.get("data_inicio", "").strip(),
        "data_fim": request.args.get("data_fim", "").strip(),
    }


@dashboard_bp.route("/dashboard")
def dashboard():
    if not usuario_logado() or not eh_leitura():
        return redirect(url_for("auth_bp.login"))

    filtros = obter_filtros_dashboard()

    dados = calcular_kpis_dashboard(
        filtro_obra=filtros["filtro_obra"],
        filtro_categoria=filtros["filtro_categoria"],
        filtro_status=filtros["filtro_status"],
        filtro_tipo_obra=filtros["filtro_tipo_obra"],
        data_inicio=filtros["data_inicio"],
        data_fim=filtros["data_fim"]
    )

    where_obras, params_obras = where_empresa()
    todas_obras = query_all(f"SELECT * FROM obras {where_obras} ORDER BY codigo ASC", params_obras)
    where_custos, params_custos = where_empresa()
    todas_categorias_rows = query_all(
        f"""
        SELECT DISTINCT categoria
        FROM custos
        {where_custos}
        {'AND' if where_custos else 'WHERE'} categoria IS NOT NULL
          AND categoria != ''
        ORDER BY categoria ASC
        """,
        params_custos,
    )
    todas_categorias = [row["categoria"] for row in todas_categorias_rows]

    return render_template(
        "dashboard.html",
        **dados,
        filtro_obra=filtros["filtro_obra"],
        filtro_categoria=filtros["filtro_categoria"],
        filtro_status=filtros["filtro_status"],
        filtro_tipo_obra=filtros["filtro_tipo_obra"],
        data_inicio=filtros["data_inicio"],
        data_fim=filtros["data_fim"],
        todas_obras=todas_obras,
        todas_categorias=todas_categorias
    )


@dashboard_bp.route("/dashboard/dados")
def dashboard_dados():
    if not usuario_logado() or not eh_leitura():
        return jsonify({"erro": "não autorizado"}), 401

    filtros = obter_filtros_dashboard()

    dados = calcular_kpis_dashboard(
        filtro_obra=filtros["filtro_obra"],
        filtro_categoria=filtros["filtro_categoria"],
        filtro_status=filtros["filtro_status"],
        filtro_tipo_obra=filtros["filtro_tipo_obra"],
        data_inicio=filtros["data_inicio"],
        data_fim=filtros["data_fim"]
    )

    payload = serializar_dashboard_json(dados, filtros)
    return jsonify(payload)


@dashboard_bp.route("/dashboard/exportar")
def dashboard_exportar():
    if not usuario_logado() or not eh_leitura():
        return redirect(url_for("auth_bp.login"))

    filtros = obter_filtros_dashboard()

    dados = calcular_kpis_dashboard(
        filtro_obra=filtros["filtro_obra"],
        filtro_categoria=filtros["filtro_categoria"],
        filtro_status=filtros["filtro_status"],
        filtro_tipo_obra=filtros["filtro_tipo_obra"],
        data_inicio=filtros["data_inicio"],
        data_fim=filtros["data_fim"]
    )

    output = BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df_kpis = pd.DataFrame([{
            "Receita Prevista": dados["total_receita"],
            "Custo Realizado": dados["total_custo"],
            "Resultado Atual": dados["margem"],
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


@dashboard_bp.route("/alertas")
def alertas():
    if not usuario_logado() or not eh_leitura():
        return redirect(url_for("auth_bp.login"))

    lista_alertas = calcular_alertas()
    return render_template("alertas.html", alertas=lista_alertas)


@dashboard_bp.route("/logs")
def logs():
    if not usuario_logado() or not eh_leitura():
        return redirect(url_for("auth_bp.login"))

    where_logs, params_logs = where_empresa()
    logs_lista = query_all(f"SELECT * FROM logs {where_logs} ORDER BY data_hora DESC", params_logs)
    return render_template("logs.html", logs=logs_lista)
