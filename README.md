# My Tools

A static site collecting the small apps and tools I build. Hosted free on Cloudflare Workers
at https://my-tools.hill-brendon.workers.dev.

Only the `public/` folder is published (set in `wrangler.jsonc`). Anything outside it stays private.

## Adding a tool

1. Create a folder inside `public/`, e.g. `public/pomodoro/`, with an `index.html` inside.
2. Add a card for it in `public/index.html`.
3. Commit and push. Cloudflare redeploys automatically.

## One-time setup

1. Create an empty **private or public** repo on GitHub named `my-tools` (no README).
2. Push this folder:
   ```bash
   git remote add origin https://github.com/<your-username>/my-tools.git
   git push -u origin main
   ```
3. In GitHub repo **Settings → Code security**, enable **Secret scanning** and **Push protection**.
4. Sign in at https://dash.cloudflare.com → **Workers & Pages → Create → Pages → Connect to Git**.
5. Pick the `my-tools` repo. Framework preset: **None**. Build command: *(leave empty)*. Output directory: `/`.
6. Deploy. Your site is live at `https://my-tools.pages.dev` (or similar).
7. Optional: **Custom domains** tab to attach a domain you own.

## Security notes

- Everything runs in the browser, so **never put API keys or passwords in any file here**: anyone can read them.
- `public/_headers` sets security headers (CSP, HSTS, clickjacking protection). If a tool loads scripts
  from a CDN not listed there, add the domain to `script-src` or the tool will break.
- Check headers after deploying at https://securityheaders.com.
