# FallbackRabbit — Website

This directory contains the static website for [fallbackrabbit.melabuilt.ai](https://fallbackrabbit.melabuilt.ai), deployed via Cloudflare Pages.

## Structure

- `index.html` — Landing page
- `docs/` — MkDocs documentation (built and deployed separately)

## Deployment

The website is automatically deployed to Cloudflare Pages when changes are pushed to the `main` branch.

### Cloudflare Pages Setup

1. Create a new project in Cloudflare Pages
2. Connect the GitHub repository: `MelaBuilt-AI/FallbackRabbit`
3. Build command: (none — static HTML)
4. Build output directory: `website`
5. Custom domain: `fallbackrabbit.melabuilt.ai`

### Manual Deploy

```bash
# Using wrangler
npx wrangler pages deploy website/ --project-name=fallbackrabbit
```