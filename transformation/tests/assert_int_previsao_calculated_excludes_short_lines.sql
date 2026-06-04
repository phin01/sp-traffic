-- Singular test: no line_id present in int_previsao_calculated should
-- also appear in stg_short_lines.
--
-- stg_short_lines is a curated list of bus lines with too few stops
-- (typically <5) for the pairwise-voting model in int_line_stops to
-- learn a stop_order. They are excluded from int_previsao_calculated
-- by the WHERE in the model. This test guards that exclusion.
--
-- A failure here means either the WHERE in int_previsao_calculated
-- was removed/altered, or new short lines have been added to
-- stg_short_lines that have not yet been filtered out.

select
    pc.line_id
from {{ ref('int_previsao_calculated') }} pc
inner join {{ source('sptraffic-blobs', 'stg_short_lines') }} sl
    on sl.line_id = pc.line_id
group by pc.line_id
