#!/bin/bash

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Замените на ваш домен и email
DOMAIN="tensu.kz"
EMAIL="tensu@example.com"

echo -e "${GREEN}Setting up SSL for domain: $DOMAIN${NC}"

# Проверяем, что домен установлен
if [ "$DOMAIN" = "tensu.kz" ]; then
    echo -e "${YELLOW}Please update EMAIL variable in this script before running${NC}"
    read -p "Enter your email for Let's Encrypt: " EMAIL
fi

# Создаем необходимые директории
echo -e "${YELLOW}Creating directories...${NC}"
mkdir -p certbot/conf
mkdir -p certbot/www

# Останавливаем существующие контейнеры, если они запущены
echo -e "${YELLOW}Stopping existing containers...${NC}"
docker stop temp-nginx 2>/dev/null || true
docker rm temp-nginx 2>/dev/null || true

# Временная конфигурация Nginx для получения сертификата
echo -e "${YELLOW}Creating temporary Nginx configuration...${NC}"
cat > nginx-temp.conf << EOF
events {
    worker_connections 1024;
}

http {
    server {
        listen 80;
        server_name $DOMAIN www.$DOMAIN;

        location /.well-known/acme-challenge/ {
            root /var/www/certbot;
        }

        location / {
            return 200 'OK';
            add_header Content-Type text/plain;
        }
    }
}
EOF

echo -e "${YELLOW}Starting temporary Nginx for certificate acquisition...${NC}"

# Запускаем временный Nginx
docker run --rm -d \
    --name temp-nginx \
    -p 80:80 \
    -v $(pwd)/nginx-temp.conf:/etc/nginx/nginx.conf \
    -v $(pwd)/certbot/www:/var/www/certbot \
    nginx:alpine

if [ $? -ne 0 ]; then
    echo -e "${RED}Failed to start temporary Nginx${NC}"
    exit 1
fi

# Ждем запуска Nginx
echo -e "${YELLOW}Waiting for Nginx to start...${NC}"
sleep 10

# Проверяем, что Nginx запущен
if ! docker ps | grep -q temp-nginx; then
    echo -e "${RED}Temporary Nginx failed to start${NC}"
    exit 1
fi

echo -e "${YELLOW}Testing domain accessibility...${NC}"
curl -f http://$DOMAIN/.well-known/acme-challenge/test 2>/dev/null || echo -e "${YELLOW}Domain test request completed${NC}"

echo -e "${GREEN}Requesting SSL certificate from Let's Encrypt...${NC}"

# Получаем SSL сертификат
docker run --rm \
    -v $(pwd)/certbot/conf:/etc/letsencrypt \
    -v $(pwd)/certbot/www:/var/www/certbot \
    certbot/certbot \
    certonly --webroot -w /var/www/certbot \
    --email $EMAIL \
    --agree-tos \
    --no-eff-email \
    --non-interactive \
    --expand \
    -d $DOMAIN \
    -d www.$DOMAIN

CERTBOT_EXIT_CODE=$?

# Останавливаем временный Nginx
echo -e "${YELLOW}Stopping temporary Nginx...${NC}"
docker stop temp-nginx 2>/dev/null || true

# Удаляем временную конфигурацию
rm -f nginx-temp.conf

if [ $CERTBOT_EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}SSL certificate obtained successfully!${NC}"
    
    # Показываем статус сертификата
    echo -e "${GREEN}Certificate details:${NC}"
    docker run --rm \
        -v $(pwd)/certbot/conf:/etc/letsencrypt \
        certbot/certbot \
        certificates
    
    echo -e "${GREEN}Setup completed! Now you can:${NC}"
    echo -e "${YELLOW}1. Update nginx.conf with your domain name ($DOMAIN)${NC}"
    echo -e "${YELLOW}2. Run: docker-compose up -d${NC}"
    
    # Проверяем, что сертификаты созданы
    if [ -f "certbot/conf/live/$DOMAIN/fullchain.pem" ]; then
        echo -e "${GREEN}✓ SSL certificates are ready${NC}"
    else
        echo -e "${RED}✗ SSL certificate files not found${NC}"
    fi
    
else
    echo -e "${RED}Failed to obtain SSL certificate${NC}"
    echo -e "${YELLOW}Common issues:${NC}"
    echo -e "${YELLOW}1. Make sure your domain DNS points to this server${NC}"
    echo -e "${YELLOW}2. Check that ports 80 and 443 are open${NC}"
    echo -e "${YELLOW}3. Verify domain ownership${NC}"
    echo -e "${YELLOW}4. Try running: dig $DOMAIN${NC}"
    exit 1
fi