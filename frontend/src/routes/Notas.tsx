/** Histórico de notas registradas. */

import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import type { NotaResumo, StatusNota } from "../api/client";
import { api, moeda } from "../api/client";
import { anoMesLegivel } from "../lib/chaveNfce";

const ETIQUETA_STATUS: Record<StatusNota, string> = {
  pendente: "pendente",
  ok: "lida automaticamente",
  falhou_parse: "precisa preencher",
  manual: "preenchida à mão",
};

export function Notas() {
  const [notas, setNotas] = useState<NotaResumo[]>([]);
  const [filtro, setFiltro] = useState<StatusNota | "">("");
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        setNotas(await api.listarNotas(filtro ? { status: filtro } : {}));
      } catch {
        setErro("Não foi possível carregar as notas.");
      }
    })();
  }, [filtro]);

  return (
    <>
      <h1 style={{ fontSize: "1.25rem", margin: "0.25rem 0 1rem" }}>Notas</h1>

      {erro && (
        <div className="aviso erro">
          <span className="icone" aria-hidden="true">
            ⚠️
          </span>
          <span>{erro}</span>
        </div>
      )}

      {/* Filtros numa linha, acima da lista. */}
      <div className="campo">
        <label htmlFor="filtro">Situação</label>
        <select
          id="filtro"
          value={filtro}
          onChange={(evento) => setFiltro(evento.target.value as StatusNota | "")}
        >
          <option value="">Todas</option>
          <option value="falhou_parse">Precisam preencher</option>
          <option value="ok">Lidas automaticamente</option>
          <option value="manual">Preenchidas à mão</option>
        </select>
      </div>

      <section className="cartao">
        {notas.length === 0 ? (
          <p className="vazio">
            Nenhuma nota aqui.{" "}
            <Link to="/adicionar">Registrar uma agora</Link>
          </p>
        ) : (
          <ul className="lista">
            {notas.map((nota) => (
              <li key={nota.id}>
                <div className="cresce">
                  <div className="titulo">
                    <Link to={`/notas/${nota.id}`}>
                      {nota.estabelecimento_nome ?? `Nota ${nota.uf}`}
                    </Link>
                  </div>
                  <div className="sub">
                    {nota.emitida_em
                      ? new Date(nota.emitida_em).toLocaleDateString("pt-BR")
                      : anoMesLegivel(nota.ano_mes_chave)}{" "}
                    · {nota.n_itens} {nota.n_itens === 1 ? "item" : "itens"} ·{" "}
                    <span className="etiqueta">{ETIQUETA_STATUS[nota.status]}</span>
                  </div>
                </div>
                <div className="numero">
                  {nota.valor_total ? moeda(nota.valor_total) : "—"}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}
