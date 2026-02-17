# ClaudeVN Marketing Site

Static marketing site built with React + Vite, served via Nginx in Docker.

## Local Development

```bash
cd site
npm install
npm run dev        # http://localhost:3000
```

## Docker

```bash
# Run just the marketing site
docker compose --profile site up site

# Run the full platform including the site
docker compose --profile full up
```

The site is served at **http://localhost:3000**.

## Production Build

```bash
npm run build      # Output in dist/
npm run preview    # Preview the production build locally
```

## Deployment (AWS S3 + CloudFront)

### Prerequisites

- AWS CLI configured with appropriate credentials
- S3 bucket configured for static website hosting
- CloudFront distribution pointing to the S3 bucket

### Deploy

```bash
BUCKET_NAME=claudevn-site CF_DIST_ID=E1234567890 ./deploy/deploy.sh
```

The deploy script will:
1. Install dependencies and build the site
2. Sync the `dist/` directory to S3 (with `--delete` to remove stale files)
3. Set cache headers: long cache (1 year, immutable) for hashed assets, short cache (5 min) for `index.html`
4. Invalidate the CloudFront cache

### Cache Strategy

| File | Cache-Control | Rationale |
|------|--------------|-----------|
| `/assets/*` (hashed) | `public, max-age=31536000, immutable` | Content-hashed filenames allow aggressive caching |
| `index.html` | `public, max-age=300, must-revalidate` | Must revalidate frequently to pick up new asset hashes |
| `robots.txt`, `sitemap.xml` | `public, max-age=3600` | Infrequently changed, 1-hour cache is sufficient |
