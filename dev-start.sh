#!/bin/bash
# dev-start.sh - Скрипт для быстрого запуска development среды

echo "🚀 Запуск Training API в development режиме..."

# Проверяем наличие .env.dev
if [ ! -f .env.dev ]; then
    echo "📝 Создание .env.dev..."
    cat > .env.dev << EOF
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=mydatabase
POSTGRES_HOST=db
POSTGRES_PORT=5432
TELEGRAM_BOT_TOKEN_STAFF=your_telegram_bot_token_here
EOF
    echo "⚠️  Пожалуйста, настройте TELEGRAM_BOT_TOKEN_STAFF в .env.dev"
fi

# Останавливаем production если запущен
docker-compose -f docker-compose.prod.yml down 2>/dev/null || true

# Запускаем development
docker-compose -f docker-compose.dev.yml up -d

echo ""
echo "✅ Development среда запущена!"
echo ""
echo "📱 API endpoints:"
echo "   🌐 http://localhost:8000"
echo "   📚 http://localhost:8000/docs (Swagger UI)"
echo "   🔍 http://localhost:8000/redoc (ReDoc)"
echo ""
echo "🗄️  Database:"
echo "   📊 PostgreSQL: localhost:5444"
echo "   👤 User: postgres"
echo "   🔑 Password: postgres"
echo "   🏷️  Database: mydatabase"
echo ""
echo "🔧 Полезные команды:"
echo "   📋 Логи API: docker-compose -f docker-compose.dev.yml logs -f api"
echo "   📋 Логи БД:  docker-compose -f docker-compose.dev.yml logs -f db"
echo "   🛑 Остановить: docker-compose -f docker-compose.dev.yml down"
echo "   🔄 Перезапуск: docker-compose -f docker-compose.dev.yml restart"
echo ""

# Ждем запуска API
echo "⏳ Ожидание запуска API..."
for i in {1..30}; do
    if curl -f http://localhost:8000/health 2>/dev/null; then
        echo "✅ API готов к работе!"
        break
    fi
    if [ $i -eq 30 ]; then
        echo "⚠️  API не отвечает, проверьте логи: docker-compose -f docker-compose.dev.yml logs api"
    fi
    sleep 2
done