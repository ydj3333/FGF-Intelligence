"""FGF v6.3 live observer client for Windows.

Captures only the selected FGF window, detects visual changes, and sends
structured screen-change events to the FGF API.

Safety:
- hard two-hour daily observation budget;
- local state file tracks the budget;
- no raw video is uploaded;
- no mouse/keyboard control;
- unknown changes remain unknown.
"""
from __future__ import annotations
import ctypes, json, os, time, uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import URLError, HTTPError
from urllib.request import Request, urlopen
import cv2
import numpy as np
from PIL import ImageGrab

DAILY_LIMIT_SECONDS = 7200
SAMPLE_FPS = 5.0
CHANGE_THRESHOLD = 8.0
MIN_EVENT_GAP_SECONDS = 2.0
STATE_FILE = Path.home() / ".fgf_observer_state.json"
API_URL = os.getenv("FGF_API_URL", "http://127.0.0.1:8000").rstrip("/")
OBSERVER_TOKEN = os.getenv("FGF_OBSERVER_TOKEN", "")
OBSERVER_VERSION = "0.1-live"
PLAYER_ID = os.getenv("FGF_PLAYER_ID", "")

user32 = ctypes.windll.user32
try:
    user32.SetProcessDPIAware()
except Exception:
    pass

def _local_day():
    return datetime.now().astimezone().date().isoformat()

def _load_budget():
    try:
        data=json.loads(STATE_FILE.read_text(encoding="utf-8"))
        if data.get("local_day")==_local_day():
            return int(data.get("used_seconds",0))
    except Exception:
        pass
    return 0

def _save_budget(used):
    STATE_FILE.write_text(json.dumps({"local_day":_local_day(),"used_seconds":int(max(0,used))},indent=2),encoding="utf-8")

def _windows():
    windows=[]
    callback_type=ctypes.WINFUNCTYPE(ctypes.c_bool,ctypes.c_void_p,ctypes.c_void_p)
    def callback(hwnd,_):
        if not user32.IsWindowVisible(hwnd): return True
        length=user32.GetWindowTextLengthW(hwnd)
        if length<=0: return True
        buf=ctypes.create_unicode_buffer(length+1)
        user32.GetWindowTextW(hwnd,buf,length+1)
        title=buf.value.strip()
        if not title: return True
        rect=ctypes.wintypes.RECT()
        if not user32.GetWindowRect(hwnd,ctypes.byref(rect)): return True
        width=rect.right-rect.left; height=rect.bottom-rect.top
        if width>=300 and height>=200:
            windows.append({"hwnd":int(hwnd),"title":title,"left":rect.left,"top":rect.top,"right":rect.right,"bottom":rect.bottom,"width":width,"height":height})
        return True
    user32.EnumWindows(callback_type(callback),0)
    return windows

def _client_bbox(hwnd):
    class POINT(ctypes.Structure):
        _fields_=[("x",ctypes.c_long),("y",ctypes.c_long)]
    rect=ctypes.wintypes.RECT()
    if not user32.GetClientRect(hwnd,ctypes.byref(rect)): raise RuntimeError("GetClientRect failed")
    p1,p2=POINT(rect.left,rect.top),POINT(rect.right,rect.bottom)
    user32.ClientToScreen(hwnd,ctypes.byref(p1)); user32.ClientToScreen(hwnd,ctypes.byref(p2))
    return p1.x,p1.y,p2.x,p2.y

def _capture(hwnd):
    left,top,right,bottom=_client_bbox(hwnd)
    if right<=left or bottom<=top: raise RuntimeError("FGF client area is invalid")
    image=ImageGrab.grab(bbox=(left,top,right,bottom),all_screens=True)
    frame=np.asarray(image)
    if frame.ndim==3 and frame.shape[2]==4: return cv2.cvtColor(frame,cv2.COLOR_RGBA2BGR)
    return cv2.cvtColor(frame,cv2.COLOR_RGB2BGR)

def _change_score(previous,current):
    a=cv2.resize(previous,(320,180)); b=cv2.resize(current,(320,180))
    a=cv2.cvtColor(a,cv2.COLOR_BGR2GRAY); b=cv2.cvtColor(b,cv2.COLOR_BGR2GRAY)
    diff=cv2.absdiff(a,b)
    return float(np.mean(diff))*0.65+float(np.mean(diff>12))*100.0*0.35

