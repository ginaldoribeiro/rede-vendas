"""Autenticação, sessões e permissões por perfil (RF23–RF26)."""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from rede_vendas import autenticacao as aut
from rede_vendas import servicos as sv
from rede_vendas.api import criar_app
from rede_vendas.banco import conectar
from rede_vendas.cli import main

SENHA = "senha-forte-123"


@pytest.fixture
def caminho(tmp_path):
    """Banco com 2 lojas, 1 produto, vendedoras Ana (Centro) e Bia (Brejo) e 3 usuários."""
    caminho = str(tmp_path / "auth.db")
    conn = conectar(caminho)
    sv.cadastrar_loja(conn, "Centro", "João Pessoa", "PB")
    sv.cadastrar_loja(conn, "Brejo", "Guarabira", "PB")
    sv.cadastrar_produto(conn, "CAD-1", "Caderno", 30, 15)
    sv.cadastrar_vendedor(conn, "Ana", 1)
    sv.cadastrar_vendedor(conn, "Bia", 2)
    sv.entrada_estoque(conn, 1, 1, 10)
    sv.entrada_estoque(conn, 2, 1, 10)
    aut.criar_usuario(conn, "gerente", "Gerente", SENHA, "GERENTE")
    aut.criar_usuario(conn, "ana", "Ana", SENHA, "VENDEDOR", vendedor_id=1)
    aut.criar_usuario(conn, "bia", "Bia", SENHA, "VENDEDOR", vendedor_id=2)
    conn.close()
    return caminho


def _cliente(caminho: str, login: str | None = None) -> TestClient:
    c = TestClient(criar_app(caminho, cookie_seguro=False))
    if login:
        r = c.post("/api/auth/entrar", json={"login": login, "senha": SENHA})
        assert r.status_code == 200, r.text
    return c


VENDA = {"itens": [{"produto_id": 1, "quantidade": 1}]}

# ------------------------------------------------------------------- senhas


def test_senha_guardada_como_hash_com_sal():
    h1, h2 = aut.gerar_hash("abcdefgh"), aut.gerar_hash("abcdefgh")
    assert h1 != h2  # sal diferente a cada vez
    assert "abcdefgh" not in h1
    assert aut.conferir_senha("abcdefgh", h1)
    assert not aut.conferir_senha("abcdefgx", h1)
    assert not aut.conferir_senha("abcdefgh", "lixo")


def test_regras_de_criacao_de_usuario(caminho):
    conn = conectar(caminho)
    with pytest.raises(sv.ErroNegocio, match="pelo menos 8"):
        aut.criar_usuario(conn, "novo", "Novo", "curta", "GERENTE")
    with pytest.raises(sv.ErroNegocio, match="ligado a um vendedor"):
        aut.criar_usuario(conn, "novo", "Novo", SENHA, "VENDEDOR")
    with pytest.raises(sv.ErroNegocio, match="Login deve"):
        aut.criar_usuario(conn, "com espaço", "Novo", SENHA, "GERENTE")
    with pytest.raises(sqlite3.IntegrityError):  # login é único, sem diferenciar maiúsculas
        aut.criar_usuario(conn, "ANA", "Outra Ana", SENHA, "GERENTE")
    with pytest.raises(sqlite3.IntegrityError):  # um usuário por vendedor
        aut.criar_usuario(conn, "ana2", "Ana de novo", SENHA, "VENDEDOR", vendedor_id=1)


# ------------------------------------------------------------- login/sessão


def test_sem_login_tudo_e_401_menos_saude_e_entrar(caminho):
    c = _cliente(caminho)
    assert c.get("/api/saude").status_code == 200
    for rota in ("/api/auth/eu", "/api/produtos", "/api/vendas", "/api/resumo", "/api/usuarios"):
        assert c.get(rota).status_code == 401, rota
    assert c.post("/api/vendas", json={**VENDA, "vendedor_id": 1}).status_code == 401


