import { useState, type FormEvent, type ReactNode } from "react";
import { api, type Loja } from "../api";
import { Cabecalho, Estado, useAviso, useCarregar, Vazio } from "../componentes/comum";
import { centavosParaTexto, paraCentavos, reais } from "../formato";
import Usuarios from "./Usuarios";

// ------------------------------------------------------- configuração

type TipoCampo = "texto" | "uf" | "dinheiro" | "percentual" | "loja";

type Campo = {
  nome: string; // nome do campo na API (no envio)
  rotulo: string;
  tipo: TipoCampo;
  leitura?: string; // nome do campo na listagem, se diferente
  exibir?: string; // campo usado só para mostrar (ex.: nome da loja em vez do id)
  opcional?: boolean;
  soNaCriacao?: boolean; // não pode ser alterado depois (ex.: código do produto)
};

type Config = {
  rota: string;
  singular: string;
  plural: string;
  campos: Campo[];
  extras?: { rotulo: string; valor: (linha: Linha) => ReactNode; numerico?: boolean }[];
  ativavel?: boolean;
};

type Linha = Record<string, unknown> & { id: number; ativo?: boolean };

const CONFIGS: Config[] = [
  {
    rota: "lojas",
    singular: "loja",
    plural: "Lojas",
    campos: [
      { nome: "nome", rotulo: "Nome", tipo: "texto" },
      { nome: "cidade", rotulo: "Cidade", tipo: "texto" },
      { nome: "uf", rotulo: "UF", tipo: "uf" },
    ],
    extras: [{ rotulo: "Vendedores ativos", valor: (l) => String(l.vendedores_ativos), numerico: true }],
  },
  {
    rota: "produtos",
    singular: "produto",
    plural: "Produtos",
    campos: [
      { nome: "sku", rotulo: "Código", tipo: "texto", soNaCriacao: true },
      { nome: "nome", rotulo: "Nome", tipo: "texto" },
      { nome: "preco_centavos", leitura: "preco", rotulo: "Preço", tipo: "dinheiro" },
      { nome: "custo_centavos", leitura: "custo", rotulo: "Custo", tipo: "dinheiro" },
    ],
    extras: [{ rotulo: "Estoque na rede", valor: (l) => String(l.estoque_total), numerico: true }],
    ativavel: true,
  },
  {
    rota: "vendedores",
    singular: "vendedor",
    plural: "Vendedores",
    campos: [
      { nome: "nome", rotulo: "Nome", tipo: "texto" },
      { nome: "loja_id", exibir: "loja", rotulo: "Loja", tipo: "loja" },
      { nome: "comissao_pct", rotulo: "Comissão (%)", tipo: "percentual" },
    ],
    ativavel: true,
  },
  {
    rota: "clientes",
    singular: "cliente",
    plural: "Clientes",
    campos: [
      { nome: "nome", rotulo: "Nome", tipo: "texto" },
      { nome: "cpf", rotulo: "CPF", tipo: "texto", opcional: true },
      { nome: "cidade", rotulo: "Cidade", tipo: "texto", opcional: true },
    ],
  },
];

// ------------------------------------------------------------ página

export default function Cadastros() {
  const [aba, setAba] = useState(CONFIGS[0].rota);
  const config = CONFIGS.find((c) => c.rota === aba);
  const abas = [...CONFIGS.map((c) => ({ rota: c.rota, nome: c.plural })), { rota: "usuarios", nome: "Acessos" }];

  return (
    <>
      <Cabecalho titulo="Cadastros" />
      <div className="abas" role="tablist">
        {abas.map((a) => (
          <button key={a.rota} role="tab" aria-selected={a.rota === aba} onClick={() => setAba(a.rota)}>
            {a.nome}
          </button>
        ))}
      </div>
      {/* key: troca de aba recomeça o estado (formulários, edição em andamento) */}
      {config ? <TabelaCadastro key={config.rota} config={config} /> : <Usuarios />}
    </>
  );
}

