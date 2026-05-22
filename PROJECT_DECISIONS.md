# SP Bus Forecast Analysis Project

## Overview

This project analyzes the relationship between weather conditions, traffic accidents, and bus arrival times in São Paulo using real-time data from the Olho Vivo API (bus geolocation and forecasts) alongside historical weather and accident data. The goal is to build a time-lapse visualization showing how environmental factors impact bus route durations over time.

## Data Sources

| Source | Type | Update Frequency | Notes |
|--------|------|------------------|-------|
| Olho Vivo API | Real-time bus data | Every 15 minutes | Free, public API for São Paulo bus routes |
| Weather API | Historical weather | Every 15 minutes | Precise coordinates available |
| Accident Data | Historical accidents | End of month (retroactive) | Precise timestamps and locations |

## Scale Estimates

- **Routes**: 20–40 bus routes to query
- **Bus stops per route**: ~76 stops
- **Unique buses**: ~2 buses circulating each route simultaneously
- **Total active buses**: ~198 buses across all routes
- **Data ingestion frequency**: Every 15 minutes

## Architecture (Bronze Layer)

### Data Flow

```
┌─────────────┐     ┌──────────────┐     ┌──────────────┐
│   Olho Vivo │────▶│   Ingestion  │────▶│   PostgreSQL │
│    API      │     │   Worker     │     │   (Bronze)   │
└─────────────┘     └──────────────┘     └─────────────┘
                                    │
                                    ▼
                              ┌──────────────┐
                              │  Weather/   │
                              │ Accident DB │
                              └──────────────┘
```

### Storage Strategy (Bronze Layer)

Three separate fact tables in PostgreSQL:

1. **bus_movements** - Raw bus position and forecast data from Olho Vivo API
   - Columns: route_id, stop_id, vehicle_id, timestamp, lat, lon, expected_arrival_time, actual_arrival_time
   
2. **weather_readings** - Weather data at precise coordinates
   - Columns: timestamp, lat, lon, temperature, humidity, precipitation, wind_speed
   
3. **accidents** - Historical accident records (retroactive)
   - Columns: date, time, lat, lon, type, description

### Key Design Decisions

- **Raw coordinates preserved**: All data stored with exact lat/lon for flexible spatial queries
- **Per-segment tracking**: Each segment is defined between consecutive bus stops on a route (76 segments/route)
- **Granular storage**: Data kept at maximum granularity; aggregations deferred to silver/gold layers
- **Separate fact tables**: Weather and accident data stored independently for flexible joins

## Next Steps

1. Design Silver Layer (ETL transformations, delay calculations)
2. Define Gold Layer metrics and dashboards
3. Implement ingestion pipeline
4. Build visualization frontend
