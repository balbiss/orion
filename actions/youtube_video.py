#youtube_video.py
import json
import re
import sys
import time
import subprocess
import shutil
from pathlib import Path
from datetime import datetime
from urllib.parse import quote_plus

try:
    import pyautogui
    _PYAUTOGUI = True
except ImportError:
    _PYAUTOGUI = False

try:
    import pygetwindow as gw
    _PYGETWINDOW = True
except ImportError:
    _PYGETWINDOW = False

try:
    import numpy as np
    _NUMPY = True
except ImportError:
    _NUMPY = False

try:
    import requests
    _REQUESTS_OK = True
except ImportError:
    _REQUESTS_OK = False

try:
    from youtube_transcript_api import YouTubeTranscriptApi
    _TRANSCRIPT_OK = True
except ImportError:
    _TRANSCRIPT_OK = False

from config import get_os, is_windows, is_mac, is_linux


def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR        = _get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

_YT_VIDEO_FILTER = "EgIQAQ%3D%3D"


def _get_api_key() -> str:
    with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["gemini_api_key"]


def _open_url(url: str) -> None:
    try:
        if is_mac():
            subprocess.Popen(["open", url])
        elif is_linux():
            subprocess.Popen(["xdg-open", url])
        else:
            subprocess.Popen(["cmd", "/c", "start", "", url], shell=False)
    except Exception as e:
        print(f"[YouTube] ⚠️ open_url failed: {e}")

def _scrape_first_video_url(query: str) -> str | None:

    if not _REQUESTS_OK:
        return None

    search_url = (
        f"https://www.youtube.com/results"
        f"?search_query={quote_plus(query)}"
        f"&sp={_YT_VIDEO_FILTER}"
    )

    try:
        r    = requests.get(search_url, headers=HEADERS, timeout=10)
        html = r.text

        video_ids = re.findall(r'"videoId":"([A-Za-z0-9_-]{11})"', html)

        seen = set()
        for vid in video_ids:
            if vid in seen:
                continue
            seen.add(vid)

            if f'/shorts/{vid}' in html:
                continue
            return f"https://www.youtube.com/watch?v={vid}"

    except Exception as e:
        print(f"[YouTube] ⚠️ scrape_first_video_url failed: {e}")

    return None

def _extract_video_id(url: str) -> str | None:
    match = re.search(
        r"(?:v=|\/v\/|youtu\.be\/|\/embed\/|\/shorts\/)([A-Za-z0-9_-]{11})", url
    )
    return match.group(1) if match else None


def _is_valid_youtube_url(url: str) -> bool:
    return bool(re.search(r"(youtube\.com|youtu\.be)", url or ""))


def _ask_for_url(prompt_text: str = "YouTube video URL:") -> str | None:
    try:
        import tkinter as tk
        from tkinter import simpledialog

        root = tk._default_root
        if root is None:
            root = tk.Tk()
            root.withdraw()

        url = simpledialog.askstring("J.A.R.V.I.S", prompt_text, parent=root)
        return url.strip() if url else None
    except Exception as e:
        print(f"[YouTube] ⚠️ URL dialog failed: {e}")
        return None


def _get_transcript(video_id: str) -> str | None:
    if not _TRANSCRIPT_OK:
        return None
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        transcript      = None

        lang_priority = ["en", "tr", "de", "fr", "es", "it", "pt", "ru", "ja", "ko", "ar", "zh"]

        try:
            transcript = transcript_list.find_manually_created_transcript(lang_priority)
        except Exception:
            pass

        if transcript is None:
            try:
                transcript = transcript_list.find_generated_transcript(lang_priority)
            except Exception:
                for t in transcript_list:
                    transcript = t
                    break

        if transcript is None:
            return None

        fetched = transcript.fetch()
        return " ".join(entry["text"] for entry in fetched)

    except Exception as e:
        print(f"[YouTube] ⚠️ Transcript fetch failed: {e}")
        return None


def _summarize_with_gemini(transcript: str, video_url: str) -> str:
    from google import genai as _genai
    from google.genai import types

    _client = _genai.Client(api_key=_get_api_key())
    max_chars = 80000
    truncated = transcript[:max_chars] + ("..." if len(transcript) > max_chars else "")
    response  = _client.models.generate_content(
        model="gemini-2.5-flash",
        contents=f"Please summarize this YouTube video transcript:\n\n{truncated}",
        config=types.GenerateContentConfig(
            system_instruction=(
                "You are ORION, an AI assistant. "
                "Summarize YouTube video transcripts clearly and concisely. "
                "Structure: 1-sentence overview, then 3-5 key points. "
                "Be direct. Address the user as 'sir'. "
                "Match the language of the transcript."
            )
        )
    )
    return response.text.strip()


