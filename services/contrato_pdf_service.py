from datetime import datetime
from pathlib import Path
import re
import textwrap

from utils import formatar_data, formatar_moeda, formatar_tipo_obra


TIPO_CONTRATO_LABELS = {
    "reforma": "Contrato de Reforma",
    "construcao": "Contrato de Construção",
    "venda": "Contrato de Venda de Imóvel",
    "prestacao_servico": "Contrato de Prestação de Serviço",
    "aditivo": "Aditivo Contratual",
}

STATUS_CONTRATO_LABELS = {
    "rascunho": "Rascunho",
    "aguardando_assinatura": "Aguardando assinatura",
    "assinado": "Assinado",
    "cancelado": "Cancelado",
    "aditivado": "Aditivado",
}


def _texto(valor, vazio="-"):
    texto = str(valor or "").strip()
    return texto if texto else vazio


def _linha(label, valor):
    return f"{label}: {_texto(valor)}"


def _normalizar_nome_arquivo(texto):
    texto = re.sub(r"[^A-Za-z0-9_-]+", "-", str(texto or "").strip())
    texto = re.sub(r"-+", "-", texto).strip("-")
    return texto[:80] or "contrato"


def _quebrar(texto, largura=92):
    linhas = []
    for bloco in str(texto or "").splitlines() or [""]:
        bloco = bloco.strip()
        if not bloco:
            linhas.append("")
            continue
        linhas.extend(textwrap.wrap(bloco, width=largura) or [""])
    return linhas


def _clausula_base(tipo):
    textos = {
        "reforma": (
            "A contratada se compromete a executar os serviços de reforma descritos neste instrumento, "
            "observando o escopo contratado, os prazos acordados e as boas práticas aplicáveis à construção civil."
        ),
        "construcao": (
            "A contratada se compromete a executar a construção descrita neste instrumento, conforme escopo, "
            "cronograma, especificações acordadas e condições comerciais estabelecidas pelas partes."
        ),
        "venda": (
            "O presente instrumento estabelece as condições comerciais para venda do imóvel indicado, incluindo "
            "valor, forma de pagamento, prazos, responsabilidades e demais condições pactuadas."
        ),
        "prestacao_servico": (
            "A contratada prestará os serviços descritos neste contrato, respeitando o escopo, os limites de "
            "responsabilidade, a forma de pagamento e os prazos acordados com a contratante."
        ),
        "aditivo": (
            "Este aditivo complementa o contrato original indicado, preservando suas condições não alteradas "
            "expressamente neste instrumento e registrando as novas condições acordadas."
        ),
    }
    return textos.get(tipo, textos["prestacao_servico"])


