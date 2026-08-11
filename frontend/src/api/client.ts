/**
 * Cliente da API. Caminhos relativos sempre: em dev o Vite encaminha /api para o
 * FastAPI, em produção o Nginx Proxy Manager faz o mesmo — nenhuma base URL condicional.
 */

const BASE = "/api/v1";

export type StatusNota = "pendente" | "ok" | "falhou_parse" | "manual";
export type OrigemEntrada = "qrcode" | "chave_manual";

export interface ErroApi {
  codigo: string;
  mensagem: string;
  detalhes?: Record<string, unknown>;
}

export class FalhaApi extends Error {
  constructor(
    readonly status: number,
    readonly erro: ErroApi,
  ) {
    super(erro.mensagem);
  }
}

async function requisitar<T>(caminho: string, init?: RequestInit): Promise<T> {
  const resposta = await fetch(`${BASE}${caminho}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });

  if (resposta.status === 204) return undefined as T;

  const corpo = await resposta.json().catch(() => null);

  if (!resposta.ok) {
    const erro: ErroApi = corpo?.erro ?? {
      codigo: "ERRO_DESCONHECIDO",
      mensagem: `Falha ${resposta.status} ao chamar a API.`,
    };
    throw new FalhaApi(resposta.status, erro);
  }

  return corpo as T;
}

export interface Item {
  id: number;
  produto_id: number | null;
  produto_nome: string | null;
  descricao_origem: string;
  gtin: string | null;
  quantidade: string;
  unidade: string | null;
  valor_unitario: string;
  valor_total: string;
}

export interface NotaResumo {
  id: number;
  chave_acesso: string;
  uf: string;
  ano_mes_chave: string;
  emitida_em: string | null;
  valor_total: string | null;
  status: StatusNota;
  origem_entrada: OrigemEntrada;
  erro_detalhe: string | null;
  n_itens: number;
  estabelecimento_nome: string | null;
}

export interface NotaDetalhe extends NotaResumo {
  cnpj_emitente: string | null;
  adapter_usado: string | null;
  url_consulta: string | null;
  url_portal_uf: string | null;
  itens: Item[];
}

export interface Produto {
  id: number;
  nome: string;
  categoria: string | null;
  n_compras: number;
  total_gasto: number;
  preco_medio: number;
}

export interface Sugestao {
  produto_id: number;
  nome: string;
  similaridade: number;
}

export interface PontoSerie {
  mes: string;
  /** Gasto ÷ quantidade do mês: o que de fato se pagou por kg/unidade. */
  preco_ponderado: number;
  preco_medio: number;
  preco_min: number;
  preco_max: number;
  total_gasto: number;
  quantidade_total: number;
  unidade: string | null;
  n_compras: number;
}

export interface SeriePrecos {
  produto: { id: number; nome: string };
  serie: PontoSerie[];
  variacao: {
    mes_inicial: string;
    preco_inicial: number;
    mes_final: string;
    preco_final: number;
    variacao_percentual: number;
    meses_com_dados: number;
  } | null;
}

export interface LinhaRanking {
  produto_id: number;
  nome: string;
  total_gasto: number;
  quantidade_total: number;
  preco_medio: number;
  n_compras: number;
}

export interface FatiaCategoria {
  categoria: string;
  total_gasto: number;
  n_itens: number;
  n_produtos: number;
  fatia: number;
}

export interface EvolucaoCategorias {
  meses: string[];
  categorias: { categoria: string; total: number; valores: number[] }[];
  agrupadas_em_outras: string[];
}

export interface ProdutoDaCategoria {
  produto_id: number;
  nome: string;
  total_gasto: number;
  n_compras: number;
  preco_medio: number;
}

export interface ContribuicaoIndice {
  produto_id: number;
  nome: string;
  preco_base: number;
  preco_novo: number;
  pontos_percentuais: number;
}

export interface IndiceCesta {
  mes_base: string;
  mes: string;
  variacao_percentual: number;
  cobertura: number;
  confianca: "alta" | "media" | "baixa";
  produtos_comparados: number;
  produtos_no_mes_base: number;
  maiores_altas: ContribuicaoIndice[];
  maiores_quedas: ContribuicaoIndice[];
}

export interface AlertaPreco {
  item_id: number;
  nota_id: number;
  produto_id: number;
  nome: string;
  descricao_origem: string;
  unidade: string | null;
  preco_pago: number;
  preco_usual: number;
  acima_percentual: number;
  data: string | null;
  compras_anteriores: number;
}

export interface ProdutoRecorrente {
  produto_id: number;
  nome: string;
  categoria: string | null;
  meses: number;
  compras: number;
  gasto: number;
}

export interface Recorrencia {
  total_meses: number;
  recorrentes: ProdutoRecorrente[];
  frequentes: ProdutoRecorrente[];
  eventuais: ProdutoRecorrente[];
  gasto_recorrente: number;
  gasto_eventual: number;
}

export interface GrupoSuspeito {
  produto_id: number;
  nome: string;
  categoria: string | null;
  n_itens: number;
  n_descricoes: number;
  menor_preco: number;
  maior_preco: number;
  motivos: string[];
  gravidade: "alta" | "media";
}

export interface PontoComparacao {
  preco: number;
  quantidade: number;
  gasto: number;
  n_compras: number;
}

export interface SerieComparacao {
  produto_id: number;
  nome: string;
  unidade: string | null;
  meses_com_compra: number;
  /** Uma posição por mês; `null` onde não houve compra (lacuna, não zero). */
  serie: (PontoComparacao | null)[];
}

export interface ComparacaoProdutos {
  meses: string[];
  produtos: SerieComparacao[];
}

export interface Totais {
  total_gasto: number;
  n_notas: number;
  n_itens: number;
  n_produtos: number;
  itens_pendentes: number;
}

export interface ItemPendente {
  item_id: number;
  nota_id: number;
  descricao_origem: string;
  gtin: string | null;
  valor_unitario: number;
  sugestoes: Sugestao[];
}

export const api = {
  criarNota: (conteudo: string, origem: OrigemEntrada) =>
    requisitar<NotaDetalhe>("/notas", {
      method: "POST",
      body: JSON.stringify({ conteudo, origem }),
    }),

  listarNotas: (params: { status?: StatusNota; limite?: number } = {}) => {
    const busca = new URLSearchParams();
    if (params.status) busca.set("status", params.status);
    if (params.limite) busca.set("limite", String(params.limite));
    return requisitar<NotaResumo[]>(`/notas?${busca}`);
  },

  obterNota: (id: number) => requisitar<NotaDetalhe>(`/notas/${id}`),

  atualizarNota: (
    id: number,
    dados: { emitida_em?: string; valor_total?: string },
  ) =>
    requisitar<NotaDetalhe>(`/notas/${id}`, {
      method: "PATCH",
      body: JSON.stringify(dados),
    }),

  reprocessarNota: (id: number) =>
    requisitar<NotaDetalhe>(`/notas/${id}/reprocessar`, { method: "POST" }),

  atualizarEstabelecimento: (
    id: number,
    dados: { razao_social?: string; nome_fantasia?: string; municipio?: string },
  ) =>
    requisitar<NotaDetalhe>(`/notas/${id}/estabelecimento`, {
      method: "PUT",
      body: JSON.stringify(dados),
    }),

  adicionarItem: (
    notaId: number,
    dados: {
      descricao_origem: string;
      quantidade: string;
      unidade?: string | null;
      valor_unitario?: string | null;
      valor_total?: string | null;
      gtin?: string | null;
      produto_id?: number | null;
      novo_produto_nome?: string | null;
    },
  ) =>
    requisitar<Item>(`/notas/${notaId}/itens`, {
      method: "POST",
      body: JSON.stringify(dados),
    }),

  atualizarItem: (
    notaId: number,
    itemId: number,
    dados: Partial<{
      descricao_origem: string;
      quantidade: string;
      unidade: string;
      valor_unitario: string;
      valor_total: string;
      gtin: string;
    }>,
  ) =>
    requisitar<Item>(`/notas/${notaId}/itens/${itemId}`, {
      method: "PUT",
      body: JSON.stringify(dados),
    }),

  removerItem: (notaId: number, itemId: number) =>
    requisitar<void>(`/notas/${notaId}/itens/${itemId}`, { method: "DELETE" }),

  vincularItem: (
    notaId: number,
    itemId: number,
    dados: { produto_id?: number; novo_produto_nome?: string },
  ) =>
    requisitar<Item>(`/notas/${notaId}/itens/${itemId}/vincular`, {
      method: "POST",
      body: JSON.stringify(dados),
    }),

  listarProdutos: (q?: string) =>
    requisitar<Produto[]>(`/produtos${q ? `?q=${encodeURIComponent(q)}` : ""}`),

  criarProduto: (nome: string, categoria?: string) =>
    requisitar<Produto>("/produtos", {
      method: "POST",
      body: JSON.stringify({ nome, categoria }),
    }),

  renomearProduto: (id: number, nome: string) =>
    requisitar<Produto>(`/produtos/${id}`, {
      method: "PUT",
      body: JSON.stringify({ nome }),
    }),

  sugestoes: (descricao: string) =>
    requisitar<Sugestao[]>(
      `/produtos/sugestoes?descricao=${encodeURIComponent(descricao)}`,
    ),

  mergeProdutos: (origem_id: number, destino_id: number) =>
    requisitar<Produto>("/produtos/merge", {
      method: "POST",
      body: JSON.stringify({ origem_id, destino_id }),
    }),

  itensPendentes: () => requisitar<ItemPendente[]>("/itens/pendentes"),

  seriePrecos: (produtoId: number) =>
    requisitar<SeriePrecos>(`/analytics/produtos/${produtoId}/serie-precos`),

  ranking: (limite = 20) =>
    requisitar<LinhaRanking[]>(`/analytics/gastos/ranking?limite=${limite}`),

  resumoMensal: () =>
    requisitar<{ mes: string; total_gasto: number; n_notas: number; n_itens: number }[]>(
      "/analytics/gastos/resumo",
    ),

  totais: () => requisitar<Totais>("/analytics/totais"),

  categorias: () => requisitar<FatiaCategoria[]>("/analytics/categorias"),

  evolucaoCategorias: (limite = 7) =>
    requisitar<EvolucaoCategorias>(
      `/analytics/categorias/evolucao?limite=${limite}`,
    ),

  produtosDaCategoria: (categoria: string) =>
    requisitar<ProdutoDaCategoria[]>(
      `/analytics/categorias/${encodeURIComponent(categoria)}/produtos`,
    ),

  indiceCesta: () => requisitar<IndiceCesta[]>("/analytics/inflacao-cesta"),

  alertasPreco: (limite = 15) =>
    requisitar<AlertaPreco[]>(`/analytics/alertas-preco?limite=${limite}`),

  recorrencia: () => requisitar<Recorrencia>("/analytics/recorrencia"),

  gruposSuspeitos: () =>
    requisitar<GrupoSuspeito[]>("/analytics/grupos-suspeitos"),

  comparar: (produtoIds: number[]) =>
    requisitar<ComparacaoProdutos>(
      `/analytics/comparar?produtos=${produtoIds.join(",")}`,
    ),
};

export function moeda(valor: number | string | null | undefined): string {
  const numero = typeof valor === "string" ? Number(valor) : (valor ?? 0);
  return numero.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

export function mesLegivel(iso: string): string {
  const data = new Date(`${iso.slice(0, 10)}T12:00:00`);
  return data.toLocaleDateString("pt-BR", { month: "short", year: "numeric" });
}
