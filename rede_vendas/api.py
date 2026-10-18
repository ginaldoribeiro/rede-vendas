"""API REST da rede de vendas (FastAPI).

Rodar em desenvolvimento:
    REDE_VENDAS_COOKIE_SEGURO=0 uvicorn rede_vendas.api:app --reload

Convenções:
- Todas as rotas ficam sob /api; a documentação interativa está em /docs.
- Valores monetários entram e saem em CENTAVOS (inteiros), como no banco.
- Login por sessão em cookie HttpOnly. Perfis: GERENTE (tudo) e VENDEDOR (vende e vê as
  próprias vendas). Sem login → 401; sem permissão → 403.
- Regras de negócio violadas → 400; registro inexistente → 404; duplicidade → 409.
- Se a pasta frontend/dist existir (após `npm run build`), o frontend é servido em /.

Variáveis de ambiente:
    REDE_VENDAS_DB            caminho do banco SQLite (padrão: rede_vendas.db)
    REDE_VENDAS_COOKIE_SEGURO 1 = cookie só via HTTPS (padrão); 0 = permite HTTP (dev/rede local)
    REDE_VENDAS_DOCS          1 = expõe /docs (padrão); 0 = esconde em produção
    REDE_VENDAS_ADMIN_LOGIN / REDE_VENDAS_ADMIN_SENHA
                              cria o primeiro gerente ao iniciar, se ainda não houver nenhum
"""

from __future__ import annotations

import logging
import os
import sqlite3
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, FastAPI, Query, Request, Response
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__
from . import autenticacao as aut
from . import relatorios as rel
from . import servicos as sv
from .banco import conectar

PASTA_FRONTEND = Path(__file__).resolve().parent.parent / "frontend" / "dist"
COOKIE_SESSAO = "rv_sessao"
log = logging.getLogger("rede_vendas")

# ------------------------------------------------------------------ modelos


class LojaIn(BaseModel):
    nome: str
    cidade: str
    uf: str = Field(min_length=2, max_length=2)


class LojaPatch(BaseModel):
    nome: str | None = None
    cidade: str | None = None
    uf: str | None = None


class ProdutoIn(BaseModel):
    sku: str
    nome: str
    preco_centavos: int = Field(ge=0)
    custo_centavos: int = Field(ge=0)


class ProdutoPatch(BaseModel):
    nome: str | None = None
    preco_centavos: int | None = Field(default=None, ge=0)
    custo_centavos: int | None = Field(default=None, ge=0)


class VendedorIn(BaseModel):
    nome: str
    loja_id: int
    comissao_pct: float = Field(default=3.0, ge=0, le=100)


class VendedorPatch(BaseModel):
    nome: str | None = None
    loja_id: int | None = None
    comissao_pct: float | None = Field(default=None, ge=0, le=100)


class ClienteIn(BaseModel):
    nome: str
    cpf: str | None = None
    cidade: str | None = None


class ClientePatch(BaseModel):
    nome: str | None = None
    cpf: str | None = None
    cidade: str | None = None


class EntradaIn(BaseModel):
    loja_id: int
    produto_id: int
    quantidade: int = Field(gt=0)


class TransferenciaIn(BaseModel):
    origem_id: int
    destino_id: int
    produto_id: int
    quantidade: int = Field(gt=0)


class ItemIn(BaseModel):
    produto_id: int
    quantidade: int = Field(gt=0)


class VendaIn(BaseModel):
    vendedor_id: int | None = None  # vendedor logado: ignorado, a venda é sempre dele
    itens: list[ItemIn] = Field(min_length=1)
    cliente_id: int | None = None
    desconto_pct: float = Field(default=0.0, ge=0, le=sv.DESCONTO_MAXIMO_PCT)


class LoginIn(BaseModel):
    login: str = Field(max_length=100)
    senha: str = Field(max_length=200)


