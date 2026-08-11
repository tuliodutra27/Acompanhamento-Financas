/**
 * Variação mensal do índice de preços da cesta, em barras divergentes.
 *
 * Forma escolhida porque o dado tem **polaridade**: acima ou abaixo de zero é a
 * informação principal, não a magnitude relativa. Daí a linha de base no zero e duas
 * cores opostas — e não uma escala sequencial, que trataria −9% e +9% como "mais" e
 * "menos" da mesma coisa.
 *
 * As cores seguem a convenção de custo, não de humor: alta de preço é ruim para quem
 * compra, então usa o polo de alerta; queda usa o polo frio.
 */

import { useState } from "react";
import { mesLegivel } from "../api/client";

export interface PontoIndice {
  mes_base: string;
  mes: string;
  variacao_percentual: number;
  cobertura: number;
  confianca: string;
  produtos_comparados: number;
}

interface Props {
  serie: PontoIndice[];
}

export function GraficoIndice({ serie }: Props) {
  const [foco, setFoco] = useState<number | null>(null);

  if (serie.length === 0) {
    return (
      <p className="vazio">
        O índice precisa de dois meses com produtos em comum para existir.
      </p>
    );
  }

  const maiorAbs = Math.max(...serie.map((p) => Math.abs(p.variacao_percentual)), 1);

  return (
    <figure>
      <div className="indice-barras">
        {serie.map((p, i) => {
          const largura = (Math.abs(p.variacao_percentual) / maiorAbs) * 50;
          const sobe = p.variacao_percentual >= 0;
          const ativo = foco === null || foco === i;
          return (
            <div
              className="indice-linha"
              key={p.mes}
              onPointerEnter={() => setFoco(i)}
              onPointerLeave={() => setFoco(null)}
            >
              <span className="indice-rotulo">{mesLegivel(p.mes)}</span>
              <div className="indice-trilha">
                <span className="indice-zero" />
                <span
                  className="indice-barra"
                  style={{
                    left: sobe ? "50%" : `${50 - largura}%`,
                    width: `${largura}%`,
                    background: sobe ? "var(--critico)" : "var(--serie-1)",
                    opacity: ativo ? 1 : 0.4,
                  }}
                />
              </div>
              <span
                className={`indice-valor ${sobe ? "delta-sobe" : "delta-desce"}`}
              >
                {sobe ? "+" : ""}
                {p.variacao_percentual.toFixed(2)}%
              </span>
              {/* Confiança fica no gráfico, não numa nota de pé de página: um número
                  com cobertura baixa não deve parecer tão firme quanto os outros. */}
              {p.confianca !== "alta" && (
                <span
                  className="etiqueta"
                  title={`Cobertura de ${p.cobertura}% do gasto do mês-base, ${p.produtos_comparados} produtos comparados`}
                >
                  {p.confianca === "baixa" ? "pouco confiável" : `${p.cobertura}%`}
                </span>
              )}
            </div>
          );
        })}
      </div>
      <figcaption>
        Variação de preço da sua cesta de um mês para o outro. Isola o preço da mudança
        do que foi comprado: pega as quantidades do mês anterior e as reavalia aos
        preços do mês seguinte.
      </figcaption>
    </figure>
  );
}
