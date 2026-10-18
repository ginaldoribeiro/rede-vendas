"""Interface de linha de comando: python -m rede_vendas <comando> [opções]."""

from __future__ import annotations

import argparse
import getpass
import os
import sqlite3
import sys
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from . import autenticacao as aut
from . import relatorios as rel
from . import servicos as sv
from .banco import conectar
from .exemplo import popular_exemplo

COLUNAS_MONETARIAS = {
    "faturamento",
    "ticket_medio",
    "comissao",
    "receita_bruta",
    "margem",
    "preco",
    "custo",
    "total",
    "desconto",
    "preco_unit",
    "subtotal",
}
ANO_PADRAO = 2026


# ------------------------------------------------------------------ saída


def _formatar_celula(coluna: str, valor: object) -> str:
    if coluna in COLUNAS_MONETARIAS:
        return sv.formatar_reais(int(valor or 0))
    if isinstance(valor, bool):
        return "sim" if valor else "não"
    if coluna == "comissao_pct":
        return f"{valor:g}%"
    if valor is None:
        return "-"
    return str(valor)


def imprimir_tabela(linhas: list[dict]) -> None:
    if not linhas:
        print("(nenhum registro)")
        return
    tabela = [{col: _formatar_celula(col, val) for col, val in linha.items()} for linha in linhas]
    colunas = list(tabela[0])
    largura = {c: max(len(c), *(len(linha[c]) for linha in tabela)) for c in colunas}

    print("  ".join(c.upper().ljust(largura[c]) for c in colunas))
    print("  ".join("-" * largura[c] for c in colunas))
    for linha in tabela:
        celulas = (
            linha[c].rjust(largura[c]) if c in COLUNAS_MONETARIAS else linha[c].ljust(largura[c])
            for c in colunas
        )
        print("  ".join(celulas))


def _itens(textos: list[str]) -> list[sv.ItemPedido]:
    """Converte ['1:2', '3:1'] em itens (produto_id:quantidade)."""
    itens = []
    for texto in textos:
        try:
            produto_id, quantidade = texto.split(":")
            itens.append(sv.ItemPedido(int(produto_id), int(quantidade)))
        except ValueError as erro:
            raise sv.ErroNegocio(f"Item inválido '{texto}'. Use produto_id:quantidade.") from erro
    return itens


# --------------------------------------------------------------- comandos


def _cmd_exemplo(conn: sqlite3.Connection, _args: argparse.Namespace) -> None:
    popular_exemplo(conn)
    print("Dados de exemplo criados.")


def _cmd_loja(conn, args) -> None:
    print("Loja criada, id", sv.cadastrar_loja(conn, args.nome, args.cidade, args.uf))


def _cmd_produto(conn, args) -> None:
    produto_id = sv.cadastrar_produto(conn, args.sku, args.nome, args.preco, args.custo)
    print("Produto criado, id", produto_id)


def _cmd_vendedor(conn, args) -> None:
    vendedor_id = sv.cadastrar_vendedor(conn, args.nome, args.loja_id, args.comissao)
    print("Vendedor criado, id", vendedor_id)


def _cmd_cliente(conn, args) -> None:
    print("Cliente criado, id", sv.cadastrar_cliente(conn, args.nome, args.cpf, args.cidade))


def _cmd_entrada(conn, args) -> None:
    novo_saldo = sv.entrada_estoque(conn, args.loja_id, args.produto_id, args.quantidade)
    print("Saldo atual:", novo_saldo)


def _cmd_transferir(conn, args) -> None:
    sv.transferir(conn, args.origem, args.destino, args.produto_id, args.quantidade)
    print("Transferência registrada.")


def _cmd_vender(conn, args) -> None:
    venda_id = sv.registrar_venda(
        conn,
        args.vendedor_id,
        _itens(args.itens),
        cliente_id=args.cliente,
        desconto_pct=args.desconto,
    )
    sql = "SELECT total_centavos FROM vendas WHERE id = ?"
    total = conn.execute(sql, (venda_id,)).fetchone()[0]
    print(f"Venda {venda_id} registrada. Total: {sv.formatar_reais(total)}")


def _cmd_cancelar(conn, args) -> None:
    sv.cancelar_venda(conn, args.venda_id)
    print("Venda cancelada e estoque devolvido.")


