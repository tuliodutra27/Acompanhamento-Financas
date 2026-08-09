/**
 * Evolução do preço de um produto mês a mês.
 *
 * Forma: linha (tendência no tempo), série única — por isso não há legenda: o título
 * do cartão nomeia o que está sendo mostrado. A faixa clara atrás da linha é o
 * intervalo mínimo–máximo pago naquele mês, no mesmo hue em passo claro; ela é
 * contexto, não uma segunda série.
 *
 * A escala do eixo Y não começa em zero de propósito: aqui o que interessa é a
 * *variação* do preço, e ancorar em zero achataria a linha até ela não dizer nada.
 * (Isso vale para linha; barras, que codificam magnitude pela área, começam em zero —
 * ver GraficoBarras.)
 */

import { useMemo, useState } from "react";
import type { PontoSerie } from "../api/client";
import { moeda } from "../api/client";

interface Props {
  serie: PontoSerie[];
  rotuloMes: (iso: string) => string;
}

const L = 46; // margem esquerda (rótulos do eixo Y)
const R = 16;
const T = 18;
const B = 26;
const LARGURA = 520;
const ALTURA = 220;

export function GraficoSerie({ serie, rotuloMes }: Props) {
  const [foco, setFoco] = useState<number | null>(null);

  const geometria = useMemo(() => {
    if (serie.length === 0) return null;

    const minimos = serie.map((p) => p.preco_min || p.preco_medio);
    const maximos = serie.map((p) => p.preco_max || p.preco_medio);
    const menor = Math.min(...minimos);
    const maior = Math.max(...maximos);
    // Folga de 12% para a linha não encostar nas bordas.
    const folga = (maior - menor) * 0.12 || Math.max(maior * 0.1, 1);
    const yMin = Math.max(0, menor - folga);
    const yMax = maior + folga;

    const larguraPlot = LARGURA - L - R;
    const alturaPlot = ALTURA - T - B;

    const x = (i: number) =>
      serie.length === 1
        ? L + larguraPlot / 2
        : L + (i / (serie.length - 1)) * larguraPlot;
    const y = (valor: number) =>
      T + alturaPlot - ((valor - yMin) / (yMax - yMin || 1)) * alturaPlot;

    const linha = serie
      .map((p, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(p.preco_medio).toFixed(1)}`)
      .join(" ");

    // Faixa min–max: sobe pelos máximos e volta pelos mínimos.
    const topo = serie.map((p, i) => `${x(i).toFixed(1)},${y(p.preco_max || p.preco_medio).toFixed(1)}`);
    const base = [...serie]
      .map((p, i) => ({ p, i }))
      .reverse()
      .map(({ p, i }) => `${x(i).toFixed(1)},${y(p.preco_min || p.preco_medio).toFixed(1)}`);
    const faixa = `M${topo.join(" L")} L${base.join(" L")} Z`;

    // Três marcas no eixo Y bastam: mais que isso vira ruído num gráfico pequeno.
    const ticks = [yMin, (yMin + yMax) / 2, yMax];

    return { x, y, linha, faixa, ticks, yMin, yMax, alturaPlot };
  }, [serie]);

  if (!geometria || serie.length === 0) {
    return (
      <p className="vazio">
        Ainda não há compras deste produto com data para montar o histórico.
      </p>
    );
  }

  const { x, y, linha, faixa, ticks } = geometria;
  const temFaixa = serie.some((p) => (p.preco_max || 0) > (p.preco_min || 0));
  const pontoFoco = foco !== null ? serie[foco] : null;

  return (
    <div className="envelope-grafico">
      <svg
        className="grafico-svg"
        viewBox={`0 0 ${LARGURA} ${ALTURA}`}
        role="img"
        aria-label="Preço médio pago por mês"
        onPointerLeave={() => setFoco(null)}
      >
        {/* Grade recessiva: referência, não protagonista. */}
        {ticks.map((valor) => (
          <g key={valor}>
            <line
              x1={L}
              x2={LARGURA - R}
              y1={y(valor)}
              y2={y(valor)}
              stroke="var(--grid)"
              strokeWidth={1}
            />
            <text className="eixo-texto" x={L - 6} y={y(valor) + 3} textAnchor="end">
              {valor.toLocaleString("pt-BR", {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2,
              })}
            </text>
          </g>
        ))}

        {temFaixa && <path d={faixa} fill="var(--serie-1-faixa)" opacity={0.35} />}

        <path d={linha} fill="none" stroke="var(--serie-1)" strokeWidth={2} strokeLinejoin="round" />

        {serie.map((ponto, i) => (
          <circle
            key={ponto.mes}
            cx={x(i)}
            cy={y(ponto.preco_medio)}
            r={foco === i ? 6 : 4}
            fill="var(--serie-1)"
            // Anel na cor da superfície separa o marcador da faixa por baixo.
            stroke="var(--surface-1)"
            strokeWidth={2}
          />
        ))}

        {/* Rótulos diretos só nas pontas — um número em cada ponto viraria poluição. */}
        <text
          className="rotulo-direto"
          x={x(0)}
          y={y(serie[0].preco_medio) - 10}
          textAnchor="start"
        >
          {moeda(serie[0].preco_medio)}
        </text>
        {serie.length > 1 && (
          <text
            className="rotulo-direto"
            x={x(serie.length - 1)}
            y={y(serie[serie.length - 1].preco_medio) - 10}
            textAnchor="end"
          >
            {moeda(serie[serie.length - 1].preco_medio)}
          </text>
        )}

        {/* Eixo X: primeiro, meio e último mês (evita rótulos sobrepostos). */}
        {[0, Math.floor((serie.length - 1) / 2), serie.length - 1]
          .filter((i, pos, todos) => todos.indexOf(i) === pos && i >= 0)
          .map((i) => (
            <text
              key={`mes-${i}`}
              className="eixo-texto"
              x={x(i)}
              y={ALTURA - 8}
              textAnchor={i === 0 ? "start" : i === serie.length - 1 ? "end" : "middle"}
            >
              {rotuloMes(serie[i].mes)}
            </text>
          ))}

        {/* Crosshair do ponto sob o cursor. */}
        {foco !== null && (
          <line
            x1={x(foco)}
            x2={x(foco)}
            y1={T}
            y2={ALTURA - B}
            stroke="var(--axis)"
            strokeWidth={1}
            strokeDasharray="3 3"
          />
        )}

        {/* Faixas de captura maiores que os marcadores, para acertar no toque. */}
        {serie.map((ponto, i) => {
          const largura = (LARGURA - L - R) / serie.length;
          return (
            <rect
              key={`alvo-${ponto.mes}`}
              x={L + i * largura}
              y={T}
              width={largura}
              height={ALTURA - T - B}
              fill="transparent"
              onPointerEnter={() => setFoco(i)}
              onPointerDown={() => setFoco(i)}
            />
          );
        })}
      </svg>

      {pontoFoco && foco !== null && (
        <div
          className="tooltip"
          style={{
            left: `${(x(foco) / LARGURA) * 100}%`,
            top: `${(y(pontoFoco.preco_medio) / ALTURA) * 100}%`,
          }}
        >
          <div className="tt-titulo">{rotuloMes(pontoFoco.mes)}</div>
          <div className="tt-valor">{moeda(pontoFoco.preco_medio)}</div>
          {pontoFoco.preco_max > pontoFoco.preco_min && (
            <div className="tt-titulo">
              de {moeda(pontoFoco.preco_min)} a {moeda(pontoFoco.preco_max)}
            </div>
          )}
          <div className="tt-titulo">
            {pontoFoco.n_compras}{" "}
            {pontoFoco.n_compras === 1 ? "compra" : "compras"}
          </div>
        </div>
      )}
    </div>
  );
}