function TabelaCadastro({ config }: { config: Config }) {
  const avisar = useAviso();
  const [todos, setTodos] = useState(false);
  const [editando, setEditando] = useState<number | null>(null);
  const linhas = useCarregar(() => api.get<Linha[]>(`/${config.rota}`, { todos: config.ativavel && todos }), [todos]);
  const lojas = useCarregar(() => api.get<Loja[]>("/lojas"));

  async function executar(acao: () => Promise<unknown>, sucesso: string) {
    try {
      await acao();
      avisar(sucesso);
      linhas.recarregar();
      lojas.recarregar();
      return true;
    } catch (e) {
      avisar((e as Error).message, "erro");
      return false;
    }
  }

  const titulo = config.singular[0].toUpperCase() + config.singular.slice(1);

  return (
    <>
      <FormularioNovo
        config={config}
        lojas={lojas.dados ?? []}
        aoSalvar={(dados) => executar(() => api.post(`/${config.rota}`, dados), `${titulo} cadastrado.`)}
      />

      <section className="bloco">
        {config.ativavel && (
          <label className="opcao">
            <input type="checkbox" checked={todos} onChange={(e) => setTodos(e.target.checked)} />
            Mostrar também os desativados
          </label>
        )}
        <Estado erro={linhas.erro} carregando={!linhas.dados} />
        {linhas.dados && !linhas.dados.length && <Vazio>Nenhum {config.singular} cadastrado ainda.</Vazio>}
        {!!linhas.dados?.length && (
          <table>
            <thead>
              <tr>
                {config.campos.map((c) => (
                  <th key={c.nome} className={ehNumerico(c) ? "num" : ""}>
                    {c.rotulo}
                  </th>
                ))}
                {config.extras?.map((x) => (
                  <th key={x.rotulo} className={x.numerico ? "num" : ""}>
                    {x.rotulo}
                  </th>
                ))}
                <th>
                  <span className="visualmente-oculto">Ações</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {linhas.dados.map((linha) =>
                editando === linha.id ? (
                  <LinhaEdicao
                    key={linha.id}
                    config={config}
                    linha={linha}
                    lojas={lojas.dados ?? []}
                    aoCancelar={() => setEditando(null)}
                    aoSalvar={async (alterados) => {
                      if (!Object.keys(alterados).length) return setEditando(null);
                      const ok = await executar(
                        () => api.patch(`/${config.rota}/${linha.id}`, alterados),
                        "Alterações salvas.",
                      );
                      if (ok) setEditando(null);
                    }}
                  />
                ) : (
                  <tr key={linha.id} className={linha.ativo === false ? "inativo" : ""}>
                    {config.campos.map((c) => (
                      <td key={c.nome} className={ehNumerico(c) ? "num" : ""}>
                        {mostrar(c, linha)}
                      </td>
                    ))}
                    {config.extras?.map((x) => (
                      <td key={x.rotulo} className={x.numerico ? "num" : ""}>
                        {x.valor(linha)}
                      </td>
                    ))}
                    <td className="acoes">
                      <button className="botao-texto" onClick={() => setEditando(linha.id)}>
                        Editar
                      </button>
                      {config.ativavel && (
                        <button
                          className="botao-texto"
                          onClick={() =>
                            executar(
                              () => api.post(`/${config.rota}/${linha.id}/${linha.ativo ? "desativar" : "ativar"}`),
                              linha.ativo ? `${titulo} desativado. O histórico foi mantido.` : `${titulo} reativado.`,
                            )
                          }
                        >
                          {linha.ativo ? "Desativar" : "Reativar"}
                        </button>
                      )}
                    </td>
                  </tr>
                ),
              )}
            </tbody>
          </table>
        )}
      </section>
    </>
  );
}

// ------------------------------------------------------- formulários

function FormularioNovo({
  config,
  lojas,
  aoSalvar,
}: {
  config: Config;
  lojas: Loja[];
  aoSalvar: (dados: Record<string, unknown>) => Promise<boolean>;
}) {
  const avisar = useAviso();

  async function enviar(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const valores = Object.fromEntries(new FormData(form)) as Record<string, string>;
    const dados: Record<string, unknown> = {};
    for (const campo of config.campos) {
      const convertido = converter(campo, valores[campo.nome] ?? "");
      if (convertido instanceof Error) return avisar(convertido.message, "erro");
      if (convertido !== undefined) dados[campo.nome] = convertido;
    }
    if (await aoSalvar(dados)) form.reset();
  }

  return (
    <form className="bloco formulario formulario-linha" onSubmit={enviar}>
      <h2>Novo {config.singular}</h2>
      <div className="linha-campos">
        {config.campos.map((c) => (
          <label key={c.nome}>
            {c.rotulo}
            {c.opcional && <span className="secundario"> (opcional)</span>}
            <Entrada campo={c} lojas={lojas} />
          </label>
        ))}
        <button className="botao-principal">Cadastrar</button>
      </div>
    </form>
  );
}

