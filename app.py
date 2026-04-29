from flask import Flask, request, url_for
from database import init_db
from utils import formatar_moeda, calcular_media_fornecedor, formatar_tipo_obra, formatar_data
from services.dashboard_service import calcular_alertas

from auth import (
    criar_usuario_admin,
    eh_admin,
    eh_gestor,
    eh_leitura,
    usuario_logado,
    usuario_perfil,
)
from routes.auth_routes import auth_bp
from routes.dashboard_routes import dashboard_bp
from routes.obras_routes import obras_bp
from routes.custos_routes import custos_bp
from routes.fornecedores_routes import fornecedores_bp
from routes.compras_routes import compras_bp
from routes.equipe_routes import equipe_bp
from routes.medicoes_routes import medicoes_bp
from routes.importacao_routes import importacao_bp
from routes.portal_routes import portal_bp          # ← NOVO

app = Flask(__name__)
app.secret_key = "chave_super_secreta_trocar_depois"

init_db()
criar_usuario_admin()


@app.context_processor
def inject_helpers():
    alertas_globais = []
    if usuario_logado() and eh_leitura():
        try:
            alertas_globais = calcular_alertas()
        except Exception:
            alertas_globais = []

    export_endpoints = {
        "dashboard_bp.dashboard": "dashboard_bp.dashboard_exportar",
        "obras_bp.obras": "obras_bp.obras_exportar",
        "custos_bp.custos": "custos_bp.custos_exportar",
        "compras_bp.compras": "compras_bp.compras_exportar",
        "fornecedores_bp.fornecedores": "fornecedores_bp.fornecedores_exportar",
        "equipe_bp.equipe": "equipe_bp.equipe_exportar",
        "medicoes_bp.medicoes": "medicoes_bp.medicoes_exportar",
    }
    menu_export_url = None
    export_endpoint = export_endpoints.get(request.endpoint)
    if usuario_logado() and export_endpoint:
        try:
            menu_export_url = url_for(export_endpoint, **request.args.to_dict(flat=True))
        except Exception:
            menu_export_url = None

    return dict(
        formatar_moeda=formatar_moeda,
        formatar_data=formatar_data,
        calcular_media_fornecedor=calcular_media_fornecedor,
        formatar_tipo_obra=formatar_tipo_obra,
        eh_admin=eh_admin,
        eh_gestor=eh_gestor,
        eh_leitura=eh_leitura,
        usuario_perfil=usuario_perfil,
        alertas_globais=alertas_globais,
        menu_export_url=menu_export_url,
    )


app.register_blueprint(auth_bp)
app.register_blueprint(dashboard_bp)
app.register_blueprint(obras_bp)
app.register_blueprint(custos_bp)
app.register_blueprint(fornecedores_bp)
app.register_blueprint(compras_bp)
app.register_blueprint(equipe_bp)
app.register_blueprint(medicoes_bp)
app.register_blueprint(importacao_bp)
app.register_blueprint(portal_bp)                  # ← NOVO


if __name__ == "__main__":
    app.run(debug=True)
