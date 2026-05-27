#!/bin/bash
# setup.sh
# Full server setup for Coffee Beans Price Tracker on Ubuntu 24 Hetzner VPS
# Run as root: bash setup.sh <your-domain.com>

set -euo pipefail

DOMAIN="${1:-}"
if [[ -z "$DOMAIN" ]]; then
  echo "Usage: bash setup.sh <your-domain.com>"
  exit 1
fi

DB_NAME="coffeebeans"
DB_USER="cbuser"
DB_PASS="$(openssl rand -base64 24)"
WP_DIR="/var/www/coffeebeans"
SCRAPERS_DIR="/opt/scrapers"
DATA_DIR="/opt/data"
ALERTS_DIR="/opt/alerts"
DRAFTS_DIR="/opt/drafts"

echo "==> Updating system packages"
apt-get update -qq
apt-get upgrade -y -qq

echo "==> Installing security basics"
apt-get install -y -qq ufw fail2ban curl wget unzip gnupg2 software-properties-common

# UFW firewall
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

# fail2ban config
cat > /etc/fail2ban/jail.local <<'EOF'
[DEFAULT]
bantime  = 1h
findtime = 10m
maxretry = 5

[sshd]
enabled = true

[nginx-http-auth]
enabled = true

[nginx-limit-req]
enabled = true
filter  = nginx-limit-req
action  = iptables-multiport[name=ReqLimit, port="http,https", protocol=tcp]
logpath = /var/log/nginx/error.log
findtime = 600
bantime  = 7200
maxretry = 10
EOF

systemctl enable fail2ban
systemctl restart fail2ban

echo "==> Installing Nginx"
apt-get install -y -qq nginx
systemctl enable nginx

echo "==> Installing PHP 8.2"
add-apt-repository -y ppa:ondrej/php
apt-get update -qq
apt-get install -y -qq \
  php8.2 php8.2-fpm php8.2-mysql php8.2-curl php8.2-gd php8.2-mbstring \
  php8.2-xml php8.2-zip php8.2-sqlite3 php8.2-intl php8.2-bcmath

systemctl enable php8.2-fpm

echo "==> Installing MariaDB"
apt-get install -y -qq mariadb-server
systemctl enable mariadb

# Secure MariaDB and create database
mysql -e "CREATE DATABASE IF NOT EXISTS \`${DB_NAME}\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
mysql -e "CREATE USER IF NOT EXISTS '${DB_USER}'@'localhost' IDENTIFIED BY '${DB_PASS}';"
mysql -e "GRANT ALL PRIVILEGES ON \`${DB_NAME}\`.* TO '${DB_USER}'@'localhost';"
mysql -e "FLUSH PRIVILEGES;"

echo "==> Installing Python 3 and dependencies"
apt-get install -y -qq python3 python3-pip python3-venv sqlite3

python3 -m venv /opt/venv
/opt/venv/bin/pip install --quiet --upgrade pip
/opt/venv/bin/pip install --quiet requests playwright anthropic

# Install Playwright browsers
/opt/venv/bin/python -m playwright install chromium
/opt/venv/bin/python -m playwright install-deps chromium

echo "==> Creating directory structure"
mkdir -p "${WP_DIR}"
mkdir -p "${SCRAPERS_DIR}"
mkdir -p "${DATA_DIR}"
mkdir -p "${ALERTS_DIR}"
mkdir -p "${DRAFTS_DIR}"
mkdir -p /var/www/coffeebeans/wp-content/plugins

chown -R www-data:www-data "${WP_DIR}"
chmod -R 755 "${WP_DIR}"
chown -R root:root "${SCRAPERS_DIR}" "${ALERTS_DIR}"
chmod -R 750 "${SCRAPERS_DIR}" "${ALERTS_DIR}"
chmod -R 770 "${DATA_DIR}" "${DRAFTS_DIR}"

