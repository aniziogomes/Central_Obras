from flask import Blueprint, redirect, url_for, request

compras_bp = Blueprint("compras_bp", __name__)


@compras_bp.route("/compras")
def compras():
    return redirect(url_for("custos_bp.custos", categoria="Material"))


@compras_bp.route("/compras/exportar")
def compras_exportar():
    return redirect(url_for("custos_bp.custos_exportar", categoria="Material"))


@compras_bp.route("/compras/nova", methods=["POST"])
def nova_compra():
    return redirect(url_for("custos_bp.custos"))


@compras_bp.route("/compras/editar/<int:compra_id>", methods=["POST"])
def editar_compra(compra_id):
    return redirect(request.referrer or url_for("custos_bp.custos"))


@compras_bp.route("/compras/excluir/<int:compra_id>", methods=["POST"])
def excluir_compra(compra_id):
    return redirect(request.referrer or url_for("custos_bp.custos"))
