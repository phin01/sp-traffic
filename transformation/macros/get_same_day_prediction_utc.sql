{% macro get_same_day_prediction_utc(reference_timestamp, prediction_time) %}
    
    -- 1. Convert reference_timestamp to local BR time to lock in the correct calendar date
    -- 2. Concat the local date with the 'HH:MM' prediction string
    -- 3. Tell Postgres it is in 'America/Sao_Paulo' time, then convert it back to UTC
    
    (
        (( {{ reference_timestamp }} at time zone 'UTC' at time zone 'America/Sao_Paulo')::date || ' ' || {{ prediction_time }} )::timestamp
        at time zone 'America/Sao_Paulo' at time zone 'UTC'
    )

{% endmacro %}