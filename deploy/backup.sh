#!/usr/bin/env sh
# Backup diário do banco da Rede de Vendas, para rodar no servidor via cron:
#
#   crontab -e
#   30 3 * * * /caminho/para/rede_vendas/deploy/backup.sh >> /var/log/rede_vendas_backup.log 2>&1
#
# Faz uma cópia consistente (segura com o sistema em uso), guarda os últimos DIAS backups no
# volume e copia o mais recente para DESTINO_EXTERNO, fora do volume do Docker.
# Um backup que fica só no mesmo servidor não protege contra a perda do servidor:
# leve o DESTINO_EXTERNO para outro lugar (outro disco, nuvem, rclone etc.).

set -eu

DIAS="${DIAS:-14}"
DESTINO_EXTERNO="${DESTINO_EXTERNO:-$HOME/backups_rede_vendas}"
PASTA_PROJETO="$(cd "$(dirname "$0")/.." && pwd)"

cd "$PASTA_PROJETO"
echo "[$(date '+%F %T')] iniciando backup"

docker compose exec -T app python -m rede_vendas backup /dados/backups
docker compose exec -T app find /dados/backups -name 'rede_vendas_*.db' -mtime "+$DIAS" -delete

mkdir -p "$DESTINO_EXTERNO"
ULTIMO="$(docker compose exec -T app sh -c 'ls -1t /dados/backups/rede_vendas_*.db | head -n 1')"
docker compose cp "app:$ULTIMO" "$DESTINO_EXTERNO/"
find "$DESTINO_EXTERNO" -name 'rede_vendas_*.db' -mtime "+$DIAS" -delete

echo "[$(date '+%F %T')] backup concluído: $DESTINO_EXTERNO/$(basename "$ULTIMO")"
