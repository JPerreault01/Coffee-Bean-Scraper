#!/bin/bash
# setup.sh — Ubuntu 24 VPS setup for Coffee Beans Price Tracker & Review Site
# Usage: bash setup.sh yourcoffeebeans.com
# Run as root on a fresh Hetzner CX23 (Ubuntu 24)

set -euo pipefail

DOMAIN="${1:-}"
if [[ -z "$DOMAIN" ]]; then
  echo "Usage: bash setup.sh yourcoffeebeans.com"
  exit 1
fi

echo "==> Setting up Coffee Beans site for domain: $DOMAIN"

# --- System update and security basics ---
apt-get update -y
apt-get upgrade -y
apt-get install -y \
  ufw \
  fail2ban \
  curl \
  wget \
  unzip \
  git \
  software-properties-common \
  ca-certificates \
  gnupg

echo "==> Configuring firewall (ufw)"
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

echo "==> Configuring fail2ban"
systemctl enable fail2ban
systemctl start fail2ban

# --- Nginx ---
echo "==> Installing Nginx"
apt-get install -y nginx
systemctl enable nginx

# --- PHP 8.2 ---
echo "==> Installing PHP 8.2"
add-apt-repository ppa:ondrej/php -y
apt-get update -y
apt-get install -y \
  php8.2 \
  php8.2-fpm \
  php8.2-mysql \
  php8.2-curl \
  php8.2-gd \
  php8.2-mbstring \
  php8.2-xml \
  php8.2-xmlrpc \
  php8.2-zip \
  php8.2-sqlite3 \
  php8.2-intl \
  php8.2-bcmath \
  php8.2-imagick

systemctl enable php8.2-fpm

# --- MariaDB ---
echo "==> Installing MariaDB"
apt-get install -y mariadb-server
systemctl enable mariadb

DB_NAME="wordpress"
DB_USER="wpuser"
DB_PASS=$(openssl rand -base64 24 | tr -dc 'a-zA-Z0-9' | head -c 24)

mysql -u root <<SQL
CREATE DATABASE IF NOT EXISTS ${DB_NAME} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS '${DB_USER}'@'localhost' IDENTIFIED BY '${DB_PASS}';
GRANT ALL PRIVILEGES ON ${DB_NAME}.* TO '${DB_USER}'@'localhost';
FLUSH PRIVILEGES;
SQL

echo "==> MariaDB credentials:"
echo "    Database: $DB_NAME"
echo "    User:     $DB_USER"
echo "    Password: $DB_PASS"
echo "    (Save these — you'll need them during WordPress setup)"

# --- WordPress ---
echo "==> Installing WordPress"
mkdir -p /var/www/coffeebeans
cd /tmp
wget -q https://wordpress.org/latest.tar.gz
tar xzf latest.tar.gz
cp -r wordpress/. /var/www/coffeebeans/
chown -R www-data:www-data /var/www/coffeebeans
chmod -R 755 /var/www/coffeebeans

cp /var/www/coffeebeans/wp-config-sample.php /var/www/coffeebeans/wp-config.php
sed -i "s/database_name_here/${DB_NAME}/" /var/www/coffeebeans/wp-config.php
sed -i "s/username_here/${DB_USER}/" /var/www/coffeebeans/wp-config.php
sed -i "s/password_here/${DB_PASS}/" /var/www/coffeebeans/wp-config.php

