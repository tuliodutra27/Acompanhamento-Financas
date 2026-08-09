# 02 — Modelo de dados

Postgres 16 + `pg_trgm`. O DDL vive em
`backend/alembic/versions/0001_schema_inicial.py`; os models em `backend/app/models/`.

## 1. Visão geral

```
estabelecimento (CNPJ)  1 ──── N  nota_fiscal  1 ──── N  item_nota  N ──── 1  produto
                                                                              │ 1
                                                                              │
                                                                              N
                                                                        produto_alias
                                                                     (GTIN | descrição)
```

- **`nota_fiscal`** é a compra, identificada pela chave de acesso (única).
- **`item_nota`** é a linha do cupom, com a descrição **como veio** — nunca reescrita.
- **`produto`** é o agrupamento que o usuário controla ("Arroz").
- **`produto_alias`** é a memória: como aquele produto aparece nas notas.

## 2. Escolhas que merecem explicação

### `produto.id` surrogate, não o GTIN como chave primária

O projeto irmão `compara-precos` usa o GTIN como PK do produto, e faz sentido lá: é um
catálogo público de mercado. Aqui não serve, por dois motivos:

1. O usuário decide a granularidade — pode querer "Arroz" genérico juntando marcas, ou
   "Arroz Tio João 5kg" separado. O GTIN impõe a granularidade do fabricante.
2. A maior parte dos itens digitados à mão **não tem GTIN**.

### `item_nota.produto_id IS NULL` é o estado, não uma flag

A fila de revisão é literalmente `WHERE produto_id IS NULL`, servida por um índice
parcial. Uma coluna `revisado BOOLEAN` separada só criaria dois campos para manter
sincronizados.

### Índices únicos parciais em `produto_alias`

```sql
CREATE UNIQUE INDEX uq_alias_gtin      ON produto_alias (gtin) WHERE gtin IS NOT NULL;
CREATE UNIQUE INDEX uq_alias_descricao ON produto_alias (descricao_normalizada)
                                       WHERE descricao_normalizada IS NOT NULL;
```

Um GTIN (ou uma descrição exata) aponta para **um** produto. É isso que faz o vínculo
ser memória e não palpite repetido — e é por isso que `registrar_alias()` é idempotente
e não sobrescreve um vínculo anterior do usuário em silêncio.

### GTIN sempre com zero-pad para 14 dígitos

GTIN chega com 8, 12, 13 ou 14 dígitos. Sem padronizar, `7896…` e `07896…` não colidem
e o mesmo produto vira dois. `normalizar_gtin()` também descarta os placeholders de
"sem código de barras" (só zeros) e qualquer coisa com comprimento inválido — que é
como o `cProd` interno do lojista é impedido de se passar por GTIN.

### `ano_mes_chave` além de `emitida_em`

`emitida_em` só existe depois do parse (ou de o usuário digitar). `ano_mes_chave` sai da
própria chave, sempre. As agregações usam
`COALESCE(date_trunc('month', emitida_em), to_date(ano_mes_chave,'YYMM'))`, então uma
nota nunca fica fora dos relatórios por falta de data.

### `payload_bruto BYTEA`

HTML da consulta, comprimido com gzip. Depurar mudança de layout de portal sem isso é
adivinhação. Retenção prevista em `retencao_payload_bruto_dias` (30) — **a rotina de
expurgo ainda não existe**, é um pendente conhecido.

## 3. As consultas que importam

Evolução de preço de um produto, mês a mês — o gráfico principal
(`services/analytics.py::serie_precos`):

```sql
SELECT date_trunc('month', COALESCE(n.emitida_em, to_date(n.ano_mes_chave,'YYMM'))) AS mes,
       AVG(i.valor_unitario) AS preco_medio,
       MIN(i.valor_unitario) AS preco_min,
       MAX(i.valor_unitario) AS preco_max,
       SUM(i.valor_total)    AS total_gasto,
       COUNT(*)              AS n_compras
FROM   item_nota i
JOIN   nota_fiscal n ON n.id = i.nota_id
WHERE  i.produto_id = :produto_id
GROUP  BY 1
ORDER  BY 1;
```

`n_compras` viaja junto de propósito: uma média de uma única compra não é tendência, e a
interface precisa poder dizer isso em vez de desenhar uma linha confiante.

Maiores gastos por produto (`ranking_gastos`): mesmo join, `GROUP BY produto`,
`ORDER BY SUM(valor_total) DESC`.

Fila de revisão:

```sql
SELECT * FROM item_nota WHERE produto_id IS NULL;   -- usa idx_item_pendentes
```

## 4. Preço unitário é o que se compara, não o total

A série usa `valor_unitario`, não `valor_total`. Comprar 2 kg de arroz num mês e 5 kg no
outro mudaria o total sem o preço ter mudado. Para itens vendidos por peso o
`valor_unitario` da nota já é o preço por quilo, então a comparação continua válida.

Onde a nota traz só o total da linha, o parser deriva
`valor_unitario = valor_total / quantidade` (e vice-versa) — ver
`layout_padrao.py::_extrair_item`.

## 5. Volume

Uma compra de mercado gera algo entre 10 e 60 linhas. Quatro compras por mês são ~150
linhas/mês, ~1.800/ano. Postgres não sente; não há necessidade de tabela de agregado nem
de política de retenção para os itens. O único campo que cresce de verdade é o
`payload_bruto`.

## 6. Migrations

```bash
cd backend
alembic upgrade head        # aplica (o container do backend já faz isso no start)
alembic revision -m "..."   # nova migration
```

A `0001` foi escrita à mão, não por autogenerate: os índices que importam aqui (GIN
trigram, únicos parciais) o autogenerate não produz corretamente.
