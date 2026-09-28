FROM python:3.12-slim

WORKDIR /app

# Deps antes do código: layer de cache não invalida a cada mudança em src/.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/
COPY config/ config/

ENV PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1

# Não é o que expõe a porta pra internet — isso é o compose + o label do
# Traefik na rede `edge`. Aqui é só documentação da porta que o processo escuta.
EXPOSE 8080

CMD ["python", "-m", "monitor.server"]
