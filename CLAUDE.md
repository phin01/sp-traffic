# CLAUDE.md

## Project Overview
SP-Traffic is a tool to analyze the impact of weather conditions and traffic accidents on bus route delays in the city of Sao Paulo, Brazil

---

## Architecture

sp-traffic
├── ingestion/          # Python ingestion scripts
|   ├── olho_vivo/      # Scripts for Olho Vivo API
|   ├── open_meteo/     # Scripts for Open Meteo API
|   └── infosiga/       # Scripts for Infosiga source
├── transformation/     # dbt project for SQL transformation (WIP)

## Tech Constraints

- Ingestion scripts using Python
- API requests using requests library
- Raw API returns saved as .json files in Azure Blob Storage
- PostgreSQL as database, with sqlalchemy as ORM
- All credentials stored in .env file, accessed with dotenv package, **using find_dotenv() as location**
- No installation of additional packages, use only packages included in requirements.txt
- Any test or temporary scripts should be saved to the /sandbox folder at the project root
- Run all scripts as modules from the project root folder (ie, python -m sandbox/script.py)
- Use relative paths when referencing other files

## Data Sources

### Olho Vivo API
- Reference: https://www.sptrans.com.br/desenvolvedores/api-do-olho-vivo-guia-de-referencia/documentacao-api/
- API base URL as OLHO_VIVO_URL in .env file at root folder
- API credentials as SPTRANS_TOKEN in .env file at root folder
- Authentication to Olho Vivo API is cookie-based, so all calls should be handled using Sessions from the requests library

### Open Meteo API

- Reference: https://open-meteo.com
- API base URL as OPEN_METEO_URL in .env file at root folder
- No credentials required

### Infosiga

- Reference: https://infosiga.detran.sp.gov.br/
- Files will be manually downloaded every month and added to the folder

### PostgreSQL

- All relevant credentials and connection information in .env file at root folder: DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, DB_NAME
- Always use parameterized queries for any inserts or updates. Always check for potential SQL injection risks

### Azure Blob Storage

- AZURE_STORAGE_KEY credential stored in .env file at root folder
- AZ_CONTAINER_NAME credential stored in .env file at root folder


## Project Roadmap

- [ ] Create script to fetch current bus data from Olho Vivo API and store in Azure Blob Storage
- [ ] Create script to determine relevant locations to query for weather data
- [ ] Create script to fetch weather data from relevant locations and store in Azure Blob Storage
- [ ] Create script to fetch bus data from Blob Storage and save to PostgreSQL database incrementally
- [ ] Create script to fetch weather data from Blob Storage and save to PostgreSQL database incrementally
- [ ] Create script to process traffic accident files and save to PostgreSQL database incrementally


## Open Topics (To be included in roadmap after breakdown into smaller steps)

- Creation of dbt project for data transformation from raw to gold layers

- Creation of a frontend application in which users can query historical data and see a time-lapse visual of weather and accidents impact on the bus route delays



