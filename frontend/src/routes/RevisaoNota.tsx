/**
 * Revisão da nota: confere/preenche os itens e vincula cada um a um produto.
 *
 * As duas situações que essa tela precisa atender bem:
 *
 * - O parse automático funcionou: os itens já estão lá, falta só vincular a produtos.
 * - O parse não passou: é aqui que o usuário digita os itens. Esse caminho tem que ser
 *   rápido, porque na prática é o mais comum — a consulta automática só funciona
 *   escaneando o QR Code, e nem todo estado responde bem a ela.
 */

import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { SeletorProduto } from "../components/SeletorProduto";
import type { NotaDetalhe } from "../api/client";
import { FalhaApi, api, moeda } from "../api/client";
import { anoMesLegivel, formatarChave } from "../lib/chaveNfce";

const EXPLICACAO_FALHA: Record<string, string> = {
  sem_url_qrcode:
    "A chave foi digitada, e a consulta por chave no portal da SEFAZ é protegida por reCAPTCHA. Preencha os itens abaixo — dá para abrir a nota no portal num toque e ir copiando.",
  captcha:
    "O portal da SEFAZ respondeu com uma verificação anti-robô. Isso barra o servidor, não você: abra a nota no portal e preencha os itens abaixo.",
  bloqueio:
    "O portal da SEFAZ recusou a consulta (bloqueio por IP ou indisponibilidade). Você pode tentar de novo mais tarde ou preencher à mão.",
  layout_mudou:
    "A página da nota veio num formato que o app ainda não sabe ler. Preencha à mão — e vale revisar o parser depois.",
  timeout: "O portal da SEFAZ não respondeu no tempo esperado. Tente de novo ou preencha à mão.",
  uf_nao_suportada: "Ainda não há consulta automática para o estado desta nota.",
  erro_inesperado: "Algo inesperado aconteceu na consulta automática. Preencha à mão.",
};

interface FormularioItem {
  descricao_origem: string;
  quantidade: string;
  unidade: string;
  valor_unitario: string;
}

const ITEM_VAZIO: FormularioItem = {
  descricao_origem: "",
  quantidade: "1",
  unidade: "UN",
  valor_unitario: "",
};

