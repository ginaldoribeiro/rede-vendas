"""Testes de listagem, edição, ativação e migração (RF16–RF19)."""

import sqlite3

import pytest

from rede_vendas import relatorios as rel
from rede_vendas import servicos as sv
from rede_vendas.banco import conectar
from rede_vendas.cli import main


@pytest.fixture
def conn():
    c = conectar(":memory:")
    sv.cadastrar_loja(c, "Centro", "João Pessoa", "PB")
    sv.cadastrar_loja(c, "Brejo", "Guarabira", "PB")
    sv.cadastrar_produto(c, "CAD-1", "Caderno", 30.0, 15.0)
    sv.cadastrar_vendedor(c, "Ana", 1, comissao_pct=5)
    sv.cadastrar_cliente(c, "Maria", cpf="111", cidade="Guarabira")
    sv.entrada_estoque(c, 1, 1, 10)
    yield c
    c.close()


# ---------------------------------------------------------------- edição


def test_editar_altera_somente_campos_informados(conn):
    sv.editar_loja(conn, 1, cidade="Bayeux")
    loja = conn.execute("SELECT * FROM lojas WHERE id = 1").fetchone()
    assert (loja["nome"], loja["cidade"], loja["uf"]) == ("Centro", "Bayeux", "PB")


def test_editar_sem_campos_rejeitado(conn):
    with pytest.raises(sv.ErroNegocio):
        sv.editar_loja(conn, 1)


def test_editar_registro_inexistente_rejeitado(conn):
    with pytest.raises(sv.ErroNegocio):
        sv.editar_vendedor(conn, 99, nome="Ninguém")


@pytest.mark.parametrize(
    ("campos", "erro"),
    [
        ({"uf": "PBX"}, "UF inválida"),
        ({"nome": "   "}, "não pode ficar vazio"),
    ],
)
def test_editar_loja_valida_campos(conn, campos, erro):
    with pytest.raises(sv.ErroNegocio, match=erro):
        sv.editar_loja(conn, 1, **campos)


def test_editar_produto_valida_par_preco_custo(conn):
    # Só o custo muda, mas a regra RN06 é checada contra o preço atual.
    with pytest.raises(sv.ErroNegocio, match="Custo não pode"):
        sv.editar_produto(conn, 1, custo=31)
    sv.editar_produto(conn, 1, preco=40, custo=31)
    prod = conn.execute("SELECT * FROM produtos WHERE id = 1").fetchone()
    assert (prod["preco_centavos"], prod["custo_centavos"]) == (4000, 3100)


def test_editar_vendedor_valida_loja_e_comissao(conn):
    with pytest.raises(sv.ErroNegocio):
        sv.editar_vendedor(conn, 1, loja_id=99)
    with pytest.raises(sv.ErroNegocio, match="Comissão"):
        sv.editar_vendedor(conn, 1, comissao_pct=150)


def test_editar_cliente_string_vazia_apaga_valor(conn):
    sv.editar_cliente(conn, 1, cpf="")
    assert conn.execute("SELECT cpf FROM clientes WHERE id = 1").fetchone()[0] is None


def test_editar_cpf_duplicado_rejeitado(conn):
    sv.cadastrar_cliente(conn, "José", cpf="222")
    with pytest.raises(sqlite3.IntegrityError):
        sv.editar_cliente(conn, 2, cpf="111")


# ------------------------------------------------- histórico preservado


def test_mudar_preco_nao_altera_vendas_passadas(conn):
    sv.registrar_venda(conn, 1, [sv.ItemPedido(1, 2)])
    sv.editar_produto(conn, 1, preco=50)
    produto = rel.produtos_mais_vendidos(conn)[0]
    assert produto["receita_bruta"] == 6000  # 2 x R$ 30,00, preço da época


def test_mudar_comissao_e_loja_nao_altera_vendas_passadas(conn):
    sv.registrar_venda(conn, 1, [sv.ItemPedido(1, 2)])  # R$ 60,00 a 5% na loja Centro
    sv.editar_vendedor(conn, 1, comissao_pct=10, loja_id=2)
    sv.entrada_estoque(conn, 2, 1, 5)
    sv.registrar_venda(conn, 1, [sv.ItemPedido(1, 1)])  # R$ 30,00 a 10% na loja Brejo

    ranking = {r["loja"]: r for r in rel.ranking_vendedores(conn)}
    assert ranking["Centro"]["comissao"] == 300
    assert ranking["Brejo"]["comissao"] == 300


# ---------------------------------------------------- ativar/desativar


