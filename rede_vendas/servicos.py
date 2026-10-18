"""Regras de negócio da rede de vendas: cadastros, estoque, vendas e transferências."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

DESCONTO_MAXIMO_PCT = 30.0
COMISSAO_MAXIMA_PCT = 100.0
TABELAS_CONSULTAVEIS = frozenset({"lojas", "produtos", "vendedores", "clientes", "vendas"})


class ErroNegocio(Exception):  # noqa: N818 — nome do domínio, em português
    """Violação de uma regra de negócio (estoque insuficiente, loja inválida...)."""


class NaoEncontrado(ErroNegocio):  # noqa: N818
    """O registro pedido não existe (a API traduz para HTTP 404)."""


def arredondar(valor: Decimal | float) -> int:
    """Arredondamento comercial: meio centavo sobe (o round() do Python arredonda para o par)."""
    return int(Decimal(str(valor)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def reais_para_centavos(valor: float | str) -> int:
    """Converte 12.5, "12.50" ou "R$ 1.234,56" para centavos."""
    texto = str(valor).replace("R$", "").strip()
    if "," in texto:  # formato brasileiro
        texto = texto.replace(".", "").replace(",", ".")
    return arredondar(Decimal(texto) * 100)


def formatar_reais(centavos: int) -> str:
    sinal = "-" if centavos < 0 else ""
    inteiro, cent = divmod(abs(centavos), 100)
    return f"{sinal}R$ {inteiro:,}".replace(",", ".") + f",{cent:02d}"


def _agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ---------------------------------------------------------------- validações


def texto_obrigatorio(valor: str, campo: str) -> str:
    valor = (valor or "").strip()
    if not valor:
        raise ErroNegocio(f"O campo '{campo}' não pode ficar vazio.")
    return valor


def _uf(valor: str) -> str:
    uf = texto_obrigatorio(valor, "uf").upper()
    if len(uf) != 2 or not uf.isalpha():  # noqa: PLR2004 — UF tem sempre 2 letras
        raise ErroNegocio(f"UF inválida: '{valor}'. Use 2 letras, como PB.")
    return uf


def _comissao(valor: float) -> float:
    if not 0 <= valor <= COMISSAO_MAXIMA_PCT:
        raise ErroNegocio(f"Comissão deve estar entre 0% e {COMISSAO_MAXIMA_PCT:g}%.")
    return float(valor)


def _preco_custo(preco_centavos: int, custo_centavos: int) -> None:
    if preco_centavos < 0 or custo_centavos < 0:
        raise ErroNegocio("Preço e custo não podem ser negativos.")
    if custo_centavos > preco_centavos:
        raise ErroNegocio("Custo não pode ser maior que o preço de venda.")


# ---------------------------------------------------------------- cadastros


def cadastrar_loja(conn: sqlite3.Connection, nome: str, cidade: str, uf: str) -> int:
    cur = conn.execute(
        "INSERT INTO lojas (nome, cidade, uf) VALUES (?, ?, ?)",
        (texto_obrigatorio(nome, "nome"), texto_obrigatorio(cidade, "cidade"), _uf(uf)),
    )
    conn.commit()
    return cur.lastrowid


def cadastrar_produto(conn, sku: str, nome: str, preco: float, custo: float) -> int:
    preco_c, custo_c = reais_para_centavos(preco), reais_para_centavos(custo)
    _preco_custo(preco_c, custo_c)
    cur = conn.execute(
        "INSERT INTO produtos (sku, nome, preco_centavos, custo_centavos) VALUES (?, ?, ?, ?)",
        (texto_obrigatorio(sku, "sku").upper(), texto_obrigatorio(nome, "nome"), preco_c, custo_c),
    )
    conn.commit()
    return cur.lastrowid


def cadastrar_vendedor(conn, nome: str, loja_id: int, comissao_pct: float = 3.0) -> int:
    _exigir(conn, "lojas", loja_id)
    cur = conn.execute(
        "INSERT INTO vendedores (nome, loja_id, comissao_pct) VALUES (?, ?, ?)",
        (texto_obrigatorio(nome, "nome"), loja_id, _comissao(comissao_pct)),
    )
    conn.commit()
    return cur.lastrowid


def cadastrar_cliente(conn, nome: str, cpf: str | None = None, cidade: str | None = None) -> int:
    cur = conn.execute(
        "INSERT INTO clientes (nome, cpf, cidade) VALUES (?, ?, ?)",
        (texto_obrigatorio(nome, "nome"), cpf or None, cidade or None),
    )
    conn.commit()
    return cur.lastrowid


# ------------------------------------------------------------------ edição
# Apenas os campos informados (diferentes de None) são alterados.


def _atualizar(conn, tabela: str, id_: int, campos: dict[str, object]) -> None:
    """UPDATE parametrizado. Tabela e colunas vêm do código, nunca da entrada do usuário."""
    if not campos:
        raise ErroNegocio("Informe pelo menos um campo para alterar.")
    atribuicoes = ", ".join(f"{coluna} = ?" for coluna in campos)
    with conn:
        conn.execute(f"UPDATE {tabela} SET {atribuicoes} WHERE id = ?", [*campos.values(), id_])


def editar_loja(conn, loja_id: int, *, nome=None, cidade=None, uf=None) -> None:
    _exigir(conn, "lojas", loja_id)
    campos = {}
    if nome is not None:
        campos["nome"] = texto_obrigatorio(nome, "nome")
    if cidade is not None:
        campos["cidade"] = texto_obrigatorio(cidade, "cidade")
    if uf is not None:
        campos["uf"] = _uf(uf)
    _atualizar(conn, "lojas", loja_id, campos)


def editar_produto(conn, produto_id: int, *, nome=None, preco=None, custo=None) -> None:
    """Altera nome, preço ou custo. Vendas passadas mantêm os valores da época (RN07)."""
    atual = _exigir(conn, "produtos", produto_id)
    campos = {}
    if nome is not None:
        campos["nome"] = texto_obrigatorio(nome, "nome")
    preco_c = reais_para_centavos(preco) if preco is not None else atual["preco_centavos"]
    custo_c = reais_para_centavos(custo) if custo is not None else atual["custo_centavos"]
    _preco_custo(preco_c, custo_c)  # valida o par final, não só o campo alterado
    if preco is not None:
        campos["preco_centavos"] = preco_c
    if custo is not None:
        campos["custo_centavos"] = custo_c
    _atualizar(conn, "produtos", produto_id, campos)


def editar_vendedor(conn, vendedor_id: int, *, nome=None, loja_id=None, comissao_pct=None) -> None:
    """Altera dados do vendedor. Vendas passadas mantêm loja e comissão da época."""
    _exigir(conn, "vendedores", vendedor_id)
    campos = {}
    if nome is not None:
        campos["nome"] = texto_obrigatorio(nome, "nome")
    if loja_id is not None:
        _exigir(conn, "lojas", loja_id)
        campos["loja_id"] = loja_id
    if comissao_pct is not None:
        campos["comissao_pct"] = _comissao(comissao_pct)
    _atualizar(conn, "vendedores", vendedor_id, campos)


def editar_cliente(conn, cliente_id: int, *, nome=None, cpf=None, cidade=None) -> None:
    """Altera dados do cliente. Passar string vazia em cpf/cidade apaga o valor."""
    _exigir(conn, "clientes", cliente_id)
    campos = {}
    if nome is not None:
        campos["nome"] = texto_obrigatorio(nome, "nome")
    if cpf is not None:
        campos["cpf"] = cpf.strip() or None
    if cidade is not None:
        campos["cidade"] = cidade.strip() or None
    _atualizar(conn, "clientes", cliente_id, campos)


def definir_ativo(conn, entidade: str, id_: int, ativo: bool) -> None:
    """Ativa ou desativa um vendedor ou produto. Nada é apagado: o histórico é preservado."""
    tabelas = {"vendedor": "vendedores", "produto": "produtos"}
    if entidade not in tabelas:
        raise ErroNegocio("Só é possível ativar/desativar 'vendedor' ou 'produto'.")
    registro = _exigir(conn, tabelas[entidade], id_)
    if bool(registro["ativo"]) == ativo:
        estado = "ativo" if ativo else "inativo"
        raise ErroNegocio(f"O {entidade} {id_} já está {estado}.")
    _atualizar(conn, tabelas[entidade], id_, {"ativo": int(ativo)})


# ---------------------------------------------------------------- listagem


def _com_bool(linhas, *colunas: str) -> list[dict]:
    """SQLite devolve 0/1; converte as colunas indicadas para bool."""
    resultado = [dict(r) for r in linhas]
    for linha in resultado:
        for coluna in colunas:
            linha[coluna] = bool(linha[coluna])
    return resultado


def listar_lojas(conn) -> list[dict]:
    sql = """
        SELECT l.id, l.nome, l.cidade, l.uf,
               (SELECT COUNT(*) FROM vendedores v WHERE v.loja_id = l.id AND v.ativo = 1)
                   AS vendedores_ativos
        FROM lojas l ORDER BY l.nome"""
    return [dict(r) for r in conn.execute(sql)]


def listar_produtos(conn, *, incluir_inativos: bool = False) -> list[dict]:
    sql = """
        SELECT p.id, p.sku, p.nome, p.preco_centavos AS preco, p.custo_centavos AS custo,
               COALESCE(SUM(e.quantidade), 0) AS estoque_total,
               p.ativo = 1 AS ativo
        FROM produtos p LEFT JOIN estoque e ON e.produto_id = p.id
        WHERE p.ativo = 1 OR ?
        GROUP BY p.id ORDER BY p.nome"""
    return _com_bool(conn.execute(sql, (incluir_inativos,)), "ativo")


def listar_vendedores(conn, *, incluir_inativos: bool = False) -> list[dict]:
    sql = """
        SELECT v.id, v.nome, v.loja_id, l.nome AS loja, v.comissao_pct, v.ativo = 1 AS ativo
        FROM vendedores v JOIN lojas l ON l.id = v.loja_id
        WHERE v.ativo = 1 OR ?
        ORDER BY l.nome, v.nome"""
    return _com_bool(conn.execute(sql, (incluir_inativos,)), "ativo")


def listar_clientes(conn) -> list[dict]:
    sql = """
        SELECT id, nome, cpf, cidade FROM clientes ORDER BY nome"""
    return [dict(r) for r in conn.execute(sql)]


def _exigir(conn, tabela: str, id_: int) -> sqlite3.Row:
    """Busca um registro por id ou lança ErroNegocio.

    O nome da tabela é validado contra uma lista fixa, evitando SQL injection.
    """
    if tabela not in TABELAS_CONSULTAVEIS:
        raise ValueError(f"Tabela não permitida: {tabela}")
    linha = conn.execute(f"SELECT * FROM {tabela} WHERE id = ?", (id_,)).fetchone()
    if linha is None:
        raise NaoEncontrado(f"Registro {id_} não encontrado em '{tabela}'.")
    return linha


# ------------------------------------------------------------------ estoque


def listar_estoque(conn, loja_id: int | None = None) -> list[dict]:
    """Saldo de cada produto ativo em cada loja (inclui saldo zero)."""
    sql = """
        SELECT l.id AS loja_id, l.nome AS loja, p.id AS produto_id, p.sku, p.nome AS produto,
               COALESCE(e.quantidade, 0) AS quantidade
        FROM lojas l CROSS JOIN produtos p
        LEFT JOIN estoque e ON e.loja_id = l.id AND e.produto_id = p.id
        WHERE p.ativo = 1 AND (? IS NULL OR l.id = ?)
        ORDER BY l.nome, p.nome"""
    return [dict(r) for r in conn.execute(sql, (loja_id, loja_id))]


def saldo(conn, loja_id: int, produto_id: int) -> int:
    linha = conn.execute(
        "SELECT quantidade FROM estoque WHERE loja_id = ? AND produto_id = ?",
        (loja_id, produto_id),
    ).fetchone()
    return linha["quantidade"] if linha else 0


def _ajustar_estoque(conn, loja_id: int, produto_id: int, delta: int) -> None:
    novo = saldo(conn, loja_id, produto_id) + delta
    if novo < 0:
        raise ErroNegocio(
            f"Estoque insuficiente do produto {produto_id} na loja {loja_id} "
            f"(disponível: {novo - delta}, solicitado: {-delta})."
        )
    conn.execute(
        """INSERT INTO estoque (loja_id, produto_id, quantidade) VALUES (?, ?, ?)
           ON CONFLICT(loja_id, produto_id) DO UPDATE SET quantidade = excluded.quantidade""",
        (loja_id, produto_id, novo),
    )


def entrada_estoque(conn, loja_id: int, produto_id: int, quantidade: int) -> int:
    if quantidade <= 0:
        raise ErroNegocio("A quantidade de entrada deve ser positiva.")
    _exigir(conn, "lojas", loja_id)
    _exigir(conn, "produtos", produto_id)
    with conn:
        _ajustar_estoque(conn, loja_id, produto_id, quantidade)
    return saldo(conn, loja_id, produto_id)


def transferir(conn, origem_id: int, destino_id: int, produto_id: int, quantidade: int) -> None:
    if origem_id == destino_id:
        raise ErroNegocio("Origem e destino devem ser lojas diferentes.")
    if quantidade <= 0:
        raise ErroNegocio("A quantidade transferida deve ser positiva.")
    _exigir(conn, "lojas", destino_id)
    with conn:  # tudo ou nada
        _ajustar_estoque(conn, origem_id, produto_id, -quantidade)
        _ajustar_estoque(conn, destino_id, produto_id, quantidade)
        conn.execute(
            "INSERT INTO transferencias (origem_id, destino_id, produto_id, quantidade, data_hora)"
            " VALUES (?, ?, ?, ?, ?)",
            (origem_id, destino_id, produto_id, quantidade, _agora()),
        )


# ------------------------------------------------------------------- vendas


@dataclass
class ItemPedido:
    produto_id: int
    quantidade: int


def registrar_venda(
    conn,
    vendedor_id: int,
    itens: list[ItemPedido],
    *,
    cliente_id: int | None = None,
    desconto_pct: float = 0.0,
    data_hora: str | None = None,
) -> int:
    """Registra uma venda na loja do vendedor, baixando o estoque de forma atômica."""
    if not itens:
        raise ErroNegocio("A venda precisa de pelo menos um item.")
    if not 0 <= desconto_pct <= DESCONTO_MAXIMO_PCT:
        raise ErroNegocio(f"Desconto permitido: de 0% a {DESCONTO_MAXIMO_PCT:g}%.")

    vendedor = _exigir(conn, "vendedores", vendedor_id)
    if not vendedor["ativo"]:
        raise ErroNegocio("Vendedor inativo não pode registrar vendas.")
    if cliente_id is not None:
        _exigir(conn, "clientes", cliente_id)
    loja_id = vendedor["loja_id"]

    with conn:
        bruto = 0
        linhas = []
        for item in itens:
            if item.quantidade <= 0:
                raise ErroNegocio("Quantidade de cada item deve ser positiva.")
            prod = _exigir(conn, "produtos", item.produto_id)
            if not prod["ativo"]:
                raise ErroNegocio(f"Produto {prod['sku']} está inativo e não pode ser vendido.")
            _ajustar_estoque(conn, loja_id, prod["id"], -item.quantidade)
            bruto += prod["preco_centavos"] * item.quantidade
            linhas.append(
                (prod["id"], item.quantidade, prod["preco_centavos"], prod["custo_centavos"])
            )

        desconto = arredondar(Decimal(bruto) * Decimal(str(desconto_pct)) / 100)
        cur = conn.execute(
            """INSERT INTO vendas (loja_id, vendedor_id, cliente_id, data_hora,
                                   desconto_centavos, total_centavos, comissao_pct)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                loja_id,
                vendedor_id,
                cliente_id,
                data_hora or _agora(),
                desconto,
                bruto - desconto,
                vendedor["comissao_pct"],  # comissão congelada no momento da venda
            ),
        )
        venda_id = cur.lastrowid
        conn.executemany(
            """INSERT INTO itens_venda (venda_id, produto_id, quantidade,
                                        preco_unit_centavos, custo_unit_centavos)
               VALUES (?, ?, ?, ?, ?)""",
            [(venda_id, *linha) for linha in linhas],
        )
    return venda_id


