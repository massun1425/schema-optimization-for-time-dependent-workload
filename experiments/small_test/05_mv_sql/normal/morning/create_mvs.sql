-- =====================================================
-- NORMAL アルゴリズム - morning
-- =====================================================

\c mv_small_test

-- ノード: leaf_1 (morning)
CREATE MATERIALIZED VIEW mv_leaf_1_morning AS
SELECT u.user_id, u.name, u.age, u.city, u.registered_date
FROM users AS u
WHERE (age >= 25)
;

-- ノード: leaf_4 (morning)
CREATE MATERIALIZED VIEW mv_leaf_4_morning AS
SELECT o.order_id, o.user_id, o.product_id, o.quantity, o.order_date, o.total_amount
FROM orders AS o
WHERE (order_date >= (CURRENT_DATE - '90 days'::interval))
;

-- ノード: leaf_7 (morning)
CREATE MATERIALIZED VIEW mv_leaf_7_morning AS
SELECT o.order_id, o.user_id, o.product_id, o.quantity, o.order_date, o.total_amount
FROM orders AS o
WHERE ((total_amount >= '100'::numeric) AND (order_date >= (CURRENT_DATE - '120 days'::interval)))
;

-- ノード: leaf_12 (morning)
CREATE MATERIALIZED VIEW mv_leaf_12_morning AS
SELECT p.product_id, p.name, p.category, p.price, p.stock
FROM products AS p
WHERE ((category)::text = 'Electronics'::text)
;

-- ノード: leaf_15 (morning)
CREATE MATERIALIZED VIEW mv_leaf_15_morning AS
SELECT u.user_id, u.name, u.age, u.city, u.registered_date
FROM users AS u
WHERE (age < 25)
;

-- ノード: non_leaf_12 (morning)
CREATE MATERIALIZED VIEW mv_non_leaf_12_morning AS
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

-- ノード: non_leaf_28 (morning)
CREATE MATERIALIZED VIEW mv_non_leaf_28_morning AS
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
WHERE o.product_id = p.product_id AND o.user_id = u.user_id AND (u.age >= 30) AND (p.price >= '500'::numeric);

-- ノード: non_leaf_38 (morning)
CREATE MATERIALIZED VIEW mv_non_leaf_38_morning AS
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
WHERE o.product_id = p.product_id AND (p.price < '300'::numeric);

