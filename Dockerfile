FROM python:3.12-slim

WORKDIR /app
ENV PYTHONPATH=/app
ENV CONFIG_PATH=/app/config/config.json

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ app/
COPY static/ static/

EXPOSE 5000

HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD ["python", "app/healthcheck.py"]

CMD ["python", "-u", "app/main.py"]
