# FallbackRabbit — Deployment

This directory contains the deployable website + docs for [fallbackrabbit.melabuilt.ai](https://fallbackrabbit.melabuilt.ai).

## Structure

- `index.html` — Landing page
- `docs/` — MkDocs Material documentation (built from `docs/` + `mkdocs.yml`)
- `assets/` — Static assets (images, OG image, etc.)

## Cloudflare Pages Deployment

### Automatic (GitHub Integration)

1. Go to Cloudflare Pages → Create project → Connect Git
2. Select `MelaBuilt-AI/FallbackRabbit`
3. Configure:
   - **Build command:** `cd /home/mela_ai/.openclaw/workspace/fallback-rabbit && .venv/bin/mkdocs build --site-dir deploy/docs`
   - **Build output:** `deploy`
   - **Root directory:** `/`
4. Add custom domain: `fallbackrabbit.melabuilt.ai`

### Manual (Wrangler)

```bash
# Build docs
mkdocs build --site-dir deploy/docs

# Deploy
npx wrangler pages deploy deploy/ --project-name=fallbackrabbit
```

## Building Docs

```bash
# Install mkdocs material (if not already)
pip install mkdocs-material

# Build
mkdocs build --site-dir deploy/docs

# Serve locally
mkdocs serve
```