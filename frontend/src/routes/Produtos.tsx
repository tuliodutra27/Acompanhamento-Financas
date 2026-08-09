/** Catálogo de produtos + fila de itens aguardando classificação. */

import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { SeletorProduto } from "../components/SeletorProduto";
import type { ItemPendente, Produto } from "../api/client";
import { api, moeda } from "../api/client";

export function Produtos() {
  const [produtos, setProdutos] = useState<Produto[]>([]);
  const [pendentes, setPendentes] = useState<ItemPendente[]>([]);
  const [busca, setBusca] = useState("");
  const [classificando, setClassificando] = useState<number | null>(null);
  const [mesclarDe, setMesclarDe] = useState<number | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  const recarregar = useCallback(async () => {
    try {
      const [listaProdutos, listaPendentes] = await Promise.all([
        api.listarProdutos(busca.trim() || undefined),
        api.itensPendentes(),
      ]);
      setProdutos(listaProdutos);
      setPendentes(listaPendentes);
    } catch {
      setErro("Não foi possível carregar os produtos.");
    }
  }, [busca]);

  useEffect(() => {
    const temporizador = setTimeout(() => void recarregar(), 200);
    return () => clearTimeout(temporizador);
  }, [recarregar]);

  const classificar = async (
    pendente: ItemPendente,
    escolha: { produto_id?: number; novo_produto_nome?: string },
  ) => {
    try {
      await api.vincularItem(pendente.nota_id, pendente.item_id, escolha);
      setClassificando(null);
      await recarregar();
    } catch {
      setErro("Não foi possível vincular o item.");
    }
  };

  const mesclar = async (destinoId: number) => {
    if (mesclarDe === null || mesclarDe === destinoId) return;
    try {
      await api.mergeProdutos(mesclarDe, destinoId);
      setMesclarDe(null);
      await recarregar();
    } catch {
      setErro("Não foi possível juntar os produtos.");
    }
  };

  return (
    <>
      <h1 style={{ fontSize: "1.25rem", margin: "0.25rem 0 1rem" }}>Produtos</h1>

      {erro && (
        <div className="aviso erro">
          <span className="icone" aria-hidden="true">
            ⚠️
          </span>
          <span>{erro}</span>
        </div>
      )}

      {pendentes.length > 0 && (
        <section className="cartao">
          <h2>Aguardando classificação ({pendentes.length})</h2>
          <p className="legenda">
            Itens sem produto não entram no histórico de preço. Classificar um item
            ensina o app: a próxima nota com a mesma descrição já vem vinculada.
          </p>
          <ul className="lista">
            {pendentes.map((pendente) => (
              <li key={pendente.item_id} style={{ display: "block" }}>
                <div style={{ display: "flex", gap: "0.75rem", alignItems: "center" }}>
                  <div className="cresce">
                    <div className="titulo">{pendente.descricao_origem}</div>
                    <div className="sub">
                      {moeda(pendente.valor_unitario)}
                      {pendente.sugestoes.length > 0 &&
                        ` · sugestão: ${pendente.sugestoes[0].nome}`}
                    </div>
                  </div>
                  <button
                    className="discreto"
                    onClick={() =>
                      setClassificando(
                        classificando === pendente.item_id ? null : pendente.item_id,
                      )
                    }
                  >
                    Classificar
                  </button>
                </div>
                {classificando === pendente.item_id && (
                  <SeletorProduto
                    descricao={pendente.descricao_origem}
                    aoEscolher={(escolha) => void classificar(pendente, escolha)}
                    aoCancelar={() => setClassificando(null)}
                  />
                )}
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="cartao">
        <h2>Seu catálogo ({produtos.length})</h2>
        <div className="campo">
          <input
            placeholder="Buscar produto"
            value={busca}
            onChange={(evento) => setBusca(evento.target.value)}
          />
        </div>

        {mesclarDe !== null && (
          <div className="aviso atencao">
            <span className="icone" aria-hidden="true">
              🔀
            </span>
            <span>
              Escolha o produto que deve <strong>absorver</strong> “
              {produtos.find((p) => p.id === mesclarDe)?.nome}”.{" "}
              <button className="discreto" onClick={() => setMesclarDe(null)}>
                cancelar
              </button>
            </span>
          </div>
        )}

        {produtos.length === 0 ? (
          <p className="vazio">
            Nenhum produto ainda. Eles nascem ao classificar os itens das notas.
          </p>
        ) : (
          <ul className="lista">
            {produtos.map((produto) => (
              <li key={produto.id}>
                <div className="cresce">
                  <div className="titulo">
                    <Link to={`/produtos/${produto.id}`}>{produto.nome}</Link>
                  </div>
                  <div className="sub">
                    {produto.n_compras}{" "}
                    {produto.n_compras === 1 ? "compra" : "compras"} · média{" "}
                    {moeda(produto.preco_medio)}
                  </div>
                </div>
                <div className="numero">{moeda(produto.total_gasto)}</div>
                {mesclarDe === null ? (
                  <button className="discreto" onClick={() => setMesclarDe(produto.id)}>
                    juntar
                  </button>
                ) : (
                  mesclarDe !== produto.id && (
                    <button className="discreto" onClick={() => void mesclar(produto.id)}>
                      absorver
                    </button>
                  )
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}
