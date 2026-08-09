# 01 — Arquitetura

## 1. O problema que define o desenho

Não existe API pública nacional que devolva os itens de uma nota fiscal em JSON. O que
existe é **uma página HTML de consulta por estado**, e essas páginas defendem-se de
automação. Isso não é um detalhe de implementação: é o fato que decide a arquitetura
inteira.

Consequência prática, e a decisão que ela impõe:

| Caminho de entrada | Automatizável? | Por quê |
|---|---|---|
| URL lida do **QR Code** | Sim, na maioria dos casos | O QR Code carrega o `cHashQRCode` — um hash assinado pelo emissor. A URL abre a nota **direto**, sem passar por formulário. |
| **Chave digitada** (44 dígitos) | **Não** | Sem o hash, o único caminho é o formulário "consulta por chave de acesso" dos portais, protegido por **reCAPTCHA**. |

Por isso o app não trata "digitou a chave" como um caminho equivalente que por acaso
falhou: ele falha **imediatamente**, com o motivo `sem_url_qrcode`, e manda o usuário
para o preenchimento manual sem gastar 10 segundos numa requisição condenada.

### 1.1 O RJ bloqueia IP residencial — descoberto em 09/08/2026, e é decisivo

Testado ao vivo, do próprio homelab, com Chromium real (Playwright). O que se descobriu,
em ordem, porque a ordem importa:

1. `curl` na página de consulta (`consultaChaveAcesso.faces`) devolve **200 com um
   desafio JavaScript do F5 Shape** (`loaderConfig = "/TSPD/?type=20"`). É fácil parar
   aqui e concluir "é anti-bot".