def _cmd_relatorio(conn, args) -> None:
    geradores: dict[str, Callable[[], list[dict]]] = {
        "lojas": lambda: rel.faturamento_por_loja(conn, args.inicio, args.fim),
        "vendedores": lambda: rel.ranking_vendedores(conn, args.inicio, args.fim),
        "produtos": lambda: rel.produtos_mais_vendidos(conn, args.inicio, args.fim),
        "estoque-baixo": lambda: rel.estoque_baixo(conn, args.minimo),
        "mensal": lambda: rel.faturamento_mensal(conn, args.ano or ANO_PADRAO),
    }
    imprimir_tabela(geradores[args.tipo]())


def _cmd_listar(conn, args) -> None:
    listagens: dict[str, Callable[[], list[dict]]] = {
        "lojas": lambda: sv.listar_lojas(conn),
        "produtos": lambda: sv.listar_produtos(conn, incluir_inativos=args.todos),
        "vendedores": lambda: sv.listar_vendedores(conn, incluir_inativos=args.todos),
        "clientes": lambda: sv.listar_clientes(conn),
        "estoque": lambda: sv.listar_estoque(conn),
        "vendas": lambda: sv.listar_vendas(conn, limite=20),
    }
    imprimir_tabela(listagens[args.entidade]())


def _cmd_editar(conn, args) -> None:
    match args.entidade:
        case "loja":
            sv.editar_loja(conn, args.id, nome=args.nome, cidade=args.cidade, uf=args.uf)
        case "produto":
            sv.editar_produto(conn, args.id, nome=args.nome, preco=args.preco, custo=args.custo)
        case "vendedor":
            sv.editar_vendedor(
                conn, args.id, nome=args.nome, loja_id=args.loja, comissao_pct=args.comissao
            )
        case "cliente":
            sv.editar_cliente(conn, args.id, nome=args.nome, cpf=args.cpf, cidade=args.cidade)
    print(f"{args.entidade.capitalize()} {args.id} atualizado.")


def _cmd_desativar(conn, args) -> None:
    sv.definir_ativo(conn, args.entidade, args.id, ativo=False)
    print(f"{args.entidade.capitalize()} {args.id} desativado. O histórico foi mantido.")


def _cmd_reativar(conn, args) -> None:
    sv.definir_ativo(conn, args.entidade, args.id, ativo=True)
    print(f"{args.entidade.capitalize()} {args.id} reativado.")


def _cmd_criar_usuario(conn, args) -> None:
    """A senha vem de REDE_VENDAS_SENHA (scripts) ou é pedida sem aparecer na tela."""
    senha = os.environ.get("REDE_VENDAS_SENHA") or getpass.getpass("Senha: ")
    if not os.environ.get("REDE_VENDAS_SENHA") and senha != getpass.getpass("Repita a senha: "):
        raise sv.ErroNegocio("As senhas não conferem.")
    usuario_id = aut.criar_usuario(
        conn, args.login, args.nome, senha, args.perfil.upper(), args.vendedor
    )
    print(f"Usuário '{args.login}' criado (id {usuario_id}).")


def _cmd_backup(conn, args) -> None:
    """Cópia consistente do banco, segura mesmo com a API rodando (API de backup do SQLite)."""
    destino = Path(args.destino)
    if destino.is_dir():
        destino = destino / f"rede_vendas_{datetime.now():%Y%m%d_%H%M%S}.db"
    if destino.exists():
        raise sv.ErroNegocio(f"O arquivo {destino} já existe.")
    copia = sqlite3.connect(destino)
    try:
        conn.backup(copia)
    finally:
        copia.close()
    print(f"Backup salvo em {destino}")


COMANDOS: dict[str, Callable[[sqlite3.Connection, argparse.Namespace], None]] = {
    "exemplo": _cmd_exemplo,
    "loja": _cmd_loja,
    "produto": _cmd_produto,
    "vendedor": _cmd_vendedor,
    "cliente": _cmd_cliente,
    "entrada": _cmd_entrada,
    "transferir": _cmd_transferir,
    "vender": _cmd_vender,
    "cancelar": _cmd_cancelar,
    "relatorio": _cmd_relatorio,
    "listar": _cmd_listar,
    "editar": _cmd_editar,
    "desativar": _cmd_desativar,
    "reativar": _cmd_reativar,
    "criar-usuario": _cmd_criar_usuario,
    "backup": _cmd_backup,
}


# ----------------------------------------------------------------- parser


def _args(parser: argparse.ArgumentParser, *nomes: str, tipo: type = str) -> None:
    for nome in nomes:
        parser.add_argument(nome, type=tipo)


