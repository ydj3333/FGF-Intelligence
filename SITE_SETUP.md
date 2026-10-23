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

## Automatic data collection (the database fills itself)

The **FGF Source Harvest** workflow runs every 6 hours and needs the same `GEMINI_API_KEY`, plus the Supabase key your corpus sync already uses. On each run it:

1. Reads every source in `data/harvest_sources.json` **and every web source already registered in your Supabase `sources` table** (inactive rows are skipped, and nothing is read twice).
2. Skips pages, posts and videos it has already processed.
3. Has the free AI pull out individual game facts from each new or changed item.
4. **Keeps a fact only if its quoted sentence appears in the source and every number in it appears there too.** Invented or garbled facts are rejected.
5. Skips facts the database already has. A fact that **contradicts** Tier 1/2 evidence (e.g. "12 permits" when the official fact says 10) is saved as **disputed** for your review and never overwrites anything.
6. Adds the new facts. Nothing is ever made Tier 1 or canonical automatically. Each fact keeps its source link, quote and date.
7. If anything new was added, it starts the database sync straight away. The app republishes a few minutes later.

The 6-hourly activity also stops a free Supabase project from being paused for inactivity.

### What is covered
| Source | How it's read | Enters as |
|---|---|---|
| foundation.game news and patches, official portal | automatically | Tier 2, live |
| Steam update notes | automatically | Tier 2, live |
| FGF wiki, Fandom wiki, Reddit | automatically | Tier 3, live |
| **Official YouTube channel** | automatically: the video description is read, and **Gemini watches each new video** | description facts Tier 2, live; facts from watching the video Tier 2 *Under Review* with a link to the exact minute |
| **YouTube playlists** (e.g. PLhETODnD1CQ9UEHk7NDJVeifZo-Bz3oDv) | automatically: Gemini watches each video | Tier 3 *Under Review* |
| **Discord** announcements | automatically once you set up the bot (below) | Tier 2, live; text in posted images is read too |
| **Instagram, Facebook, X** and in-game screens | screenshot inbox (below): these sites block automatic reading without a login | Tier 2 / Tier 1 *Under Review* / Tier 3 |
| Any other site in your `sources` table | automatically | the tier set in that row (2 or 3) |

Videos your old transcript pipeline has already turned into candidates are not watched again. Gemini's free tier allows about 8 hours of YouTube video a day. The harvester watches at most 3 new videos per source per run, which keeps it well inside that limit. Only public videos can be watched. Video facts always stay *Under Review*, because YouTube is supporting evidence and not canonical truth (core objectives). This replaces the manual "run the PC acquisition" step for new videos.

