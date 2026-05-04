# kindofshit

## Docker

Start PostgreSQL and the API:

```bash
docker compose up --build postgres api
```

The API listens on `0.0.0.0:8000` inside Docker and is published as
`http://localhost:8000` on the host. PostgreSQL is not published to the host;
it is only available to the API inside Docker's internal `backend` network.
Compose uses PostgreSQL through:

```text
DATABASE_URL=postgres://kilogram:kilogram@postgres:5432/kilogram
```

For development compose sets `AUTO_GENERATE_SCHEMA=true`, so Tortoise creates
missing tables on startup.

Run the TUI against a hosted API by setting `KILOGRAM_API_URL`:

```bash
KILOGRAM_API_URL=http://127.0.0.1:8000 uv run python -m kilogram_tui
```

On a server, replace `127.0.0.1` with the server IP or domain.
