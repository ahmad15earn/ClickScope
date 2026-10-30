import os, sys, tempfile, datetime
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from core import Store, app_label, site_label, fmt_hour, build_suggestions

def mk():
    return Store(os.path.join(tempfile.mkdtemp(), "t.db"))

def test_labels():
    assert app_label("chrome.exe") == "Google Chrome"
    assert app_label("some-tool_x.exe") == "Some Tool X"
    assert app_label(None) == "Other / system"
    assert app_label("applicationframehost.exe", "Calculator") == "Calculator"
    assert site_label("Cat videos - YouTube - Google Chrome") == "YouTube"
    assert site_label("Inbox (3) - me@gmail.com - Gmail - Microsoft\u200b Edge") == "Gmail"
    assert site_label("(3) Facebook") == "Facebook"
    assert site_label("Home / X - Brave") == "X (Twitter)"
    assert site_label("best pizza near me - Google Search") == "Google Search"
    assert site_label("") is None
    assert fmt_hour(0) == "12 AM" and fmt_hour(15) == "3 PM" and fmt_hour(None) == "\u2013"

def test_store_and_stats():
    s = mk()
    for _ in range(5): s.add_click("Google Chrome", "YouTube")
    for _ in range(2): s.add_click("VS Code")
    assert s.total("today") == 7
    assert s.top("app", "today")[0] == ("Google Chrome", 5)
    assert s.top("app", "today", desc=False)[0] == ("VS Code", 2)
    assert s.count("site", "all") == 1
    old = datetime.datetime.now() - datetime.timedelta(days=3)
    s.add_click("Slack", when=old)
    assert s.total("today") == 7 and s.total("7d") == 8 and s.total("all") == 8
    s.set("track_sites", "0"); assert s.get("track_sites") == "0"
    p = os.path.join(tempfile.mkdtemp(), "e.csv"); s.export_csv(p)
    assert "Google Chrome" in open(p, encoding="utf-8-sig").read()
    s.clear(); assert s.total("all") == 0

def test_suggestions():
    s = mk()
    assert build_suggestions(s, "all")[0]["title"] == "Not enough activity yet"
    for _ in range(130): s.add_click("Google Chrome", "YouTube")
    for _ in range(10): s.add_click("Google Chrome", "Gmail")
    for _ in range(10): s.add_click("VS Code")
    for n in ("A","B","C"): s.add_click(n)
    for _ in range(20): s.add_click("Word")
    titles = [x["title"] for x in build_suggestions(s, "all")]
    print(titles)
    assert any("browser" in t for t in titles)
    assert any("YouTube" in t for t in titles)
    assert any("Rarely" in t for t in titles)



def test_30_day_gate():
    import datetime
    s = mk()
    day, ready, unlock = s.analysis_progress()
    assert day == 1 and not ready
    s.set("first_run", (datetime.date.today() - datetime.timedelta(days=28)).isoformat())
    assert s.analysis_progress()[0] == 29 and not s.analysis_progress()[1]
    s.set("first_run", (datetime.date.today() - datetime.timedelta(days=30)).isoformat())
    assert not s.analysis_progress()[1]          # 30 days passed but no real activity yet
    for back in range(7):                        # 7 active days -> unlocked
        when = datetime.datetime.now() - datetime.timedelta(days=back)
        for _ in range(25): s.add_click("Word", when=when)
    assert s.active_days() == 7 and s.analysis_progress()[1]
    s.clear()  # clearing data restarts the learning window
    assert s.analysis_progress()[0] == 1 and not s.analysis_progress()[1]

def test_ignore_list():
    s = mk()
    s.add_click("Slack", "Gmail"); s.add_click("Word")
    s.add_ignore("app", "Slack")
    s.add_click("Slack"); s.add_click("Word", "Facebook")
    s.add_ignore("site", "Facebook"); s.add_click("Word", "Facebook")
    names = [n for n, _ in s.top("app", "all")]
    assert "Slack" not in names and s.top("site", "all") == [("Gmail", 1)], s.top("site", "all")
    assert s.total("all") == 3
    s.clear_ignored(); s.add_click("Slack"); assert s.total("all") == 4


