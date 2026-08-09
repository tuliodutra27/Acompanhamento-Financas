#!/usr/bin/env bash
#
# Verificação ponta a ponta da API contra uma instância rodando.
#
# Por que isto existe além do pytest: a suíte de testes é deliberadamente livre de
# banco e de rede (roda em 1 segundo, em qualquer lugar). Mas o comportamento que mais
# importa neste app — o vínculo item→produto por alias e as agregações mensais —
# **só existe com Postgres**, por causa do pg_trgm e das datas. Este script cobre
# exatamente essa faixa.
#
# Uso:
#   bash scripts/verificar-api.sh                      # usa http://localhost:8191
#   API=http://192.168.1.109:8191/api/v1 bash scripts/verificar-api.sh
#
# Cria dados sintéticos (CNPJ 12345678000195, chaves fabricadas). Para limpar depois:
#   docker compose exec -T db psql -U financas -d financas -c \
#     'TRUNCATE nota_fiscal, produto RESTART IDENTITY CASCADE'

set -uo pipefail
API="${API:-http://localhost:8191/api/v1}"

FALHAS=0
ok()    { echo "  OK   $1"; }
falha() { echo "  FALHA $1"; FALHAS=$((FALHAS + 1)); }

# Chaves sintéticas válidas (RJ, modelo 65). O dígito verificador de cada uma foi
# calculado pelo módulo 11 — não são notas reais.
CHAVE_AGO=33260812345678000195650010000001231123456789
CHAVE_JUL=33260712345678000195650010000001241123456782
CHAVE_JUN=33260612345678000195650010000001251123456786

json() { python3 -c "import json,sys; d=json.load(sys.stdin); print($1)" 2>/dev/null; }

echo "== 1. health =="
if curl -fsS "$API/health" | grep -q '"banco":"ok"'; then
  ok "banco acessível"
else
  falha "health não confirmou o banco — o resto não vale nada, abortando"
  exit 1
fi

echo "== 2. chave inválida é recusada =="
CODIGO=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$API/notas" \
  -H 'Content-Type: application/json' \
  -d '{"conteudo":"11111111111111111111111111111111111111111111","origem":"chave_manual"}')
[ "$CODIGO" = "400" ] && ok "HTTP 400" || falha "esperado 400, veio $CODIGO"

echo "== 3. chave digitada não tenta consulta automática =="
# Só a URL do QR Code carrega o hash assinado; a consulta por chave tem reCAPTCHA.
# O esperado é falhar na hora, sem gastar o timeout do adapter.
RESP=$(curl -s -X POST "$API/notas" -H 'Content-Type: application/json' \
  -d "{\"conteudo\":\"$CHAVE_AGO\",\"origem\":\"chave_manual\"}")
NOTA_AGO=$(echo "$RESP" | json 'd["id"]')
MOTIVO=$(echo "$RESP" | json 'd["erro_detalhe"]')
UF=$(echo "$RESP" | json 'd["uf"]')
[ "$MOTIVO" = "sem_url_qrcode" ] && ok "erro_detalhe=sem_url_qrcode" \
  || falha "esperado sem_url_qrcode, veio '$MOTIVO'"
[ "$UF" = "RJ" ] && ok "UF extraída da chave: RJ" || falha "UF veio '$UF'"

echo "== 4. reenviar a mesma chave é idempotente =="
CODIGO=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$API/notas" \
  -H 'Content-Type: application/json' \
  -d "{\"conteudo\":\"$CHAVE_AGO\",\"origem\":\"chave_manual\"}")
[ "$CODIGO" = "200" ] && ok "HTTP 200 (não duplicou)" || falha "esperado 200, veio $CODIGO"

echo "== 5. item manual com produto novo =="
ITEM=$(curl -s -X POST "$API/notas/$NOTA_AGO/itens" -H 'Content-Type: application/json' \
  -d '{"descricao_origem":"ARROZ BRANCO TIPO 1 5KG","quantidade":"2","unidade":"UN","valor_unitario":"24.90","novo_produto_nome":"Arroz"}')
PROD_ARROZ=$(echo "$ITEM" | json 'd["produto_id"]')
TOTAL=$(echo "$ITEM" | json 'd["valor_total"]')
[ -n "$PROD_ARROZ" ] && ok "produto criado (id=$PROD_ARROZ)" || falha "produto não foi criado"
[ "$TOTAL" = "49.80" ] && ok "valor_total derivado: 2 x 24,90 = 49,80" \
  || falha "valor_total veio '$TOTAL', esperado 49.80"
curl -s -X PATCH "$API/notas/$NOTA_AGO" -H 'Content-Type: application/json' \
  -d '{"emitida_em":"2026-08-05T19:42:00"}' > /dev/null