def _post(path,payload):
    body=json.dumps(payload,ensure_ascii=False).encode("utf-8")
    headers={"Content-Type":"application/json","Accept":"application/json"}
    if OBSERVER_TOKEN: headers["X-FGF-Observer-Token"]=OBSERVER_TOKEN
    req=Request(API_URL+path,data=body,headers=headers,method="POST")
    with urlopen(req,timeout=8) as response:
        return json.loads(response.read().decode("utf-8") or "{}")

def choose_window():
    windows=_windows()
    if not windows: raise RuntimeError("No visible Windows applications found.")
    print("\nVisible windows:")
    for i,item in enumerate(windows,1):
        print(f"[{i:02d}] {item['title'][:80]} ({item['width']}x{item['height']})")
    while True:
        raw=input("\nFGF window number: ").strip()
        try:
            index=int(raw)
            if 1<=index<=len(windows): return windows[index-1]
        except ValueError: pass
        print("Enter a valid window number.")

def main():
    used=_load_budget()
    remaining=max(0,DAILY_LIMIT_SECONDS-used)
    if remaining<=0: raise SystemExit("FGF daily observation limit (2 hours) is already used today.")
    window=choose_window(); hwnd=window["hwnd"]; session_id=str(uuid.uuid4())
    print(f"\nSelected: {window['title']}")
    print(f"Daily observation remaining: {remaining//60} min {remaining%60} sec")
    print(f"API: {API_URL}")
    print("No raw video will be uploaded.")
    try:
        print(_post("/api/v63/live/session/start",{
            "session_id":session_id,"player_id":PLAYER_ID,
            "observer_version":OBSERVER_VERSION,
            "metadata":{"local_day":_local_day(),"window_title":window["title"],"sample_fps":SAMPLE_FPS}
        }))
    except Exception as exc:
        raise SystemExit(f"Could not connect to FGF live API: {type(exc).__name__}: {exc}")
    for n in range(5,0,-1):
        print(f"Starting in {n}..."); time.sleep(1)
    started=time.monotonic(); next_tick=started; previous=_capture(hwnd)
    last_event=0.0; sent=0; dropped=0
    print("\nLIVE OBSERVATION STARTED. Press Ctrl+C to stop.\n")
    try:
        while True:
            elapsed=time.monotonic()-started
            if elapsed>=remaining: break
            now=time.monotonic()
            if now<next_tick:
                time.sleep(min(0.2,next_tick-now)); continue
            if not user32.IsWindow(hwnd):
                print("FGF window closed; stopping safely."); break
            frame=_capture(hwnd); score=_change_score(previous,frame)
            if score>=CHANGE_THRESHOLD and now-last_event>=MIN_EVENT_GAP_SECONDS:
                event={
                    "session_id":session_id,"event_type":"screen_changed",
                    "entity_type":"screen","entity_key":window["title"],
                    "property":"visual_change_score","new_value":round(score,3),
                    "observed_at":datetime.now(timezone.utc).isoformat(),
                    "confidence":None,"source_capture":"local_window_capture",
                    "pattern":"FGF screen changed; semantic event classification pending.",
                    "context":{"player_id":PLAYER_ID,"screen":window["title"],"observer_version":OBSERVER_VERSION}
                }
                try:
                    _post("/api/v63/live/observe",event); sent+=1; last_event=now
                except (HTTPError,URLError,OSError) as exc:
                    dropped+=1; print(f"Event delivery failed: {type(exc).__name__}: {exc}")
            previous=frame; next_tick+=1.0/SAMPLE_FPS
            if sent and sent%10==0: print(f"elapsed={int(elapsed)}s | events_sent={sent} | dropped={dropped}")
    except KeyboardInterrupt:
        print("\nStopped by user.")
    finally:
        elapsed=min(int(time.monotonic()-started),remaining)
        _save_budget(used+elapsed)
        try: print(_post("/api/v63/live/session/stop",{"session_id":session_id}))
        except Exception as exc: print(f"Session close warning: {type(exc).__name__}: {exc}")
    print(f"\nLIVE OBSERVATION COMPLETE: {elapsed}s")
    print(f"Events sent: {sent}")
    print(f"Events dropped: {dropped}")
    print(f"Daily budget used: {used+elapsed}/{DAILY_LIMIT_SECONDS}s")

if __name__=="__main__":
    main()
