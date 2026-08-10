/**
 * Atribuição de cor às categorias de gasto.
 *
 * A regra que isto respeita: **a cor segue a entidade, não a posição dela no
 * ranking**. Se a cor fosse por ordem de gasto, filtrar um período repintaria as
 * categorias sobreviventes e o leitor perderia a referência que acabou de aprender —
 * "o laranja é Mercearia" viraria "o laranja é o segundo colocado".
 *
 * Por isso existe uma ordem canônica fixa aqui. As categorias vêm de
 * `backend/app/services/classificacao.py`; a lista abaixo precisa acompanhar aquela.
 *
 * São 8 slots porque acima disso as cores deixam de ser distinguíveis (inclusive para
 * quem tem daltonismo). O backend já dobra a cauda em "Outras", que recebe **cinza**:
 * não é uma entidade, é um resto, e gastar um hue nela roubaria cor de quem precisa.
 */

const ORDEM_CANONICA = [
  "Carnes",
  "Mercearia",
  "Hortifruti",
  "Congelados",
  "Bebidas",
  "Limpeza",
  "Higiene",
  "Padaria",
  "Frios e laticínios",
  "Doces e snacks",
  "Descartáveis",
  "Bebidas alcoólicas",
  "Pet",
  "Outros",
] as const;

const RESTO = new Set(["Outras", "Outros", "Sem categoria"]);

/**
 * Mapeia as categorias presentes num gráfico para variáveis CSS de cor.
 *
 * Recebe a lista de categorias daquele gráfico e devolve a cor de cada uma, atribuída
 * pela ordem canônica — determinística para um mesmo conjunto, e estável enquanto a
 * categoria continuar no gráfico.
 */
export function mapearCores(categorias: string[]): Record<string, string> {
  const doResto = categorias.filter((c) => RESTO.has(c));
  const comHue = categorias
    .filter((c) => !RESTO.has(c))
    .sort((a, b) => {
      const ia = ORDEM_CANONICA.indexOf(a as never);
      const ib = ORDEM_CANONICA.indexOf(b as never);
      // Categoria fora da ordem canônica (regra nova no backend, ainda não listada
      // aqui) vai para o fim, em vez de disputar o slot 1 por acidente de ordenação.
      return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib);
    });

  const cores: Record<string, string> = {};
  comHue.forEach((categoria, indice) => {
    cores[categoria] = `var(--cat-${(indice % 8) + 1})`;
  });
  doResto.forEach((categoria) => {
    cores[categoria] = "var(--cat-outras)";
  });
  return cores;
}
