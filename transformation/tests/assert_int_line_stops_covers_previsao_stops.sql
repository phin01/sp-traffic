-- Singular test: every (line_id, stop_id) appearing in
-- int_previsao_calculated must also exist in int_line_stops.
--
-- A new stop or a new line appearing in the SPTrans API will surface
-- here as a (line_id, stop_id) that the pairwise-voting model has
-- never seen, meaning the stop has no stop_order assigned and
-- int_eta_to_end_of_route will silently drop it.
--
-- When this test fails, rebuild int_line_stops with:
--   dbt run --select int_line_stops --full-refresh
--
-- See ADR-0001 for how int_line_stops is built.

select
    pc.line_id,
    pc.stop_id
from {{ ref('int_previsao_calculated') }} pc
left join {{ ref('int_line_stops') }} ls
    on ls.line_id = pc.line_id
   and ls.stop_id = pc.stop_id
where ls.line_id is null
group by pc.line_id, pc.stop_id
