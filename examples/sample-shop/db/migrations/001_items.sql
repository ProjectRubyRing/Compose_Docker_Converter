-- migrate サービス (1 回だけ動くジョブ) が実行するスキーマ定義
CREATE TABLE IF NOT EXISTS shop.items (
    id    SERIAL PRIMARY KEY,
    name  TEXT NOT NULL,
    price INTEGER NOT NULL
);
INSERT INTO shop.items (name, price)
SELECT 'apple', 120 WHERE NOT EXISTS (SELECT 1 FROM shop.items WHERE name = 'apple');
