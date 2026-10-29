FROM python:3.13-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY wishlist wishlist
COPY static static

ENV WISHLIST_CONFIG=/config/config.toml \
    WISHLIST_DB=/data/wishlist.db
USER 1000:1000
EXPOSE 8000
CMD ["uvicorn", "wishlist.app:app_from_env", "--factory", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
