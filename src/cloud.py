"""Google sign-in (Supabase Auth, PKCE + local loopback) and recovery backup/restore.

Only the recovery list is synced: installed-app catalog, kept apps/sites, recovery selection, winget ids.
Click statistics are never uploaded. Standard library only.
"""
import base64
import hashlib
import http.server
import json
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

import cloud_config as cfg

CALLBACK_PORTS = range(53682, 53692)   # allow-list in Supabase: http://127.0.0.1:*/**


class CloudError(Exception):
    pass


def configured():
    return bool(cfg.SUPABASE_URL and cfg.SUPABASE_KEY)


def _http(method, url, body=None, headers=None, timeout=20):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, {"message": raw.decode("utf-8", "ignore")[:200]}
    except (urllib.error.URLError, OSError):
        raise CloudError("No internet connection.")


request = _http  # replaced in tests


# ------------------------------------------------------------------ PKCE
def pkce_pair():
    verifier = secrets.token_urlsafe(64)[:96]
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def authorize_url(redirect, challenge):
    q = urllib.parse.urlencode({"provider": "google", "redirect_to": redirect,
                                "code_challenge": challenge, "code_challenge_method": "s256"})
    return f"{cfg.SUPABASE_URL.rstrip('/')}/auth/v1/authorize?{q}"


PAGE = ("<html><head><meta charset='utf-8'><title>ClickScope</title></head><body style=\"font-family:Segoe UI,sans-serif;"
        "background:#F5F5F7;display:flex;align-items:center;justify-content:center;height:100vh;margin:0\"><div style=\""
        "background:#fff;padding:40px 56px;border-radius:20px;text-align:center;box-shadow:0 4px 24px #0001\"><h2 style=\""
        "margin:0 0 8px\">%s</h2><p style=\"color:#6E6E73;margin:0\">%s</p></div></body></html>")


def _listen():
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if "code" in q:
                self.server.code = q["code"][0]
                title, text = "You're signed in", "You can close this tab and return to ClickScope."
            elif "error" in q or "error_description" in q:
                self.server.error = (q.get("error_description") or q.get("error"))[0]
                title, text = "Sign-in failed", "Return to ClickScope and try again."
            else:
                self.send_response(204)
                self.end_headers()
                return
            body = (PAGE % (title, text)).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    for port in CALLBACK_PORTS:
        try:
            srv = http.server.HTTPServer(("127.0.0.1", port), Handler)
            srv.code = srv.error = None
            return srv, port
        except OSError:
            continue
    raise CloudError("Could not open a local port for sign-in.")


def _friendly(js, default):
    msg = (js or {}).get("error_description") or (js or {}).get("msg") or (js or {}).get("message") or default
    low = msg.lower()
    if "invalid login" in low:
        return "Wrong email or password."
    if "already registered" in low or "already been registered" in low:
        return "This email already has an account. Press Sign in instead."
    if "not confirmed" in low:
        return "Please confirm your email first (check your inbox), then sign in."
    if "rate limit" in low or "too many" in low:
        return "Too many attempts. Please wait a few minutes and try again."
    return msg


def _check(email, password):
    if "@" not in email or "." not in email.split("@")[-1]:
        raise CloudError("Please enter a valid email address.")
    if len(password) < 6:
        raise CloudError("The password needs at least 6 characters.")


def sign_up(store, email, password):
    """Create an account with email + password (no Google needed)."""
    if not configured():
        raise CloudError("Cloud backup is not configured yet.")
    email = email.strip()
    _check(email, password)
    st, js = request("POST", f"{cfg.SUPABASE_URL.rstrip('/')}/auth/v1/signup", {"email": email, "password": password},
                     {"apikey": cfg.SUPABASE_KEY})
    if st >= 300:
        raise CloudError(_friendly(js, "Could not create the account."))
    if js and js.get("access_token"):
        _save(store, js)
        return email
    raise CloudError("Account created. Check your inbox and confirm your email, then press Sign in.")


def sign_in_password(store, email, password):
    if not configured():
        raise CloudError("Cloud backup is not configured yet.")
    email = email.strip()
    _check(email, password)
    st, js = request("POST", f"{cfg.SUPABASE_URL.rstrip('/')}/auth/v1/token?grant_type=password",
                     {"email": email, "password": password}, {"apikey": cfg.SUPABASE_KEY})
    if st != 200:
        raise CloudError(_friendly(js, "Sign-in failed."))
    _save(store, js)
    return email


def sign_in(store, open_browser=None, timeout=180):
    open_browser = open_browser or webbrowser.open
    if not configured():
        raise CloudError("Cloud backup is not configured yet.")
    verifier, challenge = pkce_pair()
    srv, port = _listen()
    try:
        open_browser(authorize_url(f"http://127.0.0.1:{port}/callback", challenge))
        srv.timeout = 0.5
        end = time.time() + timeout
        while time.time() < end and not (srv.code or srv.error):
            srv.handle_request()
        if srv.error:
            raise CloudError(srv.error)
        if not srv.code:
            raise CloudError("Sign-in timed out. Please try again.")
        code = srv.code
    finally:
        srv.server_close()
    st, js = request("POST", f"{cfg.SUPABASE_URL.rstrip('/')}/auth/v1/token?grant_type=pkce",
                  {"auth_code": code, "code_verifier": verifier}, {"apikey": cfg.SUPABASE_KEY})
    if st != 200:
        raise CloudError((js or {}).get("error_description") or (js or {}).get("msg") or "Google sign-in failed.")
    _save(store, js)
    return session(store)["email"]


