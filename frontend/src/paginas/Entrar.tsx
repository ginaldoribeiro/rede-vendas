import { useState, type FormEvent } from "react";
import { api, type Usuario } from "../api";

export default function Entrar({ aoEntrar, aviso }: { aoEntrar: (u: Usuario) => void; aviso?: string }) {
  const [erro, setErro] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  async function enviar(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const dados = Object.fromEntries(new FormData(e.currentTarget));
    setEnviando(true);
    setErro(null);
    try {
      aoEntrar(await api.post<Usuario>("/auth/entrar", dados));
    } catch (falha) {
      setErro((falha as Error).message);
    } finally {
      setEnviando(false);
    }
  }

  return (
    <main className="entrar">
      <form className="entrar-cartao" onSubmit={enviar}>
        <h1>Rede de Vendas</h1>
        <p className="secundario">Entre com o login que o gerente criou para você.</p>
        {aviso && !erro && <p className="estado">{aviso}</p>}
        <label>
          Login
          <input name="login" autoComplete="username" autoCapitalize="none" required autoFocus />
        </label>
        <label>
          Senha
          <input name="senha" type="password" autoComplete="current-password" required />
        </label>
        {erro && (
          <p className="estado estado-erro" role="alert">
            {erro}
          </p>
        )}
        <button className="botao-principal" disabled={enviando}>
          {enviando ? "Entrando…" : "Entrar"}
        </button>
      </form>
    </main>
  );
}
