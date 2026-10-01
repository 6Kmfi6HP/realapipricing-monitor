#!/usr/bin/env python3
"""Fetch realapipricing.com data and diff plan prices against a local state file.

Exit codes:
  0 = no change
  2 = price / plan changes detected
  1 = fetch failed (state file is NEVER touched on failure)

Usage:
  fetch_and_diff.py --state PATH [--vendor OpenAI] [--plan-regex RE]
                    [--only subscription|metered|all] [--commit] [--force]
                    [--top N] [--with-conventions]
"""
import argparse
import json
import os
import re
import sys
import tempfile
import urllib.request
from datetime import date, datetime, timedelta

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
BASE = "https://realapipricing.com"
WATCHED = ("price_usd", "real_usd_per_mtok", "monthly_yi",
           "promo_until", "unmetered", "confidence")


def fetch_json(path):
    req = urllib.request.Request(
        BASE + path, headers={"User-Agent": UA, "Referer": BASE + "/"})
    with urllib.request.urlopen(req, timeout=90) as r:
        if r.status != 200:
            raise RuntimeError("HTTP %s on %s" % (r.status, path))
        return json.loads(r.read().decode("utf-8"))


def build_snapshot(data, only, vendor, plan_re):
    rx = re.compile(plan_re, re.I) if plan_re else None
    rows = {}
    for p in (data.get("points") or []):
        if only != "all" and p.get("billing") != only:
            continue
        if vendor and (p.get("vendor") or "").lower() != vendor.lower():
            continue
        pid = p.get("id") or "%s::%s" % (p.get("plan_id"), p.get("model"))
        if rx and not rx.search(pid + " " + str(p.get("plan", ""))):
            continue
        rows[pid] = {
            "plan": p.get("plan"),
            "vendor": p.get("vendor"),
            "billing": p.get("billing"),
            "model": p.get("model") or p.get("model_display"),
            "currency": p.get("currency"),
            "local_price": p.get("local_price"),
            "w": dict((k, p.get(k)) for k in WATCHED),
        }
    return rows, data.get("generatedAt")


def diff(old, new):
    out = {"price": [], "new": [], "gone": [], "other": []}
    for pid in sorted(set(old) | set(new)):
        a, b = old.get(pid), new.get(pid)
        if a is None:
            out["new"].append((pid, b))
        elif b is None:
            out["gone"].append((pid, a))
        else:
            for k in WATCHED:
                av, bv = a["w"].get(k), b["w"].get(k)
                if av == bv:
                    continue
                if isinstance(av, (int, float)) and isinstance(bv, (int, float)):
                    if abs(av - bv) < 1e-7:
                        continue
                rec = {"id": pid, "plan": b["plan"], "vendor": b["vendor"],
                       "field": k, "old": av, "new": bv,
                       "confidence": b["w"].get("confidence")}
                key = "price" if k in ("price_usd", "real_usd_per_mtok") else "other"
                out[key].append(rec)
    return out


def money(v, local=None, billing=None):
    if v is None and local is None:
        return "按量计费" if billing == "metered" else "—"
    if v is None:
        return str(local)
    s = "$%s" % format(v, ",.2f")
    if local and str(local) != s:
        return "%s (%s)" % (s, local)
    return s


