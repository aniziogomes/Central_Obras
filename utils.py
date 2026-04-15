def formatar_moeda(valor):
    if valor is None:
        valor = 0
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def calcular_media_fornecedor(qualidade, preco, prazo):
    qualidade = qualidade or 0
    preco = preco or 0
    prazo = prazo or 0
    return round((qualidade + preco + prazo) / 3, 1)


def formatar_tipo_obra(tipo_obra):
    if (tipo_obra or "contrato") == "venda":
        return "Para venda"
    return "Por contrato / reforma"