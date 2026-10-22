# FGF Intelligence app: one-time setup (about 10 minutes, all free)

After these steps everything runs by itself:

- Your knowledge base syncs every 6 hours (existing "FGF Corpus Synchronization" workflow).
- After each sync, the **"Publish FGF app"** workflow rebuilds the app with the fresh data and publishes it.
- Installed apps on phones pick up the new version automatically the next time they open.
- AI answers come from Google Gemini's free tier through your own small proxy. If one model is busy or out of quota, the next is used. If AI is unavailable, the app still answers from the knowledge base.

Your app's address will be `https://<your-github-name>.github.io/<repo-name>/`
(for this repo: **https://ydj3333.github.io/FGF-Intelligence/**). The exact link is shown at the end of each workflow run.

---

## Step 1 – Put this code on GitHub
Merge this branch into `main`, either through a pull request or by letting Claude push it once GitHub is linked.

## Step 2 – Turn on GitHub Pages (one click)
GitHub repo → **Settings** → **Pages** → under *Build and deployment*, set **Source** to **GitHub Actions**.

At this point the app already works, with instant answers, guides and facts. Steps 3–5 add free AI answers.

## Step 3 – Get a free Gemini key
1. Open **https://aistudio.google.com** and sign in with a Google account.
2. Click **Get API key** → **Create API key** and copy it.

Google's free tier has daily limits. Free-tier requests may be used by Google to improve its products; that's fine for public game questions.

## Step 4 – Get a free Cloudflare account (hosts the AI proxy)
1. Sign up at **https://dash.cloudflare.com** (free plan).
2. Click **Workers & Pages** once. Copy your **Account ID** from the right-hand side of that page.
3. Profile icon → **My Profile** → **API Tokens** → **Create Token** → use the template **"Edit Cloudflare Workers"** → **Continue to summary** → **Create Token**. Copy the token.

## Step 5 – Add three secrets to GitHub
GitHub repo → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**, once for each:

| Name | Value |
|---|---|
| `GEMINI_API_KEY` | the key from Step 3 |
| `CLOUDFLARE_API_TOKEN` | the token from Step 4 |
| `CLOUDFLARE_ACCOUNT_ID` | the Account ID from Step 4 |

Optional backup AI: a free key from **https://console.groq.com** saved as `GROQ_API_KEY`.

## Step 6 – Publish
GitHub repo → **Actions** → **Publish FGF app** → **Run workflow**. It takes 2–3 minutes. When it finishes, open the link shown under *build-and-publish*. The top bar should say **AI answers on**.

---

## Installing the app on a phone
- **Android (Chrome):** open the link and tap **Install app** in the top bar, or use the menu (⋮) → **Install app**.
- **iPhone (Safari):** open the link → **Share** → **Add to Home Screen**.

It opens full-screen with its own icon. Guides, facts and instant answers work offline; AI answers need internet.

## If something isn't right
- **The top bar says "Instant answers":** the AI proxy isn't set up or is unreachable. Check that the three secrets exist, then run **Publish FGF app** again. Its log says whether the proxy is healthy.
- **"The free AI has reached today's limit":** Gemini's free quota is used up for the day. It resets at midnight Pacific time. Adding `GROQ_API_KEY` gives a second free quota.
- **Using your own domain:** set a repository *variable* `FGF_SITE_ORIGIN` to `https://your-domain` so the proxy accepts it.

## What's where
| Path | What it is |
|---|---|
| `site/src/` | the app: page, search/fact-check engine, app logic |
| `site/build_site.py` | builds the app from `data/knowledge.json` (+ curated plans) |
| `site/tests/` | engine tests, local test stack, end-to-end browser test |
| `worker/` | the free AI proxy (Cloudflare Worker) and its tests |
| `.github/workflows/publish-app.yml` | the automation |
