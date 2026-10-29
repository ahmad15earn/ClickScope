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
    assert s.analysis_progress()[1]
    s.clear()  # clearing data restarts the learning window
    assert s.analysis_progress()[0] == 1 and not s.analysis_progress()[1]

if __name__ == "__main__":
    test_labels(); test_store_and_stats(); test_suggestions(); test_30_day_gate(); print("core tests OK")