def cancelar_venda(conn, venda_id: int) -> None:
    """Cancela a venda e devolve os itens ao estoque da loja."""
    venda = _exigir(conn, "vendas", venda_id)
    if venda["status"] == "CANCELADA":
        raise ErroNegocio("Venda já está cancelada.")
    with conn:
        itens = conn.execute(
            "SELECT produto_id, quantidade FROM itens_venda WHERE venda_id = ?", (venda_id,)
        ).fetchall()
        for it in itens:
            _ajustar_estoque(conn, venda["loja_id"], it["produto_id"], it["quantidade"])
        conn.execute("UPDATE vendas SET status = 'CANCELADA' WHERE id = ?", (venda_id,))


def listar_vendas(
    conn, *, loja_id: int | None = None, vendedor_id: int | None = None, limite: int = 50
) -> list[dict]:
    """Vendas mais recentes primeiro, com loja, vendedor, cliente e número de itens."""
    sql = """
        SELECT v.id, v.data_hora, l.nome AS loja, ve.nome AS vendedor, c.nome AS cliente,
               (SELECT SUM(quantidade) FROM itens_venda WHERE venda_id = v.id) AS itens,
               v.desconto_centavos AS desconto, v.total_centavos AS total, v.status
        FROM vendas v
        JOIN lojas l ON l.id = v.loja_id
        JOIN vendedores ve ON ve.id = v.vendedor_id
        LEFT JOIN clientes c ON c.id = v.cliente_id
        WHERE (? IS NULL OR v.loja_id = ?) AND (? IS NULL OR v.vendedor_id = ?)
        ORDER BY v.data_hora DESC, v.id DESC LIMIT ?"""
    parametros = (loja_id, loja_id, vendedor_id, vendedor_id, limite)
    return [dict(r) for r in conn.execute(sql, parametros)]


