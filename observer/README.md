# FGF v6.3 Live Observer

This is the live bridge from the Windows FGF game client into FGF Intelligence.

Current behavior:
- selects the FGF Windows window;
- captures only that window;
- samples the screen locally;
- detects meaningful visual changes;
- sends structured screen-change events to the FGF API;
- keeps a local two-hour-per-day hard budget;
- sends no raw video;
- has no mouse or keyboard control.

Semantic events such as Champion level changes, rewards, battle results and resource changes are the next observation-layer upgrade. The server contract already accepts those event types.

Configuration:
- FGF_API_URL, default http://127.0.0.1:8000
- FGF_OBSERVER_TOKEN, optional observer API token
- FGF_PLAYER_ID, optional player identifier

Install:

    py -m pip install -r requirements.txt

Run:

    py fgf_live_observer.py

Never put a Supabase secret key in this client.
