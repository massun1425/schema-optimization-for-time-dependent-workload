CREATE MATERIALIZED VIEW leaf_71 AS
SELECT pi.id AS pi_id, pi.person_id AS pi_person_id, pi.info_type_id AS pi_info_type_id, pi.info AS pi_info, pi.note AS pi_note
FROM person_info AS pi
WHERE pi.info_type_id = 24;