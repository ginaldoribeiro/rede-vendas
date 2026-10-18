import sqlite3

import pytest

from rede_vendas import relatorios as rel
from rede_vendas import servicos as sv
from rede_vendas.banco import conectar
from rede_vendas.cli import main


@pytest.fixture
def conn():
    c = conectar(":memory:")
    l1 = sv.cadastrar_loja(c, "Centro", "João Pessoa", "pb")
    l2 = sv.cadastrar_loja(c, "Brejo", "Guarabira", "PB")
    p = sv.cadastrar_produto(c, "cad-1", "Caderno", 30.0, 15.0)
    sv.cadastrar_vendedor(c, "Ana", l1, comissao_pct=5)
    sv.entrada_estoque(c, l1, p, 10)
    sv.entrada_estoque(c, l2, p, 2)
    yield c
    c.close()


def test_conversao_monetaria():
    assert sv.reais_para_centavos("R$ 1.234,56") == 123456
    assert sv.reais_para_centavos(29.9) == 2990
    assert sv.formatar_reais(123456) == "R$ 1.234,56"


def test_venda_baixa_estoque_e_aplica_desconto(conn):
    vid = sv.registrar_venda(conn, 1, [sv.ItemPedido(1, 3)], desconto_pct=10)
    venda = conn.execute("SELECT * FROM vendas WHERE id=?", (vid,)).fetchone()
    assert venda["total_centavos"] == 8100  # 3 x 30,00 - 10%
    assert sv.saldo(conn, 1, 1) == 7


def test_estoque_insuficiente_nao_grava_nada(conn):
    with pytest.raises(sv.ErroNegocio):
        sv.registrar_venda(conn, 1, [sv.ItemPedido(1, 11)])
    assert sv.saldo(conn, 1, 1) == 10
    assert conn.execute("SELECT COUNT(*) FROM vendas").fetchone()[0] == 0


def test_cancelamento_devolve_estoque(conn):
    vid = sv.registrar_venda(conn, 1, [sv.ItemPedido(1, 4)])
    sv.cancelar_venda(conn, vid)
    assert sv.saldo(conn, 1, 1) == 10
    with pytest.raises(sv.ErroNegocio):
        sv.cancelar_venda(conn, vid)


def test_transferencia_atomica(conn):
    sv.transferir(conn, 1, 2, 1, 5)
    assert (sv.saldo(conn, 1, 1), sv.saldo(conn, 2, 1)) == (5, 7)
    with pytest.raises(sv.ErroNegocio):
        sv.transferir(conn, 2, 1, 1, 50)
    assert (sv.saldo(conn, 1, 1), sv.saldo(conn, 2, 1)) == (5, 7)


def test_relatorios_ignoram_canceladas(conn):
    sv.registrar_venda(conn, 1, [sv.ItemPedido(1, 2)])
    cancelada = sv.registrar_venda(conn, 1, [sv.ItemPedido(1, 1)])
    sv.cancelar_venda(conn, cancelada)
    lojas = {r["loja"]: r for r in rel.faturamento_por_loja(conn)}
    assert lojas["Centro"]["faturamento"] == 6000
    ranking = rel.ranking_vendedores(conn)
    assert ranking[0]["comissao"] == 300  # 5% de R$ 60,00
    assert rel.produtos_mais_vendidos(conn)[0]["margem"] == 3000


def test_custo_maior_que_preco_rejeitado(conn):
    with pytest.raises(sv.ErroNegocio):
        sv.cadastrar_produto(conn, "X", "Errado", 10, 20)


def test_desconto_acima_do_limite_rejeitado(conn):
    with pytest.raises(sv.ErroNegocio):
        sv.registrar_venda(conn, 1, [sv.ItemPedido(1, 1)], desconto_pct=31)


def test_vendedor_inativo_nao_vende(conn):
    conn.execute("UPDATE vendedores SET ativo = 0 WHERE id = 1")
    with pytest.raises(sv.ErroNegocio):
        sv.registrar_venda(conn, 1, [sv.ItemPedido(1, 1)])


def test_transferencia_para_mesma_loja_rejeitada(conn):
    with pytest.raises(sv.ErroNegocio):
        sv.transferir(conn, 1, 1, 1, 1)


def test_sku_duplicado_rejeitado(conn):
    with pytest.raises(sqlite3.IntegrityError):
        sv.cadastrar_produto(conn, "CAD-1", "Outro caderno", 10, 5)


def test_estoque_baixo_inclui_produto_sem_registro(conn):
    sv.cadastrar_produto(conn, "NOVO", "Produto sem estoque", 10, 5)
    skus = {(r["loja"], r["sku"]) for r in rel.estoque_baixo(conn, minimo=5)}
    assert ("Centro", "NOVO") in skus
    assert ("Brejo", "CAD-1") in skus  # saldo 2


def test_cli_fluxo_completo(tmp_path, capsys):
    db = str(tmp_path / "teste.db")
    assert main(["--db", db, "exemplo"]) == 0
    assert main(["--db", db, "relatorio", "lojas"]) == 0
    assert "Loja Centro" in capsys.readouterr().out
    assert main(["--db", db, "vender", "1", "1:9999"]) == 1
    assert "Estoque insuficiente" in capsys.readouterr().err


def test_desconto_usa_arredondamento_comercial(conn):
    # 999 x R$ 0,30 = R$ 299,70 com 5% de desconto:
    # desconto exato de R$ 14,985 deve virar R$ 14,99 (meio centavo sobe), igual à tela.
    sv.cadastrar_produto(conn, "CLIPE", "Clipe", 0.30, 0.10)
    sv.entrada_estoque(conn, 1, 2, 999)
    vid = sv.registrar_venda(conn, 1, [sv.ItemPedido(2, 999)], desconto_pct=5)
    venda = conn.execute("SELECT * FROM vendas WHERE id=?", (vid,)).fetchone()
    assert venda["desconto_centavos"] == 1499
    assert venda["total_centavos"] == 29970 - 1499


def test_arredondamento_comercial():
    assert sv.arredondar(0.5) == 1
    assert sv.arredondar(2.5) == 3  # round(2.5) do Python daria 2
    assert sv.reais_para_centavos("0,005") == 1
