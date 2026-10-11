# FastAPI Topic Search

API mínima que busca en Google News lo que se está hablando de un término, lo guarda en Postgres y lo cachea 5 minutos. Sin claves ni servicios de pago.

## Endpoints

- `GET /topics/{term}` — devuelve el resultado en caché si la última búsqueda de `{term}` fue reciente (< 5 min), si no, consulta el feed RSS de Google News para `{term}` (timeout 12s, 502 si falla), lo guarda y lo devuelve.

## Local

```bash
cp .env.example .env
docker compose up --build
```

Probá con: `curl localhost:8000/topics/python`

## Deploy a Azure (Web App for Containers)

1. Crear recurso **Azure Database for PostgreSQL Flexible Server** y una base de datos. Tomar nota de la connection string, agregando `?sslmode=require`:

   ```
   postgresql+psycopg2://USER:PASS@HOST.postgres.database.azure.com:5432/DBNAME?sslmode=require
   ```

2. Crear **Azure Container Registry** y una **Web App (Linux) for Containers**.

3. En GitHub, en el repo:
   - **Secrets**: `AZURE_CREDENTIALS` (service principal), `REGISTRY_LOGIN_SERVER`, `REGISTRY_USERNAME`, `REGISTRY_PASSWORD` (admin de ACR), `DATABASE_URL`
   - **Variables**: `AZURE_WEBAPP_NAME`, `TTL_SECONDS`

4. Hacer push a `main`. El workflow builda, pushea al ACR y hace deploy.

El servicio crea la tabla `topic_searches` solo (sin migraciones, a propósito: es la app mínima).

## Troubleshooting

- Si la API arranca antes que Postgres local, reconstruí: `docker compose up -d --build` (el compose ya espera a que la DB esté healthy).