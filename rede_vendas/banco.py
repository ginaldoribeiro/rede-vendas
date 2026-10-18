"""Conexão e esquema do banco SQLite da rede de vendas.

Valores monetários são guardados em centavos (inteiros) para evitar
erros de arredondamento de ponto flutuante.
"""

import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS lojas (
    id      INTEGER PRIMARY KEY,
    nome    TEXT NOT NULL UNIQUE,
    cidade  TEXT NOT NULL,
    uf      TEXT NOT NULL CHECK (length(uf) = 2)
);

CREATE TABLE IF NOT EXISTS produtos (
    id              INTEGER PRIMARY KEY,
    sku             TEXT NOT NULL UNIQUE,
    nome            TEXT NOT NULL,
    preco_centavos  INTEGER NOT NULL CHECK (preco_centavos >= 0),
    custo_centavos  INTEGER NOT NULL CHECK (custo_centavos >= 0),
    ativo           INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS estoque (
    loja_id     INTEGER NOT NULL REFERENCES lojas(id),
    produto_id  INTEGER NOT NULL REFERENCES produtos(id),
    quantidade  INTEGER NOT NULL DEFAULT 0 CHECK (quantidade >= 0),
    PRIMARY KEY (loja_id, produto_id)
);

CREATE TABLE IF NOT EXISTS vendedores (
    id            INTEGER PRIMARY KEY,
    nome          TEXT NOT NULL,
    loja_id       INTEGER NOT NULL REFERENCES lojas(id),
    comissao_pct  REAL NOT NULL DEFAULT 3.0 CHECK (comissao_pct BETWEEN 0 AND 100),
    ativo         INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS clientes (
    id      INTEGER PRIMARY KEY,
    nome    TEXT NOT NULL,
    cpf     TEXT UNIQUE,
    cidade  TEXT
);

CREATE TABLE IF NOT EXISTS vendas (
    id                 INTEGER PRIMARY KEY,
    loja_id            INTEGER NOT NULL REFERENCES lojas(id),
    vendedor_id        INTEGER NOT NULL REFERENCES vendedores(id),
    cliente_id         INTEGER REFERENCES clientes(id),
    data_hora          TEXT NOT NULL,
    desconto_centavos  INTEGER NOT NULL DEFAULT 0,
    total_centavos     INTEGER NOT NULL,
    comissao_pct       REAL NOT NULL DEFAULT 0,
    status             TEXT NOT NULL DEFAULT 'CONCLUIDA'
                       CHECK (status IN ('CONCLUIDA', 'CANCELADA'))
);

CREATE TABLE IF NOT EXISTS itens_venda (
    id                   INTEGER PRIMARY KEY,
    venda_id             INTEGER NOT NULL REFERENCES vendas(id),
    produto_id           INTEGER NOT NULL REFERENCES produtos(id),
    quantidade           INTEGER NOT NULL CHECK (quantidade > 0),
    preco_unit_centavos  INTEGER NOT NULL,
    custo_unit_centavos  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS transferencias (
    id          INTEGER PRIMARY KEY,
    origem_id   INTEGER NOT NULL REFERENCES lojas(id),
    destino_id  INTEGER NOT NULL REFERENCES lojas(id),
    produto_id  INTEGER NOT NULL REFERENCES produtos(id),
    quantidade  INTEGER NOT NULL CHECK (quantidade > 0),
    data_hora   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS usuarios (
    id           INTEGER PRIMARY KEY,
    login        TEXT NOT NULL UNIQUE COLLATE NOCASE,
    nome         TEXT NOT NULL,
    senha_hash   TEXT NOT NULL,
    perfil       TEXT NOT NULL CHECK (perfil IN ('GERENTE', 'VENDEDOR')),
    vendedor_id  INTEGER UNIQUE REFERENCES vendedores(id),
    ativo        INTEGER NOT NULL DEFAULT 1,
    CHECK (perfil = 'GERENTE' OR vendedor_id IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS sessoes (
    token_hash  TEXT PRIMARY KEY,
    usuario_id  INTEGER NOT NULL REFERENCES usuarios(id),
    criada_em   TEXT NOT NULL,
    expira_em   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_vendas_data ON vendas(data_hora);
CREATE INDEX IF NOT EXISTS idx_itens_venda ON itens_venda(venda_id);
"""


def _colunas(conn: sqlite3.Connection, tabela: str) -> set[str]:
    return {linha[1] for linha in conn.execute(f"PRAGMA table_info({tabela})")}


def _migrar(conn: sqlite3.Connection) -> None:
    """Atualiza bancos criados pela versão 0.1.0 sem perder dados."""
    with conn:
        if "ativo" not in _colunas(conn, "produtos"):
            conn.execute("ALTER TABLE produtos ADD COLUMN ativo INTEGER NOT NULL DEFAULT 1")
        if "comissao_pct" not in _colunas(conn, "vendas"):
            conn.execute("ALTER TABLE vendas ADD COLUMN comissao_pct REAL NOT NULL DEFAULT 0")
            # Vendas antigas recebem a comissão vigente do vendedor no momento da migração.
            conn.execute(
                """UPDATE vendas SET comissao_pct =
                   (SELECT comissao_pct FROM vendedores WHERE vendedores.id = vendas.vendedor_id)"""
            )


def conectar(caminho: str = "rede_vendas.db") -> sqlite3.Connection:
    """Abre (ou cria) o banco, garante que o esquema exista e aplica migrações.

    `check_same_thread=False` permite que a API abra a conexão numa thread e a use em
    outra; cada requisição tem a sua própria conexão, então não há compartilhamento.
    """
    conn = sqlite3.connect(caminho, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    _migrar(conn)
    return conn