echo "==> Downloading WordPress"
wget -q https://wordpress.org/latest.tar.gz -O /tmp/wordpress.tar.gz
tar -xzf /tmp/wordpress.tar.gz -C /tmp
cp -r /tmp/wordpress/. "${WP_DIR}/"
chown -R www-data:www-data "${WP_DIR}"

# wp-config.php
cp "${WP_DIR}/wp-config-sample.php" "${WP_DIR}/wp-config.php"
sed -i "s/database_name_here/${DB_NAME}/" "${WP_DIR}/wp-config.php"
sed -i "s/username_here/${DB_USER}/" "${WP_DIR}/wp-config.php"
sed -i "s/password_here/${DB_PASS}/" "${WP_DIR}/wp-config.php"

# Inject unique auth keys
WP_SALTS=$(curl -s https://api.wordpress.org/secret-key/1.1/salt/)
sed -i "/AUTH_KEY/,/NONCE_SALT/d" "${WP_DIR}/wp-config.php"
sed -i "/\/\*\*#\@-\*\//i ${WP_SALTS}" "${WP_DIR}/wp-config.php"

echo "==> Configuring Nginx for ${DOMAIN}"
cat > /etc/nginx/sites-available/coffeebeans <<EOF
server {
    listen 80;
    server_name ${DOMAIN} www.${DOMAIN};
    root ${WP_DIR};
    index index.php index.html;

    client_max_body_size 64M;

    location / {
        try_files \$uri \$uri/ /index.php?\$args;
    }

    location ~ \.php\$ {
        include snippets/fastcgi-php.conf;
        fastcgi_pass unix:/run/php/php8.2-fpm.sock;
        fastcgi_param SCRIPT_FILENAME \$document_root\$fastcgi_script_name;
        include fastcgi_params;
    }

    location ~ /\.ht {
        deny all;
    }

    location = /favicon.ico { log_not_found off; access_log off; }
    location = /robots.txt  { log_not_found off; access_log off; }

    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)\$ {
        expires max;
        log_not_found off;
    }

    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml;
}
EOF

ln -sf /etc/nginx/sites-available/coffeebeans /etc/nginx/sites-enabled/coffeebeans
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx

echo "==> Installing Certbot and requesting SSL certificate"
apt-get install -y -qq certbot python3-certbot-nginx
certbot --nginx -d "${DOMAIN}" -d "www.${DOMAIN}" --non-interactive --agree-tos -m "admin@${DOMAIN}"

echo "==> Setting up cron jobs for scrapers"
CRON_FILE="/etc/cron.d/coffeebeans"
cat > "${CRON_FILE}" <<'EOF'
# Coffee Beans scraper cron jobs
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin

0 6 * * * root /opt/venv/bin/python3 /opt/scrapers/price_scraper.py >> /opt/data/scraper.log 2>&1
15 6 * * * root /opt/venv/bin/python3 /opt/alerts/send_alerts.py >> /opt/data/alerts.log 2>&1
EOF

chmod 644 "${CRON_FILE}"

echo ""
echo "=============================="
echo " Setup complete!"
echo "=============================="
echo ""
echo "Domain:        https://${DOMAIN}"
echo "WordPress dir: ${WP_DIR}"
echo "Scrapers:      ${SCRAPERS_DIR}"
echo "Data/DB:       ${DATA_DIR}"
echo "Alerts:        ${ALERTS_DIR}"
echo ""
echo "MariaDB credentials (save these):"
echo "  Database: ${DB_NAME}"
echo "  User:     ${DB_USER}"
echo "  Password: ${DB_PASS}"
echo ""
echo "Next steps:"
echo "  1. Copy your scraper files to ${SCRAPERS_DIR}/"
echo "  2. Copy your alerts script to ${ALERTS_DIR}/"
echo "  3. Create /opt/.env with your API keys (see .env.example)"
echo "  4. Visit https://${DOMAIN}/wp-admin/install.php to finish WordPress setup"
echo "  5. Install plugins: RankMath, WP Rocket, coffee-price-chart (custom), WPForms Lite"
