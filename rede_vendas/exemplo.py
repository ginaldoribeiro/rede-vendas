"""Dados de demonstração: 3 lojas na Paraíba, 6 produtos, 6 vendedores e ~150 vendas."""

import contextlib
import random
from datetime import datetime, timedelta

from . import servicos as sv

LOJAS = [
    ("Loja Centro", "João Pessoa", "PB"),
    ("Loja Brejo", "Guarabira", "PB"),
    ("Loja Serra", "Campina Grande", "PB"),
]

PRODUTOS = [
    ("CAD-001", "Caderno 10 matérias", 29.90, 14.50),
    ("MOC-002", "Mochila escolar", 149.90, 80.00),
    ("CAN-003", "Caneta esferográfica (cx 50)", 39.90, 18.00),
    ("CAL-004", "Calculadora científica", 89.90, 45.00),
    ("FON-005", "Fone de ouvido Bluetooth", 119.90, 60.00),
    ("PEN-006", "Pendrive 64 GB", 49.90, 22.00),
]


def popular_exemplo(conn, semente: int = 42) -> None:
    if conn.execute("SELECT COUNT(*) FROM lojas").fetchone()[0]:
        raise sv.ErroNegocio("O banco já possui dados; use outro arquivo com --db.")
    rnd = random.Random(semente)

    lojas = [sv.cadastrar_loja(conn, *dados) for dados in LOJAS]
    produtos = [sv.cadastrar_produto(conn, *p) for p in PRODUTOS]
    vendedores = [
        sv.cadastrar_vendedor(conn, nome, lojas[i // 2], rnd.choice([2.5, 3.0, 4.0]))
        for i, nome in enumerate(["Ana", "Bruno", "Carla", "Diego", "Elisa", "Fábio"])
    ]
    clientes = [
        sv.cadastrar_cliente(conn, n, cidade=c)
        for n, c in [
            ("Maria Souza", "Guarabira"),
            ("José Lima", "João Pessoa"),
            ("Paula Nunes", "Campina Grande"),
            ("Rafael Dias", "Guarabira"),
        ]
    ]

    for loja in lojas:
        for prod in produtos:
            sv.entrada_estoque(conn, loja, prod, rnd.randint(40, 90))

    inicio = datetime(2026, 1, 5, 9, 0)
    for _ in range(150):
        vendedor = rnd.choice(vendedores)
        escolhidos = rnd.sample(produtos, rnd.randint(1, 3))
        itens = [sv.ItemPedido(p, rnd.randint(1, 3)) for p in escolhidos]
        quando = inicio + timedelta(days=rnd.randint(0, 270), hours=rnd.randint(0, 9))
        # Se o estoque acabou naquela loja, a venda é recusada e simplesmente não acontece.
        with contextlib.suppress(sv.ErroNegocio):
            sv.registrar_venda(
                conn,
                vendedor,
                itens,
                cliente_id=rnd.choice([None, *clientes]),
                desconto_pct=rnd.choice([0, 0, 0, 5, 10]),
                data_hora=quando.isoformat(timespec="seconds"),
            )
