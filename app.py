from flask import Flask
from database import init_db
from utils import formatar_moeda, calcular_media_fornecedor, formatar_tipo_obra

from auth import (
    criar_usuario_admin,
    eh_admin,
    eh_gestor,
    eh_leitura,
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
    return dict(
        formatar_moeda=formatar_moeda,
        calcular_media_fornecedor=calcular_media_fornecedor,
        formatar_tipo_obra=formatar_tipo_obra,
        eh_admin=eh_admin,
        eh_gestor=eh_gestor,
        eh_leitura=eh_leitura,
        usuario_perfil=usuario_perfil,
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