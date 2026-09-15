# Deployment

## Local / Docker

```bash
pip install -e '.[dev]'
uvicorn agentproof.app:app --host 0.0.0.0 --port 8000
```

or:

```bash
docker compose up --build
```

## Vercel demo

The repository includes `api/index.py` and `vercel.json` for the FastAPI demo.

From a Vercel-connected checkout:

```bash
vercel
vercel --prod
```

The public demo is suitable for the synthetic flagship benchmark. The built-in SQLite store is intentionally local-first; on Vercel it should be treated as ephemeral between serverless instances. A commercial hosted version should move run/pack persistence to a managed database before accepting customer data.

## Production checklist

- persistent managed database
- authentication + tenant isolation
- secret management
- rate limiting
- audit logs
- retention controls
- monitoring and alerting
- HTTPS-only webhook policy and endpoint allow-listing
- backups and disaster recovery

See `docs/SECURITY_AND_DATA.md` before using non-synthetic data.