class UsuarioIn(BaseModel):
    login: str = Field(min_length=3, max_length=50)
    nome: str
    senha: str = Field(min_length=aut.TAMANHO_MINIMO_SENHA, max_length=200)
    perfil: Literal["GERENTE", "VENDEDOR"]
    vendedor_id: int | None = None


class NovaSenhaIn(BaseModel):
    nova: str = Field(min_length=aut.TAMANHO_MINIMO_SENHA, max_length=200)


class TrocaSenhaIn(NovaSenhaIn):
    atual: str = Field(max_length=200)


class Criado(BaseModel):
    id: int


def _reais(centavos: int | None) -> float | None:
    """A camada de serviços recebe reais; a API trabalha em centavos."""
    return None if centavos is None else centavos / 100


# -------------------------------------------------------------- dependências


def obter_conexao(request: Request) -> Iterator[sqlite3.Connection]:
    """Uma conexão por requisição, sempre fechada no final."""
    conn = conectar(request.app.state.caminho_db)
    try:
        yield conn
    finally:
        conn.close()


Conexao = Annotated[sqlite3.Connection, Depends(obter_conexao)]


def usuario_atual(request: Request, conn: Conexao) -> aut.Usuario:
    return aut.usuario_da_sessao(conn, request.cookies.get(COOKIE_SESSAO))


def exigir_gerente(usuario: Annotated[aut.Usuario, Depends(usuario_atual)]) -> aut.Usuario:
    if not usuario.gerente:
        raise aut.SemPermissao("Apenas gerentes podem fazer isso.")
    return usuario


Logado = Annotated[aut.Usuario, Depends(usuario_atual)]
Gerente = Annotated[aut.Usuario, Depends(exigir_gerente)]
Periodo = Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}-\d{2}$")]

# Três grupos de rotas: públicas, de qualquer usuário logado e só de gerente.
publico = APIRouter(prefix="/api")
logado = APIRouter(prefix="/api", dependencies=[Depends(usuario_atual)])
gerencia = APIRouter(prefix="/api", dependencies=[Depends(exigir_gerente)])

# ------------------------------------------------------------- autenticação


def _dados_usuario(u: aut.Usuario) -> dict:
    return {
        "id": u.id,
        "login": u.login,
        "nome": u.nome,
        "perfil": u.perfil,
        "vendedor_id": u.vendedor_id,
        "loja_id": u.loja_id,
        "loja": u.loja,
    }


@publico.post("/auth/entrar", tags=["autenticação"])
def entrar(dados: LoginIn, request: Request, response: Response, conn: Conexao) -> dict:
    token = aut.entrar(conn, dados.login, dados.senha, request.app.state.limite)
    response.set_cookie(
        COOKIE_SESSAO,
        token,
        max_age=int(aut.DURACAO_SESSAO.total_seconds()),
        httponly=True,  # o JavaScript da página não consegue ler o token
        secure=request.app.state.cookie_seguro,
        samesite="strict",  # outro site não consegue enviar o cookie (proteção contra CSRF)
        path="/api",
    )
    return _dados_usuario(aut.usuario_da_sessao(conn, token))


@publico.post("/auth/sair", status_code=204, tags=["autenticação"])
def sair(request: Request, response: Response, conn: Conexao) -> None:
    aut.sair(conn, request.cookies.get(COOKIE_SESSAO))
    response.delete_cookie(COOKIE_SESSAO, path="/api")


@logado.get("/auth/eu", tags=["autenticação"])
def eu(usuario: Logado) -> dict:
    return _dados_usuario(usuario)


@logado.post("/auth/senha", status_code=204, tags=["autenticação"])
def trocar_senha(dados: TrocaSenhaIn, usuario: Logado, conn: Conexao) -> None:
    """Troca a própria senha. Encerra as sessões, então é preciso entrar de novo."""
    aut.trocar_propria_senha(conn, usuario.id, dados.atual, dados.nova)