echo "== 6. item sem produto vai para a fila de revisão =="
curl -s -X POST "$API/notas/$NOTA_AGO/itens" -H 'Content-Type: application/json' \
  -d '{"descricao_origem":"PICANHA BOVINA KG","quantidade":"1.235","unidade":"KG","valor_unitario":"79.90"}' > /dev/null
if curl -fsS "$API/itens/pendentes" | grep -q PICANHA; then
  ok "item sem produto aparece em /itens/pendentes"
else
  falha "item sem produto não apareceu na fila"
fi

echo "== 7. REGRESSÃO: entrada manual autovincula por alias =="
# Este é o bug que a primeira versão tinha: autovincular só rodava no parse
# automático, então na entrada manual — o caminho mais usado — o usuário
# reclassificaria o mesmo produto em cada nota.
NOTA_JUL=$(curl -s -X POST "$API/notas" -H 'Content-Type: application/json' \
  -d "{\"conteudo\":\"$CHAVE_JUL\",\"origem\":\"chave_manual\"}" | json 'd["id"]')
VINCULADO=$(curl -s -X POST "$API/notas/$NOTA_JUL/itens" -H 'Content-Type: application/json' \
  -d '{"descricao_origem":"ARROZ BRANCO TIPO 1 5KG","quantidade":"1","unidade":"UN","valor_unitario":"22.50"}' \
  | json 'd["produto_nome"]')
[ "$VINCULADO" = "Arroz" ] && ok "descrição idêntica vinculou sozinha ao Arroz" \
  || falha "não autovinculou (produto_nome='$VINCULADO')"
curl -s -X PATCH "$API/notas/$NOTA_JUL" -H 'Content-Type: application/json' \
  -d '{"emitida_em":"2026-07-10T10:00:00"}' > /dev/null

echo "== 8. REGRESSÃO: sugestão casa nome curto em descrição longa =="
# similarity() comum afunda comparando "Arroz" com "ARROZ BRANCO T1 5 KG";
# word_similarity() é a medida certa para esse formato.
SUG=$(curl -s --get --data-urlencode "descricao=ARROZ BRANCO T1 5 KG" \
  "$API/produtos/sugestoes" | json 'd[0]["nome"] if d else "nenhuma"')
[ "$SUG" = "Arroz" ] && ok "sugeriu Arroz" || falha "sugeriu '$SUG'"

SUG=$(curl -s --get --data-urlencode "descricao=SABAO EM PO OMO" \
  "$API/produtos/sugestoes" | json 'len(d)')
[ "$SUG" = "0" ] && ok "produto sem relação não gera falso positivo" \
  || falha "gerou $SUG sugestões para algo não relacionado"

echo "== 9. nota sem data de emissão cai no mês da chave =="
# A chave carrega AAMM, então a nota entra nos relatórios mesmo sem data.
NOTA_JUN=$(curl -s -X POST "$API/notas" -H 'Content-Type: application/json' \
  -d "{\"conteudo\":\"$CHAVE_JUN\",\"origem\":\"chave_manual\"}" | json 'd["id"]')
curl -s -X POST "$API/notas/$NOTA_JUN/itens" -H 'Content-Type: application/json' \
  -d '{"descricao_origem":"ARROZ BRANCO TIPO 1 5KG","quantidade":"1","unidade":"UN","valor_unitario":"26.90"}' > /dev/null

MESES=$(curl -s "$API/analytics/produtos/$PROD_ARROZ/serie-precos" \
  | json '" ".join(p["mes"][:7] for p in d["serie"])')
echo "     meses na série: $MESES"
echo "$MESES" | grep -q "2026-06" && ok "junho entrou pelo AAMM da chave" \
  || falha "junho não apareceu na série"

echo "== 10. série de preços e variação =="
SERIE=$(curl -s "$API/analytics/produtos/$PROD_ARROZ/serie-precos")
N=$(echo "$SERIE" | json 'len(d["serie"])')
VAR=$(echo "$SERIE" | json 'd["variacao"]["variacao_percentual"] if d["variacao"] else "nula"')
[ "$N" = "3" ] && ok "3 meses na série" || falha "série tem $N meses, esperado 3"
[ "$VAR" != "nula" ] && ok "variação calculada: ${VAR}%" || falha "variação veio nula"

echo "== 11. ranking e resumo =="
curl -fsS "$API/analytics/gastos/ranking" | grep -q Arroz \
  && ok "ranking traz Arroz" || falha "ranking não trouxe Arroz"
curl -fsS "$API/analytics/gastos/resumo" | grep -q 2026-07 \
  && ok "resumo mensal traz julho" || falha "resumo mensal sem julho"
curl -fsS "$API/analytics/totais" | grep -q itens_pendentes \
  && ok "totais respondem" || falha "totais falharam"

echo
if [ "$FALHAS" -eq 0 ]; then
  echo "TUDO OK."
else
  echo "$FALHAS verificação(ões) falharam."
fi
exit $((FALHAS > 0))
