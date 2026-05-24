# SP-Traffic Domain Glossary

## Project Overview
SP-Traffic analyzes how weather conditions and traffic accidents impact bus route delays in São Paulo, Brazil. The system ingests data from multiple sources into PostgreSQL staging tables for downstream transformation (dbt) and analytics.

## Language

**Bus Line (`linha`)**
- Definition: {A specific bus route operating between two terminals
- Identifier: `line_id` (string code from SPTrans)
- Storage: PostgreSQL table `staging.stg_lines`
- Count: ~40 active lines in system

**Bus Stop (`parada`)**
- Definition: Physical location where passengers board/alight buses
- Unique Code: `cp` (integer, primary key for deduplication)
- Coordinates: `py` (latitude), `px` (longitude)
- Storage: PostgreSQL table `staging.stg_bus_stops`

**Grid Cell (`célula`)**
- Definition: Spatial bucket used to cluster bus stops for weather queries
- Size: 0.025° × 0.025° (approximately 8 km², ~3.5 km radius)
- Coordinate System: São Paulo bounding box
  - Latitude: -23.8265890 to -23.4891720
  - Longitude: -46.7636250 to -46.3830080
- Count: ~64 unique cells (reduces 400 stops to 64 API calls)

**Grid Key (`grid_key`)**
- Definition: Unique identifier for a grid cell in format `row_col`
- Example: `"10_14"` represents row 10, column 14
- Used as primary key in weather staging table