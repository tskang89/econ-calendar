# -*- coding: utf-8 -*-
"""index.html 을 만든다 — 오늘부터 한 달 치 일정 한 장.

조간 브리핑 맨 아래 '참고자료'에 걸리는 쪽이다. 평일 새벽에 새로 만든다.
자료가 어디서 왔고 무엇이 빠졌는지는 페이지 아래 각주에 그대로 적는다 —
빠진 것을 말하지 않으면 없는 일정으로 읽힌다.

주요국 경제 차트팩(tskang89/euro-chartpack)에서 떼어 낸 쪽이다. 차트팩은
주간 갱신이고 이쪽은 날마다 바뀌어, 한 저장소에 두면 되커밋이 자꾸 엉켰다.
주소도 차트팩 밑이라 일정만 따로 건네기가 어려웠다.
"""

from __future__ import annotations

import argparse
import datetime
import html
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import policy_dates                                          # noqa: E402
import schedule                                              # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "template.html"
OUTPUT = ROOT / "index.html"

WEEKDAY = "월화수목금토일"
DAYS = 7

TAG = {"policy": "통화정책", "meeting": "회의", "release": "지표",
       "event": "행사"}


def log(msg: str = "") -> None:
    print(msg, flush=True)


def esc(text: str) -> str:
    return html.escape(text, quote=True)


def render_days(events: list[dict], today: datetime.date) -> str:
    """일정이 있는 날만 싣는다.

    이레 치일 때는 빈 날도 '없습니다'로 두어 한 주 전체가 보였다. 한 달
    치에서 그러면 빈 칸이 스무 개 넘게 깔려 정작 있는 날이 묻힌다.
    """
    by_day: dict[str, list[dict]] = {}
    for e in events:
        by_day.setdefault(e["date"], []).append(e)

    out = []
    for key in sorted(by_day):
        day = datetime.date.fromisoformat(key)
        # 오늘 표시는 화면에서 다시 매긴다. 빌드가 하루 늦게 돌 때가 있어
        # (GitHub 예약이 여섯 시간 밀린다) 빌드 시점의 오늘을 박아 두면
        # 아침에 링크를 누른 사람이 어제를 오늘로 읽는다. 서버가 붙인 것은
        # 자바스크립트가 막힌 데서 쓰는 보루로 남겨 둔다.
        cls = "day today" if day == today else "day"
        head = (f'<h2><span class="d">{day.month}.{day.day}</span>'
                f'<span class="w">{WEEKDAY[day.weekday()]}요일</span></h2>')
        items = []
        for e in by_day[key]:
            klass = esc(e["kind"]) + (" major" if e.get("major") else "")
            items.append(
                f'<li class="{klass}">'
                f'<span class="tag">{TAG.get(e["kind"], e["kind"])}</span>'
                f'<span class="body">'
                f'<a class="src" href="{esc(e["url"])}" target="_blank" '
                f'rel="noopener"><span class="who">{esc(e["who"])}</span></a> '
                f'<span class="what">{esc(e["what"])}</span>'
                f'</span></li>')
        out.append(f'<section class="{cls}" data-date="{key}">{head}'
                   f'<ul>{"".join(items)}</ul></section>')
    if not out:
        return ('<div class="empty">앞으로 한 달 안에 잡힌 발표·회의가 '
                '없습니다</div>')
    return "\n".join(out)


NOTE = """<b>자료</b> 아래 여섯 곳은 공식 일정표에서 날마다 새로 받아 옵니다 —
ECB(이사회·통화정책회의), 미국 연준(FOMC), 영란은행(MPC), 한국은행(금통위),
Eurostat(유로지역 주요 지표), 독일 통계청. 폴란드·체코·스위스·튀르키예
중앙은행의 통화정책 결정일은 공식 일정표에서 확인한 날짜를 저장소에 적어
두고 씁니다 — 네 곳 중 일부는 자동 수집이 막혀 있고(봇 차단·자바스크립트
렌더링), 결정일은 한 해에 한 번 공표되고 좀처럼 바뀌지 않습니다.
기관 이름을 누르면 공식 일정표로 갑니다.
<br><br>
연준 FOMC 와 폴란드 NBP 는 이틀에 걸쳐 회의하고 <b>둘째 날</b> 결정을
내므로, 그 날짜만 적었습니다. 연준의 새 목표범위는 대개 그 다음 날부터
적용됩니다.
<br><br>
<b>굵게 표시한 것</b> 통화정책 결정, GDP, 소비자물가입니다. '물가'를 글자 그대로 잡으면 생산자·수입·도매물가까지 걸려 한 달 치의 절반 가까이가 굵어져 강조가 힘을 잃습니다.
<br><br>
<b>추려 싣습니다</b>
<ul>
<li>Eurostat 은 유로지역 주요 지표(euro indicators)로 좁혔습니다. 해설 글까지
넣으면 하루에 수십 건이 됩니다.</li>
<li>독일 통계청은 지역·행정 통계까지 함께 내는데, 여기에는 물가·고용·생산·
교역·국민계정 같은 거시지표만 싣습니다.</li>
<li>일본은행·중국인민은행은 아직 넣지 않았습니다.</li>
</ul>
Eurostat 유로지역 발표는 대개 현지 11시, 독일 통계청은 8시입니다."""


