-- =====================================================
-- NORMAL アルゴリズム - morning
-- =====================================================

\c mv_small_test

-- ノード: leaf_1
CREATE MATERIALIZED VIEW leaf_1 AS
SELECT u.user_id, u.name, u.age, u.city, u.registered_date
FROM users AS u
WHERE (age >= 25)
;

-- ノード: leaf_3
CREATE MATERIALIZED VIEW leaf_3 AS
SELECT o.order_id, o.user_id, o.product_id, o.quantity, o.order_date, o.total_amount
FROM orders AS o
WHERE (order_date >= (CURRENT_DATE - '60 days'::interval))
;

-- ノード: leaf_8
CREATE MATERIALIZED VIEW leaf_8 AS
SELECT o.order_id, o.user_id, o.product_id, o.quantity, o.order_date, o.total_amount
FROM orders AS o
WHERE ((total_amount >= '100'::numeric) AND (order_date >= (CURRENT_DATE - '120 days'::interval)))
;

-- ノード: leaf_9
CREATE MATERIALIZED VIEW leaf_9 AS
SELECT o_1.order_id, o_1.user_id, o_1.product_id, o_1.quantity, o_1.order_date, o_1.total_amount
FROM orders AS o_1
WHERE (total_amount >= '100'::numeric)
;

-- ノード: leaf_11
CREATE MATERIALIZED VIEW leaf_11 AS
SELECT p.product_id, p.name, p.category, p.price, p.stock
FROM products AS p
WHERE (price >= '300'::numeric)
;

-- ノード: leaf_15
CREATE MATERIALIZED VIEW leaf_15 AS
SELECT p.product_id, p.name, p.category, p.price, p.stock
FROM products AS p
WHERE ((category)::text = 'Electronics'::text)
;

-- ノード: leaf_18
CREATE MATERIALIZED VIEW leaf_18 AS
SELECT u.user_id, u.name, u.age, u.city, u.registered_date
FROM users AS u
WHERE (age < 25)
;

-- ノード: non_leaf_10
CREATE MATERIALIZED VIEW non_leaf_10 AS
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

-- ノード: non_leaf_20
CREATE MATERIALIZED VIEW non_leaf_20 AS
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
WHERE o.product_id = p.product_id AND o.user_id = u.user_id AND (o.order_date >= (CURRENT_DATE - '90 days'::interval)) AND (u.age >= 25);

-- ノード: non_leaf_23
CREATE MATERIALIZED VIEW non_leaf_23 AS
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

-- ノード: non_leaf_31
CREATE MATERIALIZED VIEW non_leaf_31 AS
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