@publico.get("/saude", tags=["sistema"])
def saude() -> dict:
    return {"status": "ok", "versao": __version__}


# ------------------------------------------------------------------ usuários


@gerencia.get("/usuarios", tags=["usuários"])
def listar_usuarios(conn: Conexao) -> list[dict]:
    return aut.listar_usuarios(conn)


@gerencia.post("/usuarios", status_code=201, tags=["usuários"])
def criar_usuario(dados: UsuarioIn, conn: Conexao) -> Criado:
    return Criado(
        id=aut.criar_usuario(
            conn, dados.login, dados.nome, dados.senha, dados.perfil, dados.vendedor_id
        )
    )


@gerencia.post("/usuarios/{usuario_id}/senha", status_code=204, tags=["usuários"])
def redefinir_senha(usuario_id: int, dados: NovaSenhaIn, conn: Conexao) -> None:
    aut.redefinir_senha(conn, usuario_id, dados.nova)


@gerencia.post("/usuarios/{usuario_id}/ativar", status_code=204, tags=["usuários"])
def ativar_usuario(usuario_id: int, usuario: Gerente, conn: Conexao) -> None:
    aut.definir_usuario_ativo(conn, usuario_id, True, quem=usuario)


@gerencia.post("/usuarios/{usuario_id}/desativar", status_code=204, tags=["usuários"])
def desativar_usuario(usuario_id: int, usuario: Gerente, conn: Conexao) -> None:
    aut.definir_usuario_ativo(conn, usuario_id, False, quem=usuario)


# ---------------------------------------------------------------- cadastros


@gerencia.get("/lojas", tags=["cadastros"])
def listar_lojas(conn: Conexao) -> list[dict]:
    return sv.listar_lojas(conn)


@gerencia.post("/lojas", status_code=201, tags=["cadastros"])
def criar_loja(dados: LojaIn, conn: Conexao) -> Criado:
    return Criado(id=sv.cadastrar_loja(conn, dados.nome, dados.cidade, dados.uf))


@gerencia.patch("/lojas/{loja_id}", status_code=204, tags=["cadastros"])
def editar_loja(loja_id: int, dados: LojaPatch, conn: Conexao) -> None:
    sv.editar_loja(conn, loja_id, **dados.model_dump(exclude_unset=True))


@logado.get("/produtos", tags=["cadastros"])
def listar_produtos(usuario: Logado, conn: Conexao, todos: bool = False) -> list[dict]:
    """Vendedores veem só os produtos ativos (os que podem vender)."""
    return sv.listar_produtos(conn, incluir_inativos=todos and usuario.gerente)


@gerencia.post("/produtos", status_code=201, tags=["cadastros"])
def criar_produto(dados: ProdutoIn, conn: Conexao) -> Criado:
    produto_id = sv.cadastrar_produto(
        conn, dados.sku, dados.nome, _reais(dados.preco_centavos), _reais(dados.custo_centavos)
    )
    return Criado(id=produto_id)


@gerencia.patch("/produtos/{produto_id}", status_code=204, tags=["cadastros"])
def editar_produto(produto_id: int, dados: ProdutoPatch, conn: Conexao) -> None:
    campos = dados.model_dump(exclude_unset=True)
    sv.editar_produto(
        conn,
        produto_id,
        nome=campos.get("nome"),
        preco=_reais(campos.get("preco_centavos")),
        custo=_reais(campos.get("custo_centavos")),
    )


@gerencia.get("/vendedores", tags=["cadastros"])
def listar_vendedores(conn: Conexao, todos: bool = False) -> list[dict]:
    return sv.listar_vendedores(conn, incluir_inativos=todos)


@gerencia.post("/vendedores", status_code=201, tags=["cadastros"])
def criar_vendedor(dados: VendedorIn, conn: Conexao) -> Criado:
    return Criado(id=sv.cadastrar_vendedor(conn, dados.nome, dados.loja_id, dados.comissao_pct))


