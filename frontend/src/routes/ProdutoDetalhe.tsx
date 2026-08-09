/** Histórico de preço de um produto — a tela que motivou o app. */

import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { GraficoSerie } from "../components/GraficoSerie";
import type { SeriePrecos } from "../api/client";
import { api, mesLegivel, moeda } from "../api/client";

export function ProdutoDetalhe() {
  const { id } = useParams<{ id: string }>();
  const [dados, setDados] = useState<SeriePrecos | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [verTabela, setVerTabela] = useState(false);

  useEffect(() => {
    if (!id) return;
    void (async () => {
      try {
        setDados(await api.seriePrecos(Number(id)));
      } catch {
        setErro("Não foi possível carregar o histórico deste produto.");
      }
    })();
  }, [id]);

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
  if (!dados) return <p className="vazio">Carregando…</p>;

  const { serie, variacao } = dados;
  const totalGasto = serie.reduce((soma, ponto) => soma + ponto.total_gasto, 0);
  const totalCompras = serie.reduce((soma, ponto) => soma + ponto.n_compras, 0);

  return (
    <>
      <p style={{ margin: "0.25rem 0 0.5rem" }}>
        <Link to="/produtos">← Produtos</Link>
      </p>
      <h1 style={{ fontSize: "1.25rem", margin: "0 0 1rem" }}>{dados.produto.nome}</h1>

      <div className="tiles">
        <div className="tile">
          <div className="rotulo">Preço atual</div>
          <div className="valor">
            {serie.length > 0 ? moeda(serie.at(-1)!.preco_medio) : "—"}
          </div>
          <div className="nota">
            {serie.length > 0 ? `média de ${mesLegivel(serie.at(-1)!.mes)}` : "sem dados"}
          </div>
        </div>
        <div className="tile">
          <div className="rotulo">Variação</div>
          <div className="valor">
            {variacao ? (
              <span
                className={
                  variacao.variacao_percentual > 0 ? "delta-sobe" : "delta-desce"
                }
              >
                {variacao.variacao_percentual > 0 ? "▲" : "▼"}{" "}
                {Math.abs(variacao.variacao_percentual).toFixed(1)}%
              </span>
            ) : (
              "—"
            )}
          </div>
          <div className="nota">
            {/* Com uma compra só não existe variação — dizer isso é melhor que
                mostrar 0% e passar a impressão de preço estável. */}
            {variacao
              ? `${mesLegivel(variacao.mes_inicial)} → ${mesLegivel(variacao.mes_final)}`
              : "precisa de compras em 2 meses diferentes"}
          </div>
        </div>
        <div className="tile">
          <div className="rotulo">Total gasto</div>
          <div className="valor">{moeda(totalGasto)}</div>
          <div className="nota">
            em {totalCompras} {totalCompras === 1 ? "compra" : "compras"}
          </div>
        </div>
      </div>

      <section className="cartao">
        <h2>Preço pago mês a mês</h2>
        <p className="legenda">
          Linha: preço unitário médio. Faixa clara: do menor ao maior preço pago no mês.
        </p>

        <figure>
          <GraficoSerie serie={serie} rotuloMes={mesLegivel} />
          <figcaption>
            {serie.length === 1
              ? "Só um mês com dados até agora — o histórico aparece quando houver mais compras."
              : `${serie.length} meses com compras registradas.`}
          </figcaption>
        </figure>

        {serie.length > 0 && (
          <>
            <div className="acoes">
              <button className="discreto" onClick={() => setVerTabela((v) => !v)}>
                {verTabela ? "Ocultar tabela" : "Ver como tabela"}
              </button>
            </div>

            {verTabela && (
              <div className="rolagem-x">
                <table className="tabela-dados">
                  <thead>
                    <tr>
                      <th>Mês</th>
                      <th>Médio</th>
                      <th>Mínimo</th>
                      <th>Máximo</th>
                      <th>Qtd.</th>
                      <th>Gasto</th>
                    </tr>
                  </thead>
                  <tbody>
                    {serie.map((ponto) => (
                      <tr key={ponto.mes}>
                        <td>{mesLegivel(ponto.mes)}</td>
                        <td>{moeda(ponto.preco_medio)}</td>
                        <td>{moeda(ponto.preco_min)}</td>
                        <td>{moeda(ponto.preco_max)}</td>
                        <td>{ponto.quantidade_total.toLocaleString("pt-BR")}</td>
                        <td>{moeda(ponto.total_gasto)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </section>
    </>
  );
}
