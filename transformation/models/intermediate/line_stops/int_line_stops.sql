{{ config(
    materialized='table',
    tags=['stops']
) }}

with snapshots as (
    select
        source,
        line_id,
        vehicle_id,
        stop_id,
        stop_name,
        stop_longitude,
        stop_latitude,
        minutes_until_arrival
    from {{ ref('int_previsao_calculated') }}
    where minutes_until_arrival is not null
),

pairwise_orders as (
    select
        a.line_id,
        a.stop_id as predecessor_stop_id,
        b.stop_id as successor_stop_id
    from snapshots a
    join snapshots b
      on a.source = b.source
     and a.line_id = b.line_id
     and a.vehicle_id = b.vehicle_id
     and a.minutes_until_arrival < b.minutes_until_arrival
),

pairwise_counts as (
    select
        line_id,
        predecessor_stop_id,
        successor_stop_id,
        count(*) as observations
    from pairwise_orders
    group by line_id, predecessor_stop_id, successor_stop_id
),

stop_votes as (
    select
        line_id,
        stop_id,
        sum(times_before) as times_before,
        sum(times_after)  as times_after
    from (
        select line_id, predecessor_stop_id as stop_id,
               observations as times_before, 0 as times_after
        from pairwise_counts
        union all
        select line_id, successor_stop_id as stop_id,
               0 as times_before, observations as times_after
        from pairwise_counts
    ) v
    group by line_id, stop_id
),

stop_metadata as (
    select
        line_id,
        stop_id,
        max(stop_name)       as stop_name,
        avg(stop_longitude)  as stop_longitude,
        avg(stop_latitude)   as stop_latitude
    from snapshots
    group by line_id, stop_id
),

ranked as (
    select
        v.line_id,
        v.stop_id,
        m.stop_name,
        m.stop_longitude,
        m.stop_latitude,
        v.times_before,
        v.times_after,
        v.times_before::numeric
            / nullif(v.times_before + v.times_after, 0) as forward_score,
        row_number() over (
            partition by v.line_id
            order by v.times_before::numeric
                     / nullif(v.times_before + v.times_after, 0) desc,
                     v.stop_id
        ) as stop_order
    from stop_votes v
    left join stop_metadata m
      on v.line_id = m.line_id
     and v.stop_id = m.stop_id
)

select
    line_id,
    stop_order,
    stop_id,
    stop_name,
    stop_longitude,
    stop_latitude,
    forward_score,
    times_before,
    times_after
from ranked
order by line_id, stop_order