@gerencia.patch("/vendedores/{vendedor_id}", status_code=204, tags=["cadastros"])
def editar_vendedor(vendedor_id: int, dados: VendedorPatch, conn: Conexao) -> None:
    sv.editar_vendedor(conn, vendedor_id, **dados.model_dump(exclude_unset=True))


@logado.get("/clientes", tags=["cadastros"])
def listar_clientes(conn: Conexao) -> list[dict]:
    return sv.listar_clientes(conn)


@logado.post("/clientes", status_code=201, tags=["cadastros"])
def criar_cliente(dados: ClienteIn, conn: Conexao) -> Criado:
    """Vendedores também cadastram clientes, no balcão."""
    return Criado(id=sv.cadastrar_cliente(conn, dados.nome, dados.cpf, dados.cidade))


@gerencia.patch("/clientes/{cliente_id}", status_code=204, tags=["cadastros"])
def editar_cliente(cliente_id: int, dados: ClientePatch, conn: Conexao) -> None:
    sv.editar_cliente(conn, cliente_id, **dados.model_dump(exclude_unset=True))


def _rotas_de_ativacao(entidade: str, plural: str) -> None:
    """Gera POST /<plural>/{id}/ativar e /desativar."""

    @gerencia.post(f"/{plural}/{{id_}}/ativar", status_code=204, tags=["cadastros"])
    def ativar(id_: int, conn: Conexao) -> None:
        sv.definir_ativo(conn, entidade, id_, ativo=True)

    @gerencia.post(f"/{plural}/{{id_}}/desativar", status_code=204, tags=["cadastros"])
    def desativar(id_: int, conn: Conexao) -> None:
        sv.definir_ativo(conn, entidade, id_, ativo=False)


_rotas_de_ativacao("produto", "produtos")
_rotas_de_ativacao("vendedor", "vendedores")

# ------------------------------------------------------------------ estoque


@logado.get("/estoque", tags=["estoque"])
def listar_estoque(usuario: Logado, conn: Conexao, loja_id: int | None = None) -> list[dict]:
    """Vendedores veem sempre o estoque da própria loja."""
    return sv.listar_estoque(conn, loja_id if usuario.gerente else usuario.loja_id)


@gerencia.post("/estoque/entradas", tags=["estoque"])
def registrar_entrada(dados: EntradaIn, conn: Conexao) -> dict:
    saldo = sv.entrada_estoque(conn, dados.loja_id, dados.produto_id, dados.quantidade)
    return {"saldo": saldo}


@gerencia.post("/estoque/transferencias", status_code=204, tags=["estoque"])
def registrar_transferencia(dados: TransferenciaIn, conn: Conexao) -> None:
    sv.transferir(conn, dados.origem_id, dados.destino_id, dados.produto_id, dados.quantidade)


# ------------------------------------------------------------------- vendas


@logado.get("/vendas", tags=["vendas"])
def listar_vendas(
    usuario: Logado,
    conn: Conexao,
    loja_id: int | None = None,
    limite: Annotated[int, Query(ge=1, le=500)] = 50,
) -> list[dict]:
    """Gerente vê todas; vendedor vê só as próprias."""
    if usuario.gerente:
        return sv.listar_vendas(conn, loja_id=loja_id, limite=limite)
    return sv.listar_vendas(conn, vendedor_id=usuario.vendedor_id, limite=limite)


@logado.get("/vendas/{venda_id}", tags=["vendas"])
def detalhar_venda(venda_id: int, usuario: Logado, conn: Conexao) -> dict:
    venda = sv.detalhar_venda(conn, venda_id)
    if not usuario.gerente and venda["vendedor_id"] != usuario.vendedor_id:
        # 404 em vez de 403: não confirma que a venda de outra pessoa existe.
        raise sv.NaoEncontrado(f"Registro {venda_id} não encontrado em 'vendas'.")
    return venda


