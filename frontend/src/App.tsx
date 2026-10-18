import { useCallback, useEffect, useState, type ComponentType } from "react";
import { api, EVENTO_SESSAO_ENCERRADA, type Usuario } from "./api";
import { ProvedorAvisos } from "./componentes/comum";
import { ContextoSessao, ehGerente } from "./componentes/sessao";
import Cadastros from "./paginas/Cadastros";
import Entrar from "./paginas/Entrar";
import Estoque from "./paginas/Estoque";
import MinhaConta from "./paginas/MinhaConta";
import NovaVenda from "./paginas/NovaVenda";
import Painel from "./paginas/Painel";
import Vendas from "./paginas/Vendas";

type Pagina = { rota: string; nome: string; componente: ComponentType; soGerente?: boolean };

// Navegação por hash (#/vendas): funciona ao recarregar a página sem configurar o servidor.
const PAGINAS: Pagina[] = [
  { rota: "painel", nome: "Painel", componente: Painel, soGerente: true },
  { rota: "nova-venda", nome: "Nova venda", componente: NovaVenda },
  { rota: "vendas", nome: "Vendas", componente: Vendas },
  { rota: "estoque", nome: "Estoque", componente: Estoque, soGerente: true },
  { rota: "cadastros", nome: "Cadastros", componente: Cadastros, soGerente: true },
];
const CONTA: Pagina = { rota: "minha-conta", nome: "Minha conta", componente: MinhaConta };

const rotaAtual = () => window.location.hash.replace(/^#\/?/, "");

type Estado = { tipo: "verificando" } | { tipo: "fora"; aviso?: string } | { tipo: "dentro"; usuario: Usuario };

export default function App() {
  const [estado, setEstado] = useState<Estado>({ tipo: "verificando" });

  useEffect(() => {
    api
      .get<Usuario>("/auth/eu")
      .then((usuario) => setEstado({ tipo: "dentro", usuario }))
      .catch(() => setEstado({ tipo: "fora" }));

    const encerrada = () =>
      setEstado((atual) =>
        atual.tipo === "dentro" ? { tipo: "fora", aviso: "Sua sessão terminou. Entre de novo." } : atual,
      );
    window.addEventListener(EVENTO_SESSAO_ENCERRADA, encerrada);
    return () => window.removeEventListener(EVENTO_SESSAO_ENCERRADA, encerrada);
  }, []);

  const sair = useCallback(async (aviso?: string) => {
    await api.post("/auth/sair").catch(() => {});
    setEstado({ tipo: "fora", aviso });
  }, []);

  return (
    <ProvedorAvisos>
      {estado.tipo === "verificando" && <p className="estado entrar">Carregando…</p>}
      {estado.tipo === "fora" && (
        <Entrar aviso={estado.aviso} aoEntrar={(usuario) => setEstado({ tipo: "dentro", usuario })} />
      )}
      {estado.tipo === "dentro" && (
        <ContextoSessao.Provider value={{ usuario: estado.usuario, sair }}>
          <Sistema usuario={estado.usuario} sair={sair} />
        </ContextoSessao.Provider>
      )}
    </ProvedorAvisos>
  );
}

function Sistema({ usuario, sair }: { usuario: Usuario; sair: (aviso?: string) => void }) {
  const [rota, setRota] = useState(rotaAtual);

  useEffect(() => {
    const aoMudar = () => setRota(rotaAtual());
    window.addEventListener("hashchange", aoMudar);
    return () => window.removeEventListener("hashchange", aoMudar);
  }, []);

  const permitidas = PAGINAS.filter((p) => !p.soGerente || ehGerente(usuario));
  // Rota desconhecida ou proibida cai na primeira página do perfil (vendedor: Nova venda).
  const pagina = [...permitidas, CONTA].find((p) => p.rota === rota) ?? permitidas[0];
  const Componente = pagina.componente;
  const nome = pagina.rota === "vendas" && !ehGerente(usuario) ? "Minhas vendas" : pagina.nome;

  useEffect(() => {
    document.title = `${nome} · Rede de Vendas`;
  }, [nome]);

  return (
    <div className="estrutura">
      <nav className="menu" aria-label="Seções">
        <a className="marca" href={`#/${permitidas[0].rota}`}>
          Rede de Vendas
        </a>
        <ul>
          {permitidas.map((p) => (
            <li key={p.rota}>
              <a href={`#/${p.rota}`} aria-current={p.rota === pagina.rota ? "page" : undefined}>
                {p.rota === "vendas" && !ehGerente(usuario) ? "Minhas vendas" : p.nome}
              </a>
            </li>
          ))}
        </ul>
        <div className="menu-usuario">
          <a href="#/minha-conta" aria-current={pagina === CONTA ? "page" : undefined}>
            {usuario.nome}
            <span className="secundario">{ehGerente(usuario) ? "Gerente" : usuario.loja}</span>
          </a>
          <button className="botao-texto" onClick={() => sair()}>
            Sair
          </button>
        </div>
      </nav>
      <main className="conteudo">
        <Componente key={pagina.rota} />
      </main>
    </div>
  );
}
