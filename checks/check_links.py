#!/usr/bin/env python3
"""링크 점검 (§5-A).

links.yml 을 읽어 각 URL의 상태를 확인하고 data/links.json 과
data/status.json 을 갱신한다.

판정 원칙
    200                     정상
    3xx → 최종 200          정상 (최종 주소를 반드시 기록)
    403 / 429               확인 필요 — 실패로 처리하지 않는다
    404 / 410               소실 — 이때만 워크플로를 실패시킨다
    타임아웃 / DNS 실패     재시도 후에도 실패하면 확인 필요
    expect_block: true      어떤 응답이든 '자동 판정 불가'
    url: null               '원문 대조 필요'

403을 실패로 처리하면 안 된다. 위키백과·아마존·네이버는 자동화
요청을 차단한다. 그대로 두면 매주 거짓 경보가 오고, 결국 알림을
통째로 무시하게 된다.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import date
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

OK = "ok"                 # 정상
CHECK = "check"           # 확인 필요
DEAD = "dead"             # 소실
UNJUDGED = "unjudged"     # 자동 판정 불가 (차단 사이트)
UNRESOLVED = "unresolved" # 원문 대조 필요

LABEL = {
    OK: "정상",
    CHECK: "확인 필요",
    DEAD: "소실",
    UNJUDGED: "자동 판정 불가",
    UNRESOLVED: "원문 대조 필요",
}


def probe(url: str, *, timeout: int, retries: int, ua: str) -> dict:
    """HEAD 후 필요하면 GET. 최종 주소와 상태 코드를 돌려준다."""
    headers = {
        "User-Agent": ua,
        "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
    }
    last_error = None

    for attempt in range(retries + 1):
        for method in ("head", "get"):
            try:
                r = requests.request(
                    method, url, headers=headers, timeout=timeout,
                    allow_redirects=True,
                )
            except requests.RequestException as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                continue

            # HEAD를 제대로 처리하지 않는 서버가 많다. GET으로 한 번 더.
            if method == "head" and r.status_code in (405, 400, 403, 501):
                continue

            return {
                "code": r.status_code,
                "final_url": r.url,
                "redirected": r.url.rstrip("/") != url.rstrip("/"),
                "error": None,
            }

        if attempt < retries:
            time.sleep(2 * (attempt + 1))

    return {"code": None, "final_url": None, "redirected": False,
            "error": last_error}


def classify(entry: dict, result: dict | None) -> tuple[str, str]:
    """(상태, 사람이 읽을 사유)"""
    if entry.get("url") is None:
        return UNRESOLVED, "본문 원문과 대조되지 않은 항목입니다."

    if entry.get("expect_block"):
        code = result["code"] if result else None
        detail = f"HTTP {code}" if code else (result or {}).get("error", "응답 없음")
        return UNJUDGED, f"자동화 요청을 차단하는 사이트입니다 ({detail}). 사람이 직접 확인합니다."

    code = result["code"]
    if code is None:
        return CHECK, f"연결하지 못했습니다 — {result['error']}"
    if 200 <= code < 300:
        if result["redirected"]:
            return OK, f"정상 (최종 주소 {result['final_url']})"
        return OK, "정상"
    if code in (403, 429):
        return CHECK, f"HTTP {code} — 자동화 요청이 차단된 것일 수 있습니다. 사람이 확인해 주세요."
    if code in (404, 410):
        return DEAD, f"HTTP {code} — 페이지가 사라졌습니다."
    return CHECK, f"HTTP {code}"


def main() -> int:
    cfg = yaml.safe_load((ROOT / "links.yml").read_text(encoding="utf-8"))
    d = cfg.get("defaults", {})
    timeout, retries, ua = d.get("timeout", 20), d.get("retries", 2), d.get("user_agent", "")

    out, counts = [], {k: 0 for k in LABEL}

    for group in ("practice", "references"):
        for entry in cfg.get(group, []) or []:
            result = None
            if entry.get("url"):
                result = probe(entry["url"], timeout=timeout, retries=retries, ua=ua)

            state, reason = classify(entry, result)
            counts[state] += 1

            out.append({
                "id": entry["id"],
                "group": group,
                "page": entry.get("page"),
                "title": entry.get("title"),
                "url": entry.get("url"),
                # 단축 URL의 최종 주소는 links.yml 의 resolved 를 우선한다.
                # 사람이 브라우저에서 확인해 적은 값이 자동 추적보다 믿을 만하다.
                "resolved": entry.get("resolved") or (result or {}).get("final_url"),
                "risk": entry.get("risk"),
                # reader = 독자가 열려고 인쇄된 자료. record = 그림 출처 표기.
                # 사이트는 reader 만 늘 보여주고, record 는 문제가 생겼을 때만 올린다.
                "audience": entry.get("audience", "reader"),
                "note": entry.get("note"),
                "state": state,
                "label": LABEL[state],
                "reason": reason,
            })
            print(f"[{LABEL[state]:>12}] {entry['id']:<20} {entry.get('url') or '—'}")

    today = date.today().isoformat()
    DATA.mkdir(exist_ok=True)
    (DATA / "links.json").write_text(
        json.dumps({"checked": today, "counts": counts, "links": out},
                   ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")

    # status.json 의 links 항목만 갱신한다 (노트북 결과를 덮어쓰지 않도록).
    status_path = DATA / "status.json"
    status = json.loads(status_path.read_text(encoding="utf-8")) if status_path.exists() else {}
    total = sum(counts.values())
    needs = counts[CHECK] + counts[DEAD]
    status["links"] = {
        "checked": today,
        "state": "bad" if counts[DEAD] else ("warn" if counts[CHECK] else "ok"),
        "summary": (f"{total}건 중 {needs}건 확인 필요" if needs
                    else f"{total}건 전체 정상"),
        "counts": counts,
    }
    status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")

    # 요약
    summary = "\n".join(
        f"- {LABEL[k]}: {v}건" for k, v in counts.items() if v)
    print("\n" + summary)
    if (sm := __import__("os").environ.get("GITHUB_STEP_SUMMARY")):
        with open(sm, "a", encoding="utf-8") as f:
            f.write(f"## 링크 점검 {today}\n\n{summary}\n\n")
            for item in out:
                if item["state"] in (CHECK, DEAD):
                    f.write(f"- **{item['label']}** {item['page'] or '—'}쪽 "
                            f"{item['title']} — {item['reason']}\n")

    # 소실된 링크가 있을 때만 실패시킨다. '확인 필요'로는 실패시키지 않는다.
    return 1 if counts[DEAD] else 0


if __name__ == "__main__":
    sys.exit(main())
