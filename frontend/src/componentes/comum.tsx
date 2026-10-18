import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";

// ------------------------------------------------------------ avisos

type TipoAviso = "sucesso" | "erro";
type Aviso = { id: number; texto: string; tipo: TipoAviso };
const ContextoAviso = createContext<(texto: string, tipo?: TipoAviso) => void>(() => {});

export function ProvedorAvisos({ children }: { children: ReactNode }) {
  const [avisos, setAvisos] = useState<Aviso[]>([]);
  const proximoId = useRef(1);

  const mostrar = useCallback((texto: string, tipo: TipoAviso = "sucesso") => {
    const id = proximoId.current++;
    setAvisos((atuais) => [...atuais, { id, texto, tipo }]);
    setTimeout(() => setAvisos((atuais) => atuais.filter((a) => a.id !== id)), tipo === "erro" ? 7000 : 3500);
  }, []);

  return (
    <ContextoAviso.Provider value={mostrar}>
      {children}
      <div className="avisos" role="status" aria-live="polite">
        {avisos.map((a) => (
          <p key={a.id} className={`aviso aviso-${a.tipo}`}>
            {a.texto}
          </p>
        ))}
      </div>
    </ContextoAviso.Provider>
  );
}

export const useAviso = () => useContext(ContextoAviso);

// ------------------------------------------------------- carregamento

/** Carrega dados da API e expõe `recarregar` para depois de uma alteração. */
export function useCarregar<T>(buscar: () => Promise<T>, dependencias: unknown[] = []) {
  const [dados, setDados] = useState<T | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [versao, setVersao] = useState(0);

  useEffect(() => {
    let ativo = true;
    buscar()
      .then((resultado) => {
        if (ativo) {
          setDados(resultado);
          setErro(null);
        }
      })
      .catch((e: Error) => ativo && setErro(e.message));
    return () => {
      ativo = false;
    };
    // As dependências vêm de quem chama o hook (como no useEffect).
  }, [...dependencias, versao]);

  return { dados, erro, recarregar: () => setVersao((v) => v + 1) };
}

// ---------------------------------------------------------- estados

export function Estado({ erro, carregando }: { erro: string | null; carregando: boolean }) {
  if (erro) return <p className="estado estado-erro">{erro}</p>;
  if (carregando) return <p className="estado">Carregando…</p>;
  return null;
}

export function Vazio({ children }: { children: ReactNode }) {
  return <p className="vazio">{children}</p>;
}

export function Cabecalho({ titulo, children }: { titulo: string; children?: ReactNode }) {
  return (
    <header className="cabecalho">
      <h1>{titulo}</h1>
      {children && <div className="cabecalho-acoes">{children}</div>}
    </header>
  );
}
