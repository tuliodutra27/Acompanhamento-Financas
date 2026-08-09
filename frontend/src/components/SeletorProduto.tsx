/**
 * Escolhe o produto de um item: busca no catálogo ou cria um novo.
 *
 * As sugestões vêm por similaridade de texto no servidor. Elas *sugerem* e nunca
 * vinculam sozinhas: "ARROZ 5KG" e "ARROZ 1KG" são quase idênticos como texto e
 * produtos diferentes na prática — quem decide é quem fez a compra.
 */

import { useEffect, useState } from "react";
import type { Produto, Sugestao } from "../api/client";
import { api } from "../api/client";

interface Props {
  descricao: string;
  aoEscolher: (escolha: { produto_id?: number; novo_produto_nome?: string }) => void;
  aoCancelar?: () => void;
}

export function SeletorProduto({ descricao, aoEscolher, aoCancelar }: Props) {
  const [sugestoes, setSugestoes] = useState<Sugestao[]>([]);
  const [busca, setBusca] = useState("");
  const [resultados, setResultados] = useState<Produto[]>([]);

  useEffect(() => {
    void (async () => {
      try {
        setSugestoes(await api.sugestoes(descricao));
      } catch {
        setSugestoes([]);
      }
    })();
  }, [descricao]);

  useEffect(() => {
    if (busca.trim().length < 2) {
      setResultados([]);
      return;
    }
    const temporizador = setTimeout(() => {
      void (async () => {
        try {
          setResultados(await api.listarProdutos(busca.trim()));
        } catch {
          setResultados([]);
        }
      })();
    }, 250);
    return () => clearTimeout(temporizador);
  }, [busca]);

  return (
    <div
      style={{
        background: "var(--surface-2)",
        borderRadius: 8,
        padding: "0.75rem",
        marginTop: "0.5rem",
      }}
    >
      <p className="secundario" style={{ margin: "0 0 0.5rem" }}>
        Vincular <strong>{descricao}</strong> a:
      </p>

      {sugestoes.length > 0 && (
        <div style={{ marginBottom: "0.6rem" }}>
          <label>Parecidos no seu catálogo</label>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem" }}>
            {sugestoes.map((sugestao) => (
              <button
                key={sugestao.produto_id}
                onClick={() => aoEscolher({ produto_id: sugestao.produto_id })}
              >
                {sugestao.nome}
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="campo">
        <label htmlFor={`busca-${descricao}`}>Buscar outro produto</label>
        <input
          id={`busca-${descricao}`}
          value={busca}
          placeholder="ex.: arroz"
          onChange={(evento) => setBusca(evento.target.value)}
        />
      </div>

      {resultados.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem", marginBottom: "0.6rem" }}>
          {resultados.map((produto) => (
            <button key={produto.id} onClick={() => aoEscolher({ produto_id: produto.id })}>
              {produto.nome}
            </button>
          ))}
        </div>
      )}

      <div className="acoes">
        <button
          className="primario"
          onClick={() =>
            aoEscolher({
              novo_produto_nome: (busca.trim() || descricao).slice(0, 200),
            })
          }
        >
          + Criar “{busca.trim() || descricao}”
        </button>
        {aoCancelar && <button onClick={aoCancelar}>Cancelar</button>}
      </div>
    </div>
  );
}