def _save_summary(content: str, video_url: str) -> str:
    ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"youtube_summary_{ts}.txt"
    desktop  = Path.home() / "Desktop"
    desktop.mkdir(parents=True, exist_ok=True)
    filepath = desktop / filename

    header = (
        f"ORION — YouTube Summary\n"
        f"{'─' * 50}\n"
        f"URL    : {video_url}\n"
        f"Date   : {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        f"{'─' * 50}\n\n"
    )
    filepath.write_text(header + content, encoding="utf-8")

    try:
        if is_windows():
            subprocess.Popen(["notepad.exe", str(filepath)])
        elif is_mac():
            subprocess.Popen(["open", "-t", str(filepath)])
        else:
            subprocess.Popen(["xdg-open", str(filepath)])
    except Exception as e:
        print(f"[YouTube] ⚠️ Could not open text editor: {e}")

    return str(filepath)


def _scrape_video_info(video_id: str) -> dict:
    if not _REQUESTS_OK:
        return {}
    url = f"https://www.youtube.com/watch?v={video_id}"
    try:
        r    = requests.get(url, headers=HEADERS, timeout=12)
        html = r.text
        info = {}

        for key, pattern in [
            ("title",    r'"title":\{"runs":\[\{"text":"([^"]+)"'),
            ("channel",  r'"ownerChannelName":"([^"]+)"'),
            ("views",    r'"viewCount":"(\d+)"'),
            ("duration", r'"lengthSeconds":"(\d+)"'),
            ("likes",    r'"label":"([0-9,]+ likes)"'),
        ]:
            match = re.search(pattern, html)
            if match:
                raw = match.group(1)
                if key == "views":
                    info[key] = f"{int(raw):,}"
                elif key == "duration":
                    secs = int(raw)
                    info[key] = f"{secs // 60}:{secs % 60:02d}"
                else:
                    info[key] = raw

        return info
    except Exception as e:
        print(f"[YouTube] ⚠️ Info scrape failed: {e}")
        return {}


def _scrape_trending(region: str = "TR", max_results: int = 8) -> list[dict]:
    if not _REQUESTS_OK:
        return []
    url = f"https://www.youtube.com/feed/trending?gl={region.upper()}"
    try:
        r    = requests.get(url, headers=HEADERS, timeout=12)
        html = r.text

        titles   = re.findall(r'"title":\{"runs":\[\{"text":"([^"]+)"\}\]', html)
        channels = re.findall(r'"ownerText":\{"runs":\[\{"text":"([^"]+)"', html)

        results, seen = [], set()
        for i, title in enumerate(titles):
            if title in seen or len(title) < 5:
                continue
            seen.add(title)
            channel = channels[i] if i < len(channels) else "Unknown"
            results.append({"rank": len(results) + 1, "title": title, "channel": channel})
            if len(results) >= max_results:
                break

        return results
    except Exception as e:
        print(f"[YouTube] ⚠️ Trending scrape failed: {e}")
        return []

def _focus_youtube_window() -> bool:
    for attempt in range(3):
        if is_windows():
            try:
                import win32gui
                import win32con
                import ctypes

                found = []

                def _cb(hwnd, _):
                    if win32gui.IsWindowVisible(hwnd):
                        if "youtube" in win32gui.GetWindowText(hwnd).lower():
                            found.append(hwnd)

                win32gui.EnumWindows(_cb, None)
                if found:
                    hwnd = found[0]
                    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                    # ALT key trick: bypass Windows foreground lock
                    ctypes.windll.user32.keybd_event(0x12, 0, 0, 0)       # ALT down
                    ctypes.windll.user32.keybd_event(0x12, 0, 0x0002, 0)  # ALT up
                    win32gui.SetForegroundWindow(hwnd)
                    time.sleep(0.5)
                    return True
            except Exception as e:
                print(f"[YouTube] ⚠️ win32gui focus failed: {e}")

        if _PYGETWINDOW:
            for title in gw.getAllTitles():
                if "youtube" in title.lower():
                    wins = gw.getWindowsWithTitle(title)
                    if wins:
                        try:
                            wins[0].activate()
                            time.sleep(0.5)
                            return True
                        except Exception:
                            pass

        if attempt < 2:
            time.sleep(0.8)

    print("[YouTube] ⚠️ Could not find YouTube window to focus.")
    return False


