FROM python:3.11-slim

WORKDIR /app

# 系统依赖（psycopg/bcrypt 编译用）
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 生产关闭 DEBUG
ENV PYTHONUNBUFFERED=1 PYTHONUTF8=1 DEBUG=false

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
