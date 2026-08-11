/**
 * Gastos por categoria: composição, ranking, evolução mensal e detalhamento.
 *
 * Três formas, cada uma respondendo a uma pergunta diferente — é o que evita repetir o
 * mesmo dado três vezes:
 *
 * - **Composição** (barra empilhada): "que fração do meu dinheiro vai para cada grupo".
 * - **Ranking** (barras, hue única): "quais grupos são os maiores", com comprimento
 *   comparável lado a lado. Aqui a cor não identifica nada, então não há legenda.
 * - **Evolução** (colunas empilhadas por mês): "isso muda ao longo do tempo".
 *
 * A tabela ao final não é redundância: é o caminho de leitura para quem não distingue
 * as cores, e o número exato para quem quer conferir.
 */

import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { GraficoBarras } from "../components/GraficoBarras";
import { GraficoColunasEmpilhadas } from "../components/GraficoColunasEmpilhadas";
import { GraficoComparacao } from "../components/GraficoComparacao";
import { GraficoComposicao } from "../components/GraficoComposicao";
import type {
  ComparacaoProdutos,
  EvolucaoCategorias,
  FatiaCategoria,
  ProdutoDaCategoria,
} from "../api/client";
import { api, moeda } from "../api/client";

export function Categorias() {
  const navegar = useNavigate();
  const [categorias, setCategorias] = useState<FatiaCategoria[]>([]);
  const [evolucao, setEvolucao] = useState<EvolucaoCategorias | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [verTabela, setVerTabela] = useState(false);

  const [aberta, setAberta] = useState<string | null>(null);
  const [produtos, setProdutos] = useState<ProdutoDaCategoria[]>([]);
  const [comparacao, setComparacao] = useState<ComparacaoProdutos | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        const [c, e] = await Promise.all([
          api.categorias(),
          api.evolucaoCategorias(),
        ]);
        setCategorias(c);
        setEvolucao(e);
      } catch {
        setErro("Não foi possível carregar os gastos por categoria.");
      } finally {
        setCarregando(false);
      }
    })();
  }, []);

  const abrirCategoria = async (categoria: string) => {
    if (aberta === categoria) {
      setAberta(null);
      return;
    }
    setAberta(categoria);
    setProdutos([]);
    setComparacao(null);
    try {
      const lista = await api.produtosDaCategoria(categoria);
      setProdutos(lista);

      // Compara os oito maiores em gasto: é o teto da paleta categórica, e acima
      // disso as linhas deixam de ser distinguíveis. Só produtos com mais de uma
      // compra entram — um ponto isolado não forma linha nem diz nada sobre preço.
      const comparaveis = lista.filter((p) => p.n_compras > 1).slice(0, 8);
      if (comparaveis.length >= 2) {
        setComparacao(await api.comparar(comparaveis.map((p) => p.produto_id)));
      }
    } catch {
      setErro(`Não foi possível carregar os produtos de ${categoria}.`);
    }
  };

  if (carregando) return <p className="vazio">Carregando…</p>;
  if (erro) {
    return (
      <div className="aviso erro">
        <span className="icone" aria-hidden="true">
          ⚠️
        </span>
        <span>{erro}</span>
      </div>
    );
  }

  if (categorias.length === 0) {
    return (
      <>
        <h1 style={{ fontSize: "1.25rem", margin: "0.25rem 0 1rem" }}>Categorias</h1>
        <div className="cartao">
          <h2>Nada classificado ainda</h2>
          <p className="legenda">
            As categorias aparecem quando os itens das notas estão vinculados a
            produtos. Importe uma nota para começar.
          </p>
        </div>
      </>
    );
  }

  const total = categorias.reduce((soma, c) => soma + c.total_gasto, 0);
  const maior = categorias[0];
  const meses = evolucao?.meses.length ?? 0;

  return (
    <>
      <h1 style={{ fontSize: "1.25rem", margin: "0.25rem 0 1rem" }}>Categorias</h1>

      <div className="tiles">
        <div className="tile">
          <div className="rotulo">Total classificado</div>
          <div className="valor">{moeda(total)}</div>
          <div className="nota">
            {categorias.length} categorias ·{" "}
            {categorias.reduce((s, c) => s + c.n_itens, 0)} itens
          </div>
        </div>
        <div className="tile">
          <div className="rotulo">Maior categoria</div>
          <div className="valor" style={{ fontSize: "1.15rem" }}>
            {maior.categoria}
          </div>
          <div className="nota">
            {moeda(maior.total_gasto)} · {maior.fatia}% do total
          </div>
        </div>
      </div>

      <section className="cartao">
        <h2>Composição do gasto</h2>
        <p className="legenda">
          Quanto de cada real vai para cada grupo. Toque numa categoria para ver os
          produtos dela.
        </p>
        <GraficoComposicao dados={categorias} aoClicar={abrirCategoria} />
      </section>

      <section className="cartao">
        <h2>Ranking por categoria</h2>
        <p className="legenda">
          As mesmas categorias em barras, para comparar tamanho lado a lado.
        </p>
        <GraficoBarras
          dados={categorias.map((c) => ({
            id: c.categoria,
            rotulo: c.categoria,
            valor: c.total_gasto,
            detalhe: `${c.n_itens} itens · ${c.n_produtos} produtos · ${c.fatia}%`,
          }))}
          aoClicar={(id) => void abrirCategoria(String(id))}
        />
      </section>

      {evolucao && (
        <section className="cartao">
          <h2>Evolução mês a mês</h2>
          {meses > 1 ? (
            <>
              <p className="legenda">
                Altura na mesma escala entre os meses, então a diferença de tamanho é
                diferença de gasto de verdade.
              </p>
              <GraficoColunasEmpilhadas
                meses={evolucao.meses}
                categorias={evolucao.categorias}
              />
            </>
          ) : (
            <p className="legenda">
              Há apenas um mês com compras registradas, então não existe evolução para
              mostrar ainda. Ao importar notas de outro mês, o gráfico aparece aqui.
            </p>
          )}
          {evolucao.agrupadas_em_outras.length > 0 && (
            <p className="secundario" style={{ marginTop: "0.6rem", fontSize: "0.75rem" }}>
              Agrupadas em “Outras”: {evolucao.agrupadas_em_outras.join(", ")} — acima de
              oito cores elas deixam de ser distinguíveis, inclusive para quem tem
              daltonismo.
            </p>
          )}
        </section>
      )}

      {aberta && (
        <section className="cartao">
          <h2>{aberta}</h2>
          <p className="legenda">
            Produtos desta categoria, do maior gasto para o menor.
          </p>
          {comparacao && comparacao.produtos.length >= 2 && (
            <div style={{ marginBottom: "1.2rem" }}>
              <h3 style={{ fontSize: "0.88rem", margin: "0 0 0.15rem" }}>
                Comparação de preço por unidade
              </h3>
              <p className="legenda">
                Cada linha é um produto desta categoria. O eixo é preço por kg ou
                unidade — comparar gasto total não funciona quando as quantidades
                compradas são diferentes.
              </p>
              <GraficoComparacao dados={comparacao} />
            </div>
          )}

          {produtos.length === 0 ? (
            <p className="vazio">Carregando…</p>
          ) : (
            <ul className="lista">
              {produtos.map((p) => (
                <li key={p.produto_id}>
                  <div className="cresce">
                    <div className="titulo">{p.nome}</div>
                    <div className="sub">
                      {p.n_compras} {p.n_compras === 1 ? "compra" : "compras"} · média{" "}
                      {moeda(p.preco_medio)}
                    </div>
                  </div>
                  <div className="numero">{moeda(p.total_gasto)}</div>
                  <button
                    className="discreto"
                    onClick={() => navegar(`/produtos/${p.produto_id}`)}
                  >
                    histórico
                  </button>
                </li>
              ))}
            </ul>
          )}
          <div className="acoes">
            <button onClick={() => setAberta(null)}>Fechar</button>
          </div>
        </section>
      )}

      <section className="cartao">
        <h2>Números exatos</h2>
        <div className="acoes" style={{ marginTop: 0, marginBottom: "0.5rem" }}>
          <button className="discreto" onClick={() => setVerTabela((v) => !v)}>
            {verTabela ? "Ocultar tabela" : "Ver tabela"}
          </button>
        </div>
        {verTabela && (
          <div className="rolagem-x">
            <table className="tabela-dados">
              <thead>
                <tr>
                  <th>Categoria</th>
                  <th>Gasto</th>
                  <th>Fatia</th>
                  <th>Itens</th>
                  <th>Produtos</th>
                </tr>
              </thead>
              <tbody>
                {categorias.map((c) => (
                  <tr key={c.categoria}>
                    <td>{c.categoria}</td>
                    <td>{moeda(c.total_gasto)}</td>
                    <td>{c.fatia}%</td>
                    <td>{c.n_itens}</td>
                    <td>{c.n_produtos}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr>
                  <th>Total</th>
                  <th>{moeda(total)}</th>
                  <th>100%</th>
                  <th>{categorias.reduce((s, c) => s + c.n_itens, 0)}</th>
                  <th>{categorias.reduce((s, c) => s + c.n_produtos, 0)}</th>
                </tr>
              </tfoot>
            </table>
          </div>
        )}
      </section>
    </>
  );
}