def _skip_ad() -> str:
    """Use Gemini vision to find and click the Skip Ad / Pular button."""
    if not _PYAUTOGUI:
        return "pyautogui not installed."
    try:
        import io
        import re as _re
        from google import genai as _genai
        from google.genai import types as _gtypes

        img = pyautogui.screenshot()
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        image_bytes = buf.getvalue()
        w, h = pyautogui.size()

        client = _genai.Client(api_key=_get_api_key())
        prompt = (
            f"Screen is {w}x{h} pixels. "
            "Find the YouTube 'Skip Ad', 'Skip', 'Pular' or 'Pular anúncio' button. "
            "Reply with ONLY 'x,y' pixel coordinates of the button center. "
            "If not visible reply with exactly: NOT_FOUND"
        )
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[
                _gtypes.Part.from_bytes(data=image_bytes, mime_type="image/png"),
                prompt,
            ],
        )
        text = (response.text or "").strip()
        if "NOT_FOUND" in text.upper():
            return "No skip ad button visible right now."

        match = _re.search(r"(\d+)\s*,\s*(\d+)", text)
        if match:
            x, y = int(match.group(1)), int(match.group(2))
            pyautogui.click(x, y)
            return f"Skip ad clicked at ({x},{y})."

        return "Could not determine skip button position."
    except Exception as e:
        return f"Skip ad failed: {e}"


_YT_VIDEO = (
    "document.querySelector('.html5-main-video')"
    "||document.querySelector('#movie_player video')"
    "||document.querySelector('video')"
)

_JS_COMMANDS = {
    "pause":       f"var v={_YT_VIDEO};if(v)v.pause();'ok'",
    "resume":      f"var v={_YT_VIDEO};if(v){{v.muted=false;v.play()}};'ok'",
    "toggle":      f"var v={_YT_VIDEO};if(v){{v.paused?v.play():v.pause()}};'ok'",
    "play":        f"var v={_YT_VIDEO};if(v){{v.muted=false;v.play()}};'ok'",
    "mute":        f"var v={_YT_VIDEO};if(v)v.muted=true;'muted'",
    "unmute":      f"var v={_YT_VIDEO};if(v)v.muted=false;'unmuted'",
    "volume_up":   "var p=document.querySelector('#movie_player');if(p&&p.getVolume){var nv=Math.min(100,p.getVolume()+10);p.setVolume(nv);p.unMute&&p.unMute();nv}else{var v=document.querySelector('.html5-main-video')||document.querySelector('video');if(v){v.muted=false;v.volume=Math.min(1,v.volume+0.1)};v?v.volume:'no video'}",
    "volume_down": "var p=document.querySelector('#movie_player');if(p&&p.getVolume){var nv=Math.max(0,p.getVolume()-10);p.setVolume(nv);nv}else{var v=document.querySelector('.html5-main-video')||document.querySelector('video');if(v)v.volume=Math.max(0,v.volume-0.1);v?v.volume:'no video'}",
    "forward":     f"var v={_YT_VIDEO};if(v)v.currentTime+=10;'ok'",
    "backward":    f"var v={_YT_VIDEO};if(v)v.currentTime-=10;'ok'",
    "fullscreen":  "document.querySelector('.ytp-fullscreen-button')?.click();'ok'",
    "skip_ad":     "(document.querySelector('.ytp-skip-ad-button')||document.querySelector('.ytp-ad-skip-button')||document.querySelector('[class*=\"skip\"]'))?.click();'ok'",
}


def _yt_js(js: str) -> str:
    """Run JavaScript in the active Playwright browser session."""
    try:
        from actions.browser_control import _registry
        sess = _registry.get()

        async def _run():
            page = await sess._get_page()
            result = await page.evaluate(js)
            return str(result) if result is not None else "ok"

        return sess.run(_run())
    except Exception as e:
        return f"JS error: {e}"


def _handle_control(parameters: dict, player) -> str:
    cmd = (parameters.get("command") or "toggle").lower().strip()

    if player:
        player.write_log(f"[YouTube] Control: {cmd}")

    if cmd == "close":
        try:
            from actions.browser_control import browser_control as _bc
            return _bc(parameters={"action": "close_tab"}, player=player) or "YouTube tab closed."
        except Exception as e:
            return f"Close failed: {e}"

    js = _JS_COMMANDS.get(cmd)
    if not js:
        return (
            f"Unknown control command '{cmd}'. "
            "Use: pause, resume, toggle, mute, unmute, skip_ad, close, "
            "fullscreen, forward, backward, volume_up, volume_down."
        )

    result = _yt_js(js)
    print(f"[YouTube] JS {cmd} → {result}")
    return f"YouTube: {cmd}."


