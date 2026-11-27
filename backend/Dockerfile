FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /srv/backend

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app
COPY scripts ./scripts

# Usuário sem privilégios; /srv/data guarda o banco SQLite (se usado), gravações e downloads do Argus
RUN useradd --system --uid 10001 crivo && mkdir -p /srv/data && chown -R crivo /srv/data
USER crivo

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"
# Um processo só: a fila de download das gravações e o agendador (alertas, polling) rodam dentro dele
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
