# 1. Build del frontend
FROM node:20-alpine AS frontend-build
WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ .
RUN npm run build

# 2. Backend Python sirviendo también el frontend
FROM python:3.12-slim
WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .

# Copiar el build del frontend para servirlo como archivos estáticos
COPY --from=frontend-build /frontend/dist ./static

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port $PORT"]
