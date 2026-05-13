# Persistent Storage

FallbackRabbit supports in-memory and SQLite storage backends.

## Memory Storage (Default)

Chains are stored in memory and lost on restart. Good for development and testing.

```bash
fallbackrabbit serve
# or explicitly
fallbackrabbit serve --storage memory://
```

```python
from fallbackrabbit.server import create_app
app = create_app(storage_url="memory://")
```

## SQLite Storage

Chains persist across restarts. Good for production.

```bash
fallbackrabbit serve --storage sqlite:///data/frabbit.db
```

```python
from fallbackrabbit.server import create_app
app = create_app(storage_url="sqlite:///data/frabbit.db")
```

### SQLite Features

- Thread-safe with WAL mode
- Automatic table creation on startup
- JSON serialization for chain data
- No external database server required

## Storage Backends

Both backends implement the same `StorageBackend` interface:

```python
from fallbackrabbit.storage import MemoryStorage, SqliteStorage

# Memory
storage = MemoryStorage()

# SQLite
storage = SqliteStorage("sqlite:///data/frabbit.db")
```

### Operations

| Method | Description |
|--------|-------------|
| `create(chain)` | Store a new chain |
| `get(chain_id)` | Retrieve a chain |
| `list()` | List all chains |
| `update(chain_id, updates)` | Update a chain |
| `delete(chain_id)` | Delete a chain |
| `clear()` | Remove all chains |

## Migration

Switch storage backends without data loss:

1. Export chains via API: `GET /chains`
2. Start server with new storage
3. Import chains via API: `POST /chains`