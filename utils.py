from datetime import date, datetime


def formatar_moeda(valor):
    if valor is None:
        valor = 0
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def formatar_data(valor, vazio="-", mostrar_hora=None):
    if valor is None:
        return vazio

    if isinstance(valor, datetime):
        if mostrar_hora is False:
            return valor.strftime("%d/%m/%Y")
        return valor.strftime("%d/%m/%Y %H:%M")

    if isinstance(valor, date):
        return valor.strftime("%d/%m/%Y")

    texto = str(valor).strip()
    if not texto or texto == "-":
        return vazio

    if "/" in texto and len(texto) >= 10:
        return texto

    normalizado = texto.replace("T", " ")
    formatos = (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
    )

    for formato in formatos:
        try:
            data = datetime.strptime(normalizado[:19], formato)
            tem_hora = formato != "%Y-%m-%d"
            if mostrar_hora is True or (mostrar_hora is None and tem_hora):
                return data.strftime("%d/%m/%Y %H:%M")
            return data.strftime("%d/%m/%Y")
        except ValueError:
            pass

    return texto


def calcular_media_fornecedor(qualidade, preco, prazo):
    qualidade = qualidade or 0
    preco = preco or 0
    prazo = prazo or 0
    return round((qualidade + preco + prazo) / 3, 1)


def formatar_tipo_obra(tipo_obra):
    if (tipo_obra or "contrato") == "venda":
        return "Para venda"
    return "Por contrato / reforma"
