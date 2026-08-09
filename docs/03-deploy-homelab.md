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

## 4. Autenticação — não deixe para depois

Diferente do `compara-precos` (preço público, sem risco em expor), aqui o conteúdo é o
seu histórico de compras. O caminho mais barato, sem escrever código:

**NPM → Access Lists → nova lista com usuário/senha → aplicar no Proxy Host.**

Login próprio no app (sessão/JWT) só se um dia o Basic Auth incomodar na PWA instalada —
é conforto, não segurança adicional neste cenário.

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
