"""Cloud backup logic against a fake in-memory Supabase."""
import json, os, sys, tempfile, threading, time, urllib.parse, urllib.request
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "..", "src")]
import core, cloud, cloud_config

cloud_config.SUPABASE_URL, cloud_config.SUPABASE_KEY = "https://x.supabase.co", "sb_publishable_test"
DB = {"items": [], "settings": []}
USERS, CONFIRM_EMAIL = {}, False
def fake_http(method, url, body=None, headers=None, timeout=20):
    if "grant_type=pkce" in url:
        assert body["auth_code"] == "abc" and len(body["code_verifier"]) >= 43
        return 200, {"access_token": "AT", "refresh_token": "RT", "expires_in": 3600, "user": {"email": "me@gmail.com", "id": "u1"}}
    if url.endswith("/auth/v1/signup"):
        if body["email"] in USERS: return 422, {"msg": "User already registered"}
        USERS[body["email"]] = body["password"]
        if CONFIRM_EMAIL: return 200, {"id": "u2", "email": body["email"]}
        return 200, {"access_token": "AT", "refresh_token": "RT", "expires_in": 3600, "user": {"email": body["email"], "id": "u2"}}
    if "grant_type=password" in url:
        if USERS.get(body["email"]) != body["password"]: return 400, {"error_description": "Invalid login credentials"}
        return 200, {"access_token": "AT", "refresh_token": "RT", "expires_in": 3600, "user": {"email": body["email"], "id": "u1"}}
    if "grant_type=refresh_token" in url:
        return 200, {"access_token": "AT2", "refresh_token": "RT2", "expires_in": 3600, "user": {"email": "me@gmail.com", "id": "u1"}}
    assert headers["Authorization"].startswith("Bearer ") and headers["apikey"] == "sb_publishable_test"
    if url.endswith("rpc/replace_recovery"):
        DB["items"], DB["settings"] = body["p_items"], [body["p_settings"]]; return 204, None
    if "recovery_items" in url: return 200, DB["items"]
    if "recovery_settings" in url: return 200, DB["settings"]
cloud.request = fake_http

v, ch = cloud.pkce_pair()
assert "=" not in ch and len(ch) == 43
u = cloud.authorize_url("http://127.0.0.1:53682/callback", ch)
assert "provider=google" in u and "code_challenge_method=s256" in u and "127.0.0.1" in urllib.parse.unquote(u)

def mk(): return core.Store(os.path.join(tempfile.mkdtemp(), "c.db"))
old = mk()
old.set_catalog("app", [("Chrome", "Google"), ("7-Zip", "Igor"), ("Backup Pro", "Acme")]); old.set_catalog("site", [("github.com", "9 visits")])
old.toggle_keep("7-Zip"); old.toggle_keep("Manual Tool"); old.toggle_keep_site("github.com"); old.set("recovery_apps", json.dumps(["7-Zip", "Backup Pro"]))
old.set("winget_ids", json.dumps({"7-Zip": "7zip.7zip"}))

# sign in through the real loopback server (the "browser" is simulated)
def browser(url):
    redirect = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["redirect_to"][0]
    threading.Thread(target=lambda: (time.sleep(0.2), urllib.request.urlopen(redirect + "?code=abc").read()), daemon=True).start()
assert cloud.sign_in(old, open_browser=browser, timeout=10) == "me@gmail.com" and cloud.signed_in(old)
assert old.cloud_dirty
assert cloud.push(old) == 5 and not old.cloud_dirty
assert not any("click" in k for it in DB["items"] for k in it)          # clicks are never uploaded

# brand-new PC: sign in, pull, everything is back
new = mk()
cloud.sign_in(new, open_browser=browser, timeout=10)
apps, ka, ks = cloud.pull(new)
assert set(new.kept()) == {"7-Zip", "Manual Tool"} and new.kept_sites() == ["github.com"], (new.kept(), new.kept_sites())
assert dict(new.catalog("app"))["Backup Pro"] == "Acme" and json.loads(new.get("recovery_apps")) == ["7-Zip", "Backup Pro"]
assert json.loads(new.get("winget_ids")) == {"7-Zip": "7zip.7zip"}
# expired token refreshes; sign out clears
s = cloud.session(new); s["expires_at"] = time.time() - 5; new.set("cloud_session", json.dumps(s))
cloud.push(new); assert cloud.session(new)["access_token"] == "AT2"
cloud.sign_out(new); assert not cloud.signed_in(new)
# email + password accounts (no Google needed)
e = mk()
for bad, msg in (("nope", "valid email"),):
    try: cloud.sign_up(e, bad, "secret123"); raise SystemExit("should fail")
    except cloud.CloudError as x: assert msg in str(x)
try: cloud.sign_up(e, "a@b.com", "123"); raise SystemExit("should fail")
except cloud.CloudError as x: assert "6 characters" in str(x)
assert cloud.sign_up(e, "stu@mail.com", "secret123") == "stu@mail.com" and cloud.signed_in(e)
try: cloud.sign_up(mk(), "stu@mail.com", "secret123"); raise SystemExit("should fail")
except cloud.CloudError as x: assert "already has an account" in str(x)
n = mk()
try: cloud.sign_in_password(n, "stu@mail.com", "wrongpass"); raise SystemExit("should fail")
except cloud.CloudError as x: assert "Wrong email or password" in str(x)
assert cloud.sign_in_password(n, "stu@mail.com", "secret123") == "stu@mail.com"
CONFIRM_EMAIL = True
try: cloud.sign_up(mk(), "new@mail.com", "secret123"); raise SystemExit("should fail")
except cloud.CloudError as x: assert "confirm your email" in str(x)
print("cloud OK")
