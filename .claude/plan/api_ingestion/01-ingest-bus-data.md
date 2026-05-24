# Bus data ingestion Plan

## Context

This step creates a python script responsible for fetching data from Olho Vivo API based on the bus lines stored in a PostgreSQL database. 
There are 40 bus lines to be queried from the API, and they must be done individually. 
You should be mindful of the querying volume to avoid timeouts.
Data from all 40 bus lines should be aggregated in memory and then saved as a single json file in Azure Blob Storage.

--- 

## Files to be created/modified

- Create local script at ingestion/olho_vivo/previsao_staging/main.py
- No other local files should be created or modified

---

## Implementation Details

### Fetch bus lines from PostgreSQL database

- Connect to PostgreSQL database using **sqlalchemy**
- Necessary credentials are stored as DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, DB_NAME in **.env file at project root**
- Fetch all rows from `stg_lines` table in `staging` schema. The column `line_id` (string) represent the bus lines to be queried from the API

### Authenticate to Olho Vivo API

- Use a **Session** from **requests** library to handle all requests
- Base URL for the API is stored as **OLHO_VIVO_URL** in .env file at project root
- Authentication is token-based, with the token passed as a query parameter (token found as **SPTRANS_TOKEN** in .env file at project root) 
- Authentication method is POST
- Authentication endpoint is **/Login/Autenticar?token=SPTRANS_TOKEN**
- Authentication endpoint returns a **true** string under 200 Status code if successful, **false** under the same 200 status if failed

### Fetch data from each bus line

- Once authenticated, loop over the bus lines fetched from the PostgreSQL database and query the Olho Vivo API for each line
- API endpoint for bus data is **/Previsao/Linha?codigoLinha=LINE_ID** , with LINE_ID representing each bus lines
- HTTP method is GET
- API return does not include the bus line id, so make sure to include that as an additional key to the json response
- Store all results in memory, to be saved in the following step

### Store data as a single file to Azure Blob Storage

- Authenticate to Azure Blob Storage using **BlobServiceClient** from **azure.storage.blob** package
- Required credentials (AZURE_STORAGE_KEY and AZ_CONTAINER_NAME) can be found in .env file at project root
- Create a filename with the format **previsao_TIMESTAMP.json**, with TIMESTAMP as the current UTC date time in ISO 8601 format
- Save the json file in the container under **sptrans-olhovivo/previsao/** folder

## Verification Steps

- Make sure 40 bus lines are fetched from PostgreSQL before calling the API
- Make sure authentication is successful before looping over the bus lines requests
- After saving the json file to Azure Blob Storage, fetch it and verify its contents. Use the number of records as a comparison criteria