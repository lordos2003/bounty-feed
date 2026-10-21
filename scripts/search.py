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
    r"|\d[\d,\s]*(?:\.\d+)?\s?(?:₽|(?:USDC|USDT|USD|XMR|BTC|ETH|sats?|сатош\w*|руб\w*|RUB)\b|(?-i:SOL)\b)"
    r"|(?:USDC|USDT|XMR)\s?\d[\d,]*(?:\.\d+)?)",
    re.IGNORECASE,
)
def _rx(key, default):
    pats = CFG.get(key) or default
    return re.compile("|".join(f"(?:{p})" for p in pats), re.IGNORECASE)


# Сумма засчитывается как награда, только если рядом есть слово про награду/оплату работы
# и нет слов про цену товара, тариф, бюджет рекламы и т.п. Списки настраиваются в config.json.
REWARD_CTX_RE = _rx("reward_context_regex", [r"bount", r"reward", r"награ", r"вознагр"])
PRICE_CTX_RE = _rx("price_context_regex", [r"цен[аеуыо]?\b", r"\bprice", r"стоимост", r"тариф"])
CTX_BEFORE = int(CFG.get("reward_ctx_before", 80))
CTX_AFTER = int(CFG.get("reward_ctx_after", 50))
PRICE_BEFORE = int(CFG.get("price_ctx_before", 40))
PRICE_AFTER = int(CFG.get("price_ctx_after", 25))


def _amount_value(s):
    """Числовое значение суммы (для отсева нулевых наград); None, если не разобрать."""
    m = re.search(r"\d[\d,\s]*(?:\.\d+)?", s)
    if not m:
        return None
    num = re.sub(r"[,\s]", "", m.group(0))
    try:
        return float(num)
    except ValueError:
        return None


def reward_amounts(text):
    """Суммы, похожие на награду за задачу. Возвращает (reward, other): other — остальные найденные суммы."""
    reward, other = set(), set()
    for m in AMOUNT_RE.finditer(text):
        amt = m.group(0).strip()
        before = text[max(0, m.start() - CTX_BEFORE):m.start()]
        after = text[m.end():m.end() + CTX_AFTER]
        near = text[max(0, m.start() - PRICE_BEFORE):m.start()] + " " + text[m.end():m.end() + PRICE_AFTER]
        val = _amount_value(amt)
        if (REWARD_CTX_RE.search(before) or REWARD_CTX_RE.search(after)) \
                and not PRICE_CTX_RE.search(near) and val != 0:
            reward.add(amt)
        else:
            other.add(amt)
    return sorted(reward)[:8], sorted(other - reward)[:8]


def labels_line(labels):
    """Метки как строка текста: в них часто сама сумма ("bounty: $50")."""
    names = [l if isinstance(l, str) else (l.get("name") or "") for l in labels]
    return "labels: " + " | ".join(names) if names else ""


CLAIM_RE = re.compile(
    r"(^|\s)/(attempt|claim)\b|i('| a)?m working on|i will work on|i'll work on|"
    r"assign (this )?(to )?me|can i take|i'd like to work|беру в работу|возьму",
    re.IGNORECASE,
)
PAID_RE = re.compile(r"\b(rewarded|bounty (has been )?paid|payment sent|paid out)\b", re.IGNORECASE)
STRIPE_HINT = ("algora", "opire", "polar")
TESTNET_RE = re.compile("|".join(CFG.get("testnet_regex", [])) or r"(?!x)x", re.IGNORECASE)
SECONDARY_WAIT = float(CFG.get("secondary_wait_sec", 60))


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
                if "secondary rate limit" in body.lower():
                    # вторичный лимит: X-RateLimit-Reset тут не помогает, ждём фиксированно
                    wait = int(retry) if retry else SECONDARY_WAIT
                else:
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


DEADLINE_RE = re.compile(r"(?:deadline|expires?|due(?: date)?)\W{0,5}(\d{4}-\d{2}-\d{2})", re.IGNORECASE)
EXCLUDE_STATS = {}


