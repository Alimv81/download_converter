# API Structure Reference

This document describes the expected API structure for the config sync feature.

## Base URL
Default: `http://localhost:8000`

## Endpoints

### GET /api/configs
Get all available configs from the server.

**Response Format:**
```json
[
  {
    "id": "cfg_abc123",
    "name": "CAN Standard",
    "description": "Standard CAN configuration",
    "author": "user123",
    "protocol": "can",
    "kwp_format": "0x80",
    "kwp_target": "0x12",
    "kwp_source": "0xF1",
    "input_type": "(auto)",
    "use_filter": false,
    "address_ranges": [],
    "max_line_len": "0xE0",
    "sid": "0x36",
    "use_counter": true,
    "counter_start": "1",
    "crc_type": "(none)",
    "crc_reverse": false,
    "use_checksum": false,
    "split": true,
    "out_dir": "",
    "out_prefix": "block",
    "cont_counter": false,
    "bin_start": "0x0",
    "fill": "0xFF",
    "fill_gaps": false,
    "validate_srec": false
  }
]
```

**Alternative Response Format (nested):**
```json
{
  "configs": [
    {
      "id": "cfg_abc123",
      "name": "CAN Standard",
      "description": "...",
      "author": "...",
      "config_data": {
        "protocol": "can",
        ...
      }
    }
  ]
}
```

### POST /api/configs
Upload a new config to the server.

**Request Body:**
```json
{
  "name": "My Config",
  "description": "Description here",
  "protocol": "can",
  "kwp_format": "0x80",
  ...
}
```

**Response:**
```json
{
  "id": "cfg_xyz789",
  "created_at": "2024-01-15T10:30:00Z",
  "status": "success"
}
```

## Error Handling

The API client expects:
- HTTP 200-299: Success
- HTTP 400-499: Client error (returns error message)
- HTTP 500-599: Server error (returns error message)
- Network errors: Connection timeout, DNS failure, etc.

## Implementation Notes

- The API client uses standard library `urllib` (no external dependencies)
- All requests use JSON format
- Timeout is set to 10 seconds
- The client gracefully handles offline mode (API client can be None)

## Example FastAPI Implementation

```python
from fastapi import FastAPI
from pydantic import BaseModel
from typing import List

app = FastAPI()

class Config(BaseModel):
    name: str
    protocol: str
    # ... all other fields

@app.get("/api/configs")
async def get_configs():
    # Return list of configs from database
    return configs_list

@app.post("/api/configs")
async def create_config(config: Config):
    # Save config to database
    # Return created config with ID
    return {"id": "cfg_123", "created_at": "...", "status": "success"}
```
