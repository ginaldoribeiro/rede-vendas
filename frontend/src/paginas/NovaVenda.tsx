import { useMemo, useState } from "react";
import { api, type Cliente, type ItemEstoque, type Produto, type VendaDetalhe, type Vendedor } from "../api";
import { Cabecalho, Estado, useAviso, useCarregar, Vazio } from "../componentes/comum";
import { ehGerente, useSessao } from "../componentes/sessao";
import { dataCurta, reais } from "../formato";

const DESCONTO_MAXIMO = 30;

type Carrinho = Map<number, number>; // produto_id → quantidade

export default function NovaVenda() {
  const avisar = useAviso();
  const { usuario } = useSessao();
  const gerente = ehGerente(usuario);
  // O vendedor logado vende sempre em nome próprio; só o gerente escolhe o vendedor.
  const proprio: Vendedor[] = gerente
    ? []
    : [
        {
          id: usuario.vendedor_id!,
          nome: usuario.nome,
          loja_id: usuario.loja_id!,
          loja: usuario.loja!,
          comissao_pct: 0,
          ativo: true,
        },
      ];
  const cadastros = useCarregar(() =>
    Promise.all([
      gerente ? api.get<Vendedor[]>("/vendedores") : Promise.resolve(proprio),
      api.get<Cliente[]>("/clientes"),
      api.get<Produto[]>("/produtos"),
    ]),
  );
  const [vendedorId, setVendedorId] = useState<number | null>(gerente ? null : usuario.vendedor_id);
  const [clienteId, setClienteId] = useState<number | null>(null);
  const [busca, setBusca] = useState("");
  const [carrinho, setCarrinho] = useState<Carrinho>(new Map());
  const [desconto, setDesconto] = useState(0);
  const [enviando, setEnviando] = useState(false);
  const [ultimaVenda, setUltimaVenda] = useState<VendaDetalhe | null>(null);

  const [vendedores, clientes, produtos] = cadastros.dados ?? [[], [], []];
  const vendedor = vendedores.find((v) => v.id === vendedorId) ?? null;

  const estoque = useCarregar(
    () =>
      vendedor ? api.get<ItemEstoque[]>("/estoque", { loja_id: vendedor.loja_id }) : Promise.resolve([]),
    [vendedor?.loja_id],
  );
  const saldo = useMemo(
    () => new Map((estoque.dados ?? []).map((e) => [e.produto_id, e.quantidade])),
    [estoque.dados],
  );

  const itens = [...carrinho].map(([id, quantidade]) => ({
    produto: produtos.find((p) => p.id === id)!,
    quantidade,
  }));
  const bruto = itens.reduce((soma, i) => soma + i.produto.preco * i.quantidade, 0);
  const valorDesconto = Math.round((bruto * desconto) / 100);

  const termo = busca.trim().toLowerCase();
  const visiveis = produtos.filter(
    (p) => !termo || p.nome.toLowerCase().includes(termo) || p.sku.toLowerCase().includes(termo),
  );

  function alterar(produtoId: number, delta: number) {
    setCarrinho((atual) => {
      const novo = new Map(atual);
      const desejada = (novo.get(produtoId) ?? 0) + delta;
      const quantidade = Math.min(desejada, saldo.get(produtoId) ?? 0);
      if (quantidade <= 0) novo.delete(produtoId);
      else novo.set(produtoId, quantidade);
      return novo;
    });
  }

  function trocarVendedor(id: number | null) {
    setVendedorId(id);
    setCarrinho(new Map()); // o estoque é da loja do vendedor; o carrinho anterior pode não valer
  }

  async function registrar() {
    if (!vendedor) return;
    setEnviando(true);
    try {
      const venda = await api.post<VendaDetalhe>("/vendas", {
        vendedor_id: vendedor.id,
        cliente_id: clienteId,
        desconto_pct: desconto,
        itens: itens.map((i) => ({ produto_id: i.produto.id, quantidade: i.quantidade })),
      });
      setUltimaVenda(venda);
      setCarrinho(new Map());
      setDesconto(0);
      setClienteId(null);
      estoque.recarregar();
      avisar(`Venda ${venda.id} registrada: ${reais(venda.total)}.`);
    } catch (e) {
      avisar((e as Error).message, "erro");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <>
      <Cabecalho titulo="Nova venda" />
      <Estado erro={cadastros.erro} carregando={!cadastros.dados} />

      {cadastros.dados && (
        <div className="pdv">
          <div className="pdv-escolha">
            <div className="linha-campos">
              {gerente && (
              <label>
                Vendedor
                <select
                  value={vendedorId ?? ""}
                  onChange={(e) => trocarVendedor(e.target.value ? Number(e.target.value) : null)}
                >
                  <option value="">Escolha quem está vendendo</option>
                  {vendedores.map((v) => (
                    <option key={v.id} value={v.id}>
                      {v.nome} ({v.loja})
                    </option>
                  ))}
                </select>
              </label>
              )}
              <label>
                Cliente
                <select
                  value={clienteId ?? ""}
                  onChange={(e) => setClienteId(e.target.value ? Number(e.target.value) : null)}
                >
                  <option value="">Não identificado</option>
                  {clientes.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.nome}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            {!vendedor ? (
              <Vazio>Escolha o vendedor para ver o estoque da loja dele.</Vazio>
            ) : (
              <>
                <label className="busca">
                  Buscar produto
                  <input
                    type="search"
                    value={busca}
                    placeholder="Nome ou código"
                    onChange={(e) => setBusca(e.target.value)}
                  />
                </label>
                <ul className="lista-produtos">
                  {visiveis.map((p) => {
                    const disponivel = (saldo.get(p.id) ?? 0) - (carrinho.get(p.id) ?? 0);
                    return (
                      <li key={p.id}>
                        <div>
                          <strong>{p.nome}</strong>
                          <span className="secundario">
                            {p.sku}, {disponivel} em estoque
                          </span>
                        </div>
                        <span className="num">{reais(p.preco)}</span>
                        <button onClick={() => alterar(p.id, 1)} disabled={disponivel <= 0}>
                          {disponivel > 0 ? "Adicionar" : "Sem estoque"}
                        </button>
                      </li>
                    );
                  })}
                  {!visiveis.length && <Vazio>Nenhum produto encontrado para “{busca}”.</Vazio>}
                </ul>
              </>
            )}
          </div>

          <aside className="cupom" aria-label="Cupom da venda">
            <header>
              <strong>{vendedor ? vendedor.loja : "Rede de Vendas"}</strong>
              <span>{vendedor ? `Vendedor: ${vendedor.nome}` : "Nenhum vendedor escolhido"}</span>
            </header>

            {itens.length ? (
              <ul className="cupom-itens">
                {itens.map(({ produto, quantidade }) => (
                  <li key={produto.id}>
                    <span className="cupom-nome">{produto.nome}</span>
                    <span className="cupom-qtd">
                      <button aria-label={`Remover uma unidade de ${produto.nome}`} onClick={() => alterar(produto.id, -1)}>
                        −
                      </button>
                      {quantidade} × {reais(produto.preco)}
                      <button
                        aria-label={`Adicionar uma unidade de ${produto.nome}`}
                        onClick={() => alterar(produto.id, 1)}
                        disabled={quantidade >= (saldo.get(produto.id) ?? 0)}
                      >
                        +
                      </button>
                    </span>
                    <span className="num">{reais(produto.preco * quantidade)}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="cupom-vazio">Os produtos adicionados aparecem aqui.</p>
            )}

            <dl className="cupom-totais">
              <div>
                <dt>Subtotal</dt>
                <dd>{reais(bruto)}</dd>
              </div>
              <div>
                <dt>
                  <label htmlFor="desconto">Desconto (%)</label>
                </dt>
                <dd>
                  <input
                    id="desconto"
                    type="number"
                    min={0}
                    max={DESCONTO_MAXIMO}
                    value={desconto}
                    onChange={(e) =>
                      setDesconto(Math.min(DESCONTO_MAXIMO, Math.max(0, Number(e.target.value) || 0)))
                    }
                  />
                  {valorDesconto > 0 && <span> −{reais(valorDesconto)}</span>}
                </dd>
              </div>
              <div className="cupom-total">
                <dt>Total</dt>
                <dd>{reais(bruto - valorDesconto)}</dd>
              </div>
            </dl>

            <button className="botao-principal" onClick={registrar} disabled={!itens.length || enviando}>
              {enviando ? "Registrando…" : "Registrar venda"}
            </button>
            {itens.length > 0 && (
              <button className="botao-texto" onClick={() => setCarrinho(new Map())}>
                Limpar cupom
              </button>
            )}

            {ultimaVenda && (
              <p className="cupom-ultima">
                Última venda: nº {ultimaVenda.id}, {dataCurta(ultimaVenda.data_hora)},{" "}
                {reais(ultimaVenda.total)}
              </p>
            )}
          </aside>
        </div>
      )}
    </>
  );
}