# Generate unique auth keys and salts
SALT=$(curl -s https://api.wordpress.org/secret-key/1.1/salt/)
# Remove the placeholder block and replace with real salts
python3 - <<PYEOF
import re

with open('/var/www/coffeebeans/wp-config.php', 'r') as f:
    content = f.read()

salt = """$SALT"""

# Replace the define(AUTH_KEY...) block with real salts
pattern = r"define\('AUTH_KEY'.*?define\('NONCE_SALT'.*?\);"
content = re.sub(pattern, salt.strip(), content, flags=re.DOTALL)

with open('/var/www/coffeebeans/wp-config.php', 'w') as f:
    f.write(content)
PYEOF

# --- Nginx config for WordPress ---
echo "==> Configuring Nginx for $DOMAIN"
cat > /etc/nginx/sites-available/coffeebeans <<NGINX
server {
    listen 80;
    server_name ${DOMAIN} www.${DOMAIN};
    root /var/www/coffeebeans;
    index index.php index.html;

    client_max_body_size 64M;

    location / {
        try_files \$uri \$uri/ /index.php?\$args;
    }

    location ~ \.php$ {
        include snippets/fastcgi-php.conf;
        fastcgi_pass unix:/var/run/php/php8.2-fpm.sock;
        fastcgi_param SCRIPT_FILENAME \$document_root\$fastcgi_script_name;
        include fastcgi_params;
    }

    location ~ /\.ht {
        deny all;
    }

    location = /favicon.ico { log_not_found off; access_log off; }
    location = /robots.txt  { log_not_found off; access_log off; allow all; }
    location ~* \.(css|gif|ico|jpeg|jpg|js|png|webp|woff|woff2)$ {
        expires max;
        log_not_found off;
    }
}
NGINX

ln -sf /etc/nginx/sites-available/coffeebeans /etc/nginx/sites-enabled/coffeebeans
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx

# --- Certbot / Let's Encrypt ---
echo "==> Installing Certbot"
apt-get install -y certbot python3-certbot-nginx

echo "==> Obtaining SSL certificate for $DOMAIN"
certbot --nginx -d "$DOMAIN" -d "www.$DOMAIN" \
  --non-interactive \
  --agree-tos \
  --email "admin@${DOMAIN}" \
  --redirect

# Auto-renew cron
echo "0 3 * * * root certbot renew --quiet" > /etc/cron.d/certbot-renew

# --- Python 3 + venv ---
echo "==> Setting up Python environment"
apt-get install -y python3 python3-pip python3-venv python3-dev
python3 -m venv /opt/venv
/opt/venv/bin/pip install --upgrade pip
/opt/venv/bin/pip install requests playwright anthropic

# Install Playwright Chromium browser
/opt/venv/bin/python -m playwright install chromium
/opt/venv/bin/python -m playwright install-deps chromium

# --- Directory structure ---
echo "==> Creating project directories"
mkdir -p /opt/scrapers
mkdir -p /opt/data
mkdir -p /opt/alerts
mkdir -p /opt/drafts

chown -R www-data:www-data /opt/data
chmod 755 /opt/data

# --- Cron entries ---
echo "==> Writing cron jobs"
cat > /etc/cron.d/coffeebeans <<CRON
# Coffee Beans Price Tracker
0 6 * * * root /opt/venv/bin/python3 /opt/scrapers/price_scraper.py >> /opt/data/scraper.log 2>&1
15 6 * * * root /opt/venv/bin/python3 /opt/alerts/send_alerts.py >> /opt/data/alerts.log 2>&1
CRON

chmod 644 /etc/cron.d/coffeebeans

# --- PHP SQLite permissions ---
# Allow www-data to read the SQLite database for WordPress plugin
echo "==> Setting SQLite permissions for WordPress plugin"
cat >> /etc/sudoers.d/www-data-sqlite <<SUDO
www-data ALL=(ALL) NOPASSWD: /bin/chmod 664 /opt/data/prices.db
SUDO

echo ""
echo "======================================================"
echo " Setup complete!"
echo "======================================================"
echo ""
echo " Next steps:"
echo "  1. Copy your scraper files to /opt/scrapers/"
echo "  2. Copy your alert files to /opt/alerts/"
echo "  3. Create /opt/.env with your API keys (see .env.example)"
echo "  4. Visit https://${DOMAIN}/wp-admin/install.php to finish WordPress setup"
echo "  5. Install the coffee-price-chart WordPress plugin"
echo ""
echo " MariaDB credentials (save these):"
echo "   DB Name:  $DB_NAME"
echo "   DB User:  $DB_USER"
echo "   DB Pass:  $DB_PASS"
echo ""
