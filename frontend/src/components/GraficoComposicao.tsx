/**
 * Composição do gasto por categoria: uma barra horizontal empilhada.
 *
 * Forma escolhida por ser parte-do-todo. Não é pizza de propósito: comparar ângulos é
 * mais difícil que comparar comprimentos, e com 8 fatias a pizza fica ilegível. A barra
 * também acomoda nomes longos ("Frios e laticínios") na legenda, sem rótulo inclinado.
 *
 * A cor aqui **identifica** a categoria, então a legenda é obrigatória — e cada verbete
 * traz nome e valor em texto, para a identidade nunca depender só da cor.
 */

import { useState } from "react";
import { moeda } from "../api/client";
import { mapearCores } from "../lib/coresCategoria";

export interface FatiaCategoria {
  categoria: string;
  total_gasto: number;
  fatia: number;
  n_itens?: number;
}

interface Props {
  dados: FatiaCategoria[];
  aoClicar?: (categoria: string) => void;
}

export function GraficoComposicao({ dados, aoClicar }: Props) {
  const [foco, setFoco] = useState<string | null>(null);

  if (dados.length === 0) {
    return <p className="vazio">Sem gastos classificados no período.</p>;
  }

  const cores = mapearCores(dados.map((d) => d.categoria));
  const total = dados.reduce((soma, d) => soma + d.total_gasto, 0);

  return (
    <figure>
      <div
        className="barra-composicao"
        role="img"
        aria-label={`Composição do gasto: ${dados
          .map((d) => `${d.categoria} ${d.fatia}%`)
          .join(", ")}`}
        onPointerLeave={() => setFoco(null)}
      >
        {dados.map((d) => (
          <span
            key={d.categoria}
            style={{
              // Largura pela fatia, com um piso para a categoria minúscula não
              // desaparecer por completo da barra.
              width: `${Math.max(d.fatia, 0.8)}%`,
              background: cores[d.categoria],
              opacity: foco === null || foco === d.categoria ? 1 : 0.35,
              cursor: aoClicar ? "pointer" : "default",
            }}
            title={`${d.categoria}: ${moeda(d.total_gasto)} (${d.fatia}%)`}
            onPointerEnter={() => setFoco(d.categoria)}
            onClick={() => aoClicar?.(d.categoria)}
          />
        ))}
      </div>

      <ul className="legenda-cores">
        {dados.map((d) => (
          <li
            key={d.categoria}
            onPointerEnter={() => setFoco(d.categoria)}
            onPointerLeave={() => setFoco(null)}
            style={{
              opacity: foco === null || foco === d.categoria ? 1 : 0.5,
              cursor: aoClicar ? "pointer" : "default",
            }}
            onClick={() => aoClicar?.(d.categoria)}
          >
            <span className="marca" style={{ background: cores[d.categoria] }} />
            {d.categoria}
            <span className="valor">
              {moeda(d.total_gasto)} · {d.fatia}%
            </span>
          </li>
        ))}
      </ul>

      <figcaption>Total classificado: {moeda(total)}</figcaption>
    </figure>
  );
}
