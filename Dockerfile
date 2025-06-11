FROM python:3.13-slim

# Установка OpenSSL для генерации сертификатов
RUN apt-get update && apt-get install -y openssl && rm -rf /var/lib/apt/lists/*

# Рабочая директория
WORKDIR /app

# Копируем зависимости
COPY requirements.txt .

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код приложения
COPY ./app ./app

# Создаем директорию для SSL
RUN mkdir -p /app/ssl

# Генерируем самоподписанный сертификат
RUN openssl genrsa -out /app/ssl/key.pem 2048 && \
    openssl req -new -x509 -key /app/ssl/key.pem -out /app/ssl/cert.pem -days 365 \
    -subj "/C=KZ/ST=Almaty/L=Almaty/O=Training App/CN=195.49.215.106"

# Expose HTTPS port
EXPOSE 8000

# Команда запуска FastAPI с SSL
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--ssl-keyfile", "/app/ssl/key.pem", "--ssl-certfile", "/app/ssl/cert.pem"]