def test_login_cria_cookie_seguro_e_sair_encerra_sessao(caminho):
    c = TestClient(criar_app(caminho, cookie_seguro=True), base_url="https://testserver")
    r = c.post("/api/auth/entrar", json={"login": "Gerente", "senha": SENHA})
    assert r.status_code == 200
    assert r.json()["perfil"] == "GERENTE"
    cookie = r.headers["set-cookie"].lower()
    for atributo in ("httponly", "secure", "samesite=strict", "path=/api"):
        assert atributo in cookie
    assert c.get("/api/auth/eu").status_code == 200
    c.post("/api/auth/sair")
    assert c.get("/api/auth/eu").status_code == 401


def test_senha_errada_e_bloqueio_apos_5_tentativas(caminho):
    c = _cliente(caminho)
    for _ in range(5):
        r = c.post("/api/auth/entrar", json={"login": "ana", "senha": "errada!!"})
        assert r.status_code == 401
        assert r.json()["detail"] == "Login ou senha incorretos."
    r = c.post("/api/auth/entrar", json={"login": "ana", "senha": SENHA})
    assert r.status_code == 401
    assert "Muitas tentativas" in r.json()["detail"]


def test_login_inexistente_tem_a_mesma_mensagem(caminho):
    r = _cliente(caminho).post("/api/auth/entrar", json={"login": "ninguem", "senha": SENHA})
    assert r.json()["detail"] == "Login ou senha incorretos."


def test_token_guardado_so_como_hash(caminho):
    c = _cliente(caminho, "ana")
    token = c.cookies.get("rv_sessao")
    conn = conectar(caminho)
    guardados = [r[0] for r in conn.execute("SELECT token_hash FROM sessoes")]
    assert token not in guardados
    assert len(guardados) == 1


def test_sessao_expirada(caminho):
    c = _cliente(caminho, "ana")
    conn = conectar(caminho)
    with conn:
        conn.execute("UPDATE sessoes SET expira_em = '2000-01-01T00:00:00'")
    r = c.get("/api/auth/eu")
    assert r.status_code == 401
    assert "expirou" in r.json()["detail"]


def test_trocar_propria_senha_encerra_sessoes(caminho):
    c = _cliente(caminho, "ana")
    r = c.post("/api/auth/senha", json={"atual": "errada!!", "nova": "outra-senha-1"})
    assert r.status_code == 400
    r = c.post("/api/auth/senha", json={"atual": SENHA, "nova": "outra-senha-1"})
    assert r.status_code == 204
    assert c.get("/api/auth/eu").status_code == 401
    nova = c.post("/api/auth/entrar", json={"login": "ana", "senha": "outra-senha-1"})
    assert nova.status_code == 200


# ----------------------------------------------------------------- vendedor


def test_vendedor_nao_acessa_rotas_de_gerente(caminho):
    c = _cliente(caminho, "ana")
    proibidas_get = [
        "/api/resumo",
        "/api/relatorios/lojas",
        "/api/usuarios",
        "/api/lojas",
        "/api/vendedores",
    ]
    for rota in proibidas_get:
        assert c.get(rota).status_code == 403, rota
    proibidas_post = ["/api/vendas/1/cancelar", "/api/produtos/1/desativar"]
    for rota in proibidas_post:
        assert c.post(rota).status_code == 403, rota
    corpo = {"loja_id": 1, "produto_id": 1, "quantidade": 5}
    assert c.post("/api/estoque/entradas", json=corpo).status_code == 403
    assert c.patch("/api/produtos/1", json={"preco_centavos": 1}).status_code == 403


def test_vendedor_vende_sempre_em_nome_proprio(caminho):
    c = _cliente(caminho, "ana")
    r = c.post("/api/vendas", json={**VENDA, "vendedor_id": 2})  # tenta vender como Bia
    assert r.status_code == 201
    assert r.json()["vendedor"] == "Ana"
    assert r.json()["loja"] == "Centro"


