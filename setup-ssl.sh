#!/bin/bash

# Замените на ваш домен
DOMAIN="tensu.kz"
EMAIL="tensu@example.com"

echo "Setting up SSL for domain: $DOMAIN"

# Создаем необходимые директории
mkdir -p certbot/conf
mkdir -p certbot/www

# Временная конфигурация Nginx для получения сертификата
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
            root /var/www/certbot;
            try_files \$uri \$uri/ =404;
        }
    }
}
EOF

echo "Starting temporary Nginx for certificate acquisition..."

# Запускаем временный Nginx
docker run --rm -d \
    --name temp-nginx \
    -p 80:80 \
    -v $(pwd)/nginx-temp.conf:/etc/nginx/nginx.conf \
    -v $(pwd)/certbot/www:/var/www/certbot \
    nginx:alpine

# Ждем запуска Nginx
sleep 5

echo "Requesting SSL certificate from Let's Encrypt..."

# Получаем SSL сертификат
docker run --rm \
    -v $(pwd)/certbot/conf:/etc/letsencrypt \
    -v $(pwd)/certbot/www:/var/www/certbot \
    certbot/certbot \
    certonly --webroot -w /var/www/certbot \
    --email $EMAIL \
    --agree-tos \
    --no-eff-email \
    -d $DOMAIN \
    -d www.$DOMAIN

# Останавливаем временный Nginx
docker stop temp-nginx

# Удаляем временную конфигурацию
rm nginx-temp.conf

echo "SSL certificate obtained successfully!"
echo "Now update nginx.conf with your domain name and run: docker-compose up -d"

# Показываем статус сертификата
echo "Certificate details:"
docker run --rm \
    -v $(pwd)/certbot/conf:/etc/letsencrypt \
    certbot/certbot \
    certificates