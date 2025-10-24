-- morning -> evening のマイグレーション SQL
-- =====================================================

-- CREATE MATERIALIZED VIEW
CREATE MATERIALIZED VIEW leaf_7 AS
SELECT p.product_id, p.name, p.category, p.price, p.stock
FROM leaf_11 AS p
WHERE (price >= '500'::numeric)
;

CREATE MATERIALIZED VIEW non_leaf_16 AS
SELECT o.order_id,
    o.user_id,
    o.product_id,
    o.quantity,
    o.order_date,
    o.total_amount,
    p.product_id AS p_product_id,
    p.name,
    p.category,
    p.price,
    p.stock
FROM orders AS o , leaf_11 AS p
WHERE o.product_id = p.product_id AND (o.total_amount >= '1000'::numeric) AND (p.price >= '300'::numeric);

CREATE MATERIALIZED VIEW non_leaf_28 AS
SELECT o.order_id,
    o.user_id,
    o.product_id,
    o.quantity,
    o.order_date,
    o.total_amount,
    p.product_id AS p_product_id,
    p.name,
    p.category,
    p.price,
    p.stock,
    u.user_id AS u_user_id,
    u.name AS u_name,
    u.age,
    u.city,
    u.registered_date
FROM orders AS o , leaf_15 AS p , users AS u
WHERE o.user_id = u.user_id AND o.product_id = p.product_id AND (o.order_date >= '2024-01-01'::date) AND ((p.category)::text = 'Electronics'::text);

CREATE MATERIALIZED VIEW non_leaf_5 AS
SELECT o.order_id,
    o.user_id,
    o.product_id,
    o.quantity,
    o.order_date,
    o.total_amount,
    p.product_id AS p_product_id,
    p.name,
    p.category,
    p.price,
    p.stock
FROM leaf_3 AS o , products AS p
WHERE o.product_id = p.product_id AND (o.order_date >= (CURRENT_DATE - '60 days'::interval));

-- DROP MATERIALIZED VIEW
DROP MATERIALIZED VIEW IF EXISTS leaf_11;
DROP MATERIALIZED VIEW IF EXISTS leaf_3;
DROP MATERIALIZED VIEW IF EXISTS leaf_1;
DROP MATERIALIZED VIEW IF EXISTS leaf_15;
DROP MATERIALIZED VIEW IF EXISTS non_leaf_23;

