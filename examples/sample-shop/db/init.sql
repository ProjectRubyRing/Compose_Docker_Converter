-- 初回起動時だけ実行される (postgres イメージの /docker-entrypoint-initdb.d の仕組み)
CREATE SCHEMA IF NOT EXISTS shop AUTHORIZATION shop;