# --------------------------------------------------------------- session
def _save(store, js):
    user = js.get("user") or {}
    store.set("cloud_session", json.dumps({
        "access_token": js["access_token"], "refresh_token": js.get("refresh_token", ""),
        "expires_at": time.time() + int(js.get("expires_in", 3600)),
        "email": user.get("email", ""), "user_id": user.get("id", "")}))


def session(store):
    try:
        return json.loads(store.get("cloud_session", "null"))
    except ValueError:
        return None


def signed_in(store):
    return bool(session(store))


def sign_out(store):
    store.set("cloud_session", "null")


def _token(store):
    s = session(store)
    if not s:
        raise CloudError("Not signed in.")
    if s["expires_at"] - time.time() < 90:
        st, js = request("POST", f"{cfg.SUPABASE_URL.rstrip('/')}/auth/v1/token?grant_type=refresh_token",
                      {"refresh_token": s["refresh_token"]}, {"apikey": cfg.SUPABASE_KEY})
        if st != 200:
            sign_out(store)
            raise CloudError("Your session expired. Please sign in again.")
        _save(store, js)
        s = session(store)
    return s["access_token"]


def _rest(store, method, path, body=None):
    st, js = request(method, f"{cfg.SUPABASE_URL.rstrip('/')}/rest/v1/{path}", body,
                  {"apikey": cfg.SUPABASE_KEY, "Authorization": f"Bearer {_token(store)}", "Prefer": "return=minimal"})
    if st >= 300:
        raise CloudError((js or {}).get("message") or f"Server error ({st}).")
    return js


# -------------------------------------------------------------- snapshot
def snapshot(store):
    kept, kept_sites = list(store.kept()), list(store.kept_sites())
    items, seen = [], set()
    for kind, cat, keep in (("app", store.catalog("app"), kept), ("site", store.catalog("site"), kept_sites)):
        for n, d in cat:
            items.append({"kind": kind, "name": n, "detail": d or "", "kept": n in keep})
            seen.add((kind, n))
        for n in keep:  # manually added items that are not in the scan
            if (kind, n) not in seen:
                items.append({"kind": kind, "name": n, "detail": "added manually", "kept": True})
                seen.add((kind, n))
    try:
        chosen = json.loads(store.get("recovery_apps", "[]"))
        ids = json.loads(store.get("winget_ids", "{}"))
    except ValueError:
        chosen, ids = [], {}
    return items, {"chosen": chosen, "winget_ids": ids}


def apply_snapshot(store, items, settings):
    """Merge a cloud snapshot into the local store (union, never deletes local data)."""
    app_cat = dict(store.catalog("app"))
    site_cat = dict(store.catalog("site"))
    n_apps = n_sites = 0
    for it in items:
        cat, keepfn = (app_cat, store.set_keep) if it["kind"] == "app" else (site_cat, store.toggle_keep_site)
        cat.setdefault(it["name"], it.get("detail", ""))
        if it.get("kept"):
            keepfn(it["name"], True)
            n_apps += it["kind"] == "app"
            n_sites += it["kind"] == "site"
    store.set_catalog("app", sorted(app_cat.items()))
    store.set_catalog("site", sorted(site_cat.items()))
    try:
        local_chosen = json.loads(store.get("recovery_apps", "[]")) or []
        local_ids = json.loads(store.get("winget_ids", "{}"))
    except ValueError:
        local_chosen, local_ids = [], {}
    chosen = list(dict.fromkeys(local_chosen + list((settings or {}).get("chosen") or [])))
    store.set("recovery_apps", json.dumps(chosen))
    store.set("winget_ids", json.dumps({**((settings or {}).get("winget_ids") or {}), **local_ids}))
    return len(app_cat), n_apps, n_sites


def push(store):
    items, settings = snapshot(store)
    _rest(store, "POST", "rpc/replace_recovery", {"p_items": items, "p_settings": settings})
    store.set("cloud_last_sync", time.strftime("%Y-%m-%d %H:%M"))
    store.cloud_dirty = False
    return len(items)


def pull(store):
    items = _rest(store, "GET", "recovery_items?select=kind,name,detail,kept") or []
    rows = _rest(store, "GET", "recovery_settings?select=chosen,winget_ids") or []
    result = apply_snapshot(store, items, rows[0] if rows else {})
    store.set("cloud_last_sync", time.strftime("%Y-%m-%d %H:%M"))
    return result


def run_bg(root, fn, done):
    """Run fn in a thread and call done(result, error) on the Tk thread."""
    box = {}

    def work():
        try:
            box["v"] = fn()
        except Exception as e:
            box["e"] = e
    threading.Thread(target=work, daemon=True).start()

    def poll():
        if "v" in box or "e" in box:
            done(box.get("v"), box.get("e"))
        else:
            root.after(120, poll)
    poll()
