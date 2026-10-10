# syntax=docker/dockerfile:1
# sample-shop の API サーバー (Python 標準ライブラリだけで動く小さな Web サーバー)
ARG PYTHON_VERSION=3.12

# ---- ステージ 1: 依存物の準備 (ここではバイトコードのコンパイルだけ) ----
FROM python:${PYTHON_VERSION}-alpine AS build
WORKDIR /src
COPY app.py .
RUN python -m py_compile app.py

# ---- ステージ 2: 実行用 (compose の build.target: runtime) ----
FROM python:${PYTHON_VERSION}-alpine AS runtime
ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION} \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
WORKDIR /srv
COPY --from=build /src/app.py ./app.py
RUN addgroup -g 10001 shop && adduser -D -u 10001 -G shop shop
USER 10001:10001
EXPOSE 8000
CMD ["python", "app.py"]
