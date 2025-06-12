# Makefile для управления разными средами

.PHONY: help dev-up dev-up-fast dev-down dev-logs dev-logs-api dev-build dev-rebuild dev-restart dev-shell prod-up prod-up-fast prod-down prod-logs prod-logs-api prod-logs-nginx prod-build prod-rebuild prod-restart setup-ssl clean init

# По умолчанию показываем помощь
help:
	@echo "Доступные команды:"
	@echo ""
	@echo "🛠️  DEVELOPMENT:"
	@echo "  make dev-up         - Запустить development (с автопересборкой)"
	@echo "  make dev-up-fast    - Запустить development (без пересборки)"
	@echo "  make dev-down       - Остановить development"
	@echo "  make dev-restart    - Перезапустить development"
	@echo "  make dev-build      - Пересобрать и запустить development"
	@echo "  make dev-rebuild    - Полная пересборка development"
	@echo "  make dev-logs       - Показать все логи development"
	@echo "  make dev-logs-api   - Показать логи только API"
	@echo "  make dev-shell      - Подключиться к API контейнеру"
	@echo ""
	@echo "🚀 PRODUCTION:"
	@echo "  make prod-up        - Запустить production (с автопересборкой)"
	@echo "  make prod-up-fast   - Запустить production (без пересборки)"
	@echo "  make prod-down      - Остановить production"
	@echo "  make prod-restart   - Перезапустить production"
	@echo "  make prod-build     - Пересобрать и запустить production"
	@echo "  make prod-rebuild   - Полная пересборка production"
	@echo "  make prod-logs      - Показать все логи production"
	@echo "  make prod-logs-api  - Показать логи только API"
	@echo "  make prod-logs-nginx - Показать логи только Nginx"
	@echo ""
	@echo "🔐 SSL & УТИЛИТЫ:"
	@echo "  make setup-ssl      - Настроить SSL для production (только первый раз)"
	@echo "  make clean          - Очистить все контейнеры и volumes"
	@echo "  make init           - Инициализация проекта"

# Development команды
dev-up:
	@echo "🚀 Запуск development среды..."
	@echo "🔍 Проверка изменений..."
	docker-compose -f docker-compose.dev.yml build
	docker-compose -f docker-compose.dev.yml up -d
	@echo "✅ Development среда запущена!"
	@echo "📱 API доступен на: http://localhost:8000"
	@echo "📚 Документация: http://localhost:8000/docs"
	@echo "🗄️  PostgreSQL: localhost:5444"

dev-up-fast:
	@echo "⚡ Быстрый запуск development среды (без пересборки)..."
	docker-compose -f docker-compose.dev.yml up -d
	@echo "✅ Development среда запущена!"

dev-down:
	@echo "🛑 Остановка development среды..."
	docker-compose -f docker-compose.dev.yml down

dev-restart:
	@echo "🔄 Перезапуск development среды..."
	docker-compose -f docker-compose.dev.yml restart

dev-logs:
	docker-compose -f docker-compose.dev.yml logs -f

dev-logs-api:
	docker-compose -f docker-compose.dev.yml logs -f api

dev-build:
	@echo "🔨 Пересборка development среды..."
	docker-compose -f docker-compose.dev.yml build --no-cache
	docker-compose -f docker-compose.dev.yml up -d

dev-rebuild:
	@echo "🔨 Полная пересборка development среды..."
	docker-compose -f docker-compose.dev.yml down
	docker-compose -f docker-compose.dev.yml build --no-cache
	docker-compose -f docker-compose.dev.yml up -d

dev-shell:
	docker-compose -f docker-compose.dev.yml exec api /bin/bash

# Production команды
prod-up:
	@echo "🚀 Запуск production среды..."
	@echo "🔍 Проверка изменений..."
	docker-compose -f docker-compose.prod.yml build
	docker-compose -f docker-compose.prod.yml up -d
	@echo "✅ Production среда запущена!"
	@echo "🌐 API доступен на: https://api.tensu.kz"

prod-up-fast:
	@echo "⚡ Быстрый запуск production среды (без пересборки)..."
	docker-compose -f docker-compose.prod.yml up -d
	@echo "✅ Production среда запущена!"

prod-down:
	@echo "🛑 Остановка production среды..."
	docker-compose -f docker-compose.prod.yml down

prod-restart:
	@echo "🔄 Перезапуск production среды..."
	docker-compose -f docker-compose.prod.yml restart

prod-logs:
	docker-compose -f docker-compose.prod.yml logs -f

prod-logs-api:
	docker-compose -f docker-compose.prod.yml logs -f api

prod-logs-nginx:
	docker-compose -f docker-compose.prod.yml logs -f nginx

prod-build:
	@echo "🔨 Пересборка production среды..."
	docker-compose -f docker-compose.prod.yml build --no-cache
	docker-compose -f docker-compose.prod.yml up -d

prod-rebuild:
	@echo "🔨 Полная пересборка production среды..."
	docker-compose -f docker-compose.prod.yml down
	docker-compose -f docker-compose.prod.yml build --no-cache
	docker-compose -f docker-compose.prod.yml up -d

# SSL setup
setup-ssl:
	@echo "🔐 Настройка SSL..."
	chmod +x setup-ssl.sh
	./setup-ssl.sh

# Очистка
clean:
	@echo "🧹 Очистка всех контейнеров и volumes..."
	docker-compose -f docker-compose.dev.yml down -v --remove-orphans 2>/dev/null || true
	docker-compose -f docker-compose.prod.yml down -v --remove-orphans 2>/dev/null || true
	docker system prune -f
	@echo "✅ Очистка завершена!"

# Инициализация проекта
init:
	@echo "🎯 Инициализация проекта..."
	@if [ ! -f .env.dev ]; then \
		echo "📝 Создание .env.dev..."; \
		echo "POSTGRES_USER=postgres" > .env.dev; \
		echo "POSTGRES_PASSWORD=postgres" >> .env.dev; \
		echo "POSTGRES_DB=mydatabase" >> .env.dev; \
		echo "POSTGRES_HOST=db" >> .env.dev; \
		echo "POSTGRES_PORT=5432" >> .env.dev; \
		echo "TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here" >> .env.dev; \
	fi
	@if [ -f .env ] && [ ! -f .env.prod ]; then \
		echo "📝 Переименование .env в .env.prod..."; \
		mv .env .env.prod; \
	fi
	@echo "✅ Инициализация завершена!"
	@echo "📝 Не забудьте настроить TELEGRAM_BOT_TOKEN в .env.dev"