def test_scanner_and_catalog():
    import sqlite3, scanner
    apps = scanner.clean_apps([("Google Chrome", "126.0", "Google LLC"), ("Microsoft Visual C++ 2019 Redistributable (x64)", "14", "MS"),
                               ("Update for Windows (KB5001234)", "", ""), ("7-Zip", "23.01", "Igor Pavlov"), ("google chrome", "1", ""), ("", "", "")])
    assert [a for a, _ in apps] == ["7-Zip", "Google Chrome"], apps
    assert scanner.domain_of("https://www.YouTube.com/watch?v=1") == "youtube.com"
    assert scanner.domain_of("http://192.168.0.1/x") is None and scanner.domain_of("http://localhost:3000") is None
    assert scanner.aggregate_domains([("https://github.com/a", 5), ("https://www.github.com/b", 3), ("https://x.org", 1)]) == [("github.com", 8), ("x.org", 1)]
    d = tempfile.mkdtemp(); db = os.path.join(d, "History")
    con = sqlite3.connect(db); con.execute("CREATE TABLE urls(url TEXT, visit_count INTEGER)")
    con.executemany("INSERT INTO urls VALUES(?,?)", [("https://mail.google.com/x", 40), ("https://github.com/me", 22), ("http://localhost/", 99)]); con.commit(); con.close()
    open(os.path.join(d, "Bookmarks"), "w").write('{"roots":{"bar":{"children":[{"type":"url","url":"https://notion.so/a"}]}}}')
    sites = scanner.read_sites("chromium", d)
    assert sites[0] == ("mail.google.com", "40 visits") and ("notion.so", "bookmarked") in sites, sites
    s = mk(); s.set_catalog("app", apps); s.set_catalog("site", sites)
    s.toggle_keep("7-Zip"); s.toggle_keep_site("github.com")
    p = os.path.join(tempfile.mkdtemp(), "r.txt"); s.export_inventory(p)
    txt = open(p, encoding="utf-8").read()
    assert "[ ] 7-Zip" in txt and "github.com" in txt and "Everything else" in txt and "Google Chrome" in txt


def test_recovery():
    import time, recovery
    table = """Name                 Id                    Version   Available Source
-----------------------------------------------------------------------
Google Chrome        Google.Chrome         126.0.1   127.0.2   winget
7-Zip                7zip.7zip             23.01               winget
Backup Tool Pro      Acme.BackupToolPro    4.1                 winget"""
    r = recovery.parse_table(table)
    assert r[1]["Name"] == "7-Zip" and r[1]["Id"] == "7zip.7zip" and r[0]["Id"] == "Google.Chrome", r
    assert abs(recovery.parse_progress("  \u2588\u2588 12.5 MB / 50.0 MB") - 0.25) < 1e-6
    assert recovery.safe_name('A/B:C*') == "A_B_C_"
    out = tempfile.mkdtemp()
    fails = {"Acme.BackupToolPro": 1}

    def runner(cmd, on_chunk=None, holder=None):
        if cmd[1] == "list":
            return 0, table
        if cmd[1] == "search":
            return 0, "Name  Id  Version  Match  Source\n-----\nZoom  Zoom.Zoom  6.0  Tag  winget"
        wid = cmd[cmd.index("--id") + 1]
        folder = cmd[cmd.index("--download-directory") + 1]
        if on_chunk: on_chunk("10.0 MB / 40.0 MB"); on_chunk("40.0 MB / 40.0 MB")
        if fails.get(wid):
            fails[wid] = 0
            return 1, "Download failed: network error"
        open(os.path.join(folder, "setup.exe"), "w").write("x")
        return 0, "ok"
    m = recovery.RecoveryManager(out, ["Google Chrome", "Backup Tool Pro", "Zoom", "Unknown Thing"], runner=runner)
    m.start(); m.worker.join(5)
    c = m.counts()
    assert c == {"done": 2, "failed": 1, "nosource": 1}, c
    assert os.path.exists(os.path.join(out, "Google Chrome", "setup.exe"))
    m.retry_failed(); m.worker.join(5)
    assert m.counts() == {"done": 3, "nosource": 1}, m.counts()
    idx = open(os.path.join(out, "RECOVERY.txt"), encoding="utf-8").read()
    assert "[x] Backup Tool Pro" in idx and "[?] Unknown Thing" in idx


if __name__ == "__main__":
    test_labels(); test_store_and_stats(); test_suggestions(); test_30_day_gate(); test_ignore_list(); test_scanner_and_catalog(); test_recovery(); print("core tests OK")
