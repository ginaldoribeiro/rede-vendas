"""Usuários, senhas e sessões.

- Senhas: scrypt da biblioteca padrão, com sal aleatório por usuário. Nunca guardamos a senha.
- Sessões: token aleatório entregue ao navegador em cookie HttpOnly; no banco fica só o hash
  do token, então um vazamento do banco não permite entrar como ninguém.
- Perfis: GERENTE (tudo) e VENDEDOR (vender como si mesmo e ver as próprias vendas).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta

from .servicos import ErroNegocio, NaoEncontrado, texto_obrigatorio

PERFIS = ("GERENTE", "VENDEDOR")
TAMANHO_MINIMO_SENHA = 8
DURACAO_SESSAO = timedelta(hours=12)  # um dia de trabalho
SCRYPT = {"n": 2**14, "r": 8, "p": 1}


class NaoAutenticado(ErroNegocio):  # noqa: N818
    """Login ou sessão inválidos (a API traduz para HTTP 401)."""


class SemPermissao(ErroNegocio):  # noqa: N818
    """Usuário autenticado, mas sem permissão para a ação (HTTP 403)."""


@dataclass(frozen=True)
class Usuario:
    id: int
    login: str
    nome: str
    perfil: str
    vendedor_id: int | None
    loja_id: int | None
    loja: str | None

    @property
    def gerente(self) -> bool:
        return self.perfil == "GERENTE"


# ------------------------------------------------------------------- senhas


def gerar_hash(senha: str) -> str:
    sal = secrets.token_bytes(16)
    chave = hashlib.scrypt(senha.encode(), salt=sal, **SCRYPT)
    return f"scrypt${base64.b64encode(sal).decode()}${base64.b64encode(chave).decode()}"


def conferir_senha(senha: str, senha_hash: str) -> bool:
    try:
        _, sal_b64, chave_b64 = senha_hash.split("$")
        esperada = base64.b64decode(chave_b64)
        calculada = hashlib.scrypt(senha.encode(), salt=base64.b64decode(sal_b64), **SCRYPT)
    except ValueError:
        return False
    return hmac.compare_digest(calculada, esperada)  # comparação em tempo constante


def _validar_senha(senha: str) -> str:
    if len(senha) < TAMANHO_MINIMO_SENHA:
        raise ErroNegocio(f"A senha precisa ter pelo menos {TAMANHO_MINIMO_SENHA} caracteres.")
    return senha


# ----------------------------------------------------- limite de tentativas


class LimiteTentativas:
    """Bloqueia um login por alguns minutos após várias senhas erradas seguidas.

    Fica em memória: vale para um processo só (o deploy usa um worker, por causa do SQLite).
    """

    def __init__(self, maximo: int = 5, janela_segundos: int = 15 * 60) -> None:
        self.maximo, self.janela = maximo, janela_segundos
        self._falhas: dict[str, list[float]] = {}
        self._trava = threading.Lock()

    def _recentes(self, chave: str) -> list[float]:
        limite = time.monotonic() - self.janela
        return [t for t in self._falhas.get(chave, []) if t > limite]

    def verificar(self, chave: str) -> None:
        with self._trava:
            if len(self._recentes(chave)) >= self.maximo:
                minutos = self.janela // 60
                raise NaoAutenticado(
                    f"Muitas tentativas erradas. Aguarde {minutos} minutos e tente de novo."
                )

    def registrar_falha(self, chave: str) -> None:
        with self._trava:
            self._falhas[chave] = [*self._recentes(chave), time.monotonic()]

    def limpar(self, chave: str) -> None:
        with self._trava:
            self._falhas.pop(chave, None)


# ------------------------------------------------------------------ usuários


def criar_usuario(
    conn, login: str, nome: str, senha: str, perfil: str, vendedor_id: int | None = None
) -> int:
    perfil = perfil.upper()
    if perfil not in PERFIS:
        raise ErroNegocio("Perfil deve ser GERENTE ou VENDEDOR.")
    if perfil == "VENDEDOR":
        if vendedor_id is None:
            raise ErroNegocio("Um usuário vendedor precisa estar ligado a um vendedor cadastrado.")
        if conn.execute("SELECT 1 FROM vendedores WHERE id = ?", (vendedor_id,)).fetchone() is None:
            raise NaoEncontrado(f"Vendedor {vendedor_id} não encontrado.")
    else:
        vendedor_id = None
    login = texto_obrigatorio(login, "login").lower()
    if not login.replace(".", "").replace("_", "").isalnum():
        raise ErroNegocio("Login deve ter só letras, números, ponto ou sublinhado.")
    cur = conn.execute(
        "INSERT INTO usuarios (login, nome, senha_hash, perfil, vendedor_id)"
        " VALUES (?, ?, ?, ?, ?)",
        (
            login,
            texto_obrigatorio(nome, "nome"),
            gerar_hash(_validar_senha(senha)),
            perfil,
            vendedor_id,
        ),
    )
    conn.commit()
    return cur.lastrowid


def listar_usuarios(conn) -> list[dict]:
    sql = """
        SELECT u.id, u.login, u.nome, u.perfil, u.vendedor_id, v.nome AS vendedor,
               u.ativo = 1 AS ativo
        FROM usuarios u LEFT JOIN vendedores v ON v.id = u.vendedor_id
        ORDER BY u.perfil, u.nome"""
    linhas = [dict(r) for r in conn.execute(sql)]
    for linha in linhas:
        linha["ativo"] = bool(linha["ativo"])
    return linhas


def existe_gerente(conn) -> bool:
    sql = "SELECT 1 FROM usuarios WHERE perfil = 'GERENTE' AND ativo = 1"
    return conn.execute(sql).fetchone() is not None


def _usuario(conn, usuario_id: int):
    linha = conn.execute("SELECT * FROM usuarios WHERE id = ?", (usuario_id,)).fetchone()
    if linha is None:
        raise NaoEncontrado(f"Usuário {usuario_id} não encontrado.")
    return linha


def redefinir_senha(conn, usuario_id: int, nova_senha: str) -> None:
    """Gerente define uma nova senha; todas as sessões do usuário são encerradas."""
    _usuario(conn, usuario_id)
    with conn:
        conn.execute(
            "UPDATE usuarios SET senha_hash = ? WHERE id = ?",
            (gerar_hash(_validar_senha(nova_senha)), usuario_id),
        )
        conn.execute("DELETE FROM sessoes WHERE usuario_id = ?", (usuario_id,))


def trocar_propria_senha(conn, usuario_id: int, senha_atual: str, nova_senha: str) -> None:
    if not conferir_senha(senha_atual, _usuario(conn, usuario_id)["senha_hash"]):
        raise ErroNegocio("A senha atual está incorreta.")
    redefinir_senha(conn, usuario_id, nova_senha)


def definir_usuario_ativo(conn, usuario_id: int, ativo: bool, *, quem: Usuario) -> None:
    alvo = _usuario(conn, usuario_id)
    if not ativo and usuario_id == quem.id:
        raise ErroNegocio("Você não pode desativar o próprio usuário.")
    if not ativo and alvo["perfil"] == "GERENTE":
        restantes = conn.execute(
            "SELECT COUNT(*) FROM usuarios WHERE perfil = 'GERENTE' AND ativo = 1 AND id <> ?",
            (usuario_id,),
        ).fetchone()[0]
        if restantes == 0:
            raise ErroNegocio("A rede precisa de pelo menos um gerente ativo.")
    with conn:
        conn.execute("UPDATE usuarios SET ativo = ? WHERE id = ?", (int(ativo), usuario_id))
        if not ativo:
            conn.execute("DELETE FROM sessoes WHERE usuario_id = ?", (usuario_id,))


# ------------------------------------------------------------------- sessões


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def entrar(conn, login: str, senha: str, limite: LimiteTentativas) -> str:
    """Confere login e senha e devolve um token de sessão novo."""
    chave = (login or "").strip().lower()
    limite.verificar(chave)
    linha = conn.execute(
        "SELECT * FROM usuarios WHERE login = ? AND ativo = 1", (chave,)
    ).fetchone()
    # Mesmo sem usuário, calcula um hash: a resposta leva o mesmo tempo e não revela
    # quais logins existem.
    senha_hash = linha["senha_hash"] if linha else gerar_hash("x" * TAMANHO_MINIMO_SENHA)
    if not conferir_senha(senha or "", senha_hash) or linha is None:
        limite.registrar_falha(chave)
        raise NaoAutenticado("Login ou senha incorretos.")
    limite.limpar(chave)

    token = secrets.token_urlsafe(32)
    agora = datetime.now()
    with conn:
        conn.execute("DELETE FROM sessoes WHERE expira_em < ?", (agora.isoformat(),))
        conn.execute(
            "INSERT INTO sessoes (token_hash, usuario_id, criada_em, expira_em)"
            " VALUES (?, ?, ?, ?)",
            (
                _hash_token(token),
                linha["id"],
                agora.isoformat(timespec="seconds"),
                (agora + DURACAO_SESSAO).isoformat(timespec="seconds"),
            ),
        )
    return token


def usuario_da_sessao(conn, token: str | None) -> Usuario:
    if not token:
        raise NaoAutenticado("Entre com seu login para continuar.")
    linha = conn.execute(
        """SELECT u.id, u.login, u.nome, u.perfil, u.vendedor_id,
                  v.loja_id, l.nome AS loja, s.expira_em
           FROM sessoes s
           JOIN usuarios u ON u.id = s.usuario_id AND u.ativo = 1
           LEFT JOIN vendedores v ON v.id = u.vendedor_id
           LEFT JOIN lojas l ON l.id = v.loja_id
           WHERE s.token_hash = ?""",
        (_hash_token(token),),
    ).fetchone()
    if linha is None or linha["expira_em"] < datetime.now().isoformat():
        raise NaoAutenticado("Sua sessão expirou. Entre de novo.")
    return Usuario(
        id=linha["id"],
        login=linha["login"],
        nome=linha["nome"],
        perfil=linha["perfil"],
        vendedor_id=linha["vendedor_id"],
        loja_id=linha["loja_id"],
        loja=linha["loja"],
    )


def sair(conn, token: str | None) -> None:
    if token:
        with conn:
            conn.execute("DELETE FROM sessoes WHERE token_hash = ?", (_hash_token(token),))
