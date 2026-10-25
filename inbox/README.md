# Screenshot inbox

Upload screenshots here and their game facts are added to the FGF knowledge base automatically, usually within 5 minutes.

| Folder | Put here | Enters as |
|---|---|---|
| `official/` | posts from the official **Instagram, Facebook, X or Discord** | Tier 2, live in the app |
| `ingame/` | **in-game** screens, notices, event pages | Tier 1, *Under Review* (you confirm it in the weekly admin review) |
| `community/` | creator or community posts | Tier 3, live in the app |

**From your phone:** open the repository in the GitHub app or on github.com → open the folder → **Add file → Upload files** → pick the screenshots → **Commit changes**.

Name files after their source and date where you can, e.g. `instagram-2026-10-20-astral-party.jpg`.

The AI copies the text from each image and keeps only facts whose words and numbers appear in that text. Facts already known are skipped. Facts that contradict official evidence are kept aside as *disputed* for review. Processed images move to `processed/<date>/` and are kept as evidence. The results are listed under GitHub → Actions → **FGF Screenshot Inbox**.
