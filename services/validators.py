from datetime import datetime


CATEGORIAS_CUSTO_VALIDAS = [
    "Material",
    "Mão de Obra",
    "Equipamento",
    "Projeto/Engenharia",
    "Taxas e Impostos",
    "Outros",
]


def data_no_periodo(data_texto, data_inicio="", data_fim=""):
    if not data_texto:
        return True

    try:
        data_ref = datetime.strptime(data_texto, "%Y-%m-%d").date()
    except:
        return True

    if data_inicio:
        try:
            inicio = datetime.strptime(data_inicio, "%Y-%m-%d").date()
            if data_ref < inicio:
                return False
        except:
            pass

    if data_fim:
        try:
            fim = datetime.strptime(data_fim, "%Y-%m-%d").date()
            if data_ref > fim:
                return False
        except:
            pass

    return True


def parse_valor_monetario(valor_texto):
    if valor_texto is None:
        return 0.0

    valor = str(valor_texto).strip()

    if not valor:
        return 0.0

    valor = valor.replace("R$", "").replace(" ", "")

    if "." in valor and "," in valor:
        valor = valor.replace(".", "").replace(",", ".")
    elif "," in valor:
        valor = valor.replace(",", ".")

    return float(valor)


def valor_negativo(valor):
    return valor < 0


def validar_intervalo_percentual(valor, campo="Percentual"):
    if valor < 0 or valor > 100:
        raise ValueError(f"{campo} deve ficar entre 0 e 100.")


def validar_categoria_custo(categoria):
    if categoria not in CATEGORIAS_CUSTO_VALIDAS:
        raise ValueError("Categoria de custo inválida.")