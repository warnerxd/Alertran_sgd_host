#!/bin/bash
# Ejecutar como root en el VPS Ubuntu 24.04
# ssh root@187.124.236.73  y luego: bash setup_vps.sh

set -e

APP_DIR="/opt/alertran_sgd"
VENV="$APP_DIR/venv"

echo "=== 1. Dependencias del sistema ==="
apt-get update -q
apt-get install -y python3 python3-venv python3-pip nginx rsync

echo "=== 2. Crear directorio de la aplicación ==="
mkdir -p "$APP_DIR"

echo "=== 3. Entorno virtual ==="
python3 -m venv "$VENV"
"$VENV/bin/pip" install --upgrade pip

echo "=== 4. Instalar dependencias Python ==="
"$VENV/bin/pip" install -r "$APP_DIR/requirements.txt"

echo "=== 5. Instalar navegadores Playwright ==="
"$VENV/bin/playwright" install chromium
"$VENV/bin/playwright" install-deps chromium

echo "=== 6. Instalar servicio systemd ==="
cp "$APP_DIR/deploy/alertran-sgd.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable alertran-sgd
systemctl restart alertran-sgd
systemctl status alertran-sgd --no-pager

echo "=== 7. Configurar nginx ==="
# Asegurarse que el bloque map esté en nginx.conf (sólo si no existe)
if ! grep -q "connection_upgrade" /etc/nginx/nginx.conf; then
    sed -i '/http {/a\\tmap $http_upgrade $connection_upgrade {\n\t\tdefault upgrade;\n\t\t'"''"' close;\n\t}' /etc/nginx/nginx.conf
fi

echo ""
echo "IMPORTANTE: Agrega manualmente el bloque location al server block de nginx."
echo "Ver: $APP_DIR/deploy/nginx_alertran_sgd.conf"
echo ""
echo "Luego: nginx -t && systemctl reload nginx"
