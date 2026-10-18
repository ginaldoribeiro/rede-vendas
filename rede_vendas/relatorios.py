"""Consultas gerenciais da rede. Todas consideram apenas vendas CONCLUIDAS."""

import sqlite3


def _periodo(inicio: str | None, fim: str | None) -> tuple[str, list]:
    """Filtro de período por data (AAAA-MM-DD), inclusivo nas duas pontas."""
    cond, params = "v.status = 'CONCLUIDA'", []
    if inicio:
        cond += " AND date(v.data_hora) >= date(?)"
        params.append(inicio)
    if fim:
        cond += " AND date(v.data_hora) <= date(?)"
        params.append(fim)
    return cond, params


def faturamento_por_loja(conn: sqlite3.Connection, inicio=None, fim=None) -> list[dict]:
    cond, p = _periodo(inicio, fim)
    sql = f"""
        SELECT l.nome AS loja, l.cidade || '/' || l.uf AS local,
               COUNT(DISTINCT v.id)             AS vendas,
               COALESCE(SUM(v.total_centavos),0) AS faturamento,
               COALESCE(SUM(v.total_centavos) / COUNT(DISTINCT v.id), 0) AS ticket_medio
        FROM lojas l LEFT JOIN vendas v ON v.loja_id = l.id AND {cond}
        GROUP BY l.id ORDER BY faturamento DESC"""
    return [dict(r) for r in conn.execute(sql, p)]


def ranking_vendedores(conn, inicio=None, fim=None, limite: int = 10) -> list[dict]:
    cond, p = _periodo(inicio, fim)
    sql = f"""
        SELECT ve.nome AS vendedor, l.nome AS loja,
               COUNT(v.id) AS vendas,
               SUM(v.total_centavos) AS faturamento,
               CAST(ROUND(SUM(v.total_centavos * v.comissao_pct / 100.0)) AS INTEGER) AS comissao
        FROM vendas v
        JOIN vendedores ve ON ve.id = v.vendedor_id
        JOIN lojas l ON l.id = v.loja_id  -- loja onde a venda aconteceu
        WHERE {cond}
        GROUP BY ve.id, v.loja_id ORDER BY faturamento DESC LIMIT ?"""
    return [dict(r) for r in conn.execute(sql, [*p, limite])]


def produtos_mais_vendidos(conn, inicio=None, fim=None, limite: int = 10) -> list[dict]:
    cond, p = _periodo(inicio, fim)
    sql = f"""
        SELECT pr.sku, pr.nome,
               SUM(i.quantidade) AS unidades,
               SUM(i.quantidade * i.preco_unit_centavos) AS receita_bruta,
               SUM(i.quantidade * (i.preco_unit_centavos - i.custo_unit_centavos)) AS margem
        FROM itens_venda i
        JOIN vendas v ON v.id = i.venda_id
        JOIN produtos pr ON pr.id = i.produto_id
        WHERE {cond}
        GROUP BY pr.id ORDER BY unidades DESC LIMIT ?"""
    return [dict(r) for r in conn.execute(sql, [*p, limite])]


def estoque_baixo(conn, minimo: int = 5) -> list[dict]:
    sql = """
        SELECT l.nome AS loja, pr.sku, pr.nome AS produto, COALESCE(e.quantidade, 0) AS quantidade
        FROM lojas l CROSS JOIN produtos pr
        LEFT JOIN estoque e ON e.loja_id = l.id AND e.produto_id = pr.id
        WHERE pr.ativo = 1 AND COALESCE(e.quantidade, 0) < ?
        ORDER BY quantidade, l.nome"""
    return [dict(r) for r in conn.execute(sql, (minimo,))]


def faturamento_mensal(conn, ano: int) -> list[dict]:
    sql = """
        SELECT strftime('%m', v.data_hora) AS mes,
               COUNT(*) AS vendas, SUM(v.total_centavos) AS faturamento
        FROM vendas v
        WHERE v.status = 'CONCLUIDA' AND strftime('%Y', v.data_hora) = ?
        GROUP BY mes ORDER BY mes"""
    return [dict(r) for r in conn.execute(sql, (str(ano),))]
