"""Testes da API REST (RF20). Cada teste usa um banco novo em arquivo temporário."""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from rede_vendas import autenticacao as aut
from rede_vendas.api import criar_app
from rede_vendas.banco import conectar

SENHA = "senha-de-teste"


@pytest.fixture
def cliente(tmp_path):
    """Cliente HTTP já logado como gerente, com 2 lojas, 1 produto e 1 vendedor."""
    caminho = str(tmp_path / "api.db")
    conn = conectar(caminho)
    aut.criar_usuario(conn, "gerente", "Gerente", SENHA, "GERENTE")
    conn.close()
    with TestClient(criar_app(caminho, cookie_seguro=False)) as c:
        c.post("/api/auth/entrar", json={"login": "gerente", "senha": SENHA})
        loja = c.post("/api/lojas", json={"nome": "Centro", "cidade": "João Pessoa", "uf": "PB"})
        c.post("/api/lojas", json={"nome": "Brejo", "cidade": "Guarabira", "uf": "PB"})
        c.post(
            "/api/produtos",
            json={
                "sku": "CAD-1",
                "nome": "Caderno",
                "preco_centavos": 3000,
                "custo_centavos": 1500,
            },
        )
        c.post("/api/vendedores", json={"nome": "Ana", "loja_id": loja.json()["id"]})
        c.post("/api/estoque/entradas", json={"loja_id": 1, "produto_id": 1, "quantidade": 10})
        yield c


def test_saude(cliente):
    assert cliente.get("/api/saude").json()["status"] == "ok"


def test_cadastro_e_listagem(cliente):
    resposta = cliente.post("/api/clientes", json={"nome": "Maria", "cpf": "111"})
    assert resposta.status_code == 201
    assert cliente.get("/api/clientes").json()[0]["nome"] == "Maria"
    produto = cliente.get("/api/produtos").json()[0]
    assert produto == {
        "id": 1,
        "sku": "CAD-1",
        "nome": "Caderno",
        "preco": 3000,
        "custo": 1500,
        "estoque_total": 10,
        "ativo": True,
    }


def test_venda_completa_e_cancelamento(cliente):
    resposta = cliente.post(
        "/api/vendas",
        json={"vendedor_id": 1, "itens": [{"produto_id": 1, "quantidade": 2}], "desconto_pct": 10},
    )
    assert resposta.status_code == 201
    venda = resposta.json()
    assert venda["total"] == 5400
    assert venda["lista_itens"][0]["subtotal"] == 6000

    estoque = cliente.get("/api/estoque", params={"loja_id": 1}).json()
    assert estoque[0]["quantidade"] == 8

    assert cliente.post(f"/api/vendas/{venda['id']}/cancelar").status_code == 204
    assert cliente.get("/api/vendas").json()[0]["status"] == "CANCELADA"
    assert cliente.get("/api/estoque", params={"loja_id": 1}).json()[0]["quantidade"] == 10


def test_regra_de_negocio_vira_400(cliente):
    resposta = cliente.post(
        "/api/vendas", json={"vendedor_id": 1, "itens": [{"produto_id": 1, "quantidade": 99}]}
    )
    assert resposta.status_code == 400
    assert "Estoque insuficiente" in resposta.json()["detail"]


def test_inexistente_vira_404(cliente):
    assert cliente.get("/api/vendas/999").status_code == 404
    assert cliente.patch("/api/lojas/999", json={"nome": "X"}).status_code == 404


def test_duplicado_vira_409(cliente):
    resposta = cliente.post(
        "/api/produtos",
        json={"sku": "cad-1", "nome": "Outro", "preco_centavos": 10, "custo_centavos": 5},
    )
    assert resposta.status_code == 409
    assert "sku" in resposta.json()["detail"]


def test_validacao_de_entrada_vira_422(cliente):
    resposta = cliente.post("/api/vendas", json={"vendedor_id": 1, "itens": []})
    assert resposta.status_code == 422
    resposta = cliente.get("/api/relatorios/lojas", params={"inicio": "18/10/2026"})
    assert resposta.status_code == 422


def test_editar_e_desativar(cliente):
    assert cliente.patch("/api/produtos/1", json={"preco_centavos": 3500}).status_code == 204
    assert cliente.get("/api/produtos").json()[0]["preco"] == 3500
    assert cliente.patch("/api/produtos/1", json={}).status_code == 400

    assert cliente.post("/api/vendedores/1/desativar").status_code == 204
    assert cliente.get("/api/vendedores").json() == []
    assert cliente.get("/api/vendedores", params={"todos": True}).json()[0]["ativo"] is False
    assert cliente.post("/api/vendedores/1/ativar").status_code == 204


def test_transferencia(cliente):
    corpo = {"origem_id": 1, "destino_id": 2, "produto_id": 1, "quantidade": 4}
    assert cliente.post("/api/estoque/transferencias", json=corpo).status_code == 204
    saldos = {e["loja"]: e["quantidade"] for e in cliente.get("/api/estoque").json()}
    assert saldos == {"Centro": 6, "Brejo": 4}


def test_relatorios_e_resumo(cliente):
    cliente.post(
        "/api/vendas", json={"vendedor_id": 1, "itens": [{"produto_id": 1, "quantidade": 3}]}
    )
    resumo = cliente.get("/api/resumo").json()
    assert resumo["faturamento"] == 9000
    assert resumo["vendas"] == 1
    assert resumo["ticket_medio"] == 9000
    assert cliente.get("/api/relatorios/vendedores").json()[0]["comissao"] == 270  # 3%
    assert cliente.get("/api/relatorios/produtos").json()[0]["unidades"] == 3
    assert cliente.get("/api/relatorios/estoque-baixo", params={"minimo": 8}).json()
    mensal = cliente.get("/api/relatorios/mensal", params={"ano": datetime.now().year}).json()
    assert sum(m["faturamento"] for m in mensal) == 9000