def montar_linhas_contrato(contrato, cliente=None, obra=None, empresa=None, origem=None):
    tipo = contrato["tipo_contrato"] or "prestacao_servico"
    titulo = contrato["titulo"] or TIPO_CONTRATO_LABELS.get(tipo, "Contrato")
    linhas = [
        (titulo.upper(), 16, True),
        (f"Número: {_texto(contrato['numero_contrato'])} | Versão: {contrato['versao'] or 1}", 10, False),
        ("", 8, False),
        ("1. PARTES", 12, True),
        (_linha("Contratada", empresa["nome"] if empresa else "Empresa responsável"), 10, False),
        (_linha("Documento da contratada", empresa["documento"] if empresa and "documento" in empresa.keys() else ""), 10, False),
        (_linha("Contratante", cliente["nome_completo"] if cliente else "Cliente não informado"), 10, False),
        (_linha("CPF/CNPJ", cliente["cpf_cnpj"] if cliente else ""), 10, False),
        (_linha("RG/IE", cliente["rg_ie"] if cliente else ""), 10, False),
        (_linha("Endereço do contratante", cliente["endereco"] if cliente else ""), 10, False),
        (_linha("Cidade/UF", f"{cliente['cidade'] or '-'} / {cliente['estado'] or '-'}" if cliente else ""), 10, False),
        ("", 8, False),
        ("2. DADOS DA OBRA", 12, True),
        (_linha("Obra", f"{obra['codigo']} - {obra['nome']}" if obra else "Sem obra vinculada"), 10, False),
        (_linha("Endereço da obra", obra["endereco"] if obra else ""), 10, False),
        (_linha("Tipologia", obra["tipologia"] if obra else ""), 10, False),
        (_linha("Tipo da obra", formatar_tipo_obra(obra["tipo_obra"]) if obra else ""), 10, False),
        (_linha("Área", f"{obra['area_m2']} m²" if obra and obra["area_m2"] else ""), 10, False),
        ("", 8, False),
        ("3. OBJETO DO CONTRATO", 12, True),
    ]

    for linha in _quebrar(_clausula_base(tipo)):
        linhas.append((linha, 10, False))

    if origem:
        linhas.extend([
            ("", 8, False),
            ("Contrato original", 10, True),
            (_linha("Número", origem["numero_contrato"]), 10, False),
            (_linha("Título", origem["titulo"]), 10, False),
        ])

    if tipo == "aditivo":
        linhas.extend([
            ("", 8, False),
            ("Motivo do aditivo", 10, True),
        ])
        for linha in _quebrar(contrato["motivo_aditivo"] or "Não informado."):
            linhas.append((linha, 10, False))

    secoes = [
        ("4. ESCOPO CONTRATADO", contrato["escopo_servico"]),
        ("5. ITENS INCLUSOS", contrato["itens_inclusos"]),
        ("6. ITENS NÃO INCLUSOS", contrato["itens_nao_inclusos"]),
        ("7. RESPONSABILIDADES DA CONTRATADA", contrato["responsabilidades_contratada"]),
        ("8. RESPONSABILIDADES DA CONTRATANTE", contrato["responsabilidades_contratante"]),
        ("9. GARANTIAS", contrato["garantias"]),
        ("10. CLÁUSULAS ADICIONAIS", contrato["clausulas_adicionais"]),
    ]

    for titulo_secao, conteudo in secoes:
        linhas.append(("", 8, False))
        linhas.append((titulo_secao, 12, True))
        texto = conteudo or "Não informado."
        for linha in _quebrar(texto):
            linhas.append((linha, 10, False))

    linhas.extend([
        ("", 8, False),
        ("11. CONDIÇÕES FINANCEIRAS", 12, True),
        (_linha("Valor total", formatar_moeda(contrato["valor_total"] or 0)), 10, False),
        (_linha("Entrada", formatar_moeda(contrato["entrada"] or 0)), 10, False),
        (_linha("Forma de pagamento", contrato["forma_pagamento"]), 10, False),
        (_linha("Quantidade de parcelas", contrato["quantidade_parcelas"]), 10, False),
        (_linha("Valor da parcela", formatar_moeda(contrato["valor_parcela"] or 0)), 10, False),
        (_linha("Primeiro vencimento", formatar_data(contrato["vencimento_primeira_parcela"], "-")), 10, False),
        (_linha("Índice de reajuste", contrato["indice_reajuste"]), 10, False),
        (_linha("Multa por atraso", f"{contrato['multa_atraso'] or 0}%"), 10, False),
        (_linha("Juros de mora", f"{contrato['juros_mora'] or 0}% ao mês"), 10, False),
        ("", 8, False),
        ("12. PRAZOS", 12, True),
        (_linha("Prazo de execução", f"{contrato['prazo_execucao'] or 0} dia(s)"), 10, False),
        (_linha("Data de início", formatar_data(contrato["data_inicio"], "-")), 10, False),
        (_linha("Data final prevista", formatar_data(contrato["data_fim_prevista"], "-")), 10, False),
        ("", 8, False),
        ("13. OBSERVAÇÕES", 12, True),
    ])

    for linha in _quebrar(contrato["observacoes"] or "Sem observações adicionais."):
        linhas.append((linha, 10, False))

    linhas.extend([
        ("", 8, False),
        ("14. LOCAL, DATA E ASSINATURAS", 12, True),
        (f"Emitido em {datetime.now().strftime('%d/%m/%Y')}.", 10, False),
        ("", 8, False),
        ("____________________________________________", 10, False),
        ("Contratada", 10, False),
        ("", 8, False),
        ("____________________________________________", 10, False),
        ("Contratante", 10, False),
    ])
    return linhas