@logado.post("/vendas", status_code=201, tags=["vendas"])
def registrar_venda(dados: VendaIn, usuario: Logado, conn: Conexao) -> dict:
    if usuario.gerente:
        if dados.vendedor_id is None:
            raise sv.ErroNegocio("Informe o vendedor da venda.")
        vendedor_id = dados.vendedor_id
    else:
        vendedor_id = usuario.vendedor_id  # o vendedor só vende em nome próprio
    venda_id = sv.registrar_venda(
        conn,
        vendedor_id,
        [sv.ItemPedido(i.produto_id, i.quantidade) for i in dados.itens],
        cliente_id=dados.cliente_id,
        desconto_pct=dados.desconto_pct,
    )
    log.info("venda %s registrada por %s", venda_id, usuario.login)
    return sv.detalhar_venda(conn, venda_id)


@gerencia.post("/vendas/{venda_id}/cancelar", status_code=204, tags=["vendas"])
def cancelar_venda(venda_id: int, usuario: Gerente, conn: Conexao) -> None:
    sv.cancelar_venda(conn, venda_id)
    log.info("venda %s cancelada por %s", venda_id, usuario.login)


# --------------------------------------------------------------- relatórios


@gerencia.get("/relatorios/lojas", tags=["relatórios"])
def relatorio_lojas(conn: Conexao, inicio: Periodo = None, fim: Periodo = None) -> list[dict]:
    return rel.faturamento_por_loja(conn, inicio, fim)


@gerencia.get("/relatorios/vendedores", tags=["relatórios"])
def relatorio_vendedores(
    conn: Conexao, inicio: Periodo = None, fim: Periodo = None, limite: int = 10
) -> list[dict]:
    return rel.ranking_vendedores(conn, inicio, fim, limite)


@gerencia.get("/relatorios/produtos", tags=["relatórios"])
def relatorio_produtos(
    conn: Conexao, inicio: Periodo = None, fim: Periodo = None, limite: int = 10
) -> list[dict]:
    return rel.produtos_mais_vendidos(conn, inicio, fim, limite)


@gerencia.get("/relatorios/estoque-baixo", tags=["relatórios"])
def relatorio_estoque_baixo(conn: Conexao, minimo: Annotated[int, Query(ge=0)] = 5) -> list[dict]:
    return rel.estoque_baixo(conn, minimo)


@gerencia.get("/relatorios/mensal", tags=["relatórios"])
def relatorio_mensal(conn: Conexao, ano: int) -> list[dict]:
    return rel.faturamento_mensal(conn, ano)


@gerencia.get("/resumo", tags=["relatórios"])
def resumo(
    conn: Conexao,
    inicio: Periodo = None,
    fim: Periodo = None,
    minimo: Annotated[int, Query(ge=0)] = 5,
) -> dict:
    """Indicadores para o painel: faturamento, nº de vendas, ticket médio, alertas."""
    lojas = rel.faturamento_por_loja(conn, inicio, fim)
    faturamento = sum(loja["faturamento"] for loja in lojas)
    vendas = sum(loja["vendas"] for loja in lojas)
    return {
        "faturamento": faturamento,
        "vendas": vendas,
        "ticket_medio": faturamento // vendas if vendas else 0,
        "lojas": len(lojas),
        "itens_estoque_baixo": len(rel.estoque_baixo(conn, minimo)),
    }


# ---------------------------------------------------------------- aplicação

CABECALHOS_SEGURANCA = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Content-Security-Policy": (
        "default-src 'self'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "  # inline: gráfico
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    ),
}
ROTAS_DOCUMENTACAO = ("/docs", "/redoc", "/openapi.json")


