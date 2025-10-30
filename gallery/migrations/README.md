# D1 Database Setup

## Initial Setup

1. **Create the D1 database:**
   ```bash
   cd gallery
   npx wrangler d1 create claude-draws-submissions
   ```

2. **Update wrangler.toml:**
   - Copy the `database_id` from the output
   - Replace `TO_BE_CREATED` in `wrangler.toml` with the actual database ID

3. **Run migrations:**
   ```bash
   # For production
   npx wrangler d1 migrations apply claude-draws-submissions --remote

   # For local development (optional)
   npx wrangler d1 migrations apply claude-draws-submissions --local
   ```

## Querying the Database

```bash
# Execute SQL queries (production)
npx wrangler d1 execute claude-draws-submissions --remote --command "SELECT * FROM submissions WHERE status = 'pending' ORDER BY created_at LIMIT 10;"

# Execute SQL queries (local)
npx wrangler d1 execute claude-draws-submissions --local --command "SELECT * FROM submissions LIMIT 10;"
```

## Testing Locally

```bash
# Start local dev server with D1
npm run dev
```

The D1 database will be available in your SvelteKit API routes via `platform.env.DB`.
