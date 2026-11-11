FROM python:3.13-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY vyshyu vyshyu
COPY static static

ENV VYSHYU_CONFIG=/config/config.toml \
    VYSHYU_DB=/data/vyshyu.db
USER 1000:1000
EXPOSE 8000
CMD ["uvicorn", "vyshyu.app:app_from_env", "--factory", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
