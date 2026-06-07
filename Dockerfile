FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py guardian.py web.py config.json ./
COPY static/ static/

EXPOSE 5000

CMD ["python", "-u", "app.py"]