def _tratar_erros(app: FastAPI) -> None:
    def resposta(status: int):
        def tratar(_req: Request, erro: Exception) -> JSONResponse:
            return JSONResponse(status_code=status, content={"detail": str(erro)})

        return tratar

    # O FastAPI escolhe o tratador da classe mais específica do erro.
    app.add_exception_handler(aut.NaoAutenticado, resposta(401))
    app.add_exception_handler(aut.SemPermissao, resposta(403))
    app.add_exception_handler(sv.NaoEncontrado, resposta(404))
    app.add_exception_handler(sv.ErroNegocio, resposta(400))

    @app.exception_handler(sqlite3.IntegrityError)
    def integridade(_req: Request, erro: sqlite3.IntegrityError) -> JSONResponse:
        mensagem = "Registro duplicado ou referência inválida"
        if "UNIQUE" in str(erro):
            campo = str(erro).rsplit(".", 1)[-1]
            mensagem = f"Já existe um cadastro com este valor de '{campo}'."
        return JSONResponse(status_code=409, content={"detail": mensagem})


def _criar_primeiro_gerente(caminho_db: str) -> None:
    """Na primeira subida, cria o gerente definido nas variáveis de ambiente."""
    login = os.environ.get("REDE_VENDAS_ADMIN_LOGIN")
    senha = os.environ.get("REDE_VENDAS_ADMIN_SENHA")
    conn = conectar(caminho_db)
    try:
        if aut.existe_gerente(conn):
            return
        if not (login and senha):
            log.warning(
                "Nenhum gerente cadastrado. Defina REDE_VENDAS_ADMIN_LOGIN e "
                "REDE_VENDAS_ADMIN_SENHA ou rode: python -m rede_vendas criar-usuario"
            )
            return
        aut.criar_usuario(conn, login, "Gerente", senha, "GERENTE")
        log.warning("Gerente inicial '%s' criado. Troque a senha no primeiro acesso.", login)
    finally:
        conn.close()


def _ligado(variavel: str, padrao: str = "1") -> bool:
    return os.environ.get(variavel, padrao).strip().lower() not in {"0", "false", "nao", "não"}


def criar_app(caminho_db: str | None = None, *, cookie_seguro: bool | None = None) -> FastAPI:
    caminho_db = caminho_db or os.environ.get("REDE_VENDAS_DB", "rede_vendas.db")
    docs = _ligado("REDE_VENDAS_DOCS")

    @asynccontextmanager
    async def ciclo_de_vida(_app: FastAPI) -> AsyncIterator[None]:
        _criar_primeiro_gerente(caminho_db)
        yield

    app = FastAPI(
        title="Rede de Vendas",
        version=__version__,
        description="API da rede de lojas. Valores monetários em centavos.",
        lifespan=ciclo_de_vida,
        docs_url="/docs" if docs else None,
        redoc_url=None,
        openapi_url="/openapi.json" if docs else None,
    )
    app.state.caminho_db = caminho_db
    app.state.cookie_seguro = (
        _ligado("REDE_VENDAS_COOKIE_SEGURO") if cookie_seguro is None else cookie_seguro
    )
    app.state.limite = aut.LimiteTentativas()

    @app.middleware("http")
    async def cabecalhos_de_seguranca(request: Request, call_next):
        resposta = await call_next(request)
        cabecalhos = dict(CABECALHOS_SEGURANCA)
        if request.url.path.startswith(ROTAS_DOCUMENTACAO):
            cabecalhos.pop("Content-Security-Policy")  # o /docs carrega scripts de CDN
        if request.url.path.startswith("/api"):
            resposta.headers["Cache-Control"] = "no-store"
        for nome, valor in cabecalhos.items():
            resposta.headers.setdefault(nome, valor)
        return resposta

    for router in (publico, logado, gerencia):
        app.include_router(router)
    _tratar_erros(app)
    if PASTA_FRONTEND.is_dir():  # produção: o próprio FastAPI serve o React compilado
        app.mount("/", StaticFiles(directory=PASTA_FRONTEND, html=True), name="frontend")
    return app


app = criar_app()
