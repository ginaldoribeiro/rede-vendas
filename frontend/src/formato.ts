const moeda = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
const dataHora = new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short" });

export const reais = (centavos: number) => moeda.format((centavos ?? 0) / 100);

export const dataCurta = (iso: string) => dataHora.format(new Date(iso));

/** "29,90", "29.90", "R$ 1.234,56" → centavos. Devolve null se não for um número. */
export function paraCentavos(texto: string): number | null {
  let limpo = texto.replace(/R\$\s?/, "").trim();
  if (limpo.includes(",")) limpo = limpo.replace(/\./g, "").replace(",", ".");
  if (!/^\d+(\.\d{1,2})?$/.test(limpo)) return null;
  return Math.round(Number(limpo) * 100);
}

/** Centavos → texto editável no formato brasileiro ("29,90"). */
export const centavosParaTexto = (centavos: number) => (centavos / 100).toFixed(2).replace(".", ",");

export const MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];

/** Abaixo desta quantidade numa loja, o produto aparece como "para repor". */
export const ESTOQUE_MINIMO = 10;
