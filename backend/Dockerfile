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
# --no-server-header: não expõe "server: uvicorn". --proxy-headers: o IP do cliente vem do X-Forwarded-For só quando
# a requisição chega de FORWARDED_ALLOW_IPS (o proxy; padrão 127.0.0.1), usado no limite de tentativas de login.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1 --no-server-header --proxy-headers --forwarded-allow-ips=${FORWARDED_ALLOW_IPS:-127.0.0.1}"]
