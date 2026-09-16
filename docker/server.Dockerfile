FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY serv_fich_multithread.py szasar.py ./
RUN mkdir -p /app/files \
    && useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app

USER appuser
EXPOSE 6012

HEALTHCHECK --interval=5s --timeout=3s --start-period=5s --retries=5 \
    CMD python -c "import socket; s=socket.create_connection(('127.0.0.1', 6012), 2); s.close()"

CMD ["python", "serv_fich_multithread.py"]
