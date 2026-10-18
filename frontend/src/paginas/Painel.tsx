import { useState } from "react";
import {
  api,
  type LinhaEstoqueBaixo,
  type LinhaLoja,
  type LinhaMes,
  type LinhaVendedor,
  type Resumo,
} from "../api";
import { Cabecalho, Estado, useCarregar, Vazio } from "../componentes/comum";
import { ESTOQUE_MINIMO, MESES, reais } from "../formato";

const ANO_ATUAL = new Date().getFullYear();

export default function Painel() {
  const [inicio, setInicio] = useState("");
  const [fim, setFim] = useState("");
  const [ano, setAno] = useState(ANO_ATUAL);
  const periodo = { inicio, fim };

  const { dados, erro } = useCarregar(
    () =>
      Promise.all([
        api.get<Resumo>("/resumo", { ...periodo, minimo: ESTOQUE_MINIMO }),
        api.get<LinhaLoja[]>("/relatorios/lojas", periodo),
        api.get<LinhaVendedor[]>("/relatorios/vendedores", { ...periodo, limite: 5 }),
        api.get<LinhaEstoqueBaixo[]>("/relatorios/estoque-baixo", { minimo: ESTOQUE_MINIMO }),
      ]),
    [inicio, fim],
  );
  const mensal = useCarregar(() => api.get<LinhaMes[]>("/relatorios/mensal", { ano }), [ano]);

  return (
    <>
      <Cabecalho titulo="Painel">
        <label>
          De
          <input type="date" value={inicio} onChange={(e) => setInicio(e.target.value)} />
        </label>
        <label>
          Até
          <input type="date" value={fim} onChange={(e) => setFim(e.target.value)} />
        </label>
        {(inicio || fim) && (
          <button
            className="botao-texto"
            onClick={() => {
              setInicio("");
              setFim("");
            }}
          >
            Ver todo o período
          </button>
        )}
      </Cabecalho>

      <Estado erro={erro} carregando={!dados} />
      {dados && <ConteudoPainel {...{ dados, ano, setAno, mensal: mensal.dados }} />}
    </>
  );
}

function ConteudoPainel({
  dados: [resumo, lojas, vendedores, estoqueBaixo],
  mensal,
  ano,
  setAno,
}: {
  dados: [Resumo, LinhaLoja[], LinhaVendedor[], LinhaEstoqueBaixo[]];
  mensal: LinhaMes[] | null;
  ano: number;
  setAno: (ano: number) => void;
}) {
  return (
    <>
      <dl className="indicadores">
        <div>
          <dt>Faturamento</dt>
          <dd>{reais(resumo.faturamento)}</dd>
        </div>
        <div>
          <dt>Vendas concluídas</dt>
          <dd>{resumo.vendas.toLocaleString("pt-BR")}</dd>
        </div>
        <div>
          <dt>Ticket médio</dt>
          <dd>{reais(resumo.ticket_medio)}</dd>
        </div>
        <div className={resumo.itens_estoque_baixo ? "indicador-alerta" : ""}>
          <dt>Itens com estoque baixo</dt>
          <dd>
            <a href="#/estoque">{resumo.itens_estoque_baixo}</a>
          </dd>
        </div>
      </dl>

      <section className="bloco">
        <div className="bloco-titulo">
          <h2>Faturamento por mês</h2>
          <select value={ano} onChange={(e) => setAno(Number(e.target.value))} aria-label="Ano">
            {[ANO_ATUAL, ANO_ATUAL - 1, ANO_ATUAL - 2].map((a) => (
              <option key={a}>{a}</option>
            ))}
          </select>
        </div>
        {mensal ? <GraficoMensal linhas={mensal} /> : <p className="estado">Carregando…</p>}
      </section>

      <div className="duas-colunas">
        <section className="bloco">
          <h2>Lojas</h2>
          {lojas.length ? (
            <table>
              <thead>
                <tr>
                  <th>Loja</th>
                  <th className="num">Vendas</th>
                  <th className="num">Faturamento</th>
                  <th className="num">Ticket médio</th>
                </tr>
              </thead>
              <tbody>
                {lojas.map((l) => (
                  <tr key={l.loja}>
                    <td>
                      {l.loja}
                      <span className="secundario">{l.local}</span>
                    </td>
                    <td className="num">{l.vendas}</td>
                    <td className="num">{reais(l.faturamento)}</td>
                    <td className="num">{reais(l.ticket_medio)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <Vazio>Nenhuma loja cadastrada. Comece em Cadastros.</Vazio>
          )}
        </section>

        <section className="bloco">
          <h2>Melhores vendedores</h2>
          {vendedores.length ? (
            <table>
              <thead>
                <tr>
                  <th>Vendedor</th>
                  <th className="num">Faturamento</th>
                  <th className="num">Comissão</th>
                </tr>
              </thead>
              <tbody>
                {vendedores.map((v) => (
                  <tr key={`${v.vendedor}-${v.loja}`}>
                    <td>
                      {v.vendedor}
                      <span className="secundario">{v.loja}</span>
                    </td>
                    <td className="num">{reais(v.faturamento)}</td>
                    <td className="num">{reais(v.comissao)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <Vazio>Nenhuma venda no período.</Vazio>
          )}
        </section>
      </div>

      <section className="bloco">
        <h2>Para repor</h2>
        <p className="ajuda">Produtos com menos de {ESTOQUE_MINIMO} unidades na loja.</p>
        {estoqueBaixo.length ? (
          <table>
            <thead>
              <tr>
                <th>Loja</th>
                <th>Produto</th>
                <th className="num">Em estoque</th>
              </tr>
            </thead>
            <tbody>
              {estoqueBaixo.slice(0, 8).map((e) => (
                <tr key={`${e.loja}-${e.sku}`}>
                  <td>{e.loja}</td>
                  <td>
                    {e.produto}
                    <span className="secundario">{e.sku}</span>
                  </td>
                  <td className={`num ${e.quantidade === 0 ? "alerta" : ""}`}>{e.quantidade}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <Vazio>Todas as lojas estão abastecidas.</Vazio>
        )}
        {estoqueBaixo.length > 8 && (
          <p className="ajuda">
            Mostrando 8 de {estoqueBaixo.length}. <a href="#/estoque">Ver todos no estoque.</a>
          </p>
        )}
      </section>
    </>
  );
}

function GraficoMensal({ linhas }: { linhas: LinhaMes[] }) {
  const porMes = new Map(linhas.map((l) => [Number(l.mes), l]));
  const maior = Math.max(1, ...linhas.map((l) => l.faturamento));
  const total = linhas.reduce((soma, l) => soma + l.faturamento, 0);

  if (!linhas.length) return <Vazio>Nenhuma venda neste ano.</Vazio>;

  return (
    <figure className="grafico">
      <ol className="barras" aria-label={`Faturamento mensal, total ${reais(total)}`}>
        {MESES.map((nome, i) => {
          const linha = porMes.get(i + 1);
          const valor = linha?.faturamento ?? 0;
          return (
            <li key={nome} title={`${nome}: ${reais(valor)} em ${linha?.vendas ?? 0} vendas`}>
              <span className="barra-valor">{valor ? reais(valor).replace(/,\d\d$/, "") : ""}</span>
              <span className="barra" style={{ height: `${(valor / maior) * 100}%` }} />
              <span className="barra-mes">{nome}</span>
            </li>
          );
        })}
      </ol>
    </figure>
  );
}
