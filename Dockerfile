FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN python -m venv /app/.venv && /app/.venv/bin/python -m pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["/app/.venv/bin/uvicorn","app.main:app","--host","0.0.0.0","--port","8000"]