def build(today: datetime.date) -> str:
    log(f"일정 수집 — {today} 부터 {schedule.month_end(today)} 까지")
    events, warn = schedule.week(today, log=log)
    # 표가 말라 가는 곳. 통화정책 일자(손으로 채우는 것)와 Destatis 저장분
    # (사무소에서만 채울 수 있는 것) 둘 다 여기서 센다.
    health = policy_dates.health(today) + schedule.cache_health(today)
    warn += health
    for w in health:
        log(w)

    # 기준일만 적는다. 차트팩 링크는 template.html 이 다음 줄에 따로 둔다.
    # 예전에는 이 줄 끝에 가운뎃점으로 이어 붙였는데, 그러면 링크가 기준일의
    # 꼬리처럼 읽혀 눈에 들어오지 않았다. 차트팩 쪽도 '향후 1개월 주요 일정 →'
    # 를 머리글의 제 줄에 두고 있으므로, 두 페이지가 같은 꼴이 된다.
    stamp = (f'{today.year}년 {today.month}월 {today.day}일 '
             f'({WEEKDAY[today.weekday()]}) 기준')

    # 수집이 실패한 것은 화면에도 적는다. 조용히 빈 일정표를 내놓으면
    # '이번 주는 일정이 없다'로 읽힌다.
    # '받지 못했다'(통째로 빠짐)와 '받지 못해 … 받아 둔 것을 쓴다'(저장분으로
    # 대체)를 둘 다 잡는다. 뒤의 경우는 일정이 빠진 것이 아니라 묵은 것이므로
    # 꼬리말을 달리 붙인다 — '전부가 아닐 수 있다'고 적으면 틀린 말이 된다.
    fetch_fail = [w for w in warn if "받지 못" in w]
    cached_only = fetch_fail and all("받아 둔 것을 쓴다" in w for w in fetch_fail)
    warn_html = ""
    if fetch_fail:
        tail = (" 그 사이에 바뀐 일정이 있을 수 있습니다." if cached_only
                else " 아래 일정이 전부가 아닐 수 있습니다.")
        head = ("<b>일부 자료는 받아 둔 것을 씁니다.</b> " if cached_only
                else "<b>일부 자료를 받지 못했습니다.</b> ")
        warn_html = ('<div class="warn">' + head
                     + " / ".join(esc(w) for w in fetch_fail)
                     + tail + "</div>")

    html_out = TEMPLATE.read_text(encoding="utf-8")
    html_out = html_out.replace("__STAMP__", stamp)
    html_out = html_out.replace("__DAYS__", render_days(events, today))
    html_out = html_out.replace("__WARN__", warn_html)
    html_out = html_out.replace("__NOTE__", NOTE)
    html_out = html_out.replace("__OPS__", ops_blob(today, events, warn))
    log(f"\n일정 {len(events)}건")
    return html_out


# 페이지에 사람 눈에 안 보이는 한 덩어리를 심는다. 독자용이 아니라 주간
# 자체 점검용이다. 별도 파일로 두지 않는 까닭은 이미 Pages 에 올라가는 파일
# 안에 있으면 받는 쪽이 주소 하나로 끝나기 때문이다.
def ops_blob(today, events, warn) -> str:
    """빌드 상태를 JSON 한 줄로. 경고는 손질하지 않고 그대로 싣는다."""
    days = sorted({e["date"] for e in events})
    ops = {
        "built": datetime.datetime.now(datetime.UTC)
                         .strftime("%Y-%m-%dT%H:%MZ"),
        "asOf": today.isoformat(),
        "events": len(events),
        "first": days[0] if days else None,
        "last": days[-1] if days else None,
        "warn": [" ".join(w.split()) for w in warn],
        # 항목 목록도 함께 싣는다. 조간 브리핑이 머리에 '오늘 볼 것' 한 줄을
        # 넣는데, 그 재료가 여기다. 페이지 HTML 을 긁게 하면 화면을 손볼
        # 때마다 그쪽이 깨지므로, 기계가 읽을 자리를 따로 둔다.
        #
        # 날짜·누가·무엇·굵게 표시 여부만 담는다. 주소는 넣지 않는다 —
        # 브리핑은 제목만 쓰고, 자세한 것은 일정 페이지 링크가 맡는다.
        "items": [{"d": e["date"], "who": e["who"], "what": e["what"],
                   "kind": e["kind"], "major": bool(e.get("major"))}
                  for e in sorted(events, key=lambda x: (x["date"],
                                                         not x.get("major")))],
    }
    return json.dumps(ops, ensure_ascii=False).replace("<", "\\u003c")


def main() -> int:
    ap = argparse.ArgumentParser(description="향후 1개월 주요 일정 페이지")
    ap.add_argument("--check", action="store_true",
                    help="쓰지 않고 만들어만 본다")
    ap.add_argument("--date", help="기준일을 바꿔 본다 (YYYY-MM-DD)")
    args = ap.parse_args()

    today = (datetime.date.fromisoformat(args.date) if args.date
             else datetime.date.today())
    page = build(today)
    if args.check:
        log("--check: 파일을 쓰지 않았다.")
        return 0
    OUTPUT.write_text(page, encoding="utf-8")
    log(f"index.html 갱신 — {len(page):,}자")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
