FROM python:3.12-slim

WORKDIR /app
ENV PYTHONPATH=/app
ENV CONFIG_PATH=/app/config/config.json

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ app/
COPY static/ static/

EXPOSE 5000

HEALTHCHECK --interval=60s --timeout=5s --start-period=10s --retries=3 \
    CMD cat /tmp/heartbeat || exit 1

CMD ["python", "-u", "app/main.py"]
