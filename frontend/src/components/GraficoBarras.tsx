/**
 * Barras horizontais para comparar magnitude (ranking de gastos, total por mês).
 *
 * Horizontal porque os nomes dos produtos são longos — vertical obrigaria rótulo
 * inclinado. Série única, hue única: a cor aqui não identifica nada, só desenha a
 * magnitude, então não há legenda. A escala **começa em zero**: a barra codifica valor
 * pela extensão, e cortar a base mentiria sobre a proporção entre as barras.
 */

import { useState } from "react";
import { moeda } from "../api/client";

export interface BarraDado {
  id: string | number;
  rotulo: string;
  valor: number;
  detalhe?: string;
}

interface Props {
  dados: BarraDado[];
  aoClicar?: (id: string | number) => void;
}

const ALTURA_BARRA = 26;
const ESPACO = 8; // 2px seriam o mínimo; aqui há rótulo entre as barras

export function GraficoBarras({ dados, aoClicar }: Props) {
  const [foco, setFoco] = useState<string | number | null>(null);

  if (dados.length === 0) {
    return <p className="vazio">Sem dados no período.</p>;
  }

  const maior = Math.max(...dados.map((d) => d.valor)) || 1;

  return (
    <div className="envelope-grafico">
      <ul className="lista" style={{ listStyle: "none" }}>
        {dados.map((dado) => {
          const proporcao = (dado.valor / maior) * 100;
          const emFoco = foco === dado.id;
          return (
            <li
              key={dado.id}
              style={{
                display: "block",
                borderBottom: "none",
                padding: `0 0 ${ESPACO}px`,
                cursor: aoClicar ? "pointer" : "default",
              }}
              onPointerEnter={() => setFoco(dado.id)}
              onPointerLeave={() => setFoco(null)}
              onClick={() => aoClicar?.(dado.id)}
            >
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  gap: "0.75rem",
                  fontSize: "0.83rem",
                  marginBottom: "0.2rem",
                }}
              >
                <span
                  style={{
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                    fontWeight: 550,
                  }}
                >
                  {dado.rotulo}
                </span>
                <span
                  style={{
                    fontVariantNumeric: "tabular-nums",
                    fontWeight: 620,
                    whiteSpace: "nowrap",
                  }}
                >
                  {moeda(dado.valor)}
                </span>
              </div>
              <div
                style={{
                  height: ALTURA_BARRA - 12,
                  background: "var(--surface-2)",
                  borderRadius: 4,
                  overflow: "hidden",
                }}
              >
                <div
                  style={{
                    width: `${proporcao}%`,
                    height: "100%",
                    background: "var(--serie-1)",
                    // Ponta arredondada só no fim do dado; a base fica ancorada.
                    borderRadius: "0 4px 4px 0",
                    opacity: emFoco ? 1 : 0.9,
                    transition: "opacity 120ms",
                  }}
                />
              </div>
              {dado.detalhe && (
                <div
                  className="secundario"
                  style={{ marginTop: "0.15rem", fontSize: "0.75rem" }}
                >
                  {dado.detalhe}
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
