# 03 — Deploy no homelab

O padrão do homelab é **um projeto Docker Compose por app**, em `~/apps/<nome>/`, cada um
na sua rede Docker. O Nginx Proxy Manager não compartilha rede com os apps: alcança cada
um pela porta publicada no host, via o gateway `172.18.0.1`.

## 1. Portas

| Serviço | Host | Container |
|---|---|---|
| `web` (PWA) | `8190` | 80 |
| `backend` (API) | `8191` | 8000 |
| `db` (Postgres) | — | 5432 (não publicada) |

8190/8191 foram escolhidas para não colidir com o `compara-precos`, que usa 8090/8091.

## 2. Subir

```bash
cd ~/apps
git clone https://github.com/tuliodutra27/Acompanhamento-Financas.git acompanhamento-financas
cd acompanhamento-financas
cp .env.example .env
$EDITOR .env                 # defina DB_PASSWORD (o compose falha se estiver vazia)
docker compose up -d --build
docker compose logs -f backend    # confirmar "alembic upgrade head" e o uvicorn subindo
```

Verificação rápida:

```bash
curl -s localhost:8191/api/v1/health          # {"status":"ok","banco":"ok",...}
curl -s localhost:8191/api/v1/ufs-suportadas  # lista das 27 UFs
curl -sI localhost:8190                        # 200 do nginx do frontend
```

## 3. Nginx Proxy Manager

Novo **Proxy Host**, uma entrada só:

| Forward Hostname / IP | Porta |
|---|---|
| `172.18.0.1` | `8190` |

Não precisa de Custom Location para `/api`: o nginx do container `web` encaminha `/api`
para o backend pela rede interna do Compose (ver `frontend/nginx.conf`). O app roda numa
única origem em qualquer cenário — direto na porta, atrás do NPM, ou em dev — e CORS sai
do desenho. A porta 8191 segue publicada apenas para acesso direto à API e depuração.

Se o ingress público for o Tailscale Funnel (que já termina TLS antes de chegar ao NPM),
deixar o SSL desligado neste Proxy Host. O Funnel tem limite de 3 portas simultâneas —
se as três já estiverem ocupadas, este app entra como uma Custom Location num Proxy Host
existente (ex. `/financas` → `172.18.0.1:8190`); nesse caso é preciso ajustar o `base` do
Vite e o prefixo da API, porque o app assume estar servido na raiz.

> **HTTPS não é opcional aqui.** O scanner de QR Code usa `getUserMedia`, que só funciona
> em contexto seguro (exceto `localhost`). Sem TLS, o app funciona mas o scanner não abre
> — e o scanner é justamente o caminho que habilita o preenchimento automático.

## 4. Autenticação

O app tem login próprio: **uma senha**, sem cadastro de usuário — não há um segundo
usuário para distinguir. Duas variáveis no `.env`:

```bash
AUTH_SENHA=a-senha-que-voce-escolher
SECRET_KEY=$(openssl rand -hex 32)
```

`AUTH_SENHA` **vazia deixa o app aberto**, que é o comportamento de antes do login
existir. Isso é intencional: subir a stack pela primeira vez não deveria exigir escolher
senha antes de qualquer coisa funcionar. Para não virar uma proteção imaginária, o app
mostra uma faixa amarela em todas as telas enquanto estiver nesse estado.

`SECRET_KEY` assina o cookie de sessão **e** deriva o token do atalho de importação.
Trocar o valor desloga todas as sessões e invalida os atalhos já instalados no navegador
— é o botão de revogação, e o único jeito de cortar um atalho vazado.

### Por que o atalho de importação tem credencial própria

O atalho roda dentro da página da SEFAZ e envia a nota de **outra origem**. O cookie de
sessão usa `SameSite=Lax`, que é justamente o que protege contra CSRF — e por isso não
acompanha um POST entre sites. Havia duas saídas: afrouxar o cookie para `SameSite=None`
(reabrindo CSRF em todas as rotas) ou dar ao atalho uma credencial restrita a uma rota.
A segunda foi a escolhida. O token é derivado da `SECRET_KEY` por HMAC, vale só para
`POST /notas/importar-html`, e se vazar permite **inserir** uma nota — não ler o
histórico, não apagar nada.

Consequência prática: **quem já tinha o atalho instalado precisa reinstalá-lo** pela tela
*Importar*, porque agora ele carrega o token na URL. O atalho antigo responde
"Atalho não autorizado" com instrução na própria aba.

### O que continua valendo

O Basic Auth do NPM (Access Lists) segue disponível e é **complementar**, não redundante:
ele barra antes da requisição chegar ao app. Se você usar os dois, o custo é digitar duas
senhas na primeira visita.

## 5. Backup

Os vínculos produto↔item e os itens digitados à mão **não são reconstruíveis** de
nenhuma fonte externa — se o disco morrer, o trabalho manual se perde junto. Configurar
antes de acumular dado que dói perder:

```bash
# ~/apps/acompanhamento-financas/backup.sh
set -euo pipefail
DESTINO=~/backups/financas
mkdir -p "$DESTINO"
docker compose -f ~/apps/acompanhamento-financas/docker-compose.yml \
  exec -T db pg_dump -U financas financas \
  | gzip > "$DESTINO/financas-$(date +%F).sql.gz"
# manter 30 dias
find "$DESTINO" -name 'financas-*.sql.gz' -mtime +30 -delete
```

```cron
0 3 * * * /bin/bash ~/apps/acompanhamento-financas/backup.sh
```

E copiar para **fora do disco físico do servidor** — o Nextcloud que já roda ali é o
mesmo disco, então serve de conveniência, não de backup. Um destino externo de verdade
(object storage gratuito, ou outra máquina) é o que fecha isso.

Restaurar:

```bash
gunzip -c financas-2026-08-09.sql.gz | docker compose exec -T db psql -U financas financas
```

## 6. Atualizar

```bash
cd ~/apps/acompanhamento-financas
git pull
docker compose up -d --build
```

As migrations rodam no start do backend. Não há deploy coordenado a respeitar: é um
usuário, e alguns segundos de indisponibilidade não custam nada.

## 7. Recursos

Estimativa: Postgres ~150–300 MB, backend ~150–250 MB, nginx ~15 MB — total abaixo de
600 MB. Folga confortável no servidor, mesmo com o resto do homelab rodando.

## 8. Quando algo quebra

| Sintoma | Onde olhar |
|---|---|
| 502 no NPM | `docker compose ps`; o backend pode estar reiniciando por falha de migration |
| `/health` diz `banco: indisponivel` | container `db` subiu? senha do `.env` mudou depois do primeiro `up`? |
| Todas as notas caem em `falhou_parse` | normal se as chaves estão sendo digitadas (`sem_url_qrcode`); se vierem de QR Code, ver `erro_detalhe` para distinguir `captcha` de `layout_mudou` |
| Scanner não abre | acesso está em HTTPS? permissão de câmera concedida? |
| Um parse quebrou depois de funcionar | `payload_bruto` da nota tem o HTML que o portal devolveu — é por onde começar |
