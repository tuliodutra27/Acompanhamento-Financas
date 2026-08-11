/**
 * Compara o preço de vários produtos no mesmo eixo — pensado para cortes de carne.
 *
 * O eixo é **preço por unidade de medida** (R$/kg), nunca gasto total: comprar 0,8 kg
 * de acém por R$ 42 e 1,2 kg por R$ 40 parece "quase o mesmo gasto" e esconde uma alta
 * de 57% no quilo. O tooltip mostra quantidade e gasto justamente para deixar essa
 * diferença explícita.
 *
 * Aqui a cor **identifica** cada corte, então é paleta categórica com legenda
 * obrigatória — e o teto de séries é o da paleta: acima disso as linhas deixam de ser
 * distinguíveis.
 *
 * Mês sem compra é lacuna na linha, não zero: um produto que não foi comprado não teve
 * preço zero.
 */

import { useMemo, useState } from "react";
import { mesLegivel, moeda } from "../api/client";
import type { ComparacaoProdutos } from "../api/client";

const CORES = [
  "var(--cat-1)",
  "var(--cat-2)",
  "var(--cat-3)",
  "var(--cat-4)",
  "var(--cat-5)",
  "var(--cat-6)",
  "var(--cat-7)",
  "var(--cat-8)",
];

const L = 52;
const R = 14;
const T = 16;
const B = 26;
const LARGURA = 560;
const ALTURA = 250;

interface Props {
  dados: ComparacaoProdutos;
}

export function GraficoComparacao({ dados }: Props) {
  const [foco, setFoco] = useState<{ serie: number; mes: number } | null>(null);

  const geo = useMemo(() => {
    const valores = dados.produtos
      .flatMap((p) => p.serie.map((s) => s?.preco ?? null))
      .filter((v): v is number => v !== null && v > 0);
    if (valores.length === 0 || dados.meses.length === 0) return null;

    const menor = Math.min(...valores);
    const maior = Math.max(...valores);
    const folga = (maior - menor) * 0.12 || maior * 0.1;
    const yMin = Math.max(0, menor - folga);
    const yMax = maior + folga;

    const largura = LARGURA - L - R;
    const altura = ALTURA - T - B;
    const x = (i: number) =>
      dados.meses.length === 1
        ? L + largura / 2
        : L + (i / (dados.meses.length - 1)) * largura;
    const y = (v: number) => T + altura - ((v - yMin) / (yMax - yMin || 1)) * altura;

    return { x, y, yMin, yMax };
  }, [dados]);

  if (!geo) {
    return <p className="vazio">Sem preço registrado para comparar.</p>;
  }

  const { x, y, yMin, yMax } = geo;
  const ticks = [yMin, (yMin + yMax) / 2, yMax];
  const emFoco = foco ? dados.produtos[foco.serie] : null;
  const pontoFoco = emFoco ? emFoco.serie[foco!.mes] : null;

  return (
    <figure>
      <div className="envelope-grafico">
        <svg
          className="grafico-svg"
          viewBox={`0 0 ${LARGURA} ${ALTURA}`}
          role="img"
          aria-label="Comparação de preço por unidade entre produtos"
          onPointerLeave={() => setFoco(null)}
        >
          {ticks.map((v) => (
            <g key={v}>
              <line
                x1={L}
                x2={LARGURA - R}
                y1={y(v)}
                y2={y(v)}
                stroke="var(--grid)"
                strokeWidth={1}
              />
              <text className="eixo-texto" x={L - 6} y={y(v) + 3} textAnchor="end">
                {v.toLocaleString("pt-BR", { maximumFractionDigits: 0 })}
              </text>
            </g>
          ))}

          {dados.produtos.map((p, iSerie) => {
            const cor = CORES[iSerie % CORES.length];
            // Segmentos separados por lacuna: uma única <path> ligaria março a julho
            // por cima de meses sem compra, inventando continuidade.
            const segmentos: string[] = [];
            let atual: string[] = [];
            p.serie.forEach((ponto, i) => {
              if (ponto && ponto.preco > 0) {
                atual.push(`${x(i).toFixed(1)},${y(ponto.preco).toFixed(1)}`);
              } else if (atual.length) {
                segmentos.push(atual.join(" L"));
                atual = [];
              }
            });
            if (atual.length) segmentos.push(atual.join(" L"));

            return (
              <g key={p.produto_id}>
                {segmentos.map((seg, i) => (
                  <path
                    key={i}
                    d={`M${seg}`}
                    fill="none"
                    stroke={cor}
                    strokeWidth={2}
                    strokeLinejoin="round"
                    opacity={foco === null || foco.serie === iSerie ? 1 : 0.25}
                  />
                ))}
                {p.serie.map((ponto, i) =>
                  ponto && ponto.preco > 0 ? (
                    <circle
                      key={i}
                      cx={x(i)}
                      cy={y(ponto.preco)}
                      r={foco?.serie === iSerie && foco?.mes === i ? 6 : 4}
                      fill={cor}
                      stroke="var(--surface-1)"
                      strokeWidth={2}
                      opacity={foco === null || foco.serie === iSerie ? 1 : 0.25}
                      onPointerEnter={() => setFoco({ serie: iSerie, mes: i })}
                    />
                  ) : null,
                )}
              </g>
            );
          })}

          {dados.meses.map((mes, i) =>
            i === 0 ||
            i === dados.meses.length - 1 ||
            i === Math.floor((dados.meses.length - 1) / 2) ? (
              <text
                key={mes}
                className="eixo-texto"
                x={x(i)}
                y={ALTURA - 8}
                textAnchor={
                  i === 0 ? "start" : i === dados.meses.length - 1 ? "end" : "middle"
                }
              >
                {mesLegivel(mes)}
              </text>
            ) : null,
          )}
        </svg>

        {emFoco && pontoFoco && foco && (
          <div
            className="tooltip"
            style={{
              left: `${(x(foco.mes) / LARGURA) * 100}%`,
              top: `${(y(pontoFoco.preco) / ALTURA) * 100}%`,
            }}
          >
            <div className="tt-titulo">
              {emFoco.nome} · {mesLegivel(dados.meses[foco.mes])}
            </div>
            <div className="tt-valor">
              {moeda(pontoFoco.preco)}/{emFoco.unidade?.toLowerCase() || "un"}
            </div>
            {/* Quantidade e gasto ao lado do preço: é o par que mostra "comprei menos
                e paguei mais", que o gasto total sozinho esconde. */}
            <div className="tt-titulo">
              {pontoFoco.quantidade.toLocaleString("pt-BR")}{" "}
              {emFoco.unidade?.toLowerCase() || "un"} · {moeda(pontoFoco.gasto)}
            </div>
          </div>
        )}
      </div>

      <ul className="legenda-cores">
        {dados.produtos.map((p, i) => (
          <li
            key={p.produto_id}
            onPointerEnter={() => setFoco({ serie: i, mes: 0 })}
            onPointerLeave={() => setFoco(null)}
          >
            <span
              className="marca"
              style={{ background: CORES[i % CORES.length] }}
            />
            {p.nome}
            <span className="valor">
              {p.meses_com_compra}/{dados.meses.length} meses
            </span>
          </li>
        ))}
      </ul>
      <figcaption>
        Preço por unidade de medida, não gasto total — é o único jeito de comparar
        cortes comprados em pesos diferentes.
      </figcaption>
    </figure>
  );
}
