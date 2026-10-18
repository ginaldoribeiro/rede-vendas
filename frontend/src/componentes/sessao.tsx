import { createContext, useContext } from "react";
import type { Usuario } from "../api";

type Sessao = { usuario: Usuario; sair: (aviso?: string) => void };

export const ContextoSessao = createContext<Sessao | null>(null);

/** Usuário logado. Só é usado dentro do app autenticado, onde sempre existe. */
export function useSessao(): Sessao {
  const sessao = useContext(ContextoSessao);
  if (!sessao) throw new Error("useSessao fora do app autenticado");
  return sessao;
}

export const ehGerente = (u: Usuario) => u.perfil === "GERENTE";
