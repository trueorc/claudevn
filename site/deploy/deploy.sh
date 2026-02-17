#!/usr/bin/env bash
set -euo pipefail

# ClaudeVN Marketing Site - S3 + CloudFront Deployment
#
# Required environment variables:
#   BUCKET_NAME    - S3 bucket name (e.g., claudevn-site)
#   CF_DIST_ID     - CloudFront distribution ID
#
# Optional:
#   AWS_PROFILE    - AWS CLI profile to use
#
# Usage:
#   BUCKET_NAME=claudevn-site CF_DIST_ID=E1234567890 ./deploy.sh

if [ -z "${BUCKET_NAME:-}" ]; then
  echo "Error: BUCKET_NAME is required" >&2
  exit 1
fi

if [ -z "${CF_DIST_ID:-}" ]; then
  echo "Error: CF_DIST_ID is required" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SITE_DIR="$(dirname "$SCRIPT_DIR")"

echo "Building site..."
cd "$SITE_DIR"
npm ci
npm run build

echo "Syncing to s3://${BUCKET_NAME}..."
aws s3 sync dist/ "s3://${BUCKET_NAME}" \
  --delete \
  --cache-control "public, max-age=31536000, immutable" \
  --exclude "index.html" \
  --exclude "robots.txt" \
  --exclude "sitemap.xml"

# Upload index.html and SEO files with short cache
aws s3 cp dist/index.html "s3://${BUCKET_NAME}/index.html" \
  --cache-control "public, max-age=300, must-revalidate"

for f in robots.txt sitemap.xml; do
  if [ -f "dist/${f}" ]; then
    aws s3 cp "dist/${f}" "s3://${BUCKET_NAME}/${f}" \
      --cache-control "public, max-age=3600"
  fi
done

echo "Invalidating CloudFront cache..."
aws cloudfront create-invalidation \
  --distribution-id "${CF_DIST_ID}" \
  --paths "/*"

echo "Deployment complete."
