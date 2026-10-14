#!/usr/bin/env python3
"""Сбор открытых GitHub issues с вознаграждением (bounty) в GitHub Actions.
Пишет results/latest.json, results/latest.md, results/seen.json. Только стандартная библиотека."""
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG = json.load(open(os.path.join(ROOT, "scripts", "config.json"), encoding="utf-8"))
OUT = os.path.join(ROOT, "results")
TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
API = "https://api.github.com"
NOW = dt.datetime.now(dt.timezone.utc)
TODAY = NOW.date().isoformat()
START = time.time()
DEADLINE = START + float(os.environ.get("BOUNTY_DEADLINE_MIN", "24")) * 60
SEARCH_DEADLINE = START + float(CFG.get("search_budget_min", 12)) * 60
SEARCH_SLEEP = float(CFG.get("search_sleep_sec", 15))
LOG_LINES = []


def log(msg):
    line = f"{dt.datetime.now(dt.timezone.utc).strftime('%H:%M:%S')} {msg}"
    print(line, flush=True)
    LOG_LINES.append(line)


def out_of_time():
    return time.time() > DEADLINE

AMOUNT_RE = re.compile(
    r"(\$\s?\d[\d,]*(?:\.\d+)?\s?[kK]?"
    r"|\d[\d,\s]*(?:\.\d+)?\s?(?:₽|(?:USDC|USDT|USD|XMR|BTC|SOL|ETH|sats?|сатош\w*|руб\w*|RUB)\b)"
    r"|(?:USDC|USDT|XMR)\s?\d[\d,]*(?:\.\d+)?)",
    re.IGNORECASE,
)
CLAIM_RE = re.compile(
    r"(^|\s)/(attempt|claim)\b|i('| a)?m working on|i will work on|i'll work on|"
    r"assign (this )?(to )?me|can i take|i'd like to work|беру в работу|возьму",
    re.IGNORECASE,
)
PAID_RE = re.compile(r"\b(rewarded|bounty (has been )?paid|payment sent|paid out)\b", re.IGNORECASE)
STRIPE_HINT = ("algora", "opire", "polar")


def gh(path, params=None, accept="application/vnd.github+json"):
    url = path if path.startswith("http") else API + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "Accept": accept,
        "Authorization": f"Bearer {TOKEN}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "bounty-feed",
    })
    for attempt in range(3):
        if out_of_time():
            return None
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            try:
                body = re.sub(r"\s+", " ", e.read().decode("utf-8", "replace"))[:300]
            except Exception:
                body = ""
            if e.code in (403, 429):
                reset = e.headers.get("X-RateLimit-Reset")
                retry = e.headers.get("Retry-After")
                remaining = e.headers.get("X-RateLimit-Remaining")
                wait = int(retry) if retry else (max(5, int(reset) - int(time.time()) + 2) if reset else 30)
                wait = min(wait, 60)
                log(f"HTTP {e.code} try {attempt + 1}/3 remaining={remaining} wait={wait}s "
                    f"body={body} url={url[:110]}")
                time.sleep(wait)
                continue
            log(f"HTTP {e.code} body={body[:150]} url={url[:110]}")
            return None
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            log(f"network error {e!r} try {attempt + 1}/3 url={url[:90]}")
            time.sleep(5)
    return None


def excluded(item):
    repo = item["repository_url"].split("/repos/")[1]
    owner = repo.split("/")[0]
    if owner in CFG["exclude_owners"] or repo in CFG["exclude_repos"]:
        return True
    return any(re.search(p, item["title"], re.IGNORECASE) for p in CFG["exclude_title_regex"])


def search_all():
    created = (NOW - dt.timedelta(days=CFG["created_days"])).date().isoformat()
    updated = (NOW - dt.timedelta(days=CFG["updated_days"])).date().isoformat()
    found = {}
    for q in CFG["queries"]:
        if time.time() > SEARCH_DEADLINE or out_of_time():
            log("search budget reached, stopping search (remaining queries skipped)")
            break
        full = f"{q} is:issue is:open no:assignee created:>={created} updated:>={updated}"
        for page in range(1, CFG["max_pages_per_query"] + 1):
            if time.time() > SEARCH_DEADLINE or out_of_time():
                break
            data = gh("/search/issues", {"q": full, "sort": "updated", "order": "desc",
                                         "per_page": 100, "page": page})
            time.sleep(SEARCH_SLEEP)
            if not data:
                log(f"[ -- ] p{page} {q} (no data)")
                break
            items = data.get("items", [])
            for it in items:
                if it.get("pull_request") or excluded(it):
                    continue
                rec = found.setdefault(it["html_url"], {"item": it, "queries": []})
                rec["queries"].append(q)
            log(f"[{len(items):3}] p{page} {q} (unique so far: {len(found)})")
            if len(items) < 100:
                break
    return found


