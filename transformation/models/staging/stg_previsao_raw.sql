{{
    config(
        materialized='incremental',
        unique_key=['source']
    )
}}

WITH raw_data AS (
    SELECT
        source, 
        data::jsonb AS previsao_data,
        loaded_at
    FROM {{ source('sptraffic-blobs', 'stg_previsao_raw') }}
)

select
    r.source,
    
    -- Level 1: Root Array Attributes
    (root.value ->> 'line_id')::varchar as line_id,
    (root.value ->> 'hr')::varchar as snapshot_hour,
    
    -- Level 2: Nested 'ps' (Points/Stops) Attributes
    (ps.value ->> 'cp')::bigint as stop_id,
    (ps.value ->> 'np')::varchar as stop_name,
    (ps.value ->> 'px')::numeric as stop_longitude,
    (ps.value ->> 'py')::numeric as stop_latitude,
    
    -- Level 3: Deeply Nested 'vs' (Vehicles) Attributes
    (vs.value ->> 'p')::varchar as vehicle_id,
    (vs.value ->> 't')::varchar as prediction_time,
    (vs.value ->> 'ta')::timestamp as snapshot_time,
    (vs.value ->> 'px')::numeric as vehicle_longitude,
    (vs.value ->> 'py')::numeric as vehicle_latitude,
    (vs.value ->> 'a')::boolean as is_accessible,

    r.loaded_at
    
from raw_data r
-- 1. Flatten the root array
cross join lateral jsonb_array_elements(r.previsao_data) as root(value)
-- 2. Flatten the 'ps' array inside the current root object
cross join lateral jsonb_array_elements(root.value -> 'ps') as ps(value)
-- 3. Flatten the 'vs' array inside the current 'ps' object
cross join lateral jsonb_array_elements(ps.value -> 'vs') as vs(value)

{% if is_incremental() %}
WHERE loaded_at > (SELECT MAX(loaded_at) FROM {{ this }})
{% endif %}