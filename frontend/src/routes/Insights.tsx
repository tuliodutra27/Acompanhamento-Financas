/**
 * Insights de preço: índice da cesta, alertas, recorrência e revisão de agrupamento.
 *
 * A ordem das seções é deliberada — do mais confiável para o que exige julgamento:
 *
 * 1. **Índice da cesta**: o número mais sólido, com a confiança à vista.
 * 2. **O que puxou o índice**: a explicação do número acima, não uma repetição dele.
 * 3. **Alertas**: comparação com o histórico anterior a cada compra.
 * 4. **Recorrência**: onde o preço pesa (recorrentes) e o que explica picos (eventuais).
 * 5. **Revisão de agrupamento**: os grupos que podem estar juntando produtos distintos.
 *    Fica no fim de propósito, mas fica — esconder isso faria as seções acima
 *    parecerem mais confiáveis do que são.
 */

import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { GraficoIndice } from "../components/GraficoIndice";
import { api, mesLegivel, moeda } from "../api/client";
import type {
  AlertaPreco,
  GrupoSuspeito,
  IndiceCesta,
  Recorrencia,
} from "../api/client";

export function Insights() {
  const [indice, setIndice] = useState<IndiceCesta[]>([]);
  const [alertas, setAlertas] = useState<AlertaPreco[]>([]);
  const [recorrencia, setRecorrencia] = useState<Recorrencia | null>(null);
  const [suspeitos, setSuspeitos] = useState<GrupoSuspeito[]>([]);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState<string | null>(null);
  const [verTodosAlertas, setVerTodosAlertas] = useState(false);

  useEffect(() => {
    void (async () => {
      try {
        const [i, a, r, s] = await Promise.all([
          api.indiceCesta(),
          api.alertasPreco(30),
          api.recorrencia(),
          api.gruposSuspeitos(),
        ]);
        setIndice(i);
        setAlertas(a);
        setRecorrencia(r);
        setSuspeitos(s);
      } catch {
        setErro("Não foi possível carregar os insights.");
      } finally {
        setCarregando(false);
      }
    })();
  }, []);

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

  const confiaveis = indice.filter((p) => p.confianca !== "baixa");
  // Composto só com os meses de confiança aceitável: encadear um mês de dados
  // incompletos no acumulado contaminaria todos os seguintes.
  const composto =
    confiaveis.length > 0
      ? (confiaveis.reduce(
          (acc, p) => acc * (1 + p.variacao_percentual / 100),
          1,
        ) -
          1) *
        100
      : null;

  const alertasVisiveis = verTodosAlertas ? alertas : alertas.slice(0, 8);

  // Produtos que aparecem acima do usual várias vezes: um alerta isolado pode ser
  // acaso, repetição é padrão.
  const repetidos = Object.entries(
    alertas.reduce<Record<string, number>>((acc, a) => {
      acc[a.nome] = (acc[a.nome] ?? 0) + 1;
      return acc;
    }, {}),
  )
    .filter(([, n]) => n >= 3)
    .sort((a, b) => b[1] - a[1]);

  return (
    <>
      <h1 style={{ fontSize: "1.25rem", margin: "0.25rem 0 1rem" }}>Insights</h1>

      {composto !== null && (
        <div className="tiles">
          <div className="tile">
            <div className="rotulo">Inflação da sua cesta</div>
            <div className="valor">
              <span className={composto >= 0 ? "delta-sobe" : "delta-desce"}>
                {composto >= 0 ? "+" : ""}
                {composto.toFixed(1)}%
              </span>
            </div>
            <div className="nota">
              acumulado em {confiaveis.length}{" "}
              {confiaveis.length === 1 ? "mês" : "meses"} de dados confiáveis
            </div>
          </div>
          {recorrencia && (
            <div className="tile">
              <div className="rotulo">Compra recorrente</div>
              <div className="valor">{moeda(recorrencia.gasto_recorrente)}</div>
              <div className="nota">
                {recorrencia.recorrentes.length} produtos em todos os{" "}
                {recorrencia.total_meses} meses
              </div>
            </div>
          )}
        </div>
      )}

      <section className="cartao">
        <h2>Índice de preços da sua cesta</h2>
        <p className="legenda">
          Não é o total gasto — esse mistura preço com mudança do que você comprou. Aqui
          o mesmo carrinho é reprecificado mês a mês.
        </p>
        <GraficoIndice serie={indice} />
      </section>

      {indice.length > 0 && (
        <section className="cartao">
          <h2>O que puxou o índice</h2>
          <p className="legenda">
            Contribuição de cada produto, em pontos percentuais do índice do mês. É o
            que transforma o número numa explicação.
          </p>
          {[...indice].reverse().map((p) => (
            <div key={p.mes} style={{ marginBottom: "1rem" }}>
              <div
                style={{
                  fontSize: "0.85rem",
                  fontWeight: 620,
                  marginBottom: "0.35rem",
                }}
              >
                {mesLegivel(p.mes_base)} → {mesLegivel(p.mes)}{" "}
                <span className={p.variacao_percentual >= 0 ? "delta-sobe" : "delta-desce"}>
                  {p.variacao_percentual >= 0 ? "+" : ""}
                  {p.variacao_percentual.toFixed(2)}%
                </span>
              </div>
              <ul className="lista">
                {[...p.maiores_altas.slice(0, 3), ...p.maiores_quedas.slice(0, 3)].map(
                  (c) => (
                    <li key={`${p.mes}-${c.produto_id}`}>
                      <div className="cresce">
                        <div className="titulo">
                          <Link to={`/produtos/${c.produto_id}`}>{c.nome}</Link>
                        </div>
                        <div className="sub">
                          {moeda(c.preco_base)} → {moeda(c.preco_novo)}
                        </div>
                      </div>
                      <div
                        className={`numero ${
                          c.pontos_percentuais >= 0 ? "delta-sobe" : "delta-desce"
                        }`}
                      >
                        {c.pontos_percentuais >= 0 ? "+" : ""}
                        {c.pontos_percentuais.toFixed(2)} p.p.
                      </div>
                    </li>
                  ),
                )}
              </ul>
            </div>
          ))}
        </section>
      )}

      {repetidos.length > 0 && (
        <section className="cartao">
          <h2>Produtos em que você paga acima do usual com frequência</h2>
          <p className="legenda">
            Um alerta isolado pode ser acaso; repetição é padrão. Estes apareceram três
            vezes ou mais.
          </p>
          <ul className="lista">
            {repetidos.map(([nome, n]) => (
              <li key={nome}>
                <div className="cresce">
                  <div className="titulo">{nome}</div>
                </div>
                <div className="numero">{n}×</div>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="cartao">
        <h2>Compras acima do preço habitual</h2>
        <p className="legenda">
          Comparado com a mediana das compras <strong>anteriores</strong> àquela data —
          a pergunta é "naquele dia, estava acima do que eu vinha pagando?".
        </p>
        {alertas.length === 0 ? (
          <p className="vazio">Nenhuma compra 30% acima do habitual.</p>
        ) : (
          <>
            <ul className="lista">
              {alertasVisiveis.map((a) => (
                <li key={a.item_id}>
                  <div className="cresce">
                    <div className="titulo">
                      <Link to={`/produtos/${a.produto_id}`}>{a.nome}</Link>
                    </div>
                    <div className="sub">
                      {a.data} · pagou {moeda(a.preco_pago)}, vinha pagando{" "}
                      {moeda(a.preco_usual)} ({a.compras_anteriores} compras antes)
                    </div>
                  </div>
                  <div className="numero delta-sobe">+{a.acima_percentual}%</div>
                </li>
              ))}
            </ul>
            {alertas.length > 8 && (
              <div className="acoes">
                <button
                  className="discreto"
                  onClick={() => setVerTodosAlertas((v) => !v)}
                >
                  {verTodosAlertas
                    ? "Mostrar menos"
                    : `Ver todos os ${alertas.length}`}
                </button>
              </div>
            )}
          </>
        )}
      </section>

      {recorrencia && (
        <section className="cartao">
          <h2>Recorrente x eventual</h2>
          <p className="legenda">
            Nos recorrentes é onde a variação de preço pesa no orçamento. Os eventuais
            explicam picos de gasto que não são inflação.
          </p>
          <div className="tiles" style={{ marginBottom: "0.8rem" }}>
            <div className="tile">
              <div className="rotulo">Recorrentes</div>
              <div className="valor" style={{ fontSize: "1.2rem" }}>
                {moeda(recorrencia.gasto_recorrente)}
              </div>
              <div className="nota">{recorrencia.recorrentes.length} produtos</div>
            </div>
            <div className="tile">
              <div className="rotulo">Eventuais</div>
              <div className="valor" style={{ fontSize: "1.2rem" }}>
                {moeda(recorrencia.gasto_eventual)}
              </div>
              <div className="nota">compra pontual</div>
            </div>
          </div>

          <h3 style={{ fontSize: "0.85rem", margin: "0.5rem 0 0.3rem" }}>
            Comprados em todos os {recorrencia.total_meses} meses
          </h3>
          <ul className="lista">
            {recorrencia.recorrentes.map((r) => (
              <li key={r.produto_id}>
                <div className="cresce">
                  <div className="titulo">
                    <Link to={`/produtos/${r.produto_id}`}>{r.nome}</Link>
                  </div>
                  <div className="sub">
                    {r.compras} compras · {r.categoria}
                  </div>
                </div>
                <div className="numero">{moeda(r.gasto)}</div>
              </li>
            ))}
          </ul>

          <h3 style={{ fontSize: "0.85rem", margin: "1rem 0 0.3rem" }}>
            Maiores compras eventuais
          </h3>
          <ul className="lista">
            {recorrencia.eventuais.slice(0, 6).map((r) => (
              <li key={r.produto_id}>
                <div className="cresce">
                  <div className="titulo">
                    <Link to={`/produtos/${r.produto_id}`}>{r.nome}</Link>
                  </div>
                  <div className="sub">
                    {r.meses} de {recorrencia.total_meses} meses
                  </div>
                </div>
                <div className="numero">{moeda(r.gasto)}</div>
              </li>
            ))}
          </ul>
        </section>
      )}

      {suspeitos.length > 0 && (
        <section className="cartao">
          <h2>Revisar agrupamento ({suspeitos.length})</h2>
          <p className="legenda">
            Produtos que podem estar juntando coisas diferentes. Isso importa porque um
            agrupamento errado vira “variação de preço” que não existe — e contamina o
            índice acima.
          </p>
          <ul className="lista">
            {suspeitos.map((g) => (
              <li key={g.produto_id}>
                <div className="cresce">
                  <div className="titulo">
                    <Link to={`/produtos/${g.produto_id}`}>{g.nome}</Link>{" "}
                    {g.gravidade === "alta" && (
                      <span className="etiqueta" style={{ borderColor: "var(--critico)" }}>
                        provável erro
                      </span>
                    )}
                  </div>
                  <div className="sub">
                    {moeda(g.menor_preco)} a {moeda(g.maior_preco)} ·{" "}
                    {g.motivos.join("; ")}
                  </div>
                </div>
                <div className="numero secundario">{g.n_descricoes} descrições</div>
              </li>
            ))}
          </ul>
          <p className="secundario" style={{ fontSize: "0.75rem", marginTop: "0.6rem" }}>
            “Unidades misturadas” quase sempre é erro: venda por peso e por unidade não
            compartilham escala de preço. “Preço varia N×” pode ser real — hortifruti
            oscila muito.
          </p>
        </section>
      )}
    </>
  );
}
