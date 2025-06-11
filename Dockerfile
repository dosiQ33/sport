FROM python:3.13-slim

# Рабочая директория
WORKDIR /app

# Копируем зависимости
COPY requirements.txt .

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код приложения
COPY ./app ./app

# Expose HTTP port (SSL будет обрабатывать Nginx)
EXPOSE 8000

# Команда запуска FastAPI без SSL (HTTP только)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]