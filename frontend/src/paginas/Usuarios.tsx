import { useState, type FormEvent } from "react";
import { api, type UsuarioCadastro, type Vendedor } from "../api";
import { Estado, useAviso, useCarregar, Vazio } from "../componentes/comum";
import { useSessao } from "../componentes/sessao";

export default function Usuarios() {
  const avisar = useAviso();
  const { usuario: eu } = useSessao();
  const [perfil, setPerfil] = useState<"VENDEDOR" | "GERENTE">("VENDEDOR");
  const [redefinindo, setRedefinindo] = useState<number | null>(null);
  const usuarios = useCarregar(() => api.get<UsuarioCadastro[]>("/usuarios"));
  const vendedores = useCarregar(() => api.get<Vendedor[]>("/vendedores"));

  // Cada vendedor tem no máximo um acesso; só os que ainda não têm aparecem na lista.
  const comAcesso = new Set((usuarios.dados ?? []).map((u) => u.vendedor_id));
  const semAcesso = (vendedores.dados ?? []).filter((v) => !comAcesso.has(v.id));

  async function executar(acao: () => Promise<unknown>, sucesso: string) {
    try {
      await acao();
      avisar(sucesso);
      usuarios.recarregar();
      return true;
    } catch (e) {
      avisar((e as Error).message, "erro");
      return false;
    }
  }

  async function criar(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const dados = Object.fromEntries(new FormData(form)) as Record<string, string>;
    const corpo = {
      ...dados,
      perfil,
      vendedor_id: perfil === "VENDEDOR" ? Number(dados.vendedor_id) : null,
    };
    if (await executar(() => api.post("/usuarios", corpo), `Acesso de ${dados.nome} criado.`)) {
      form.reset();
    }
  }

  async function redefinir(e: FormEvent<HTMLFormElement>, u: UsuarioCadastro) {
    e.preventDefault();
    const nova = String(new FormData(e.currentTarget).get("nova"));
    const ok = await executar(
      () => api.post(`/usuarios/${u.id}/senha`, { nova }),
      `Senha de ${u.nome} redefinida. Passe a nova senha para a pessoa.`,
    );
    if (ok) setRedefinindo(null);
  }

  return (
    <>
      <form className="bloco formulario formulario-linha" onSubmit={criar}>
        <h2>Novo acesso</h2>
        <p className="ajuda">
          Vendedores só registram vendas e veem as próprias vendas. Gerentes acessam tudo.
        </p>
        <div className="linha-campos">
          <label>
            Perfil
            <select value={perfil} onChange={(e) => setPerfil(e.target.value as typeof perfil)}>
              <option value="VENDEDOR">Vendedor</option>
              <option value="GERENTE">Gerente</option>
            </select>
          </label>
          {perfil === "VENDEDOR" && (
            <label>
              Vendedor
              <select name="vendedor_id" required defaultValue="">
                <option value="" disabled>
                  {semAcesso.length ? "Escolha" : "Todos já têm acesso"}
                </option>
                {semAcesso.map((v) => (
                  <option key={v.id} value={v.id}>
                    {v.nome} ({v.loja})
                  </option>
                ))}
              </select>
            </label>
          )}
          <label>
            Nome
            <input name="nome" required />
          </label>
          <label>
            Login
            <input name="login" required minLength={3} autoCapitalize="none" pattern="[A-Za-z0-9._]+" />
          </label>
          <label>
            Senha inicial
            <input name="senha" type="password" required minLength={8} autoComplete="new-password" />
          </label>
          <button className="botao-principal">Criar acesso</button>
        </div>
      </form>

      <section className="bloco">
        <Estado erro={usuarios.erro} carregando={!usuarios.dados} />
        {usuarios.dados && !usuarios.dados.length && <Vazio>Nenhum acesso criado ainda.</Vazio>}
        {!!usuarios.dados?.length && (
          <table>
            <thead>
              <tr>
                <th>Nome</th>
                <th>Login</th>
                <th>Perfil</th>
                <th>
                  <span className="visualmente-oculto">Ações</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {usuarios.dados.map((u) => (
                <tr key={u.id} className={u.ativo ? "" : "inativo"}>
                  <td>
                    {u.nome}
                    {!u.ativo && <span className="secundario">Desativado</span>}
                  </td>
                  <td>{u.login}</td>
                  <td>{u.perfil === "GERENTE" ? "Gerente" : `Vendedor (${u.vendedor})`}</td>
                  <td className="acoes">
                    {redefinindo === u.id ? (
                      <form className="redefinir" onSubmit={(e) => redefinir(e, u)}>
                        <input
                          name="nova"
                          type="password"
                          aria-label={`Nova senha de ${u.nome}`}
                          placeholder="Nova senha"
                          minLength={8}
                          required
                          autoFocus
                          autoComplete="new-password"
                        />
                        <button className="botao-principal">Salvar</button>
                        <button type="button" className="botao-texto" onClick={() => setRedefinindo(null)}>
                          Cancelar
                        </button>
                      </form>
                    ) : (
                      <>
                        <button className="botao-texto" onClick={() => setRedefinindo(u.id)}>
                          Redefinir senha
                        </button>
                        {u.id !== eu.id && (
                          <button
                            className="botao-texto"
                            onClick={() =>
                              executar(
                                () => api.post(`/usuarios/${u.id}/${u.ativo ? "desativar" : "ativar"}`),
                                u.ativo ? `Acesso de ${u.nome} desativado.` : `Acesso de ${u.nome} reativado.`,
                              )
                            }
                          >
                            {u.ativo ? "Desativar" : "Reativar"}
                          </button>
                        )}
                      </>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </>
  );
}