### Discord (optional, 5 minutes)
A bot can only read servers it has been added to, so the free route is to follow the official announcements into **your own** server:
1. In the official FGF Discord, open the announcements channel. If it shows **Follow**, click it and choose a channel in your own server (create a free server if you don't have one). If there's no Follow button, use the screenshot inbox for Discord posts instead.
2. Go to **discord.com/developers/applications** → **New Application** → **Bot** → **Reset Token** and copy the token. On the same page, turn on **Message Content Intent**.
3. **OAuth2 → URL Generator**: tick **bot**, then the permissions **View Channels** and **Read Message History**. Open the generated link and add the bot to your server.
4. In Discord: **Settings → Advanced → Developer Mode** on. Right-click the channel that receives the announcements → **Copy Channel ID**. Right-click your server → **Copy Server ID**.
5. In GitHub: add a secret `DISCORD_BOT_TOKEN` (the token) and variables `FGF_DISCORD_CHANNEL_IDS` (the channel ID; separate several with commas) and `FGF_DISCORD_GUILD_ID` (the server ID).

The first run reads the newest 15 posts, and later runs read only new ones. Until the bot is set up, the run summary shows Discord as *not configured*. That is not an error.

### Screenshot inbox (Instagram, Facebook, X, in-game)
Upload screenshots to the `inbox/` folder of the repository: from the GitHub phone app or github.com, open `inbox/official`, `inbox/ingame` or `inbox/community` → **Add file → Upload files** → **Commit changes**. The **FGF Screenshot Inbox** workflow reads the text in each image, keeps only facts whose words and numbers appear in it, and moves the image to `inbox/processed/` as evidence. In-game screenshots enter as Tier 1 *Under Review*, so you confirm them before they count as Tier 1. See `inbox/README.md`.

### Checking and trying it
Each run's summary (GitHub → Actions → FGF Source Harvest) lists every new fact, every disputed fact and every source that couldn't be read. To try it safely first, run it manually with **dry run** ticked: it reports what it would add without writing anything.

To add a source, either add a row to the Supabase `sources` table (a web address, a name, and a tier of 2 or 3), or add an entry to `data/harvest_sources.json`. The available adapters are `page`, `news_index`, `steam_news`, `sitemap`, `mediawiki_recent`, `reddit_new`, `youtube_channel`, `youtube_playlist` and `discord_channel`.

## What the app knows
Everything is built into the app, so it works offline too:
- every fact in the database (official, wiki and community; unverified and disputed ones are labelled);
- the YouTube facts from creator videos, labelled "creator video" and ranked below official facts;
- the curated event guides.

Every 6 hours, new facts flow in on their own: sources → database → app. The AI follows the project's rules:
- official facts first;
- no invented numbers;
- unverified and video facts presented as unconfirmed;
- "give me 5 options" returns exactly 5, using labelled templates instead of invented Champion names.

## The app learns from players (one-time: 2 minutes)
Under every answer, players can tap 👍 / 👎 or **Correct this** (with an optional link to proof). When the AI can't answer a question from the facts, the app notes that too. All of this is sent anonymously, with no account or device details.

Every night the **FGF Learning** workflow:
- **checks every link players send**: facts from that page or video go through the same checks as the harvester and enter *Under Review*. Players can point to evidence but never change facts directly.
- **collects knowledge gaps** (questions asked often but not answered) for your review page, and marks them *covered* once the facts arrive.
- puts **corrections without a link** on your review page.
- **flags facts** that keep appearing in unhelpful answers so you can re-check them.
- writes everything to `data/learning_report.md`, and starts a database sync when new facts were found.

To switch it on:
1. In Supabase → **SQL Editor**, paste the contents of `sql/app_feedback.sql` and click **Run**. This creates the feedback table with security rules: the public key may only *add* feedback, never read it. No existing table is changed.
2. Recommended: in Supabase → **Settings → API keys**, copy the **publishable** key and add it in GitHub as the secret `FGF_SUPABASE_PUBLISHABLE_KEY`. Without it, the existing Supabase secret key is used.
3. Run **Publish FGF app** once, so the AI proxy gets the setting.

## Your review page (one-time: 3 minutes)
Everything the system adds by itself waits for you on one private page, which works on a phone: **https://ydj3333.github.io/FGF-Intelligence/admin.html** (bookmark it; players don't see a link to it).

| Tab | What's there | Your buttons |
|---|---|---|
| **To review** | new facts from the harvester, screenshots, watched videos and player links, with the quote and a link to the source | Approve · Approve as Tier 1 (needs your proof) · Reject. Tick several to approve or reject them together. Search and tier filter. |
| **Disputes** | a new fact next to the official fact it contradicts | Keep current fact · Accept new, retire old |
| **Player corrections** | corrections players sent without a link | Add as a fact · Done · Dismiss |
| **Knowledge gaps** | questions players ask that the app can't answer, most asked first | Answer with a fact · Dismiss |
| **+ Add a fact** | add something you've confirmed yourself | Save (exact duplicates are refused) |

Approved changes reach players with the next sync (within 6 hours), or straight away with **Publish now**. Every decision is recorded with the date, your note and the previous state, both in the fact itself and in the `admin_audit` table. Tier 1 is only ever set by you, with proof.

To switch it on:
1. Run `sql/app_feedback.sql` in Supabase (the same script as the learning loop; re-running it is safe). It adds the gap and audit tables.
2. In GitHub, add a secret `FGF_ADMIN_PASSWORD`: a password of **at least 12 characters** that you don't use anywhere else. Five wrong tries lock sign-in for 10 minutes, and a sign-in lasts 12 hours. To sign everyone out, change the password and run Publish FGF app.
3. Optional, for **Publish now**: create a fine-grained token on GitHub (Settings → Developer settings → Fine-grained tokens) with access to this repository only and the permission *Actions: Read and write*. Add it as the secret `FGF_GITHUB_DISPATCH_TOKEN`.
4. Run **Publish FGF app** once.

The proxy gets the Supabase secret key only when the review password is set. The key stays in Cloudflare's encrypted secrets and is never in the app or in Git.

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
| `scripts/harvest_sources.py`, `data/harvest_sources.json` | the self-filling harvester and its source list |
| `scripts/ingest_screenshots.py`, `inbox/` | the screenshot inbox |
| `.github/workflows/fgf-source-harvest.yml`, `fgf-screenshot-inbox.yml` | their schedules |
| `scripts/learn_from_players.py`, `.github/workflows/fgf-learning.yml`, `sql/app_feedback.sql` | the learning loop |
| `scripts/export_video_evidence.py` | brings the YouTube facts into the app at each publish |
| `data/knowledge_gaps.json`, `data/learning_report.md` | snapshot of knowledge gaps and fact votes; the nightly learning report |
| `site/src/admin.html`, `site/src/admin.js`, `worker/src/admin.js` | your review page and its API |
