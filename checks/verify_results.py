#!/usr/bin/env python3
"""결과 검증 (§5-C).

실행이 끝난 노트북(build/executed/*.ipynb)의 출력을 바깥에서 읽어
핵심 수치가 기대 범위 안에 있는지 확인한다.

왜 노트북 안에 검증 셀을 넣지 않는가
    notebooks/ 아래 사본은 구글 드라이브 원본과 바이트 단위로 같아야
    한다. 검증 셀을 넣으면 그 순간 사본과 원본이 달라지고, 점검
    도구가 독자와 다른 코드를 검사하게 된다.

왜 완전 일치를 요구하지 않는가
    난수 시드 때문에 매번 실패한다. 본문 60쪽에도 "학습할 때마다
    산출되는 값은 조금씩 달라질 수 있다"고 적혀 있다. 핵심 수치
    몇 개만 범위로 확인한다.

판정 원칙 (2026-09-08 개편)
    기본은 "오류 없이 끝까지 실행됐는가" 하나다. 수치 검사는 실행 점검이
    원리적으로 잡지 못하는 곳에만 둔다. 지금은 두 곳뿐이다.
      · 85쪽 — 오류 없이 잘 돌아가면서 본문 논지를 뒤집을 수 있다
      · 60쪽 — 오류 없이 수렴만 실패할 수 있다
    수치 규칙을 늘리기 전에 "실행 점검으로 잡히지 않는가"를 먼저 물을 것.
    규칙이 늘수록 노트북이 아니라 규칙이 고장 나서 거짓 경보가 난다.

⚠ 85쪽은 판정 방향이 반대다. notebooks.yml 의 inverted 주석을 읽을 것.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
EXECUTED = ROOT / "build" / "executed"
DATA = ROOT / "data"


def cell_outputs(nb: dict) -> list[str]:
    """노트북의 모든 출력 텍스트를 셀 순서대로."""
    texts = []
    for cell in nb.get("cells", []):
        for out in cell.get("outputs", []):
            if "text" in out:
                texts.append("".join(out["text"]))
            data = out.get("data", {})
            if "text/plain" in data:
                texts.append("".join(data["text/plain"]))
    return texts


# input() 은 CI 에 키보드가 없어서 반드시 이 오류로 끝난다. 노트북이
# 깨진 것이 아니므로 실행 실패로 세지 않는다. 108·220쪽이 여기 해당한다.
IGNORED_ERRORS = {"StdinNotImplementedError"}


def run_errors(nb: dict) -> list[str]:
    """실행 중 발생한 오류. 위 예외 목록은 정상으로 본다."""
    found = []
    for cell in nb.get("cells", []):
        for out in cell.get("outputs", []):
            if out.get("output_type") != "error":
                continue
            name = out.get("ename") or "?"
            if name in IGNORED_ERRORS:
                continue
            value = (out.get("evalue") or "").strip().splitlines()
            found.append(f"{name}: {value[0][:120]}" if value else name)
    return found


def extract(spec: dict, outputs: list[str]):
    if spec.get("last_output_nonempty"):
        return bool(outputs) and bool(outputs[-1].strip())

    joined = "\n".join(outputs)
    if "contains" in spec:
        # 수치가 아니라 "여기까지 도달했는가"를 보는 검사.
        return spec["contains"] in joined
    found = re.findall(spec["pattern"], joined, flags=re.IGNORECASE)
    if not found:
        return None
    value = found[-1] if spec.get("take", "last") == "last" else found[0]
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def judge(value, rule: dict) -> bool:
    if value is None:
        return False
    if "truthy" in rule:
        return bool(value) == bool(rule["truthy"])
    if "lt" in rule:
        return value < rule["lt"]
    if "gt" in rule:
        return value > rule["gt"]
    if "near" in rule:
        return abs(value - rule["near"]) <= rule.get("tol", 0.01)
    raise ValueError(f"알 수 없는 판정 규칙: {rule}")


def main() -> int:
    cfg = yaml.safe_load((ROOT / "notebooks.yml").read_text(encoding="utf-8"))
    results, failed, skipped = [], 0, 0

    for spec in cfg["notebooks"]:
        nb_id, page = spec["id"], spec["page"]

        if not spec.get("ci", False):
            skipped += 1
            results.append({"id": nb_id, "page": page, "title": spec["title"],
                            "state": "manual", "label": "수동 점검",
                            "detail": "CI 대상이 아닙니다."})
            print(f"[  수동 점검] {page}쪽 {spec['title']}")
            continue

        source = ROOT / spec["file"]
        executed = EXECUTED / (Path(spec["file"]).stem + ".ipynb")

        # 사본이 아직 배치되지 않은 것과 실행이 깨진 것은 다르다.
        # 전자를 실패로 처리하면 사본을 넣기 전까지 매달 거짓 경보가 온다.
        if not source.exists():
            skipped += 1
            results.append({"id": nb_id, "page": page, "title": spec["title"],
                            "state": "wait", "label": "점검 예정",
                            "detail": f"노트북 사본이 아직 없습니다 ({spec['file']})."})
            print(f"[  점검 예정] {page}쪽 {spec['title']} — 사본 미배치")
            continue

        if not executed.exists():
            failed += 1
            results.append({"id": nb_id, "page": page, "title": spec["title"],
                            "state": "bad", "label": "실행 실패",
                            "detail": "실행 결과 파일이 없습니다. 실행 단계를 확인하세요."})
            print(f"[  실행 실패] {page}쪽 {spec['title']}")
            continue

        nb = json.loads(executed.read_text(encoding="utf-8"))

        # 기본 판정: 오류 없이 끝까지 실행됐는가.
        problems = [f"실행 오류 — {e}" for e in run_errors(nb)]

        outputs = cell_outputs(nb)
        for check in spec.get("checks", []):
            value = extract(check["extract"], outputs)
            if not judge(value, check["assert"]):
                problems.append(f"{check['name']}(측정 {value}) — {check['on_fail'].strip()}")

        if problems:
            failed += 1
            # 실행이 깨진 것과 결과가 어긋난 것은 독자에게 다른 사건이다.
            state = "bad"
            label = "실행 오류" if problems[0].startswith("실행 오류") else "결과 이상"
        else:
            state, label = "ok", "정상"

        # 85쪽이 실패했다는 것은 '학습에 성공했다'는 뜻이다.
        if problems and spec.get("inverted"):
            label = "⚠ 논지 뒤집힘"

        results.append({"id": nb_id, "page": page, "title": spec["title"],
                        "state": state, "label": label,
                        "detail": " / ".join(problems)
                        or ("오류 없이 실행됐습니다." if not spec.get("checks")
                            else "오류 없이 실행됐고 수치도 기대 범위 안입니다.")})
        print(f"[{label:>10}] {page}쪽 {spec['title']}"
              + (f"\n             {' / '.join(problems)}" if problems else ""))

    today = date.today().isoformat()
    DATA.mkdir(exist_ok=True)
    status_path = DATA / "status.json"
    status = json.loads(status_path.read_text(encoding="utf-8")) if status_path.exists() else {}
    ran = len(results) - skipped
    if ran == 0:
        state, summary = "wait", "대상 6개 (188쪽 그림 제외) — 사본 배치 대기"
    elif failed:
        state, summary = "bad", f"{ran}개 중 {failed}개 확인 필요"
    else:
        state, summary = "ok", f"{ran}개 전체 정상"

    status["notebooks"] = {
        "checked": today if ran else None,
        "state": state,
        "summary": summary,
        "results": results,
    }
    status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")

    if (sm := __import__("os").environ.get("GITHUB_STEP_SUMMARY")):
        with open(sm, "a", encoding="utf-8") as f:
            f.write(f"## 실행·결과 점검 {today}\n\n")
            for r in results:
                f.write(f"- **{r['label']}** {r['page']}쪽 {r['title']} — {r['detail']}\n")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
