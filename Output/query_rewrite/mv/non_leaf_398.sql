CREATE MATERIALIZED VIEW non_leaf_398 AS
SELECT mi1.id AS mi1_id, mi1.movie_id AS mi1_movie_id, mi1.info_type_id AS mi1_info_type_id, mi1.info AS mi1_info, mi1.note AS mi1_note
FROM movie_info AS mi1
WHERE mi1.info ~~* '%20%' AND mi1.info_type_id = 110;