def exclusion_reason(item):
    """Причина исключения задачи или None. Нужна, чтобы не тратить enrich на закрытые/неоплачиваемые."""
    repo = item["repository_url"].split("/repos/")[1]
    owner = repo.split("/")[0]
    if owner in CFG["exclude_owners"]:
        return "owner"
    if repo in CFG["exclude_repos"]:
        return "repo"
    title = item["title"]
    if any(re.search(p, title, re.IGNORECASE) for p in CFG["exclude_title_regex"]):
        return "title"
    bad_labels = {x.lower() for x in CFG.get("exclude_labels", [])}
    for lab in item.get("labels", []):
        if (lab.get("name") or "").strip().lower() in bad_labels:
            return "label:" + lab["name"].strip().lower()
    text = f"{title}\n{item.get('body') or ''}"
    for p in CFG.get("exclude_text_regex", []):
        if re.search(p, text, re.IGNORECASE):
            return "text"
    if CFG.get("skip_expired_deadline", True):
        for m in DEADLINE_RE.finditer(text):
            if m.group(1) < TODAY:
                return "deadline"
    return None


def excluded(item):
    reason = exclusion_reason(item)
    if reason:
        key = reason.split(":")[0]
        EXCLUDE_STATS[key] = EXCLUDE_STATS.get(key, 0) + 1
    return bool(reason)


def search_all():
    created = (NOW - dt.timedelta(days=CFG["created_days"])).date().isoformat()
    updated = (NOW - dt.timedelta(days=CFG["updated_days"])).date().isoformat()
    found = {}
    queries = [q if isinstance(q, dict) else {"q": q} for q in CFG["queries"]]
    for qi, qd in enumerate(queries):
        q = qd["q"]
        if time.time() > SEARCH_DEADLINE or out_of_time():
            skipped = [x["q"] for x in queries[qi:]]
            log(f"search budget reached, skipped {len(skipped)} queries: {skipped}")
            break
        full = f"{q} is:issue is:open no:assignee created:>={created} updated:>={updated}"
        for page in range(1, int(qd.get("pages", CFG["max_pages_per_query"])) + 1):
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


def pre_score(rec):
    """Дешёвая оценка по данным поиска (без API): задаёт порядок обогащения."""
    it = rec["item"]
    text = f"{it['title']}\n{it.get('body') or ''}"
    labels = " ".join(l["name"] for l in it.get("labels", [])).lower()
    text = labels_line(it.get("labels", [])) + "\n" + text
    s = len(rec["queries"])
    s += 3 if reward_amounts(text)[0] else 0
    s += 2 if ("bounty" in labels or "reward" in labels) else 0
    s += 1 if it.get("author_association") in ("OWNER", "MEMBER", "COLLABORATOR") else 0
    s += 1 if (NOW.date() - dt.date.fromisoformat(it["updated_at"][:10])).days <= 7 else 0
    s -= 5 if TESTNET_RE.search(text) else 0
    return s


