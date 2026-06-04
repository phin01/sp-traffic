{% macro get_time_difference_in_minutes(timestamp1, timestamp2) %}

extract(
        epoch from ({{ timestamp1 }} - {{ timestamp2 }})
    ) / 60

{% endmacro %}