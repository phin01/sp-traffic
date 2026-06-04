{% macro get_prediction_timestamp_utc(prediction_timestamp, reference_timestamp) %}

case 
    -- If the prediction time is over 12 hours behind the snapshot, it belongs to the NEXT day
    when {{ prediction_timestamp }} < {{ reference_timestamp }} - interval '12 hours' 
        then {{ prediction_timestamp }} + interval '1 day'
    
    -- If a snapshot is at 00:05 and prediction is 23:55 (bus delayed from yesterday), it belongs to the PREVIOUS day
    when {{ prediction_timestamp }} > {{ reference_timestamp }} + interval '12 hours'
        then {{ prediction_timestamp }} - interval '1 day'
        
    else {{ prediction_timestamp }}
end

{% endmacro %}