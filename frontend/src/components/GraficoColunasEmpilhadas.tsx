/**
 * Gasto por categoria, mês a mês: uma coluna empilhada por mês.
 *
 * Colunas verticais em vez de barras horizontais porque o eixo aqui é **tempo**, e
 * tempo se lê da esquerda para a direita. A altura usa uma escala compartilhada entre
 * os meses (não 100% normalizado), então dá para ver que um mês custou mais que o
 * outro — normalizar esconderia justamente isso.
 *
 * Usa as mesmas cores de categoria do gráfico de composição, de propósito: a cor de uma
 * categoria tem de ser a mesma em todas as telas, senão cada gráfico exige reaprender a
 * legenda.
 */

import { useState } from "react";
import { mesLegivel, moeda } from "../api/client";
import { mapearCores } from "../lib/coresCategoria";

export interface SerieCategoria {
  categoria: string;
  total: number;
  valores: number[];
}

interface Props {
  meses: string[];
  categorias: SerieCategoria[];
}

export function GraficoColunasEmpilhadas({ meses, categorias }: Props) {
  const [foco, setFoco] = useState<{ mes: number; categoria: string } | null>(null);

  if (meses.length === 0 || categorias.length === 0) {
    return <p className="vazio">Sem dados no período.</p>;
  }

  const cores = mapearCores(categorias.map((c) => c.categoria));
  const totaisPorMes = meses.map((_, i) =>
    categorias.reduce((soma, c) => soma + (c.valores[i] ?? 0), 0),
  );
  const maior = Math.max(...totaisPorMes) || 1;

  const emFoco = foco
    ? categorias.find((c) => c.categoria === foco.categoria)
    : undefined;

  return (
    <figure>
      <div className="envelope-grafico">
        <div className="colunas-mes" onPointerLeave={() => setFoco(null)}>
          {meses.map((mes, i) => (
            <div className="coluna" key={mes}>
              <div className="total-mes">{moeda(totaisPorMes[i])}</div>
              <div
                className="pilha"
                role="img"
                aria-label={`${mesLegivel(mes)}: ${moeda(totaisPorMes[i])}`}
              >
                {/* Ordem invertida: a primeira categoria (maior gasto) fica na base,
                    ancorada, que é de onde a leitura de empilhamento parte. */}
                {[...categorias].reverse().map((c) => {
                  const valor = c.valores[i] ?? 0;
                  if (valor <= 0) return null;
                  const alturaPct = (valor / maior) * 100;
                  const ativo =
                    foco === null ||
                    (foco.mes === i && foco.categoria === c.categoria);
                  return (
                    <span
                      key={c.categoria}
                      style={{
                        height: `${alturaPct}%`,
                        background: cores[c.categoria],
                        opacity: ativo ? 1 : 0.35,
                      }}
                      title={`${c.categoria} — ${mesLegivel(mes)}: ${moeda(valor)}`}
                      onPointerEnter={() =>
                        setFoco({ mes: i, categoria: c.categoria })
                      }
                    />
                  );
                })}
              </div>
              <div className="rotulo-mes">{mesLegivel(mes).replace(". de ", "/")}</div>
            </div>
          ))}
        </div>

        {foco && emFoco && (
          <div
            className="tooltip"
            style={{ left: "50%", top: 0, transform: "translate(-50%, -100%)" }}
          >
            <div className="tt-titulo">
              {emFoco.categoria} · {mesLegivel(meses[foco.mes])}
            </div>
            <div className="tt-valor">{moeda(emFoco.valores[foco.mes] ?? 0)}</div>
          </div>
        )}
      </div>

      <ul className="legenda-cores">
        {categorias.map((c) => (
          <li key={c.categoria}>
            <span className="marca" style={{ background: cores[c.categoria] }} />
            {c.categoria}
            <span className="valor">{moeda(c.total)}</span>
          </li>
        ))}
      </ul>
    </figure>
  );
}
