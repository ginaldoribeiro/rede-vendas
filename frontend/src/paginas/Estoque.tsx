import { useState, type FormEvent } from "react";
import { api, type ItemEstoque, type Loja, type Produto } from "../api";
import { Cabecalho, Estado, useAviso, useCarregar, Vazio } from "../componentes/comum";
import { ESTOQUE_MINIMO as MINIMO } from "../formato";

export default function Estoque() {
  const avisar = useAviso();
  const [lojaId, setLojaId] = useState("");
  const [soBaixo, setSoBaixo] = useState(false);
  const cadastros = useCarregar(() => Promise.all([api.get<Loja[]>("/lojas"), api.get<Produto[]>("/produtos")]));
  const estoque = useCarregar(() => api.get<ItemEstoque[]>("/estoque", { loja_id: lojaId }), [lojaId]);
  const [lojas, produtos] = cadastros.dados ?? [[], []];

  const linhas = (estoque.dados ?? []).filter((e) => !soBaixo || e.quantidade < MINIMO);

  async function enviar(caminho: string, corpo: object, sucesso: string) {
    try {
      await api.post(caminho, corpo);
      avisar(sucesso);
      estoque.recarregar();
      return true;
    } catch (e) {
      avisar((e as Error).message, "erro");
      return false;
    }
  }

  return (
    <>
      <Cabecalho titulo="Estoque">
        <label>
          Loja
          <select value={lojaId} onChange={(e) => setLojaId(e.target.value)}>
            <option value="">Todas</option>
            {lojas.map((l) => (
              <option key={l.id} value={l.id}>
                {l.nome}
              </option>
            ))}
          </select>
        </label>
        <label className="opcao">
          <input type="checkbox" checked={soBaixo} onChange={(e) => setSoBaixo(e.target.checked)} />
          Só abaixo de {MINIMO} unidades
        </label>
      </Cabecalho>

      <div className="duas-colunas">
        <FormEntrada lojas={lojas} produtos={produtos} aoEnviar={enviar} />
        <FormTransferencia lojas={lojas} produtos={produtos} aoEnviar={enviar} />
      </div>

      <Estado erro={estoque.erro} carregando={!estoque.dados} />
      {estoque.dados && (
        <section className="bloco">
          {linhas.length ? (
            <table>
              <thead>
                <tr>
                  <th>Loja</th>
                  <th>Código</th>
                  <th>Produto</th>
                  <th className="num">Quantidade</th>
                </tr>
              </thead>
              <tbody>
                {linhas.map((e) => (
                  <tr key={`${e.loja_id}-${e.produto_id}`}>
                    <td>{e.loja}</td>
                    <td className="secundario-celula">{e.sku}</td>
                    <td>{e.produto}</td>
                    <td className={`num ${e.quantidade < MINIMO ? "alerta" : ""}`}>{e.quantidade}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <Vazio>{soBaixo ? "Nenhum item abaixo do mínimo." : "Nenhum produto ativo cadastrado."}</Vazio>
          )}
        </section>
      )}
    </>
  );
}

type PropsForm = {
  lojas: Loja[];
  produtos: Produto[];
  aoEnviar: (caminho: string, corpo: object, sucesso: string) => Promise<boolean>;
};

function SelecaoLoja({ nome, rotulo, lojas }: { nome: string; rotulo: string; lojas: Loja[] }) {
  return (
    <label>
      {rotulo}
      <select name={nome} required defaultValue="">
        <option value="" disabled>
          Escolha
        </option>
        {lojas.map((l) => (
          <option key={l.id} value={l.id}>
            {l.nome}
          </option>
        ))}
      </select>
    </label>
  );
}

function SelecaoProduto({ produtos }: { produtos: Produto[] }) {
  return (
    <label>
      Produto
      <select name="produto_id" required defaultValue="">
        <option value="" disabled>
          Escolha
        </option>
        {produtos.map((p) => (
          <option key={p.id} value={p.id}>
            {p.nome}
          </option>
        ))}
      </select>
    </label>
  );
}

const numeros = (form: HTMLFormElement) =>
  Object.fromEntries([...new FormData(form)].map(([chave, valor]) => [chave, Number(valor)]));

function FormEntrada({ lojas, produtos, aoEnviar }: PropsForm) {
  async function enviar(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const dados = numeros(form);
    if (await aoEnviar("/estoque/entradas", dados, `Entrada de ${dados.quantidade} unidades registrada.`)) {
      form.reset();
    }
  }
  return (
    <form className="bloco formulario" onSubmit={enviar}>
      <h2>Entrada de mercadoria</h2>
      <SelecaoLoja nome="loja_id" rotulo="Loja" lojas={lojas} />
      <SelecaoProduto produtos={produtos} />
      <label>
        Quantidade
        <input name="quantidade" type="number" min={1} required />
      </label>
      <button className="botao-principal">Registrar entrada</button>
    </form>
  );
}

function FormTransferencia({ lojas, produtos, aoEnviar }: PropsForm) {
  async function enviar(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const dados = numeros(form);
    if (await aoEnviar("/estoque/transferencias", dados, `${dados.quantidade} unidades transferidas.`)) {
      form.reset();
    }
  }
  return (
    <form className="bloco formulario" onSubmit={enviar}>
      <h2>Transferência entre lojas</h2>
      <div className="linha-campos">
        <SelecaoLoja nome="origem_id" rotulo="De" lojas={lojas} />
        <SelecaoLoja nome="destino_id" rotulo="Para" lojas={lojas} />
      </div>
      <SelecaoProduto produtos={produtos} />
      <label>
        Quantidade
        <input name="quantidade" type="number" min={1} required />
      </label>
      <button className="botao-principal">Transferir</button>
    </form>
  );
}
