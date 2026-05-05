from flask import session

from database import execute, query_all, query_one


EMPRESA_PADRAO_NOME = "Canteiro Interno"
TABELAS_TENANT = {
    "usuarios",
    "obras",
    "custos",
    "fornecedores",
    "compras",
    "equipe",
    "medicoes",
    "importacoes",
    "custos_importados_categoria",
    "fotos_obra",
    "logs",
}
TABELAS_FILHAS_OBRA = {
    "custos",
    "compras",
    "equipe",
    "medicoes",
    "custos_importados_categoria",
    "fotos_obra",
}


def empresa_id_atual():
    valor = session.get("empresa_id")
    try:
        return int(valor) if valor else None
    except (TypeError, ValueError):
        return None


def tem_acesso_global():
    return session.get("usuario_perfil") == "admin" and empresa_id_atual() is None


def eh_admin_global():
    return tem_acesso_global()


def normalizar_empresa_id(valor):
    try:
        empresa_id = int(valor)
    except (TypeError, ValueError):
        return None
    return empresa_id if empresa_id > 0 else None


def empresa_padrao_id():
    empresa = query_one("SELECT id FROM empresas WHERE nome = ?", (EMPRESA_PADRAO_NOME,))
    if empresa:
        return empresa["id"]
    return execute(
        "INSERT INTO empresas (nome, ativo) VALUES (?, 1)",
        (EMPRESA_PADRAO_NOME,),
    )


def listar_empresas(apenas_ativas=False):
    where = "WHERE ativo = 1" if apenas_ativas else ""
    return query_all(f"SELECT * FROM empresas {where} ORDER BY nome ASC")


def obter_empresa(empresa_id):
    empresa_id = normalizar_empresa_id(empresa_id)
    if not empresa_id:
        return None
    return query_one("SELECT * FROM empresas WHERE id = ?", (empresa_id,))


def obter_ou_criar_empresa(nome):
    nome = (nome or "").strip()
    if not nome:
        raise ValueError("Informe a empresa do usuario.")
    empresa = query_one("SELECT id FROM empresas WHERE lower(nome) = lower(?)", (nome,))
    if empresa:
        execute("UPDATE empresas SET ativo = 1 WHERE id = ?", (empresa["id"],))
        return empresa["id"]
    return execute("INSERT INTO empresas (nome, ativo) VALUES (?, 1)", (nome,))


def empresa_usuario_por_form(perfil, empresa_id_form="", empresa_nome_form=""):
    empresa_nome_form = (empresa_nome_form or "").strip()
    empresa_id = normalizar_empresa_id(empresa_id_form)

    if empresa_nome_form:
        return obter_ou_criar_empresa(empresa_nome_form)

    if empresa_id:
        empresa = obter_empresa(empresa_id)
        if not empresa:
            raise ValueError("Empresa nao encontrada.")
        return empresa_id

    if perfil == "admin":
        return None

    raise ValueError("Selecione ou informe a empresa deste usuario.")


def empresa_id_para_insert(empresa_id_form=None):
    empresa_id_sessao = empresa_id_atual()
    if empresa_id_sessao:
        return empresa_id_sessao

    if tem_acesso_global():
        empresa_id = normalizar_empresa_id(empresa_id_form)
        if empresa_id and obter_empresa(empresa_id):
            return empresa_id
        return empresa_padrao_id()

    return empresa_padrao_id()


def filtro_empresa_expr(alias=None):
    if tem_acesso_global():
        return "", ()

    empresa_id = empresa_id_atual()
    if not empresa_id:
        return "1 = 0", ()

    coluna = f"{alias}.empresa_id" if alias else "empresa_id"
    return f"{coluna} = ?", (empresa_id,)


def where_empresa(alias=None):
    expr, params = filtro_empresa_expr(alias)
    return (f"WHERE {expr}", params) if expr else ("", ())


def and_empresa(alias=None):
    expr, params = filtro_empresa_expr(alias)
    return (f"AND {expr}", params) if expr else ("", ())


def aplicar_filtro_empresa(clausulas, params, alias=None):
    expr, expr_params = filtro_empresa_expr(alias)
    if expr:
        clausulas.append(expr)
        params.extend(expr_params)


def listar_obras_acessiveis(order_by="nome ASC", campos="*"):
    where, params = where_empresa("o")
    return query_all(
        f"""
        SELECT {campos}
        FROM obras o
        LEFT JOIN empresas e ON e.id = o.empresa_id
        {where}
        ORDER BY {order_by}
        """,
        params,
    )


def obter_obra_acessivel(obra_id=None, codigo=None, campos="o.*"):
    if obra_id is None and codigo is None:
        return None

    if obra_id is not None:
        filtro = "o.id = ?"
        params = [obra_id]
    else:
        filtro = "o.codigo = ?"
        params = [codigo]

    extra, extra_params = and_empresa("o")
    return query_one(
        f"""
        SELECT {campos}
        FROM obras o
        LEFT JOIN empresas e ON e.id = o.empresa_id
        WHERE {filtro}
        {extra}
        """,
        tuple(params) + tuple(extra_params),
    )


def obter_registro_acessivel(tabela, registro_id, campos="*"):
    if tabela not in TABELAS_TENANT:
        raise ValueError("Tabela sem suporte de tenant.")
    extra, params = and_empresa()
    return query_one(
        f"SELECT {campos} FROM {tabela} WHERE id = ? {extra}",
        (registro_id,) + tuple(params),
    )


def sincronizar_empresa_filhos_obra(obra_id, empresa_id):
    for tabela in TABELAS_FILHAS_OBRA:
        execute(
            f"UPDATE {tabela} SET empresa_id = ? WHERE obra_id = ?",
            (empresa_id, obra_id),
        )


def empresa_id_da_entidade(entidade, entidade_id):
    entidade_para_tabela = {
        "obra": "obras",
        "custo": "custos",
        "fornecedor": "fornecedores",
        "compra": "compras",
        "equipe": "equipe",
        "medicao": "medicoes",
        "planilha": "importacoes",
        "usuario": "usuarios",
    }
    tabela = entidade_para_tabela.get(entidade)
    if not tabela or not entidade_id:
        return None
    try:
        row = query_one(f"SELECT empresa_id FROM {tabela} WHERE id = ?", (entidade_id,))
    except Exception:
        return None
    return row["empresa_id"] if row and "empresa_id" in row.keys() else None
