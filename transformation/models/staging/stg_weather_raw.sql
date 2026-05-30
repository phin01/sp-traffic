{{
    config(
        materialized='incremental',
        unique_key='location_id'
    )
}}

WITH raw_data AS (
    SELECT
        source, 
        data::jsonb AS weather_data,
        loaded_at
    FROM {{ source('sptraffic-blobs', 'stg_weather_raw') }}
)

select
    r.source,
    nested_data.key as location_id,

    (nested_data.value ->> 'latitude')::numeric as latitude,
    (nested_data.value ->> 'longitude')::numeric as longitude,
    
    (nested_data.value -> 'current' ->> 'time')::timestamp as snapshot_time,
    (nested_data.value -> 'current' ->> 'temperature_2m')::numeric as temperature,
    (nested_data.value -> 'current' ->> 'precipitation')::numeric as precipitation,
    (nested_data.value -> 'current' ->> 'rain')::numeric as rain,
    (nested_data.value -> 'current' ->> 'showers')::numeric as showers,
    (nested_data.value -> 'current' ->> 'relative_humidity_2m')::numeric as relative_humidity,
    (nested_data.value -> 'current' ->> 'weather_code')::numeric as weather_code,
    r.loaded_at

from raw_data r
cross join lateral jsonb_each(r.weather_data) as nested_data(key, value)


{% if is_incremental() %}
WHERE loaded_at > (SELECT MAX(loaded_at) FROM {{ this }})
{% endif %}