import { useState, type FormEvent } from "react";
import { api } from "../api";
import { Cabecalho } from "../componentes/comum";
import { useSessao } from "../componentes/sessao";

export default function MinhaConta() {
  const { usuario, sair } = useSessao();
  const [erro, setErro] = useState<string | null>(null);

  async function trocar(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const { atual, nova, repetida } = Object.fromEntries(new FormData(e.currentTarget)) as Record<string, string>;
    if (nova !== repetida) return setErro("A nova senha e a repetição não são iguais.");
    try {
      await api.post("/auth/senha", { atual, nova });
      sair("Senha trocada. Entre com a nova senha."); // a troca encerra todas as sessões; o usuário entra de novo com a senha nova
    } catch (falha) {
      setErro((falha as Error).message);
    }
  }

  return (
    <>
      <Cabecalho titulo="Minha conta" />
      <section className="bloco conta">
        <dl className="dados-conta">
          <div>
            <dt>Nome</dt>
            <dd>{usuario.nome}</dd>
          </div>
          <div>
            <dt>Login</dt>
            <dd>{usuario.login}</dd>
          </div>
          <div>
            <dt>Perfil</dt>
            <dd>{usuario.perfil === "GERENTE" ? "Gerente" : `Vendedor da ${usuario.loja}`}</dd>
          </div>
        </dl>
      </section>

      <form className="bloco formulario conta" onSubmit={trocar}>
        <h2>Trocar senha</h2>
        <p className="ajuda">Depois da troca, você precisa entrar de novo em todos os aparelhos.</p>
        <label>
          Senha atual
          <input name="atual" type="password" autoComplete="current-password" required />
        </label>
        <label>
          Nova senha (mínimo de 8 caracteres)
          <input name="nova" type="password" autoComplete="new-password" minLength={8} required />
        </label>
        <label>
          Repita a nova senha
          <input name="repetida" type="password" autoComplete="new-password" minLength={8} required />
        </label>
        {erro && (
          <p className="estado estado-erro" role="alert">
            {erro}
          </p>
        )}
        <button className="botao-principal">Trocar senha</button>
      </form>
    </>
  );
}