def enrich(rec):
    it = rec["item"]
    repo = it["repository_url"].split("/repos/")[1]
    n = it["number"]
    text = f"{labels_line(it.get('labels', []))}\n{it['title']}\n{it.get('body') or ''}"
    out = {
        "url": it["html_url"], "repo": repo, "number": n, "title": it["title"],
        "created": it["created_at"][:10], "updated": it["updated_at"][:10],
        "comments": it["comments"], "labels": [l["name"] for l in it.get("labels", [])],
        "author": it["user"]["login"], "author_association": it.get("author_association"),
        "queries": rec["queries"],
        "body_snippet": re.sub(r"\s+", " ", (it.get("body") or ""))[:500],
        "prs_open": [], "prs_merged": [], "prs_closed": [],
        "claims": 0, "claimers": [], "bot_bounty": None,
        "paid_hint": False, "testnet_hint": False, "enriched": False,
        "pre_score": rec.get("pre_score"),
    }
    all_text = text
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
                all_text += "\n" + body
                login = ((ev.get("user") or ev.get("actor") or {}).get("login") or "").lower()
                if any(h in login for h in STRIPE_HINT) and ("bounty" in body.lower() or "💎" in body):
                    out["bot_bounty"] = {"bot": login, "text": re.sub(r"\s+", " ", body)[:300]}
                    text += "\n" + body
                if CLAIM_RE.search(body) and login not in out["claimers"]:
                    out["claims"] += 1
                    out["claimers"].append(login)
                if PAID_RE.search(body):
                    out["paid_hint"] = True
    amounts, other_amounts = reward_amounts(text)
    out["amounts"] = amounts
    out["amounts_other"] = other_amounts  # суммы без контекста награды (цены, бюджеты) — для отладки
    out["testnet_hint"] = bool(TESTNET_RE.search(all_text))
    out["stripe_likely"] = bool(out["bot_bounty"]) or any(
        h in " ".join(out["labels"]).lower() for h in STRIPE_HINT)
    s = 0
    s += 3 if amounts else 0
    s += 2 if any("bounty" in l.lower() or "reward" in l.lower() for l in out["labels"]) else 0
    s += 1 if out["author_association"] in ("OWNER", "MEMBER", "COLLABORATOR") else 0
    s += 1 if (NOW.date() - dt.date.fromisoformat(out["updated"])).days <= 7 else 0
    usd = [float(x.replace(",", "")) for a in amounts
           for x in re.findall(r"\$\s?(\d[\d,]*(?:\.\d+)?)", a)]
    s -= 3 if usd and max(usd) < 5 else 0  # микро-награды ($1–4) почти всегда шум
    s -= 3 if not amounts else 0  # без явной суммы это почти никогда не оплачиваемая задача
    s -= 2 if out["stripe_likely"] else 0
    s -= 4 * len(out["prs_open"])
    s -= 10 if out["prs_merged"] else 0
    s -= min(out["claims"], 3) * 2
    s -= 10 if out["paid_hint"] else 0
    s -= 8 if out["testnet_hint"] else 0
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
    log(f"search finished: {len(found)} unique issues, {time.time() - START:.0f}s elapsed; "
        f"excluded by filters (with repeats): {EXCLUDE_STATS}")
    if not found:
        log("ничего не найдено — latest.json не перезаписываю")
        sys.exit(1)
    for rec in found.values():
        rec["pre_score"] = pre_score(rec)
    order = sorted(found.values(), key=lambda r: (r["pre_score"], r["item"]["updated_at"]), reverse=True)
    results = []
    not_enriched_reason = {"limit": 0, "time": 0}
    for i, rec in enumerate(order):
        if i < CFG["max_enrich"] and not out_of_time():
            results.append(enrich(rec))
            time.sleep(0.4)
            if (i + 1) % 50 == 0:
                log(f"enriched {i + 1}/{min(len(order), CFG['max_enrich'])}")
        else:
            not_enriched_reason["limit" if i >= CFG["max_enrich"] else "time"] += 1
            it = rec["item"]
            text = f"{labels_line(it.get('labels', []))}\n{it['title']}\n{it.get('body') or ''}"
            results.append({"url": it["html_url"], "title": it["title"],
                            "repo": it["repository_url"].split("/repos/")[1],
                            "number": it["number"],
                            "created": it["created_at"][:10], "updated": it["updated_at"][:10],
                            "labels": [l["name"] for l in it.get("labels", [])],
                            "author_association": it.get("author_association"),
                            "body_snippet": re.sub(r"\s+", " ", (it.get("body") or ""))[:500],
                            "amounts": reward_amounts(text)[0],
                            "testnet_hint": bool(TESTNET_RE.search(text)),
                            "queries": rec["queries"], "enriched": False,
                            "pre_score": rec["pre_score"], "score": -99})
    if any(not_enriched_reason.values()):
        log(f"not enriched: {not_enriched_reason}")
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
    shown = 0
    for r in results:
        if shown >= 150:
            break
        # в сводку — только задачи с явной суммой, без признаков тестовой сети и с положительной оценкой
        if not r.get("enriched") or not r["amounts"] or r["testnet_hint"] or r["score"] <= 0:
            continue
        shown += 1
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
