/** Painel: os números do topo, o ranking de gastos e o total por mês. */

import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { GraficoBarras } from "../components/GraficoBarras";
import type { LinhaRanking, Totais } from "../api/client";
import { api, mesLegivel, moeda } from "../api/client";

interface ResumoMes {
  mes: string;
  total_gasto: number;
  n_notas: number;
  n_itens: number;
}

export function Dashboard() {
  const navegar = useNavigate();
  const [totais, setTotais] = useState<Totais | null>(null);
  const [ranking, setRanking] = useState<LinhaRanking[]>([]);
  const [meses, setMeses] = useState<ResumoMes[]>([]);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        const [t, r, m] = await Promise.all([
          api.totais(),
          api.ranking(10),
          api.resumoMensal(),
        ]);
        setTotais(t);
        setRanking(r);
        setMeses(m);
      } catch {
        setErro("Não foi possível carregar os dados. O servidor está no ar?");
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

  const semDados = (totais?.n_notas ?? 0) === 0;
  const mesAtual = meses.at(-1);
  const mesAnterior = meses.at(-2);
  const variacaoMes =
    mesAtual && mesAnterior && mesAnterior.total_gasto > 0
      ? ((mesAtual.total_gasto - mesAnterior.total_gasto) / mesAnterior.total_gasto) * 100
      : null;

  return (
    <>
      <h1 style={{ fontSize: "1.25rem", margin: "0.25rem 0 1rem" }}>Painel</h1>

      {semDados ? (
        <div className="cartao">
          <h2>Comece registrando um cupom</h2>
          <p className="legenda">
            Escaneie o QR Code de uma nota de mercado. A partir da segunda compra do
            mesmo produto, o histórico de preço já começa a fazer sentido.
          </p>
          <Link className="botao primario" to="/adicionar">
            📷 Registrar a primeira nota
          </Link>
        </div>
      ) : (
        <>
          <div className="tiles">
            <div className="tile">
              <div className="rotulo">Gasto no mês</div>
              <div className="valor">{moeda(mesAtual?.total_gasto ?? 0)}</div>
              <div className="nota">
                {variacaoMes === null ? (
                  "sem mês anterior para comparar"
                ) : (
                  <>
                    <span className={variacaoMes > 0 ? "delta-sobe" : "delta-desce"}>
                      {variacaoMes > 0 ? "▲" : "▼"} {Math.abs(variacaoMes).toFixed(1)}%
                    </span>{" "}
                    vs. {mesLegivel(mesAnterior!.mes)}
                  </>
                )}
              </div>
            </div>
            <div className="tile">
              <div className="rotulo">Total acumulado</div>
              <div className="valor">{moeda(totais?.total_gasto ?? 0)}</div>
              <div className="nota">
                {totais?.n_notas} notas · {totais?.n_itens} itens
              </div>
            </div>
            <div className="tile">
              <div className="rotulo">Produtos</div>
              <div className="valor">{totais?.n_produtos ?? 0}</div>
              <div className="nota">no seu catálogo</div>
            </div>
          </div>

          {(totais?.itens_pendentes ?? 0) > 0 && (
            <div className="aviso atencao">
              <span className="icone" aria-hidden="true">
                🏷️
              </span>
              <span>
                <strong>{totais?.itens_pendentes} itens</strong> ainda não estão
                vinculados a um produto — sem isso eles não entram no histórico de
                preço.{" "}
                <Link to="/produtos">Classificar agora</Link>
              </span>
            </div>
          )}

          <section className="cartao">
            <h2>Maiores gastos por produto</h2>
            <p className="legenda">Acumulado de todo o período registrado.</p>
            <GraficoBarras
              dados={ranking.map((linha) => ({
                id: linha.produto_id,
                rotulo: linha.nome,
                valor: linha.total_gasto,
                detalhe: `${linha.n_compras} ${
                  linha.n_compras === 1 ? "compra" : "compras"
                } · média ${moeda(linha.preco_medio)}`,
              }))}
              aoClicar={(id) => navegar(`/produtos/${id}`)}
            />
          </section>

          {meses.length > 1 && (
            <section className="cartao">
              <h2>Total por mês</h2>
              <p className="legenda">Quanto foi para o mercado em cada mês.</p>
              <GraficoBarras
                dados={meses.map((mes) => ({
                  id: mes.mes,
                  rotulo: mesLegivel(mes.mes),
                  valor: mes.total_gasto,
                  detalhe: `${mes.n_notas} ${mes.n_notas === 1 ? "nota" : "notas"}`,
                }))}
              />
            </section>
          )}
        </>
      )}
    </>
  );
}
