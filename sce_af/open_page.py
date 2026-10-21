"""Open or focus the local page. Avoids webbrowser (macOS can double-fire)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from typing import Any, Callable

RunProc = Callable[..., Any]
StartFile = Callable[[str], Any]


def url_match_prefix(url: str) -> str:
    text = str(url or "").strip().split("#", 1)[0]
    while text.endswith("/"):
        text = text[:-1]
    return text


def macos_focus_script(url: str) -> str:
    prefix = json.dumps(url_match_prefix(url))
    return f'''
function run() {{
  var prefix = {prefix};
  function focusChromium(name) {{
    try {{
      var app = Application(name);
      if (!app.running()) return false;
      var windows = app.windows();
      for (var i = 0; i < windows.length; i++) {{
        var tabs = windows[i].tabs();
        for (var j = 0; j < tabs.length; j++) {{
          var u = "";
          try {{ u = tabs[j].url(); }} catch (e) {{}}
          if (u && u.indexOf(prefix) === 0) {{
            windows[i].activeTabIndex = j + 1;
            windows[i].index = 1;
            app.activate();
            return true;
          }}
        }}
      }}
    }} catch (e) {{}}
    return false;
  }}
  function focusSafari() {{
    try {{
      var app = Application("Safari");
      if (!app.running()) return false;
      var windows = app.windows();
      for (var i = 0; i < windows.length; i++) {{
        var tabs = windows[i].tabs();
        for (var j = 0; j < tabs.length; j++) {{
          var u = "";
          try {{ u = tabs[j].url(); }} catch (e) {{}}
          if (u && u.indexOf(prefix) === 0) {{
            windows[i].currentTab = tabs[j];
            windows[i].index = 1;
            app.activate();
            return true;
          }}
        }}
      }}
    }} catch (e) {{}}
    return false;
  }}
  if (focusChromium("Google Chrome")) return "1";
  if (focusChromium("Microsoft Edge")) return "1";
  if (focusSafari()) return "1";
  return "0";
}}
'''


def try_focus_existing(
    url: str,
    *,
    platform: str | None = None,
    run: RunProc | None = None,
) -> bool:
    plat = platform if platform is not None else sys.platform
    if plat != "darwin":
        return False
    runner = run or subprocess.run
    try:
        proc = runner(
            ["osascript", "-l", "JavaScript"],
            input=macos_focus_script(url),
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
    except Exception:
        return False
    out = getattr(proc, "stdout", "") or ""
    return str(out).strip() == "1"


def open_new_once(
    url: str,
    *,
    platform: str | None = None,
    run: RunProc | None = None,
    startfile: StartFile | None = None,
) -> None:
    plat = platform if platform is not None else sys.platform
    runner = run or subprocess.run
    if plat == "darwin":
        runner(["open", url], check=False)
        return
    if plat == "win32" or str(plat).startswith("win"):
        opener = startfile or os.startfile
        opener(url)
        return
    runner(["xdg-open", url], check=False)


def _open_now(
    url: str,
    *,
    platform: str | None = None,
    run: RunProc | None = None,
    startfile: StartFile | None = None,
) -> None:
    if try_focus_existing(url, platform=platform, run=run):
        return
    open_new_once(url, platform=platform, run=run, startfile=startfile)


def open_app_page(
    url: str,
    delay: bool = False,
    *,
    platform: str | None = None,
    run: RunProc | None = None,
    startfile: StartFile | None = None,
) -> None:
    def _go() -> None:
        if delay:
            time.sleep(0.4)
        try:
            _open_now(url, platform=platform, run=run, startfile=startfile)
        except Exception:
            pass

    if delay:
        threading.Thread(target=_go, daemon=True).start()
        return
    _go()
