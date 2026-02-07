# -*- coding: utf-8 -*-
import os
import platform
from datetime import datetime

from aqt import mw, gui_hooks
import aqt.utils as U
from aqt.qt import QApplication, Qt

_pending_error_text: str | None = None
_installed = False


def _get_config() -> dict:
    cfg = mw.addonManager.getConfig(__name__) or {}
    # defaults (in case user deletes keys)
    cfg.setdefault("debug", False)
    cfg.setdefault("log_path", "~/Downloads/anki_sync_no_bounce.log")
    return cfg


def _log(line: str) -> None:
    cfg = _get_config()
    if not cfg.get("debug", False):
        return

    path = os.path.expanduser(str(cfg.get("log_path", ""))).strip()
    if not path:
        return

    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
    except Exception:
        # if user set a filename without dir, dirname("") will fail; ignore
        pass

    with open(path, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now().isoformat()} {line}\n")


def _install_patch() -> None:
    global _installed
    if _installed:
        return
    _installed = True

    if platform.system() != "Darwin":
        _log("not macOS, patch skipped")
        return

    # your earlier confirmed entrypoint
    import aqt.sync as SYNC

    orig_handle = SYNC.handle_sync_error

    def patched_handle_sync_error(mw_, err):
        global _pending_error_text

        # Determine foreground/background
        try:
            is_front = mw_.isActiveWindow()
        except Exception:
            try:
                is_front = (mw.app.activeWindow() is mw_)
            except Exception:
                is_front = True

        if not is_front:
            _pending_error_text = str(err)
            _log("BACKGROUND SYNC ERROR (deferred)")
            _log(f"type={type(err)!r}")
            _log(f"str={_pending_error_text!r}")
            _log(f"repr={err!r}")
            return

        return orig_handle(mw_, err)

    SYNC.handle_sync_error = patched_handle_sync_error
    _log("patch installed")

    # When app becomes active, show deferred error once
    app = QApplication.instance()

    def on_app_state_changed(state):
        global _pending_error_text
        if state == Qt.ApplicationState.ApplicationActive and _pending_error_text:
            text = _pending_error_text
            _pending_error_text = None
            _log("show deferred sync error (app active)")
            U.show_warning(text, parent=mw)

    app.applicationStateChanged.connect(on_app_state_changed)


# Important: wait until profile is open (mw.pm may be not ready earlier)
gui_hooks.profile_did_open.append(_install_patch)