2. Com um **navegador real**, o desafio se resolve — e por baixo dele aparece a mensagem
   verdadeira, da própria SEFAZ-RJ:

   > "As operadoras de telecomunicação do Brasil possuem alguns de seus endereços IP
   > usados por serviços residenciais que estão listados em catálogos internacionais […]
   > nosso serviço de segurança da informação bloqueia acessos provenientes desses
   > endereços IP aos serviços que tratam de informações sujeitas a sigilo fiscal."
   >
   > "Recomendamos que entre em contato com sua operadora […] para mudar seu endereço IP,
   > **ou tente acessar o serviço de outra origem**. Adicionalmente, […] poderá entrar em
   > contato através do [OuvERJ](https://www.rj.gov.br/ouverj/) informando o número do IP
   > e detalhamento do erro."

**O bloqueio é de reputação de IP, não de automação.** Consequências práticas:

- **Navegador headless não resolve.** O F5 é só o invólucro; o bloqueio vem antes e vale
  para qualquer cliente naquele IP. Isso poupou implementar um adapter Playwright inteiro
  — a exploração custou minutos e evitou horas.
- **O caminho não é técnico, é de origem de rede.** As saídas são as que a própria SEFAZ
  lista: mudar de IP, acessar de outra origem (outra rede/dispositivo), ou pedir
  desbloqueio pelo OuvERJ (a mensagem traz um número de incidente).
- **Captura no dispositivo do usuário volta a ser o plano principal** para extração
  automática — não por causa de captcha, mas porque o telefone em rede móvel é "outra
  origem" e pode não estar bloqueado. Precisa ser verificado por rede, não presumido.

> Registro de correção: versões anteriores deste documento afirmavam que o bloqueio era
> anti-bot (Imperva/reCAPTCHA) e que o IP residencial "não estava bloqueado". Ambas as
> afirmações estavam erradas, e vinham de parar a investigação no desafio do F5 sem
> executá-lo.

## 2. Componentes

```
┌───────────────────────────┐   HTTPS/JSON   ┌──────────────────────────────┐
│ PWA (React + Vite)         │ ─────────────► │ API (FastAPI)                │
│ câmera + validação da      │ ◄───────────── │ /api/v1/notas, /produtos,    │
│ chave no cliente           │                │ /analytics                    │
└───────────────────────────┘                └──────┬───────────────────────┘
                                                    │
                                    ┌───────────────┴───────────────┐
                                    ▼                               ▼
                          ┌──────────────────┐          ┌──────────────────────┐
                          │ Postgres 16      │          │ Camada de adapters   │
                          │ + pg_trgm        │          │ (por UF)             │
                          └──────────────────┘          └──────┬───────────────┘
                                                               │
                                                    ┌──────────┴──────────┐
                                                    ▼                     ▼
                                          PortalPadraoAdapter    (UF com layout
                                          (todas as UFs)          próprio, futuro)
```

Sem Redis e sem PostGIS, ao contrário do projeto irmão: aqui não há busca geográfica
nem comparação entre lojas, e o volume é de um usuário. Cache e fila seriam complexidade
sem retorno. `GET /notas/{id}` já existe para polling, então migrar a ingestão para uma
fila depois não muda o contrato da API.

## 3. A chave de acesso trabalha offline

Os 44 dígitos carregam dado útil sem nenhuma consulta:

```
01-02  cUF      código IBGE da UF      -> 33 = RJ
03-06  AAMM     ano e mês de emissão   -> 2608 = ago/2026
07-20  CNPJ     emitente
21-22  mod      55 = NF-e, 65 = NFC-e
23-25  série
26-34  nNF      número da nota
35     tpEmis
36-43  cNF
44     cDV      dígito verificador (módulo 11)
```

Isso é implementado em `backend/app/core/chave_nfce.py` **e** espelhado em
`frontend/src/lib/chaveNfce.ts`. A duplicação é deliberada: o cliente valida o dígito
verificador e mostra "UF: RJ, compra de ago/2026" **antes** de qualquer requisição —
erro de digitação aparece na hora, e o usuário já sabe o que esperar.

É também o que garante que uma nota cujo parse falhou ainda tenha UF, CNPJ e mês
preenchidos, e portanto **apareça nos relatórios** mesmo antes de ter os itens.

## 4. Fluxo de ingestão

```
POST /notas {conteudo, origem}
  │
  ├─ valida a chave (formato + dígito verificador) ─── inválida → 400, sem tocar a rede
  ├─ chave já existe? ──────────────────────────────── sim → devolve a nota (200, idempotente)
  ├─ cria nota_fiscal(status=pendente, uf/cnpj/mês extraídos da chave)
  ├─ adapter_para(uf)
  │     ├─ não há adapter        → falhou_parse (uf_nao_suportada)
  │     ├─ sem URL do QR Code    → falhou_parse (sem_url_qrcode)   [instantâneo]
  │     └─ busca a página (10s)
  │            ├─ sucesso  → grava itens → autovincula por GTIN/descrição → status=ok
  │            └─ falha    → falhou_parse (captcha | bloqueio | layout_mudou | timeout)
  └─ devolve a nota; o frontend escolhe a tela pelo campo `status`
```

Regras dos adapters (`app/adapters/base.py`):

1. Timeout explícito por requisição.
2. **Nunca deixar exceção estranha vazar** — toda falha vira `ParseFalhou` com um
   `motivo` da enum. Quem chama trata um caso só.
3. Guardar o HTML bruto comprimido em `nota_fiscal.payload_bruto` — é o que permite
   descobrir *o que* mudou quando um parse quebrar, sem reproduzir a falha.

Distinguir os motivos importa porque eles levam a ações diferentes: `captcha` significa
"esse estado não é automatizável, não insista"; `layout_mudou` significa "o parser
precisa de manutenção".

## 5. Por que um adapter atende todas as UFs

Duas padronizações fazem isso funcionar:

- **O conteúdo do QR Code é nacional.** `...?p=<chave>|<versão>|<ambiente>|<hash>` —
  só a URL-base antes do `?p=` muda por estado, e ela vem escrita no próprio cupom.
  Extrair a chave é um regex, não um parser por UF.
- **A página de resposta** segue, na maioria dos estados, a implementação de referência
  do ENCAT/SVRS (`#tabResult`, `.txtTit`, `.Rqtd`, `.RvlUnit`, `.valor`). Um parser
  cobre todos eles.

Então `registry.py` registra o `PortalPadraoAdapter` para as 27 UFs. Isso não é
otimismo: o custo de tentar é uma requisição HTTP, e a falha já tem caminho definido.
Assumir de antemão que um estado não funciona seria descartar dado que talvez viesse de
graça. Estados com layout próprio entram em `ADAPTERS_ESPECIFICOS`.

**O que não foi verificado:** cada UF individualmente. Só o layout de referência está
implementado, e a lista de URLs em `urls_uf.py` (usada apenas para o link "abrir no
portal") vem de fonte pública, sem teste um a um. Estados fora do padrão vão falhar com
`layout_mudou` — e cair no manual, que funciona para todos desde o primeiro dia.

## 6. Vínculo item → produto

O agrupamento é o que transforma linhas de cupom em série histórica. Três níveis, e o
ponto de desenho é **onde a automação para**:

| Nível | Sinal | Automático? |
|---|---|---|
| 1 | GTIN já conhecido (`produto_alias.gtin`) | sim |
| 2 | Descrição normalizada idêntica (`produto_alias.descricao_normalizada`) | sim |
| 3 | Similaridade de texto (`pg_trgm`) | **não — só sugere** |

O nível 3 nunca vincula sozinho porque `ARROZ 5KG` e `ARROZ 1KG` são quase idênticos
como texto e produtos diferentes na prática. Uma automação errada aqui contaminaria
silenciosamente o histórico de preço — exatamente o dado que o app existe para produzir.

O código do produto que o portal mostra (`(Código: …)`) é o `cProd` do lojista, que no
varejo *às vezes* é o GTIN. Ele passa por `normalizar_gtin()`, que só aceita
comprimentos válidos de GTIN (8/12/13/14) e faz zero-pad para 14 — sem isso, um código
interno curto viraria um "GTIN" e faria produtos diferentes colidirem no mesmo alias.

## 7. Decisões registradas

| Decisão | Motivo |
|---|---|
| Escopo só mercado, item a item | Pedido explícito: o objetivo é preço de produto ao longo do tempo, não orçamento doméstico completo. |
| PWA, não app nativo | Instalável pelo navegador, atualização imediata, custo zero de distribuição. |
| Ingestão síncrona no request | Um usuário, poucas notas por semana; fila seria infra sem retorno. |
| `produto.id` surrogate, não GTIN como PK | O usuário controla a granularidade do agrupamento, e itens digitados à mão não têm GTIN. |
| Sem `UNIQUE` no nome do produto | Unicidade em texto livre é frágil (acento, espaço, caixa). A UI sugere reaproveitar; `POST /produtos/merge` corrige o que passar. |
| Payload bruto no banco (não object storage) | Volume mínimo e depuração local; não vale um bucket para isso. |
| Basic Auth no NPM em vez de login no app | É dado pessoal atrás de um proxy que já sabe fazer isso. Login próprio é conforto, não segurança adicional aqui. |

## 8. Descartado

- **Consulta automática a partir da chave digitada** — o formulário exige interação que
  não vale automatizar. É o motivo de existir o motivo `sem_url_qrcode` em vez de uma
  tentativa silenciosa.
- **Browser headless (Playwright) para vencer o bloqueio do RJ** — investigado e
  descartado com evidência (seção 1.1): o bloqueio é de reputação de IP e vale para
  qualquer cliente naquela rede, então um navegador real não muda o resultado. A
  exploração ficou registrada porque o *método* serve para qualquer outra UF: subir a
  imagem oficial do Playwright, abrir a página e ler o que aparece **depois** do desafio,
  em vez de concluir pelo que o `curl` mostra.
- **Certificado digital e-CPF / web service de Distribuição de DF-e** (puxar todas as
  notas do CPF em lote) — exige certificado pago, e é incerto se NFC-e de varejo aparece
  nessa consulta, já que o CPF é opcional na nota. Investigado no projeto irmão.

## 9. Em aberto

- **Qual rede consegue alcançar o portal do RJ?** O homelab (banda larga residencial)
  está bloqueado (seção 1.1). Falta verificar, rede por rede: celular em dados móveis,
  o PC na mesma LAN, e o telefone como *exit node* do Tailscale (que faria a saída do
  servidor usar o IP da operadora móvel). A resposta define se a extração automática é
  possível e por qual caminho — e é um teste de dois minutos, não uma decisão de projeto.
- **Vale abrir chamado no OuvERJ** pedindo desbloqueio do IP? A própria mensagem da SEFAZ
  sugere isso e fornece número de incidente. Precedente favorável: o projeto irmão
  `compara-precos` já trilhou o caminho de pedido formal a órgão estadual.
- Quais UFs de fato funcionam pelo caminho do QR Code? Só o uso real responde. Cada
  falha grava o motivo, então a resposta se acumula sozinha em `nota_fiscal.erro_detalhe`.
- Expurgo do `payload_bruto` (`retencao_payload_bruto_dias`, padrão 30) ainda não tem
  rotina agendada — hoje o campo só cresce.
- O nome do estabelecimento vem do parse; quando o parse falha, fica em branco até o
  usuário digitar. Enriquecer por CNPJ via BrasilAPI é um próximo passo barato.
