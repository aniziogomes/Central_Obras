from datetime import datetime
import re


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


def caminho_redirecionamento_seguro(valor, fallback):
    caminho = str(valor or "").strip()
    if caminho.startswith("/") and not caminho.startswith("//") and "\n" not in caminho and "\r" not in caminho:
        return caminho
    return fallback


def limpar_texto(valor, max_len=255, obrigatorio=False, campo="Campo"):
    texto = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", str(valor or "")).strip()
    if obrigatorio and not texto:
        raise ValueError(f"{campo} e obrigatorio.")
    if len(texto) > max_len:
        raise ValueError(f"{campo} deve ter no maximo {max_len} caracteres.")
    return texto


def parse_int_positivo(valor, campo="ID"):
    try:
        numero = int(str(valor or "").strip())
    except (TypeError, ValueError):
        raise ValueError(f"{campo} invalido.")
    if numero <= 0:
        raise ValueError(f"{campo} invalido.")
    return numero


def parse_int_nao_negativo(valor, campo="Numero"):
    try:
        numero = int(str(valor or "").strip())
    except (TypeError, ValueError):
        raise ValueError(f"{campo} invalido.")
    if numero < 0:
        raise ValueError(f"{campo} nao pode ser negativo.")
    return numero


def validar_nota(valor, campo="Nota"):
    nota = parse_valor_monetario(valor)
    if nota < 0 or nota > 10:
        raise ValueError(f"{campo} deve ficar entre 0 e 10.")
    return nota


def valor_negativo(valor):
    return valor < 0


def validar_intervalo_percentual(valor, campo="Percentual"):
    if valor < 0 or valor > 100:
        raise ValueError(f"{campo} deve ficar entre 0 e 100.")


def validar_categoria_custo(categoria):
    if categoria not in CATEGORIAS_CUSTO_VALIDAS:
        raise ValueError("Categoria de custo inválida.")