def montar_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rede_vendas", description="Gestão de uma rede de lojas.")
    parser.add_argument(
        "--db",
        default=os.environ.get("REDE_VENDAS_DB", "rede_vendas.db"),
        help="arquivo SQLite (padrão: $REDE_VENDAS_DB ou rede_vendas.db)",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("exemplo", help="popula o banco com dados de demonstração")

    _args(sub.add_parser("loja", help="cadastra loja"), "nome", "cidade", "uf")

    p = sub.add_parser("produto", help="cadastra produto")
    _args(p, "sku", "nome")
    _args(p, "preco", "custo", tipo=float)

    p = sub.add_parser("vendedor", help="cadastra vendedor")
    _args(p, "nome")
    _args(p, "loja_id", tipo=int)
    p.add_argument("--comissao", type=float, default=3.0)

    p = sub.add_parser("cliente", help="cadastra cliente")
    _args(p, "nome")
    p.add_argument("--cpf")
    p.add_argument("--cidade")

    p = sub.add_parser("entrada", help="entrada de estoque")
    _args(p, "loja_id", "produto_id", "quantidade", tipo=int)

    p = sub.add_parser("transferir", help="transfere estoque entre lojas")
    _args(p, "origem", "destino", "produto_id", "quantidade", tipo=int)

    p = sub.add_parser("vender", help="registra venda (itens no formato produto_id:qtd)")
    _args(p, "vendedor_id", tipo=int)
    p.add_argument("itens", nargs="+")
    p.add_argument("--cliente", type=int)
    p.add_argument("--desconto", type=float, default=0.0)

    p = sub.add_parser("cancelar", help="cancela venda e devolve estoque")
    _args(p, "venda_id", tipo=int)

    p = sub.add_parser("relatorio", help="relatórios gerenciais")
    p.add_argument("tipo", choices=["lojas", "vendedores", "produtos", "estoque-baixo", "mensal"])
    p.add_argument("--inicio", help="data inicial AAAA-MM-DD")
    p.add_argument("--fim", help="data final AAAA-MM-DD")
    p.add_argument("--minimo", type=int, default=5)
    p.add_argument("--ano", type=int)

    p = sub.add_parser("listar", help="lista cadastros")
    p.add_argument(
        "entidade", choices=["lojas", "produtos", "vendedores", "clientes", "estoque", "vendas"]
    )
    p.add_argument("--todos", action="store_true", help="inclui produtos/vendedores inativos")

    _parser_editar(sub)

    p = sub.add_parser("criar-usuario", help="cria usuário de acesso ao sistema web")
    _args(p, "login", "nome")
    p.add_argument("--perfil", choices=["gerente", "vendedor"], default="gerente")
    p.add_argument("--vendedor", type=int, help="id do vendedor (obrigatório para perfil vendedor)")

    p = sub.add_parser("backup", help="copia o banco para um arquivo ou pasta")
    p.add_argument("destino")

    for comando, ajuda in (("desativar", "desativa"), ("reativar", "reativa")):
        p = sub.add_parser(comando, help=f"{ajuda} vendedor ou produto (sem apagar histórico)")
        p.add_argument("entidade", choices=["vendedor", "produto"])
        _args(p, "id", tipo=int)
    return parser


def _parser_editar(sub: argparse._SubParsersAction) -> None:
    """editar <entidade> <id> [--campo valor ...]: só os campos informados mudam."""
    editar = sub.add_parser("editar", help="altera cadastros (só os campos informados)")
    entidades = editar.add_subparsers(dest="entidade", required=True)

    p = entidades.add_parser("loja")
    _args(p, "id", tipo=int)
    for campo in ("--nome", "--cidade", "--uf"):
        p.add_argument(campo)

    p = entidades.add_parser("produto")
    _args(p, "id", tipo=int)
    p.add_argument("--nome")
    p.add_argument("--preco", type=float)
    p.add_argument("--custo", type=float)

    p = entidades.add_parser("vendedor")
    _args(p, "id", tipo=int)
    p.add_argument("--nome")
    p.add_argument("--loja", type=int, help="id da nova loja")
    p.add_argument("--comissao", type=float)

    p = entidades.add_parser("cliente")
    _args(p, "id", tipo=int)
    for campo in ("--nome", "--cpf", "--cidade"):
        p.add_argument(campo, help="texto vazio apaga o valor" if campo != "--nome" else None)


def main(argv: list[str] | None = None) -> int:
    args = montar_parser().parse_args(argv)
    conn = conectar(args.db)
    try:
        COMANDOS[args.cmd](conn, args)
    except sv.ErroNegocio as erro:
        print("Erro:", erro, file=sys.stderr)
        return 1
    except sqlite3.IntegrityError as erro:
        print(
            "Erro de integridade (registro duplicado ou referência inválida):",
            erro,
            file=sys.stderr,
        )
        return 1
    finally:
        conn.close()
    return 0