def test_produto_inativo_nao_vende_e_sai_das_listagens(conn):
    sv.definir_ativo(conn, "produto", 1, ativo=False)
    with pytest.raises(sv.ErroNegocio, match="inativo"):
        sv.registrar_venda(conn, 1, [sv.ItemPedido(1, 1)])
    assert sv.listar_produtos(conn) == []
    assert len(sv.listar_produtos(conn, incluir_inativos=True)) == 1
    assert rel.estoque_baixo(conn, minimo=100) == []


def test_reativar_vendedor_volta_a_vender(conn):
    sv.definir_ativo(conn, "vendedor", 1, ativo=False)
    assert sv.listar_vendedores(conn) == []
    sv.definir_ativo(conn, "vendedor", 1, ativo=True)
    assert sv.registrar_venda(conn, 1, [sv.ItemPedido(1, 1)])


def test_desativar_duas_vezes_rejeitado(conn):
    sv.definir_ativo(conn, "vendedor", 1, ativo=False)
    with pytest.raises(sv.ErroNegocio, match="já está inativo"):
        sv.definir_ativo(conn, "vendedor", 1, ativo=False)


def test_desativar_entidade_nao_suportada(conn):
    with pytest.raises(sv.ErroNegocio):
        sv.definir_ativo(conn, "loja", 1, ativo=False)


# ------------------------------------------------------------- listagem


def test_listagens(conn):
    assert sv.listar_lojas(conn)[0]["vendedores_ativos"] == 0  # Brejo vem antes (ordem alfabética)
    assert sv.listar_produtos(conn)[0]["estoque_total"] == 10
    assert sv.listar_vendedores(conn)[0]["loja"] == "Centro"
    assert sv.listar_clientes(conn)[0]["cpf"] == "111"


# -------------------------------------------------------------- migração

ESQUEMA_V010 = """
CREATE TABLE lojas (id INTEGER PRIMARY KEY, nome TEXT NOT NULL UNIQUE,
                    cidade TEXT NOT NULL, uf TEXT NOT NULL);
CREATE TABLE produtos (id INTEGER PRIMARY KEY, sku TEXT NOT NULL UNIQUE, nome TEXT NOT NULL,
                       preco_centavos INTEGER NOT NULL, custo_centavos INTEGER NOT NULL);
CREATE TABLE vendedores (id INTEGER PRIMARY KEY, nome TEXT NOT NULL, loja_id INTEGER NOT NULL,
                         comissao_pct REAL NOT NULL DEFAULT 3.0, ativo INTEGER NOT NULL DEFAULT 1);
CREATE TABLE vendas (id INTEGER PRIMARY KEY, loja_id INTEGER NOT NULL,
                     vendedor_id INTEGER NOT NULL, cliente_id INTEGER, data_hora TEXT NOT NULL,
                     desconto_centavos INTEGER NOT NULL DEFAULT 0,
                     total_centavos INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'CONCLUIDA');
INSERT INTO lojas VALUES (1, 'Centro', 'João Pessoa', 'PB');
INSERT INTO produtos VALUES (1, 'CAD-1', 'Caderno', 3000, 1500);
INSERT INTO vendedores VALUES (1, 'Ana', 1, 5.0, 1);
INSERT INTO vendas VALUES (1, 1, 1, NULL, '2026-05-01T10:00:00', 0, 6000, 'CONCLUIDA');
"""


def test_migracao_de_banco_da_versao_anterior(tmp_path):
    caminho = str(tmp_path / "antigo.db")
    antigo = sqlite3.connect(caminho)
    antigo.executescript(ESQUEMA_V010)
    antigo.close()

    conn = conectar(caminho)
    assert conn.execute("SELECT ativo FROM produtos WHERE id = 1").fetchone()[0] == 1
    assert conn.execute("SELECT comissao_pct FROM vendas WHERE id = 1").fetchone()[0] == 5.0
    conn.close()
    conectar(caminho).close()  # abrir de novo não deve falhar (migração idempotente)


# ------------------------------------------------------------------- CLI


def test_cli_listar_editar_desativar(tmp_path, capsys):
    db = ["--db", str(tmp_path / "t.db")]
    assert main([*db, "exemplo"]) == 0
    assert main([*db, "editar", "produto", "1", "--preco", "35"]) == 0
    assert main([*db, "desativar", "vendedor", "1"]) == 0
    capsys.readouterr()
    assert main([*db, "listar", "vendedores", "--todos"]) == 0
    assert "não" in capsys.readouterr().out
    assert main([*db, "editar", "loja", "1"]) == 1
    assert "pelo menos um campo" in capsys.readouterr().err
