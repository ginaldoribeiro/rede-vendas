// Cliente HTTP da API. Todos os valores monetários estão em centavos.

export type Loja = { id: number; nome: string; cidade: string; uf: string; vendedores_ativos: number };
export type Produto = {
  id: number;
  sku: string;
  nome: string;
  preco: number;
  custo: number;
  estoque_total: number;
  ativo: boolean;
};
export type Vendedor = {
  id: number;
  nome: string;
  loja_id: number;
  loja: string;
  comissao_pct: number;
  ativo: boolean;
};
export type Cliente = { id: number; nome: string; cpf: string | null; cidade: string | null };
export type ItemEstoque = {
  loja_id: number;
  loja: string;
  produto_id: number;
  sku: string;
  produto: string;
  quantidade: number;
};
export type Venda = {
  id: number;
  data_hora: string;
  loja: string;
  vendedor: string;
  cliente: string | null;
  itens: number;
  desconto: number;
  total: number;
  status: "CONCLUIDA" | "CANCELADA";
};
export type ItemVenda = {
  sku: string;
  nome: string;
  quantidade: number;
  preco_unit: number;
  subtotal: number;
};
export type VendaDetalhe = Omit<Venda, "itens"> & { comissao_pct: number; lista_itens: ItemVenda[] };
export type Resumo = {
  faturamento: number;
  vendas: number;
  ticket_medio: number;
  lojas: number;
  itens_estoque_baixo: number;
};
export type LinhaLoja = { loja: string; local: string; vendas: number; faturamento: number; ticket_medio: number };
export type LinhaVendedor = { vendedor: string; loja: string; vendas: number; faturamento: number; comissao: number };
export type LinhaMes = { mes: string; vendas: number; faturamento: number };
export type LinhaEstoqueBaixo = { loja: string; sku: string; produto: string; quantidade: number };

export type Perfil = "GERENTE" | "VENDEDOR";
export type Usuario = {
  id: number;
  login: string;
  nome: string;
  perfil: Perfil;
  vendedor_id: number | null;
  loja_id: number | null;
  loja: string | null;
};
export type UsuarioCadastro = {
  id: number;
  login: string;
  nome: string;
  perfil: Perfil;
  vendedor_id: number | null;
  vendedor: string | null;
  ativo: boolean;
};

/** Disparado quando a API responde 401: a sessão acabou e o app volta para o login. */
export const EVENTO_SESSAO_ENCERRADA = "rv:sessao-encerrada";

type Detalhe = string | { msg: string; loc?: (string | number)[] }[];

async function requisitar<T>(metodo: string, caminho: string, corpo?: unknown): Promise<T> {
  let resposta: Response;
  try {
    resposta = await fetch(`/api${caminho}`, {
      method: metodo,
      headers: corpo === undefined ? undefined : { "Content-Type": "application/json" },
      body: corpo === undefined ? undefined : JSON.stringify(corpo),
    });
  } catch {
    throw new Error("Não foi possível falar com o servidor. Verifique se a API está rodando.");
  }
  if (resposta.status === 401 && caminho !== "/auth/entrar") {
    window.dispatchEvent(new Event(EVENTO_SESSAO_ENCERRADA));
  }
  if (resposta.status === 204) return undefined as T;
  const dados = await resposta.json().catch(() => null);
  if (!resposta.ok) {
    const detalhe: Detalhe | undefined = dados?.detail;
    const mensagem = Array.isArray(detalhe)
      ? detalhe.map((d) => `${d.loc?.at(-1) ?? "campo"}: ${d.msg}`).join("; ")
      : detalhe ?? `Erro ${resposta.status}`;
    throw new Error(mensagem);
  }
  return dados as T;
}

function consulta(parametros: Record<string, string | number | boolean | undefined | null>): string {
  const busca = new URLSearchParams();
  for (const [chave, valor] of Object.entries(parametros)) {
    if (valor !== undefined && valor !== null && valor !== "") busca.set(chave, String(valor));
  }
  const texto = busca.toString();
  return texto ? `?${texto}` : "";
}

export const api = {
  get: <T>(caminho: string, parametros = {}) => requisitar<T>("GET", caminho + consulta(parametros)),
  post: <T = void>(caminho: string, corpo?: unknown) => requisitar<T>("POST", caminho, corpo ?? {}),
  patch: (caminho: string, corpo: unknown) => requisitar<void>("PATCH", caminho, corpo),
};
