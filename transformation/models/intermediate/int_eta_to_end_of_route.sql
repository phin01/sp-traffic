{{ config(
    materialized='table',
    tags=['fct', 'previsao']
) }}

with calc as (

    select
        source,
        blob_timestamp,
        snapshot_timestamp,
        line_id,
        vehicle_id,
        stop_id,
        stop_name,
        minutes_until_arrival
    from {{ ref('int_previsao_calculated') }}
    where minutes_until_arrival is not null

),

with_order as (

    select
        c.source,
        c.blob_timestamp,
        c.snapshot_timestamp,
        c.line_id,
        c.vehicle_id,
        c.stop_id,
        c.stop_name,
        c.minutes_until_arrival,
        ls.stop_order
    from calc c
    join {{ ref('int_line_stops') }} ls
      on ls.line_id = c.line_id
     and ls.stop_id = c.stop_id

),

next_stop as (

    select
        source,
        line_id,
        vehicle_id,
        blob_timestamp,
        snapshot_timestamp,
        next_stop_id,
        next_stop_order,
        next_stop_name,
        next_stop_eta
    from (
        select
            source,
            line_id,
            vehicle_id,
            blob_timestamp,
            snapshot_timestamp,
            stop_id as next_stop_id,
            stop_order as next_stop_order,
            stop_name as next_stop_name,
            minutes_until_arrival as next_stop_eta,
            row_number() over (
                partition by source, line_id, vehicle_id
                order by minutes_until_arrival
            ) as rn
        from with_order
        where minutes_until_arrival > 0
    ) t
    where rn = 1

),

terminal as (

    select
        line_id,
        terminal_stop_id,
        terminal_stop_order
    from (
        select
            line_id,
            stop_id as terminal_stop_id,
            stop_order as terminal_stop_order,
            row_number() over (
                partition by line_id
                order by stop_order desc
            ) as rn
        from {{ ref('int_line_stops') }}
    ) t
    where rn = 1

),

final_stop as (

    select
        w.source,
        w.line_id,
        w.vehicle_id,
        t.terminal_stop_id as final_stop_id,
        t.terminal_stop_order as final_stop_order,
        w.stop_name as final_stop_name,
        w.minutes_until_arrival as final_stop_eta
    from with_order w
    join terminal t
      on t.line_id = w.line_id
     and t.terminal_stop_id = w.stop_id

)

select
    n.source,
    n.line_id,
    n.vehicle_id,
    n.blob_timestamp,
    n.snapshot_timestamp,
    f.final_stop_order - n.next_stop_order                         as segments_remaining,
    f.final_stop_eta - n.next_stop_eta                             as eta_to_end,
    (f.final_stop_eta - n.next_stop_eta)::numeric
        / nullif(f.final_stop_order - n.next_stop_order, 0)        as eta_per_segment,
    n.next_stop_id,
    n.next_stop_order,
    n.next_stop_name,
    n.next_stop_eta,
    f.final_stop_id,
    f.final_stop_order,
    f.final_stop_name,
    f.final_stop_eta

from next_stop n
join final_stop f
  on f.source = n.source
 and f.line_id = n.line_id
 and f.vehicle_id = n.vehicle_id
where f.final_stop_eta > n.next_stop_eta
  and f.final_stop_order > n.next_stop_order
