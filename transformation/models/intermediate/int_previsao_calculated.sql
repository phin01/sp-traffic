{{ config(
    materialized='incremental',
    unique_key=['source', 'line_id', 'stop_id', 'vehicle_id', 'prediction_time'],
    incremental_strategy='merge',
    on_schema_change='append_new_columns',
    tags=['fct', 'previsao']
) }}

with raw_data as (

    select
        source,
        blob_timestamp,
        line_id,
        snapshot_hour,
        stop_id,
        stop_name,
        stop_longitude,
        stop_latitude,
        vehicle_id,
        prediction_time,
        snapshot_timestamp,
        vehicle_longitude,
        vehicle_latitude,
        is_accessible,
        loaded_at
    from {{ ref('stg_previsao_raw') }}
    where line_id is not null
      and line_id not in (select line_id from {{ source('sptraffic-blobs', 'stg_short_lines') }})
    {% if is_incremental() %}
      and loaded_at > (select max(loaded_at) from {{ this }})
    {% endif %}
),

base_timestamps as (

select 
    *,
    -- Get prediction timestamps in UTC assuming they are on the same day as the snapshot (we will adjust for overnight predictions later)
    -- Calculated separately for blob and snapshot timestamps to handle edge cases where they might be on different days
    -- We have found edge cases in which the snapshot_timestamp was heavily delayed, generating excessive ETA times that did not reflect the actual data
    {{ get_same_day_prediction_utc('blob_timestamp', 'prediction_time') }} as blob_same_day_prediction_utc,
    {{ get_same_day_prediction_utc('snapshot_timestamp', 'prediction_time') }} as snapshot_same_day_prediction_utc
    
    from raw_data
),

adjusted_timestamps as (
select
    *,

    -- This covers overnight edge cases
    -- For example: Snapshot at 23:55, ETA at 00:05
    {{ get_prediction_timestamp_utc('blob_same_day_prediction_utc', 'blob_timestamp') }} as blob_prediction_timestamp_utc,
    {{ get_prediction_timestamp_utc('snapshot_same_day_prediction_utc', 'snapshot_timestamp') }} as snapshot_prediction_timestamp_utc

from base_timestamps
),

eta_calculation as (

select 
    *,

    {{ get_time_difference_in_minutes('blob_prediction_timestamp_utc', 'blob_timestamp') }} as blob_minutes_until_arrival,
    {{ get_time_difference_in_minutes('snapshot_prediction_timestamp_utc', 'snapshot_timestamp') }} as snapshot_minutes_until_arrival

from adjusted_timestamps

)

select 
    source,
    blob_timestamp,
    line_id,
    snapshot_hour,
    stop_id,
    stop_name,
    stop_longitude,
    stop_latitude,
    vehicle_id,
    prediction_time,
    snapshot_timestamp,
    vehicle_longitude,
    vehicle_latitude,
    is_accessible,
    loaded_at,
    blob_same_day_prediction_utc,
    snapshot_same_day_prediction_utc,
    blob_prediction_timestamp_utc,
    snapshot_prediction_timestamp_utc,
    case 
        when blob_minutes_until_arrival < 0 then snapshot_minutes_until_arrival
        else blob_minutes_until_arrival
    end as minutes_until_arrival

from eta_calculation