def render(data, rows, d, gen, top):
    L = ["# 真实API定价 · 价格监控报告", ""]
    L.append("数据日期 `generatedAt`: **%s** | 抓取时间: %s | 匹配套餐: **%d**"
             % (gen, datetime.now().strftime("%Y-%m-%d %H:%M"), len(rows)))
    conv = data.get("conventions") or {}
    if conv.get("usdPerCny"):
        L.append("汇率口径: 1 USD = %s CNY" % conv["usdPerCny"])
    promos = conv.get("promotions") or {}
    if promos:
        promo_items = []
        for pkey, pval in promos.items():
            if isinstance(pval, dict):
                label = pval.get("labelZh") or pval.get("labelEn") or pkey
                dates = "%s ~ %s" % (pval.get("startDate", "—"), pval.get("endDate", "—"))
                promo_items.append("- %s (%s)" % (label, dates))
        if promo_items:
            L.append("活跃促销活动:")
            L.extend(promo_items)
    L.append("")

    changed = any(d[k] for k in ("price", "new", "gone", "other"))
    if not changed:
        L.append("**无价格变动。**")
        L.append("")
    else:
        if d["price"]:
            L += ["## 价格变动", "",
                  "| 套餐 | 厂商 | 字段 | 旧 | 新 | 置信度 |",
                  "|---|---|---|---|---|---|"]
            for r in d["price"]:
                L.append("| %s | %s | `%s` | %s | **%s** | %s |"
                         % (r["plan"], r["vendor"], r["field"],
                            r["old"], r["new"], r["confidence"]))
            L.append("")
        if d["new"]:
            L += ["## 新增套餐 (%d)" % len(d["new"]), "",
                  "| 套餐 | 厂商 | 模型 | 月费 | 真实 $/MTok |",
                  "|---|---|---|---|---|"]
            for _pid, b in d["new"][:top]:
                L.append("| %s | %s | %s | %s | %s |"
                         % (b["plan"], b["vendor"], b["model"],
                            money(b["w"]["price_usd"], b.get("local_price"), b.get("billing")),
                            b["w"]["real_usd_per_mtok"]))
            L.append("")
        if d["gone"]:
            L.append("## 下架/移除 (%d)" % len(d["gone"]))
            for _pid, a in d["gone"][:top]:
                L.append("- %s (%s, %s)" % (a["plan"], a["vendor"], a["model"]))
            L.append("")
        if d["other"]:
            L += ["## 其他信号（促销/额度/置信度）", "",
                  "| 套餐 | 字段 | 旧 | 新 |", "|---|---|---|---|"]
            for r in d["other"][:top]:
                L.append("| %s | `%s` | %s | %s |"
                         % (r["plan"], r["field"], r["old"], r["new"]))
            L.append("")

    # promo expiry scan
    today = date.today()
    horizon = (today + timedelta(days=30)).isoformat()
    today_s = today.isoformat()
    expiring, soon = [], []
    for r in rows.values():
        pu = r["w"].get("promo_until")
        if not pu:
            continue
        (expiring if pu <= today_s else (soon if pu <= horizon else [])).append(r)
    if expiring:
        L.append("## 已过期促销")
        for r in sorted(expiring, key=lambda x: x["w"]["promo_until"]):
            L.append("- %s · 截止 %s · 现价 %s · $/MTok %s"
                     % (r["plan"], r["w"]["promo_until"],
                        money(r["w"]["price_usd"], r.get("local_price"), r.get("billing")),
                        r["w"]["real_usd_per_mtok"]))
        L.append("")
    if soon:
        L.append("## 30 天内到期促销")
        for r in sorted(soon, key=lambda x: x["w"]["promo_until"]):
            L.append("- %s · 截止 %s · unmetered=%s"
                     % (r["plan"], r["w"]["promo_until"], r["w"]["unmetered"]))
        L.append("")

    if not changed:
        ranked = sorted((r for r in rows.values()
                         if r["w"].get("real_usd_per_mtok")),
                        key=lambda r: r["w"]["real_usd_per_mtok"])
        L += ["## 最划算 Top %d（真实 $/MTok 最低）" % min(top, len(ranked)), "",
              "| 套餐 | 厂商 | 月费 | 真实 $/MTok | 置信度 |",
              "|---|---|---|---|---|"]
        for r in ranked[:top]:
            L.append("| %s | %s | %s | %.4f | %s |"
                     % (r["plan"], r["vendor"],
                        money(r["w"]["price_usd"], r.get("local_price"), r.get("billing")),
                        r["w"]["real_usd_per_mtok"], r["w"]["confidence"]))
        L.append("")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--state",
                    default=os.path.expanduser("~/.hermes/realapipricing/state.json"))
    ap.add_argument("--vendor")
    ap.add_argument("--plan-regex")
    ap.add_argument("--only", default="subscription",
                    choices=["subscription", "metered", "all"])
    ap.add_argument("--commit", action="store_true")
    ap.add_argument("--force", action="store_true",
                    help="allow commit even if baseline filter mismatches")
    ap.add_argument("--with-conventions", action="store_true",
                    help="also fetch site.json for fx rate / promo metadata")
    ap.add_argument("--top", type=int, default=15)
    a = ap.parse_args()

    try:
        data = fetch_json("/data/points.json")
        if a.with_conventions:
            try:
                data["conventions"] = fetch_json("/data/site.json").get("conventions")
            except Exception as e:
                print("WARN: site.json fetch failed (%s), continuing" % e,
                      file=sys.stderr)
    except Exception as e:
        print("FETCH FAILED: %s\nState file left untouched: %s" % (e, a.state),
              file=sys.stderr)
        return 1

    rows, gen = build_snapshot(data, a.only, a.vendor, a.plan_regex)

    prev = {}
    prev_meta = {}
    if os.path.exists(a.state):
        try:
            with open(a.state) as f:
                state_obj = json.load(f)
                prev = state_obj.get("rows", {})
                prev_meta = {
                    "filter": state_obj.get("filter"),
                    "generatedAt": state_obj.get("generatedAt"),
                    "count": state_obj.get("count"),
                }
        except Exception as e:
            print("WARN: unreadable state (%s), treating as first run" % e,
                  file=sys.stderr)

    curr_filter = {
        "only": a.only,
        "vendor": a.vendor,
        "plan_regex": a.plan_regex,
    }
    prev_filter = prev_meta.get("filter")
    if prev and prev_filter is not None and prev_filter != curr_filter:
        print("WARN: baseline filter mismatch: state file has %s, current run has %s. "
              "Comparing different filter scopes produces false addition/removal diffs."
              % (prev_filter, curr_filter), file=sys.stderr)
        if a.commit and not a.force:
            print("REFUSING TO COMMIT: baseline filter mismatch. Use a dedicated --state file "
                  "or pass --force to overwrite.", file=sys.stderr)
            return 1

    first_run = not prev
    d = ({"price": [], "new": [], "gone": [], "other": []} if first_run
         else diff(prev, rows))
    if first_run:
        d["new"] = sorted(rows.items())

    print(render(data, rows, d, gen, a.top))

    if a.commit:
        parent = os.path.dirname(a.state) or "."
        os.makedirs(parent, exist_ok=True)
        payload = {
            "generatedAt": gen,
            "fetchedAt": datetime.now().isoformat(timespec="seconds"),
            "filter": {"only": a.only, "vendor": a.vendor,
                       "plan_regex": a.plan_regex},
            "count": len(rows),
            "rows": rows,
        }
        fd, tmp = tempfile.mkstemp(dir=parent)
        with os.fdopen(fd, "w") as f:
            json.dump(payload, f, ensure_ascii=False, indent=1)
        os.replace(tmp, a.state)
        print("\n[baseline %s] %s (%d plans, generatedAt=%s)"
              % ("written" if first_run else "updated", a.state, len(rows), gen))

    return 2 if any(d[k] for k in ("price", "new", "gone")) else 0


if __name__ == "__main__":
    sys.exit(main())