def test_vendedor_ve_so_proprias_vendas_e_proprio_estoque(caminho):
    ana, bia = _cliente(caminho, "ana"), _cliente(caminho, "bia")
    venda_ana = ana.post("/api/vendas", json=VENDA).json()["id"]
    bia.post("/api/vendas", json=VENDA)

    assert [v["vendedor"] for v in ana.get("/api/vendas").json()] == ["Ana"]
    assert bia.get(f"/api/vendas/{venda_ana}").status_code == 404  # nem confirma que existe
    assert ana.get(f"/api/vendas/{venda_ana}").status_code == 200

    estoque = ana.get("/api/estoque", params={"loja_id": 2}).json()  # pede outra loja
    assert {e["loja"] for e in estoque} == {"Centro"}


def test_vendedor_cadastra_cliente_mas_nao_edita(caminho):
    c = _cliente(caminho, "ana")
    assert c.post("/api/clientes", json={"nome": "Maria"}).status_code == 201
    assert c.patch("/api/clientes/1", json={"nome": "Outra"}).status_code == 403


# ------------------------------------------------------------------ gerente


def test_gerente_precisa_informar_vendedor(caminho):
    c = _cliente(caminho, "gerente")
    assert c.post("/api/vendas", json=VENDA).status_code == 400
    assert c.post("/api/vendas", json={**VENDA, "vendedor_id": 2}).json()["vendedor"] == "Bia"


def test_gerente_gerencia_usuarios(caminho):
    c = _cliente(caminho, "gerente")
    corpo = {"login": "novo", "nome": "Novo", "senha": SENHA, "perfil": "GERENTE"}
    assert c.post("/api/usuarios", json=corpo).status_code == 201
    assert c.post("/api/usuarios", json=corpo).status_code == 409

    ana = _cliente(caminho, "ana")
    assert c.post("/api/usuarios/2/desativar").status_code == 204
    assert ana.get("/api/auth/eu").status_code == 401  # sessão encerrada na hora
    assert c.post("/api/usuarios/2/ativar").status_code == 204

    assert c.post("/api/usuarios/2/senha", json={"nova": "redefinida-1"}).status_code == 204
    r = ana.post("/api/auth/entrar", json={"login": "ana", "senha": "redefinida-1"})
    assert r.status_code == 200


def test_rede_nunca_fica_sem_gerente(caminho):
    c = _cliente(caminho, "gerente")
    r = c.post("/api/usuarios/1/desativar")
    assert r.status_code == 400
    assert "próprio usuário" in r.json()["detail"]


# --------------------------------------------------------- primeira subida


def test_primeiro_gerente_criado_pelas_variaveis(tmp_path, monkeypatch):
    monkeypatch.setenv("REDE_VENDAS_ADMIN_LOGIN", "admin")
    monkeypatch.setenv("REDE_VENDAS_ADMIN_SENHA", SENHA)
    caminho = str(tmp_path / "novo.db")
    with TestClient(criar_app(caminho, cookie_seguro=False)) as c:
        assert (
            c.post("/api/auth/entrar", json={"login": "admin", "senha": SENHA}).status_code == 200
        )
    monkeypatch.setenv("REDE_VENDAS_ADMIN_SENHA", "outra-senha-qualquer")
    with TestClient(criar_app(caminho, cookie_seguro=False)) as c:  # não recria nem troca
        assert (
            c.post("/api/auth/entrar", json={"login": "admin", "senha": SENHA}).status_code == 200
        )


def test_cabecalhos_de_seguranca(caminho):
    r = _cliente(caminho).get("/api/saude")
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "default-src 'self'" in r.headers["content-security-policy"]
    assert r.headers["cache-control"] == "no-store"


# ---------------------------------------------------------------------- CLI


def test_cli_criar_usuario_e_backup(caminho, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("REDE_VENDAS_SENHA", SENHA)
    db = ["--db", caminho]
    assert main([*db, "criar-usuario", "carlos", "Carlos", "--perfil", "gerente"]) == 0
    assert main([*db, "backup", str(tmp_path)]) == 0
    copia = next(tmp_path.glob("rede_vendas_*.db"))
    conn = conectar(str(copia))
    assert conn.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0] == 4
    assert "Backup salvo" in capsys.readouterr().out
