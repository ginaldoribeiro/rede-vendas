import { Fragment, useState } from "react";
import { api, type Loja, type Venda, type VendaDetalhe } from "../api";
import { Cabecalho, Estado, useAviso, useCarregar, Vazio } from "../componentes/comum";
import { ehGerente, useSessao } from "../componentes/sessao";
import { dataCurta, reais } from "../formato";

export default function Vendas() {
  const avisar = useAviso();
  const gerente = ehGerente(useSessao().usuario);
  const [lojaId, setLojaId] = useState("");
  const [aberta, setAberta] = useState<VendaDetalhe | null>(null);
  const lojas = useCarregar(() => (gerente ? api.get<Loja[]>("/lojas") : Promise.resolve([])));
  const vendas = useCarregar(() => api.get<Venda[]>("/vendas", { loja_id: lojaId, limite: 100 }), [lojaId]);

  async function abrir(id: number) {
    if (aberta?.id === id) return setAberta(null);
    try {
      setAberta(await api.get<VendaDetalhe>(`/vendas/${id}`));
    } catch (e) {
      avisar((e as Error).message, "erro");
    }
  }

  async function cancelar(venda: Venda) {
    const confirmar = window.confirm(
      `Cancelar a venda nº ${venda.id} de ${reais(venda.total)}? Os itens voltam para o estoque de ${venda.loja}.`,
    );
    if (!confirmar) return;
    try {
      await api.post(`/vendas/${venda.id}/cancelar`);
      avisar(`Venda ${venda.id} cancelada. O estoque foi devolvido.`);
      setAberta(null);
      vendas.recarregar();
    } catch (e) {
      avisar((e as Error).message, "erro");
    }
  }

  return (
    <>
      <Cabecalho titulo={gerente ? "Vendas" : "Minhas vendas"}>
        {gerente && (
        <label>
          Loja
          <select value={lojaId} onChange={(e) => setLojaId(e.target.value)}>
            <option value="">Todas</option>
            {lojas.dados?.map((l) => (
              <option key={l.id} value={l.id}>
                {l.nome}
              </option>
            ))}
          </select>
        </label>
        )}
        <a className="botao-principal" href="#/nova-venda">
          Nova venda
        </a>
      </Cabecalho>

      <Estado erro={vendas.erro} carregando={!vendas.dados} />
      {vendas.dados && !vendas.dados.length && (
        <Vazio>
          Nenhuma venda registrada ainda. <a href="#/nova-venda">Registre a primeira.</a>
        </Vazio>
      )}

      {!!vendas.dados?.length && (
        <section className="bloco">
          <p className="ajuda">As 100 vendas mais recentes. Clique numa venda para ver os itens.</p>
          <table className="tabela-clicavel">
            <thead>
              <tr>
                <th className="num">Nº</th>
                <th>Data</th>
                <th>Loja</th>
                <th>Vendedor</th>
                <th>Cliente</th>
                <th className="num">Itens</th>
                <th className="num">Total</th>
                <th>Situação</th>
              </tr>
            </thead>
            <tbody>
              {vendas.dados.map((v) => (
                <Fragment key={v.id}>
                  <tr
                    className={v.status === "CANCELADA" ? "cancelada" : ""}
                    onClick={() => abrir(v.id)}
                    aria-expanded={aberta?.id === v.id}
                  >
                    <td className="num">{v.id}</td>
                    <td>{dataCurta(v.data_hora)}</td>
                    <td>{v.loja}</td>
                    <td>{v.vendedor}</td>
                    <td>{v.cliente ?? <span className="secundario">Não identificado</span>}</td>
                    <td className="num">{v.itens}</td>
                    <td className="num">{reais(v.total)}</td>
                    <td>{v.status === "CANCELADA" ? "Cancelada" : "Concluída"}</td>
                  </tr>
                  {aberta?.id === v.id && (
                    <tr className="detalhe">
                      <td colSpan={8}>
                        <DetalheVenda venda={aberta} aoCancelar={gerente ? () => cancelar(v) : undefined} />
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </>
  );
}

function DetalheVenda({ venda, aoCancelar }: { venda: VendaDetalhe; aoCancelar?: () => void }) {
  return (
    <div className="detalhe-venda">
      <table>
        <thead>
          <tr>
            <th>Produto</th>
            <th className="num">Qtd.</th>
            <th className="num">Preço na venda</th>
            <th className="num">Subtotal</th>
          </tr>
        </thead>
        <tbody>
          {venda.lista_itens.map((i) => (
            <tr key={i.sku}>
              <td>
                {i.nome}
                <span className="secundario">{i.sku}</span>
              </td>
              <td className="num">{i.quantidade}</td>
              <td className="num">{reais(i.preco_unit)}</td>
              <td className="num">{reais(i.subtotal)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="detalhe-rodape">
        <span>
          Desconto {reais(venda.desconto)}. Comissão de {venda.comissao_pct}% para {venda.vendedor}.
        </span>
        {venda.status === "CONCLUIDA" && aoCancelar && (
          <button className="botao-perigo" onClick={aoCancelar}>
            Cancelar venda
          </button>
        )}
      </div>
    </div>
  );
}
