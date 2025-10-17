-- ================================================
-- Query rewritten using Advanced Rewrite Engine
-- ================================================
-- Selected MVs: 1
-- Match Type: partial
-- MV Used: mv_leaf_9
-- Matched Tables: p
-- Coverage Score: 50.0%
-- ================================================

SELECT leaf_9.category,
    COUNT(o.order_id) as order_count,
    SUM(o.total_amount) as total_sales,
    AVG(o.quantity) as avg_quantity
FROM leaf_9 orders o INNER JOIN o ON leaf_9.product_id = o.product_id
WHERE leaf_9.price >= 300
  AND o.total_amount >= 1000;