def detalhar_venda(conn, venda_id: int) -> dict:
    """Cabeçalho da venda com a lista de itens e os valores gravados no momento da venda."""
    _exigir(conn, "vendas", venda_id)
    cabecalho = _vendas_por_id(conn, venda_id)[0]
    itens = conn.execute(
        """SELECT p.sku, p.nome, i.quantidade, i.preco_unit_centavos AS preco_unit,
                  i.quantidade * i.preco_unit_centavos AS subtotal
           FROM itens_venda i JOIN produtos p ON p.id = i.produto_id
           WHERE i.venda_id = ? ORDER BY i.id""",
        (venda_id,),
    )
    return {**cabecalho, "lista_itens": [dict(r) for r in itens]}


def _vendas_por_id(conn, venda_id: int) -> list[dict]:
    sql = """
        SELECT v.id, v.data_hora, l.nome AS loja, v.vendedor_id, ve.nome AS vendedor,
               c.nome AS cliente, v.desconto_centavos AS desconto, v.total_centavos AS total,
               v.comissao_pct, v.status
        FROM vendas v
        JOIN lojas l ON l.id = v.loja_id
        JOIN vendedores ve ON ve.id = v.vendedor_id
        LEFT JOIN clientes c ON c.id = v.cliente_id
        WHERE v.id = ?"""
    return [dict(r) for r in conn.execute(sql, (venda_id,))]