function LinhaEdicao({
  config,
  linha,
  lojas,
  aoSalvar,
  aoCancelar,
}: {
  config: Config;
  linha: Linha;
  lojas: Loja[];
  aoSalvar: (alterados: Record<string, unknown>) => void;
  aoCancelar: () => void;
}) {
  const avisar = useAviso();
  const formId = `editar-${config.rota}-${linha.id}`;

  function enviar(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const valores = Object.fromEntries(new FormData(e.currentTarget)) as Record<string, string>;
    const alterados: Record<string, unknown> = {};
    for (const campo of config.campos.filter((c) => !c.soNaCriacao)) {
      const convertido = converter(campo, valores[campo.nome] ?? "", true);
      if (convertido instanceof Error) return avisar(convertido.message, "erro");
      if (convertido === undefined) continue;
      const original = linha[campo.leitura ?? campo.nome] ?? "";
      if (convertido !== original && !(convertido === "" && original === "")) {
        alterados[campo.nome] = convertido;
      }
    }
    aoSalvar(alterados); // só os campos que mudaram vão para a API
  }

  return (
    <tr className="editando">
      {config.campos.map((c) => (
        <td key={c.nome}>
          {c.soNaCriacao ? (
            mostrar(c, linha)
          ) : (
            <Entrada campo={c} lojas={lojas} inicial={valorEditavel(c, linha)} form={formId} rotulo={c.rotulo} />
          )}
        </td>
      ))}
      {config.extras?.map((x) => <td key={x.rotulo} />)}
      <td className="acoes">
        <form id={formId} onSubmit={enviar} />
        <button className="botao-principal" form={formId}>
          Salvar
        </button>
        <button className="botao-texto" onClick={aoCancelar}>
          Cancelar
        </button>
      </td>
    </tr>
  );
}

function Entrada({
  campo,
  lojas,
  inicial = "",
  form,
  rotulo,
}: {
  campo: Campo;
  lojas: Loja[];
  inicial?: string;
  form?: string;
  rotulo?: string;
}) {
  const comum = { name: campo.nome, defaultValue: inicial, form, "aria-label": rotulo };
  switch (campo.tipo) {
    case "loja":
      return (
        <select {...comum} required>
          <option value="" disabled>
            Escolha
          </option>
          {lojas.map((l) => (
            <option key={l.id} value={l.id}>
              {l.nome}
            </option>
          ))}
        </select>
      );
    case "uf":
      return <input {...comum} required maxLength={2} size={3} pattern="[A-Za-z]{2}" placeholder="PB" />;
    case "dinheiro":
      return <input {...comum} required inputMode="decimal" size={8} placeholder="0,00" />;
    case "percentual":
      return <input {...comum} type="number" min={0} max={100} step="0.5" size={5} placeholder="3" />;
    default:
      return <input {...comum} required={!campo.opcional} />;
  }
}

// --------------------------------------------------------- conversões

const ehNumerico = (c: Campo) => c.tipo === "dinheiro" || c.tipo === "percentual";

function mostrar(campo: Campo, linha: Linha): ReactNode {
  const valor = linha[campo.exibir ?? campo.leitura ?? campo.nome];
  if (valor === null || valor === undefined || valor === "") return <span className="secundario">—</span>;
  if (campo.tipo === "dinheiro") return reais(valor as number);
  if (campo.tipo === "percentual") return `${valor}%`;
  return String(valor);
}

function valorEditavel(campo: Campo, linha: Linha): string {
  const valor = linha[campo.leitura ?? campo.nome];
  if (valor === null || valor === undefined) return "";
  return campo.tipo === "dinheiro" ? centavosParaTexto(valor as number) : String(valor);
}

/** Texto do formulário → valor da API. `undefined` = não enviar; Error = mensagem para o usuário. */
function converter(campo: Campo, texto: string, edicao = false): unknown {
  const limpo = texto.trim();
  switch (campo.tipo) {
    case "dinheiro": {
      const centavos = paraCentavos(limpo);
      return centavos === null ? new Error(`${campo.rotulo}: use um valor como 29,90.`) : centavos;
    }
    case "percentual":
      return limpo === "" ? undefined : Number(limpo);
    case "loja":
      return Number(limpo);
    case "uf":
      return limpo.toUpperCase();
    default:
      // Na criação, opcional vazio não é enviado; na edição, "" apaga o valor.
      if (campo.opcional && limpo === "" && !edicao) return undefined;
      return limpo;
  }
}
