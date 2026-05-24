# Error Handling and Logging Strategy

## Logging Framework
Use existing `utils/logging.py` module with structured logging:
```python
logger = get_logger("ingestion.olho_vivo.previsao")
logger.info(f"Found {len(blobs)} blobs to process")
logger.warning(f"Failed to download blob {blob_name}: {error}")
```

## Error Categories and Handling

### 1. Azure Storage Errors
| Error | Action | Log Level |
|-------|--------|-----------|
| Container not found | Exit with error message | ERROR |
| Blob download fails (404) | Skip blob, log warning | WARNING |
| Blob download fails (network) | Retry 3 times, then skip | WARNING |

### 2. Database Errors
| Error | Action | Log Level |
|-------|--------|-----------|
| Connection refused | Exit with error message | ERROR |
| Insert conflict (duplicate source) | Skip duplicate, log warning | WARNING |
| JSON decode error | Skip blob, log error | ERROR |

### 3. Blob Listing Errors
| Error | Action | Log Level |
|-------|--------|-----------|
| List blobs fails | Exit with error message | ERROR |
| No blobs found | Exit gracefully (no data available) | INFO |

## Retry Strategy
- Azure blob downloads: 3 retries with exponential backoff (1s, 2s, 4s)
- Database inserts: Single attempt (failures logged and skipped)

## Graceful Degradation
Script continues processing other blobs if individual failures occur. Only exits on critical errors (container not found, database connection failure).