def enrich(rec):
    it = rec["item"]
    repo = it["repository_url"].split("/repos/")[1]
    n = it["number"]
    text = f"{it['title']}\n{it.get('body') or ''}"
    out = {
        "url": it["html_url"], "repo": repo, "number": n, "title": it["title"],
        "created": it["created_at"][:10], "updated": it["updated_at"][:10],
        "comments": it["comments"], "labels": [l["name"] for l in it.get("labels", [])],
        "author": it["user"]["login"], "author_association": it.get("author_association"),
        "queries": rec["queries"],
        "body_snippet": re.sub(r"\s+", " ", (it.get("body") or ""))[:500],
        "prs_open": [], "prs_merged": [], "prs_closed": [],
        "claims": 0, "claimers": [], "bot_bounty": None,
        "paid_hint": False, "enriched": False,
    }
    timeline = gh(f"/repos/{repo}/issues/{n}/timeline", {"per_page": 100})
    if isinstance(timeline, list):
        out["enriched"] = True
        for ev in timeline:
            e = ev.get("event")
            if e == "cross-referenced":
                src = (ev.get("source") or {}).get("issue") or {}
                if src.get("pull_request"):
                    pr = src["html_url"]
                    if src["pull_request"].get("merged_at"):
                        out["prs_merged"].append(pr)
                    elif src.get("state") == "open":
                        out["prs_open"].append(pr)
                    else:
                        out["prs_closed"].append(pr)
            elif e == "commented":
                body = ev.get("body") or ""
                login = ((ev.get("user") or ev.get("actor") or {}).get("login") or "").lower()
                if any(h in login for h in STRIPE_HINT) and ("bounty" in body.lower() or "💎" in body):
                    out["bot_bounty"] = {"bot": login, "text": re.sub(r"\s+", " ", body)[:300]}
                    text += "\n" + body
                if CLAIM_RE.search(body) and login not in out["claimers"]:
                    out["claims"] += 1
                    out["claimers"].append(login)
                if PAID_RE.search(body):
                    out["paid_hint"] = True
    amounts = sorted({m.group(0).strip() for m in AMOUNT_RE.finditer(text)})[:8]
    out["amounts"] = amounts
    out["stripe_likely"] = bool(out["bot_bounty"]) or any(
        h in " ".join(out["labels"]).lower() for h in STRIPE_HINT)
    s = 0
    s += 3 if amounts else 0
    s += 2 if any("bounty" in l.lower() or "reward" in l.lower() for l in out["labels"]) else 0
    s += 1 if out["author_association"] in ("OWNER", "MEMBER", "COLLABORATOR") else 0
    s += 1 if (NOW.date() - dt.date.fromisoformat(out["updated"])).days <= 7 else 0
    s -= 2 if out["stripe_likely"] else 0
    s -= 4 * len(out["prs_open"])
    s -= 10 if out["prs_merged"] else 0
    s -= min(out["claims"], 3) * 2
    s -= 10 if out["paid_hint"] else 0
    out["score"] = s
    return out


def main():
    if not TOKEN:
        print("GH_TOKEN не задан", file=sys.stderr)
        sys.exit(1)
    os.makedirs(OUT, exist_ok=True)
    seen_path = os.path.join(OUT, "seen.json")
    seen = json.load(open(seen_path, encoding="utf-8")) if os.path.exists(seen_path) else {}

    found = search_all()
    log(f"search finished: {len(found)} unique issues, {time.time() - START:.0f}s elapsed")
    if not found:
        log("ничего не найдено — latest.json не перезаписываю")
        sys.exit(1)
    order = sorted(found.values(), key=lambda r: -len(r["queries"]))
    results = []
    for i, rec in enumerate(order):
        if i < CFG["max_enrich"] and not out_of_time():
            results.append(enrich(rec))
            time.sleep(0.4)
            if (i + 1) % 25 == 0:
                log(f"enriched {i + 1}/{min(len(order), CFG['max_enrich'])}")
        else:
            it = rec["item"]
            results.append({"url": it["html_url"], "title": it["title"],
                            "repo": it["repository_url"].split("/repos/")[1],
                            "number": it["number"],
                            "created": it["created_at"][:10], "updated": it["updated_at"][:10],
                            "queries": rec["queries"], "enriched": False, "score": -99})
    for r in results:
        first = seen.setdefault(r["url"], TODAY)
        r["first_seen"] = first
        r["is_new"] = first == TODAY
    results.sort(key=lambda r: (r["score"], r.get("updated", "")), reverse=True)

    payload = {"generated_at": NOW.isoformat(timespec="seconds"),
               "count": len(results), "new_today": sum(r["is_new"] for r in results),
               "results": results}
    json.dump(payload, open(os.path.join(OUT, "latest.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    json.dump(seen, open(seen_path, "w", encoding="utf-8"), ensure_ascii=False, indent=0, sort_keys=True)

    lines = [f"# Bounty feed — {payload['generated_at']}",
             f"Всего: {payload['count']}, новых сегодня: {payload['new_today']}", "",
             "| score | new | issue | amounts | PR open/merged | claims | updated |",
             "|---|---|---|---|---|---|---|"]
    for r in results[:150]:
        if not r.get("enriched"):
            continue
        title = r["title"].replace("|", "/")[:80]
        lines.append(f"| {r['score']} | {'🆕' if r['is_new'] else ''} | [{r['repo']}#{r['number']}]({r['url']}) {title} "
                     f"| {', '.join(r['amounts'])[:40]} | {len(r['prs_open'])}/{len(r['prs_merged'])} "
                     f"| {r['claims']} | {r['updated']} |")
    open(os.path.join(OUT, "latest.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    log(f"done: {payload['count']} results, {payload['new_today']} new, "
        f"enriched {sum(1 for r in results if r.get('enriched'))}, {time.time() - START:.0f}s total")


if __name__ == "__main__":
    try:
        main()
    finally:
        os.makedirs(OUT, exist_ok=True)
        with open(os.path.join(OUT, "run.log"), "w", encoding="utf-8") as f:
            f.write("\n".join(LOG_LINES) + "\n")
