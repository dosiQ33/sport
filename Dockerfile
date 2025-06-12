FROM python:3.13-slim

# Установка переменной среды
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Создание пользователя для безопасности
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Рабочая директория
WORKDIR /app

# Установка системных зависимостей
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Копируем зависимости
COPY requirements.txt .

# Устанавливаем зависимости
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Копируем код приложения
COPY ./app ./app

# Создаем директории для логов
RUN mkdir -p /app/logs && chown -R appuser:appuser /app

# Переключаемся на пользователя приложения
USER appuser

# Expose HTTP port
EXPOSE 8000

# Команда по умолчанию (может быть переопределена в docker-compose)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]