export function RevisaoNota() {
  const { id } = useParams<{ id: string }>();
  const notaId = Number(id);
  const [nota, setNota] = useState<NotaDetalhe | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [vinculando, setVinculando] = useState<number | null>(null);
  const [novoItem, setNovoItem] = useState<FormularioItem>(ITEM_VAZIO);
  const [salvando, setSalvando] = useState(false);

  const recarregar = useCallback(async () => {
    try {
      setNota(await api.obterNota(notaId));
    } catch {
      setErro("Não foi possível carregar a nota.");
    }
  }, [notaId]);

  useEffect(() => {
    void recarregar();
  }, [recarregar]);

  const adicionarItem = async () => {
    if (!novoItem.descricao_origem.trim() || !novoItem.valor_unitario) return;
    setSalvando(true);
    setErro(null);
    try {
      await api.adicionarItem(notaId, {
        descricao_origem: novoItem.descricao_origem.trim(),
        quantidade: novoItem.quantidade.replace(",", ".") || "1",
        unidade: novoItem.unidade || null,
        valor_unitario: novoItem.valor_unitario.replace(",", "."),
      });
      setNovoItem(ITEM_VAZIO);
      await recarregar();
    } catch (causa) {
      setErro(
        causa instanceof FalhaApi ? causa.erro.mensagem : "Não foi possível salvar o item.",
      );
    } finally {
      setSalvando(false);
    }
  };

  const vincular = async (
    itemId: number,
    escolha: { produto_id?: number; novo_produto_nome?: string },
  ) => {
    try {
      await api.vincularItem(notaId, itemId, escolha);
      setVinculando(null);
      await recarregar();
    } catch (causa) {
      setErro(
        causa instanceof FalhaApi ? causa.erro.mensagem : "Não foi possível vincular o item.",
      );
    }
  };

  const remover = async (itemId: number) => {
    try {
      await api.removerItem(notaId, itemId);
      await recarregar();
    } catch {
      setErro("Não foi possível remover o item.");
    }
  };

  if (!nota) {
    return erro ? (
      <div className="aviso erro">
        <span className="icone" aria-hidden="true">
          ⚠️
        </span>
        <span>{erro}</span>
      </div>
    ) : (
      <p className="vazio">Carregando…</p>
    );
  }

  const parseFalhou = nota.status === "falhou_parse";
  const pendentes = nota.itens.filter((item) => item.produto_id === null).length;

  return (
    <>
      <p style={{ margin: "0.25rem 0 0.5rem" }}>
        <Link to="/notas">← Notas</Link>
      </p>
      <h1 style={{ fontSize: "1.2rem", margin: "0 0 0.35rem" }}>
        {nota.estabelecimento_nome ?? "Nota sem nome de loja"}
      </h1>
      <p className="secundario" style={{ margin: "0 0 1rem" }}>
        <span className="etiqueta">{nota.uf}</span>{" "}
        {nota.emitida_em
          ? new Date(nota.emitida_em).toLocaleString("pt-BR")
          : `compra de ${anoMesLegivel(nota.ano_mes_chave)}`}
        {nota.valor_total ? ` · ${moeda(nota.valor_total)}` : ""}
      </p>

      {erro && (
        <div className="aviso erro">
          <span className="icone" aria-hidden="true">
            ⚠️
          </span>
          <span>{erro}</span>
        </div>
      )}

      {nota.status === "ok" && (
        <div className="aviso ok">
          <span className="icone" aria-hidden="true">
            ✅
          </span>
          <span>
            {nota.itens.length} itens lidos automaticamente do portal da SEFAZ.
            {pendentes > 0 && ` ${pendentes} ainda precisam de um produto.`}
          </span>
        </div>
      )}

      {parseFalhou && (
        <div className="aviso atencao">
          <span className="icone" aria-hidden="true">
            ✍️
          </span>
          <span>
            {EXPLICACAO_FALHA[nota.erro_detalhe ?? ""] ??
              "O preenchimento automático não funcionou para esta nota."}
            {nota.url_portal_uf && (
              <>
                {" "}
                <a href={nota.url_consulta ?? nota.url_portal_uf} target="_blank" rel="noreferrer">
                  Abrir a nota no portal da SEFAZ ↗
                </a>
              </>
            )}
          </span>
        </div>
      )}

      <section className="cartao">
        <h2>Itens ({nota.itens.length})</h2>
        {nota.itens.length === 0 ? (
          <p className="legenda">Nenhum item ainda. Adicione abaixo.</p>
        ) : (
          <ul className="lista">
            {nota.itens.map((item) => (
              <li key={item.id} style={{ display: "block" }}>
                <div style={{ display: "flex", gap: "0.75rem", alignItems: "center" }}>
                  <div className="cresce">
                    <div className="titulo">{item.descricao_origem}</div>
                    <div className="sub">
                      {Number(item.quantidade).toLocaleString("pt-BR")}{" "}
                      {item.unidade ?? "UN"} × {moeda(item.valor_unitario)}
                      {item.produto_nome ? (
                        <>
                          {" · "}
                          <span className="etiqueta">{item.produto_nome}</span>
                        </>
                      ) : (
                        <>
                          {" · "}
                          <span style={{ color: "var(--atencao)" }}>sem produto</span>
                        </>
                      )}
                    </div>
                  </div>
                  <div className="numero">{moeda(item.valor_total)}</div>
                </div>
                <div className="acoes">
                  <button
                    className="discreto"
                    onClick={() => setVinculando(vinculando === item.id ? null : item.id)}
                  >
                    {item.produto_id ? "Trocar produto" : "Vincular a um produto"}
                  </button>
                  <button className="discreto" onClick={() => void remover(item.id)}>
                    Remover
                  </button>
                </div>
                {vinculando === item.id && (
                  <SeletorProduto
                    descricao={item.descricao_origem}
                    aoEscolher={(escolha) => void vincular(item.id, escolha)}
                    aoCancelar={() => setVinculando(null)}
                  />
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="cartao">
        <h2>Adicionar item</h2>
        <p className="legenda">
          Como aparece no cupom. O vínculo com o produto pode ser feito depois — o
          importante é registrar preço e quantidade.
        </p>

        <div className="campo">
          <label htmlFor="descricao">Descrição</label>
          <input
            id="descricao"
            value={novoItem.descricao_origem}
            placeholder="ex.: ARROZ BRANCO TIPO 1 5KG"
            onChange={(e) => setNovoItem({ ...novoItem, descricao_origem: e.target.value })}
          />
        </div>

        <div className="linha-campos">
          <div className="campo">
            <label htmlFor="qtd">Quantidade</label>
            <input
              id="qtd"
              inputMode="decimal"
              value={novoItem.quantidade}
              onChange={(e) => setNovoItem({ ...novoItem, quantidade: e.target.value })}
            />
          </div>
          <div className="campo">
            <label htmlFor="un">Unidade</label>
            <input
              id="un"
              value={novoItem.unidade}
              onChange={(e) => setNovoItem({ ...novoItem, unidade: e.target.value })}
            />
          </div>
          <div className="campo">
            <label htmlFor="valor">Valor unitário</label>
            <input
              id="valor"
              inputMode="decimal"
              placeholder="0,00"
              value={novoItem.valor_unitario}
              onChange={(e) => setNovoItem({ ...novoItem, valor_unitario: e.target.value })}
            />
          </div>
        </div>

        <button
          className="primario"
          disabled={salvando || !novoItem.descricao_origem.trim() || !novoItem.valor_unitario}
          onClick={() => void adicionarItem()}
        >
          {salvando ? "Salvando…" : "Adicionar item"}
        </button>
      </section>

      <section className="cartao">
        <h2>Detalhes da nota</h2>
        <p className="secundario mono">{formatarChave(nota.chave_acesso)}</p>
        <p className="secundario" style={{ margin: "0.4rem 0 0" }}>
          Status: {nota.status}
          {nota.adapter_usado ? ` · adapter: ${nota.adapter_usado}` : ""}
        </p>
        {parseFalhou && nota.itens.length === 0 && nota.url_consulta && (
          <div className="acoes">
            <button
              onClick={() =>
                void api
                  .reprocessarNota(notaId)
                  .then(() => recarregar())
                  .catch(() => setErro("A nova tentativa também não passou."))
              }
            >
              Tentar consulta automática de novo
            </button>
          </div>
        )}
      </section>
    </>
  );
}
