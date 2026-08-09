# Acompanhamento de Finanças

PWA pessoal para acompanhar gastos de **mercado, item a item**, a partir de notas
fiscais eletrônicas (NFC-e). Você escaneia o QR Code do cupom (ou digita a chave de
acesso), o app registra os itens e responde as perguntas que um extrato bancário não
responde:

- quanto você pagou no **arroz** em cada mês do ano — e no feijão, na carne;
- quais são seus **maiores gastos** por produto;
- se está gastando mais **este mês** do que no passado.

Uso pessoal, hospedado em homelab próprio atrás do Nginx Proxy Manager.

## Como funciona a entrada de notas

Este é o ponto que define a experiência, então vale ser explícito:

| Caminho | O que acontece |
|---|---|
| **Escanear o QR Code** (recomendado) | A URL do QR Code carrega o *hash assinado* da nota e abre a página dela direto no portal da SEFAZ. O backend busca essa página e tenta ler os itens automaticamente. |
| **Digitar a chave de acesso** | Vai direto para o preenchimento manual. A consulta por chave nos portais estaduais passa por um formulário protegido por **reCAPTCHA** — não é automatizável, e tentar só gastaria o tempo do usuário. |

Quando o parse automático não passa (captcha, bloqueio de IP, layout diferente,
timeout), a nota **não é perdida**: ela fica registrada com o motivo da falha, e a tela
de revisão vira um formulário rápido — já com UF, CNPJ e mês da compra preenchidos, que
saem da própria chave de acesso, sem nenhuma consulta de rede.

Um adapter único (`PortalPadraoAdapter`) atende todas as UFs, porque o conteúdo do QR
Code é padronizado nacionalmente e a maioria dos estados usa a página de consulta de
referência do ENCAT/SVRS. Estados com layout próprio se registram em
`ADAPTERS_ESPECIFICOS` sem mudar mais nada.

## Como o histórico de preço se forma

Para "quanto paguei no arroz" fazer sentido, `ARROZ TIO JOAO T1 5KG` (de uma loja) e
`ARROZ BR TIPO1 5 KG` (de outra) precisam apontar para o mesmo **produto**. O app
resolve isso em três níveis:

1. **GTIN** — se o código de barras já é conhecido, é o mesmo produto. Automático.
2. **Descrição exata** (normalizada) — se aquele texto já foi vinculado uma vez, vale
   para sempre. Automático.
3. **Similaridade de texto** (`pg_trgm`) — apenas **sugere**. `ARROZ 5KG` e `ARROZ 1KG`
   são quase idênticos como texto e produtos diferentes na prática, então quem decide é
   você. A decisão é gravada como alias e não é perguntada de novo.

## Stack

| Camada | Escolha |
|---|---|
| Frontend | React + Vite + TypeScript, `vite-plugin-pwa`, scanner via `BarcodeDetector` com ponyfill (Safari/iOS) |
| Backend | Python 3.12 + FastAPI, SQLAlchemy 2 async, Alembic |
| Banco | Postgres 16 (+ `pg_trgm`) |
| Parsing | `httpx` + BeautifulSoup/lxml |
| Deploy | Docker Compose, atrás do Nginx Proxy Manager |

Sem PostGIS e sem Redis: este app não tem busca geográfica nem comparação entre lojas,
e o volume é de um usuário — cache e fila não se pagariam.

## Rodar

```bash
cp .env.example .env      # defina DB_PASSWORD
docker compose up -d --build
```

- App: <http://localhost:8190>
- API + documentação: <http://localhost:8191/api/docs>

As migrations rodam no start do container do backend.

### Dev sem Docker

```bash
# backend
cd backend
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload

# frontend (outra aba)
cd frontend
npm install
npm run dev          # http://localhost:5173, /api encaminhado para :8000
```

### Testes

```bash
cd backend && pytest
```

Os testes não precisam de banco nem de rede: cobrem a leitura da chave de acesso
(incluindo o dígito verificador), o parser de HTML contra uma página de exemplo, e a
normalização de descrições.

## Deploy no homelab

O padrão do homelab é um projeto Compose por app, com o Nginx Proxy Manager alcançando
os containers pelas portas publicadas no host. Este app usa **8190** (web) e **8191**
(API) — escolhidas para não colidir com o `compara-precos` (8090/8091).

No NPM, criar um Proxy Host com duas Custom Locations:

| Location | Destino |
|---|---|
| `/` | `172.18.0.1:8190` |
| `/api` | `172.18.0.1:8191` |

Dois pontos que **não** devem ficar para depois:

- **Autenticação.** Diferente do `compara-precos` (que lida com preço público), aqui o
  conteúdo é seu histórico de compras. O caminho mais barato é uma **Access List
  (Basic Auth)** no Proxy Host do NPM — zero código.
- **Backup.** `pg_dump` diário para fora do disco do servidor. Os vínculos
  produto↔item e os itens digitados à mão não são reconstruíveis de nenhuma fonte
  externa.

A câmera exige **HTTPS** (contexto seguro) — só `localhost` é exceção. O TLS vem do
ingress (Tailscale Funnel / NPM).

## Documentação

| Documento | Assunto |
|---|---|
| [docs/01-arquitetura.md](docs/01-arquitetura.md) | Componentes, fluxo de ingestão, decisões e o que foi descartado |
| [docs/02-modelo-de-dados.md](docs/02-modelo-de-dados.md) | Schema, por que cada escolha, e as queries de análise |
| [docs/03-deploy-homelab.md](docs/03-deploy-homelab.md) | Passo a passo do deploy, NPM, backup |
