-- ================================================
-- Query rewritten using Advanced Rewrite Engine
-- ================================================
-- Selected MVs: 1
-- Match Type: partial
-- MV Used: mv_leaf_4
-- Matched Tables: o
-- Coverage Score: 33.3%
-- ================================================

SELECT u.city,
    p.category,
    u.age,
    COUNT(DISTINCT u.user_id) as unique_customers,
    COUNT(leaf_4.order_id) as total_orders,
    SUM(leaf_4.quantity) as total_quantity,
    SUM(leaf_4.total_amount) as total_revenue,
    AVG(leaf_4.total_amount) as avg_order_value
FROM leaf_4 users u products p INNER JOIN u ON u.user_id = leaf_4.user_id INNER JOIN p ON leaf_4.product_id = p.product_id
WHERE leaf_4.order_date >= CURRENT_DATE - INTERVAL '90 days'
  AND u.age >= 25;