FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TZ=America/Sao_Paulo
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY alembic.ini ./
COPY migrations ./migrations
COPY app ./app
EXPOSE 8000
# Atualiza o banco (migrações do Alembic) e sobe a API.
# Um único worker: o agendador de rotinas roda dentro do processo da API
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1"]
