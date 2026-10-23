FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY config.py config.toml.example ./
RUN cp config.toml.example config.toml
COPY auth.py file_store.py replication.py server_runtime.py serv_fich_multithread.py szasar.py tls.py ./
RUN mkdir -p /app/files /app/certs \
    && useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app

USER appuser
EXPOSE 50012 60012

HEALTHCHECK --interval=5s --timeout=3s --start-period=5s --retries=5 \
    CMD python -c "import os,ssl,socket; ctx=ssl.create_default_context(cafile=os.environ.get('TLS_CA_FILE','/app/certs/ca.crt')); s=ctx.wrap_socket(socket.create_connection(('127.0.0.1', int(os.environ.get('SERVER_PORT','50012'))), 3), server_hostname=os.environ.get('TLS_SERVER_NAME','localhost')); s.close()"

CMD ["python", "serv_fich_multithread.py"]