def _handle_play(parameters: dict, player) -> str:
    query = parameters.get("query", "").strip()
    if not query:
        return "Please tell me what you'd like to watch, sir."

    if player:
        player.write_log(f"[YouTube] Searching: {query}")

    print(f"[YouTube] 🔍 Scraping first non-Shorts video for: {query}")

    video_url = _scrape_first_video_url(query)

    if not video_url:
        print(f"[YouTube] ⚠️ Scrape failed, using search page")
        video_url = (
            f"https://www.youtube.com/results"
            f"?search_query={quote_plus(query)}"
            f"&sp={_YT_VIDEO_FILTER}"
        )

    browser = parameters.get("browser", "chrome").lower().strip() or "chrome"
    print(f"[YouTube] ▶️ Opening via Playwright ({browser}): {video_url}")
    try:
        from actions.browser_control import browser_control as _bc
        _bc(parameters={"action": "go_to", "url": video_url, "browser": browser}, player=player)
    except Exception as e:
        print(f"[YouTube] ⚠️ Playwright failed ({e}), fallback to _open_url")
        _open_url(video_url)

    return f"Playing: {query}"


def _handle_summarize(parameters: dict, player, speak) -> str:
    if not _TRANSCRIPT_OK:
        return "youtube-transcript-api is not installed. Run: pip install youtube-transcript-api"

    url = _ask_for_url("Please paste the YouTube video URL:")
    if not url:
        return "No URL provided, sir. Summary cancelled."
    if not _is_valid_youtube_url(url):
        return "That doesn't appear to be a valid YouTube URL, sir."

    video_id = _extract_video_id(url)
    if not video_id:
        return "Could not extract video ID from that URL, sir."

    if player:
        player.write_log(f"[YouTube] Summarizing: {url}")
    if speak:
        speak("Fetching the transcript now, sir. One moment.")

    transcript = _get_transcript(video_id)
    if not transcript:
        return "I couldn't retrieve a transcript for that video, sir."

    if speak:
        speak("Transcript retrieved. Generating summary now.")

    try:
        summary = _summarize_with_gemini(transcript, url)
    except Exception as e:
        return f"Summary generation failed, sir: {e}"

    if speak:
        speak(summary)

    if parameters.get("save", False):
        saved_path = _save_summary(summary, url)
        return f"Summary complete and saved to Desktop: {saved_path}"

    return summary


def _handle_get_info(parameters: dict, player, speak) -> str:
    url = parameters.get("url", "").strip()
    if not url:
        url = _ask_for_url("Please paste the YouTube video URL:")
    if not url or not _is_valid_youtube_url(url):
        return "Please provide a valid YouTube URL, sir."

    video_id = _extract_video_id(url)
    if not video_id:
        return "Could not extract video ID, sir."

    if player:
        player.write_log(f"[YouTube] Getting info: {url}")

    info = _scrape_video_info(video_id)
    if not info:
        return "Could not retrieve video information, sir."

    lines = [
        f"{key.capitalize()}: {info[key]}"
        for key in ("title", "channel", "views", "duration", "likes")
        if key in info
    ]
    result = "\n".join(lines)

    if speak:
        speak(f"Here's the video info, sir. {result.replace(chr(10), '. ')}")

    return result


def _handle_trending(parameters: dict, player, speak) -> str:
    region = parameters.get("region", "TR").upper()

    if player:
        player.write_log(f"[YouTube] Trending: {region}")

    trending = _scrape_trending(region=region, max_results=8)
    if not trending:
        return f"Could not fetch trending videos for region {region}, sir."

    lines  = [f"Top trending videos in {region}:"]
    lines += [f"{v['rank']}. {v['title']} — {v['channel']}" for v in trending]
    result = "\n".join(lines)

    if speak:
        top3   = trending[:3]
        spoken = "Here are the top trending videos, sir. " + ". ".join(
            f"Number {v['rank']}: {v['title']} by {v['channel']}" for v in top3
        )
        speak(spoken)

    return result

_ACTION_MAP = {
    "play":      _handle_play,
    "summarize": _handle_summarize,
    "get_info":  _handle_get_info,
    "trending":  _handle_trending,
    "control":   _handle_control,
}


def youtube_video(
    parameters:     dict,
    response=None,
    player=None,
    session_memory=None,
    speak=None,
) -> str:
    params = parameters or {}
    action = params.get("action", "play").lower().strip()

    if player:
        player.write_log(f"[YouTube] Action: {action}")
    print(f"[YouTube] ▶️  Action: {action}  Params: {params}")

    handler = _ACTION_MAP.get(action)
    if handler is None:
        return (
            f"Unknown YouTube action: '{action}'. "
            "Available: play, summarize, get_info, trending."
        )

    try:
        if action in ("play", "control"):
            return handler(params, player) or "Done."
        return handler(params, player, speak) or "Done."
    except Exception as e:
        print(f"[YouTube] ❌ Error in {action}: {e}")
        return f"YouTube {action} failed, sir: {e}"