def _pdf_escape_bytes(texto):
    raw = str(texto or "").encode("cp1252", "replace")
    raw = raw.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")
    raw = raw.replace(b"\r", b" ").replace(b"\n", b" ")
    return raw


def _comando_texto(texto, x, y, tamanho=10, negrito=False):
    fonte = b"F2" if negrito else b"F1"
    texto_bytes = _pdf_escape_bytes(texto)
    return b"BT /%s %d Tf %.2f %.2f Td (%s) Tj ET\n" % (fonte, tamanho, x, y, texto_bytes)


def _montar_paginas(linhas):
    paginas = []
    atual = []
    y = 790
    for texto, tamanho, negrito in linhas:
        altura = max(12, tamanho + 5)
        if y < 64:
            paginas.append(atual)
            atual = []
            y = 790
        if texto == "":
            y -= altura * 0.65
            continue
        atual.append((texto, 54, y, tamanho, negrito))
        y -= altura
    if atual:
        paginas.append(atual)
    return paginas or [[("Contrato sem conteúdo.", 54, 790, 10, False)]]


def _renderizar_pdf(linhas, destino):
    paginas = _montar_paginas(linhas)
    objetos = []

    def add(obj):
        objetos.append(obj)
        return len(objetos)

    catalog_id = add(b"<< /Type /Catalog /Pages 2 0 R >>")
    pages_id = add(b"")
    font_regular_id = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    font_bold_id = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")

    page_ids = []
    for indice, pagina in enumerate(paginas, start=1):
        stream = b""
        stream += _comando_texto("Canteiro - Contratos", 54, 820, 9, True)
        stream += _comando_texto(f"Página {indice}", 500, 820, 8, False)
        for item in pagina:
            stream += _comando_texto(*item)
        content_id = add(b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream))
        page_id = add(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            b"/Resources << /Font << /F1 %d 0 R /F2 %d 0 R >> >> /Contents %d 0 R >>"
            % (font_regular_id, font_bold_id, content_id)
        )
        page_ids.append(page_id)

    kids = b" ".join(b"%d 0 R" % page_id for page_id in page_ids)
    objetos[pages_id - 1] = b"<< /Type /Pages /Kids [%s] /Count %d >>" % (kids, len(page_ids))

    pdf = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
    offsets = [0]
    for i, obj in enumerate(objetos, start=1):
        offsets.append(len(pdf))
        pdf += b"%d 0 obj\n%s\nendobj\n" % (i, obj)

    xref_pos = len(pdf)
    pdf += b"xref\n0 %d\n" % (len(objetos) + 1)
    pdf += b"0000000000 65535 f \n"
    for offset in offsets[1:]:
        pdf += b"%010d 00000 n \n" % offset
    pdf += b"trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF" % (
        len(objetos) + 1,
        catalog_id,
        xref_pos,
    )

    destino.write_bytes(pdf)


def gerar_pdf_contrato(contrato, cliente=None, obra=None, empresa=None, origem=None, pasta_destino="uploads/contratos"):
    pasta = Path(pasta_destino)
    pasta.mkdir(parents=True, exist_ok=True)
    numero = _normalizar_nome_arquivo(contrato["numero_contrato"] or f"contrato-{contrato['id']}")
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    destino = pasta / f"{numero}-v{contrato['versao'] or 1}-{timestamp}.pdf"
    linhas = montar_linhas_contrato(contrato, cliente=cliente, obra=obra, empresa=empresa, origem=origem)
    _renderizar_pdf(linhas, destino)
    return str(destino)
