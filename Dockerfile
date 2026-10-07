FROM python:3.12-slim

WORKDIR /app
ENV PYTHONPATH=/app
ENV CONFIG_PATH=/app/config/config.json

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ app/
COPY static/ static/

# Usuario sem privilegio: um comprometimento dentro do container nao deve
# render root, e o volume de configuracao nao deve ficar com arquivos de root
# no host. UID 1000 e o primeiro usuario comum na maioria das distros, entao
# um bind mount de `./config` costuma casar sem ajuste.
RUN useradd --uid 1000 --create-home --shell /usr/sbin/nologin guardian \
    && mkdir -p /app/config \
    && chown -R guardian:guardian /app

USER guardian

EXPOSE 5000

HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD ["python", "app/healthcheck.py"]

CMD ["python", "-u", "app/main.py"]
