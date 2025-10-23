-- morning -> evening のマイグレーション SQL
-- =====================================================

-- CREATE MATERIALIZED VIEW
CREATE MATERIALIZED VIEW non_leaf_33 AS
-- No MVs selected for this query
-- Using original tables

SELECT o.order_id, o.user_id, o.product_id, o.quantity, o.order_date, o.total_amount, p.product_id, p.name, p.category, p.price, p.stock, u.user_id, u.name, u.age, u.city, u.registered_date
FROM (SELECT o.order_id, o.user_id, o.product_id, o.quantity, o.order_date, o.total_amount, p.product_id, p.name, p.category, p.price, p.stock
FROM (SELECT o.order_id, o.user_id, o.product_id, o.quantity, o.order_date, o.total_amount
FROM orders AS o
WHERE (order_date >= '2024-01-01'::date)) AS leaf_11
, (SELECT p.product_id, p.name, p.category, p.price, p.stock
FROM (SELECT p.product_id, p.name, p.category, p.price, p.stock
FROM products AS p
WHERE ((category)::text = 'Electronics'::text)) AS leaf_12) AS non_leaf_30) AS non_leaf_31
, (SELECT u.user_id, u.name, u.age, u.city, u.registered_date
FROM (SELECT u.user_id, u.name, u.age, u.city, u.registered_date
FROM users AS u) AS leaf_13) AS non_leaf_32;

CREATE MATERIALIZED VIEW non_leaf_17 AS
SELECT o.order_id, o.user_id, o.product_id, o.quantity, o.order_date, o.total_amount, p.product_id, p.name, p.category, p.price, p.stock
FROM (SELECT o.order_id, o.user_id, o.product_id, o.quantity, o.order_date, o.total_amount
FROM orders AS o
WHERE (total_amount >= '1000'::numeric)) AS leaf_8
, (SELECT p.product_id, p.name, p.category, p.price, p.stock
FROM (SELECT p.product_id, p.name, p.category, p.price, p.stock
FROM products AS p
WHERE (price >= '300'::numeric)) AS leaf_9) AS non_leaf_16;

CREATE MATERIALIZED VIEW non_leaf_20 AS
-- No MVs selected for this query
-- Using original tables

SELECT o.order_id, o.user_id, o.product_id, o.quantity, o.order_date, o.total_amount, u.user_id, u.name, u.age, u.city, u.registered_date
FROM (SELECT o.order_id, o.user_id, o.product_id, o.quantity, o.order_date, o.total_amount
FROM orders AS o
WHERE (order_date >= (CURRENT_DATE - '90 days'::interval))) AS leaf_4
, (SELECT u.user_id, u.name, u.age, u.city, u.registered_date
FROM (SELECT u.user_id, u.name, u.age, u.city, u.registered_date
FROM users AS u
WHERE (age >= 25)) AS leaf_1) AS non_leaf_1;

CREATE MATERIALIZED VIEW non_leaf_5 AS
SELECT o.order_id, o.user_id, o.product_id, o.quantity, o.order_date, o.total_amount, p.product_id, p.name, p.category, p.price, p.stock
FROM (SELECT o.order_id, o.user_id, o.product_id, o.quantity, o.order_date, o.total_amount
FROM orders AS o
WHERE (order_date >= (CURRENT_DATE - '60 days'::interval))) AS leaf_2
, (SELECT p.product_id, p.name, p.category, p.price, p.stock
FROM (SELECT p.product_id, p.name, p.category, p.price, p.stock
FROM products AS p) AS leaf_3) AS non_leaf_4;

-- DROP MATERIALIZED VIEW
DROP MATERIALIZED VIEW IF EXISTS leaf_4;
DROP MATERIALIZED VIEW IF EXISTS leaf_7;
DROP MATERIALIZED VIEW IF EXISTS non_leaf_28;
DROP MATERIALIZED VIEW IF EXISTS leaf_12;
DROP MATERIALIZED VIEW IF EXISTS leaf_1;

