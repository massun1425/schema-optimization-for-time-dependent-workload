-- =====================================================
-- NORMAL アルゴリズム - evening
-- =====================================================

\c mv_small_test

-- ノード: leaf_4 (evening)
CREATE MATERIALIZED VIEW mv_leaf_4_evening AS
SELECT o.order_id, o.user_id, o.product_id, o.quantity, o.order_date, o.total_amount
FROM orders AS o
WHERE (order_date >= (CURRENT_DATE - '90 days'::interval))
;

-- ノード: leaf_9 (evening)
CREATE MATERIALIZED VIEW mv_leaf_9_evening AS
SELECT p.product_id, p.name, p.category, p.price, p.stock
FROM products AS p
WHERE (price >= '300'::numeric)
;

-- ノード: non_leaf_5 (evening)
CREATE MATERIALIZED VIEW mv_non_leaf_5_evening AS
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
FROM orders AS o , products AS p
WHERE o.product_id = p.product_id AND (o.order_date >= (CURRENT_DATE - '60 days'::interval));

-- ノード: non_leaf_12 (evening)
CREATE MATERIALIZED VIEW mv_non_leaf_12_evening AS
SELECT o.order_id,
    o.user_id,
    o.product_id,
    o.quantity,
    o.order_date,
    o.total_amount,
    u.user_id AS u_user_id,
    u.name,
    u.age,
    u.city,
    u.registered_date,
    p.product_id AS p_product_id,
    p.name AS p_name,
    p.category,
    p.price,
    p.stock
FROM orders AS o , users AS u , products AS p
WHERE o.product_id = p.product_id AND o.user_id = u.user_id AND (o.order_date >= (CURRENT_DATE - '90 days'::interval)) AND (u.age >= 30) AND (p.price >= '500'::numeric);

