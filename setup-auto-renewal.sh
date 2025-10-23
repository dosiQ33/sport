#!/bin/bash

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}=== Setting up Auto-Renewal for SSL Certificates ===${NC}\n"

# Step 1: Test current nginx ACME challenge configuration
echo -e "${YELLOW}Step 1: Testing nginx ACME challenge path...${NC}"
mkdir -p certbot/www/.well-known/acme-challenge
echo "test-file" > certbot/www/.well-known/acme-challenge/test.txt

sleep 2
if curl -f http://api.tensu.kz/.well-known/acme-challenge/test.txt 2>/dev/null | grep -q "test-file"; then
    echo -e "${GREEN}✓ Nginx ACME challenge path is working!${NC}"
else
    echo -e "${RED}✗ Nginx ACME challenge path is NOT working!${NC}"
    echo -e "${YELLOW}This needs to be fixed for auto-renewal to work${NC}"
fi

rm certbot/www/.well-known/acme-challenge/test.txt

# Step 2: Backup current docker-compose.prod.yml
echo -e "\n${YELLOW}Step 2: Backing up current docker-compose.prod.yml...${NC}"
if [ -f docker-compose.prod.yml ]; then
    cp docker-compose.prod.yml docker-compose.prod.yml.backup.$(date +%Y%m%d_%H%M%S)
    echo -e "${GREEN}✓ Backup created${NC}"
fi

# Step 3: Update docker-compose.prod.yml
echo -e "\n${YELLOW}Step 3: Updating docker-compose.prod.yml with new certbot configuration...${NC}"

cat > docker-compose.prod.yml << 'EOF'
version: "3.9"

services:
  db:
    image: postgres:latest
    container_name: training_postgres
    env_file:
      - .env
    ports:
      - "5444:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    networks:
      - app-network

  api:
    build: .
    container_name: training_app
    depends_on:
      - db
    env_file:
      - .env
    expose:
      - "8000"
    volumes:
      - ./app:/app/app
    networks:
      - app-network

  nginx:
    image: nginx:alpine
    container_name: training_nginx
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
      - ./certbot/conf:/etc/letsencrypt
      - ./certbot/www:/var/www/certbot
    depends_on:
      - api
    networks:
      - app-network

  certbot:
    image: certbot/certbot
    container_name: training_certbot
    restart: unless-stopped
    volumes:
      - ./certbot/conf:/etc/letsencrypt
      - ./certbot/www:/var/www/certbot
    entrypoint: "/bin/sh -c 'trap exit TERM; while :; do certbot renew --webroot -w /var/www/certbot --quiet; sleep 21d & wait $${!}; done;'"
    depends_on:
      - nginx
    networks:
      - app-network

volumes:
  postgres_data:

networks:
  app-network:
    driver: bridge
EOF

echo -e "${GREEN}✓ docker-compose.prod.yml updated${NC}"

# Step 4: Test renewal with dry-run
echo -e "\n${YELLOW}Step 4: Testing certificate renewal (dry-run)...${NC}"
docker run --rm \
    -v $(pwd)/certbot/conf:/etc/letsencrypt \
    -v $(pwd)/certbot/www:/var/www/certbot \
    certbot/certbot \
    renew --webroot -w /var/www/certbot --dry-run

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Dry-run renewal successful!${NC}"
else
    echo -e "${RED}✗ Dry-run renewal failed${NC}"
    echo -e "${YELLOW}Auto-renewal may not work properly${NC}"
fi

# Step 5: Restart with new configuration
echo -e "\n${YELLOW}Step 5: Restarting containers with new configuration...${NC}"
docker compose -f docker-compose.prod.yml down
docker compose -f docker-compose.prod.yml up -d

echo -e "${GREEN}✓ Containers restarted${NC}"

# Step 6: Verify certbot is running
echo -e "\n${YELLOW}Step 6: Verifying certbot container...${NC}"
sleep 5
if docker ps | grep -q training_certbot; then
    echo -e "${GREEN}✓ Certbot container is running${NC}"
else
    echo -e "${RED}✗ Certbot container is not running${NC}"
fi

# Step 7: Create monitoring script
echo -e "\n${YELLOW}Step 7: Creating SSL expiry monitoring script...${NC}"

cat > ~/check-ssl-expiry.sh << 'EOFMON'
#!/bin/bash
CERT_FILE="/home/ubuntu/sport/certbot/conf/live/api.tensu.kz/fullchain.pem"

if [ ! -f "$CERT_FILE" ]; then
    echo "ERROR: Certificate file not found!"
    exit 1
fi

EXPIRY_DATE=$(openssl x509 -enddate -noout -in "$CERT_FILE" | cut -d= -f2)
EXPIRY_EPOCH=$(date -d "$EXPIRY_DATE" +%s)
NOW_EPOCH=$(date +%s)
DAYS_UNTIL_EXPIRY=$(( ($EXPIRY_EPOCH - $NOW_EPOCH) / 86400 ))

echo "SSL Certificate Status:"
echo "  Expires: $EXPIRY_DATE"
echo "  Days remaining: $DAYS_UNTIL_EXPIRY"

if [ $DAYS_UNTIL_EXPIRY -lt 7 ]; then
    echo "  Status: CRITICAL - Certificate expires in less than 7 days!"
    exit 2
elif [ $DAYS_UNTIL_EXPIRY -lt 30 ]; then
    echo "  Status: WARNING - Certificate expires in less than 30 days"
    exit 1
else
    echo "  Status: OK"
    exit 0
fi
EOFMON

chmod +x ~/check-ssl-expiry.sh
echo -e "${GREEN}✓ Monitoring script created at ~/check-ssl-expiry.sh${NC}"

# Step 8: Show current certificate status
echo -e "\n${YELLOW}Step 8: Current certificate status...${NC}"
~/check-ssl-expiry.sh

# Step 9: Setup cron job
echo -e "\n${YELLOW}Step 9: Setting up daily certificate check...${NC}"
(crontab -l 2>/dev/null | grep -v check-ssl-expiry; echo "0 6 * * * /home/ubuntu/check-ssl-expiry.sh >> /home/ubuntu/ssl-check.log 2>&1") | crontab -
echo -e "${GREEN}✓ Daily cron job added (runs at 6 AM)${NC}"

# Summary
echo -e "\n${BLUE}=== Setup Complete ===${NC}"
echo -e "${GREEN}✓ Auto-renewal is now configured${NC}"
echo -e "${GREEN}✓ Certbot will check for renewal every 21 days${NC}"
echo -e "${GREEN}✓ Certificates will auto-renew when they have 30 days left${NC}"
echo -e "${GREEN}✓ Daily monitoring is set up${NC}"

echo -e "\n${YELLOW}What happens now:${NC}"
echo -e "  • Certbot checks renewal every 21 days"
echo -e "  • Renewal happens automatically if certificate expires in < 30 days"
echo -e "  • Daily check logs to ~/ssl-check.log"
echo -e "  • You can manually check anytime: ~/check-ssl-expiry.sh"

echo -e "\n${YELLOW}Manual renewal test command:${NC}"
echo -e "  docker exec training_certbot certbot renew --webroot -w /var/www/certbot --dry-run"

echo -e "\n${YELLOW}Check certbot logs:${NC}"
echo -e "  docker logs training_certbot"

echo -e "\n${GREEN}All done! Your SSL will now renew automatically. 🎉${NC}"
