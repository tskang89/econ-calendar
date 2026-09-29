# -*- coding: utf-8 -*-
"""유로지역 밖 중앙은행의 통화정책 결정일 — 손으로 적어 둔 표.

왜 긁어 오지 않는가. 네 곳 모두 자동 수집이 막혀 있다(2026-09-29 확인).

  폴란드 NBP   봇 차단(Imperva). 사람이 브라우저로 열어야 내용이 보인다.
  체코 ČNB     일정 페이지가 자바스크립트로 그려진다. 받아 온 문서에는
               날짜가 한 줄도 없다.
  스위스 SNB   데이터 포털이 단일 페이지 앱이고, 공개 API 에 캘린더 표가
               없다.
  튀르키예 TCMB 일정 페이지가 리디렉션으로 막힌다.

대신 손으로 적는다. 정책 결정일은 한 해에 한 번 공표되고 좀처럼 바뀌지
않으므로, 네 나라 페이지를 날마다 긁는 것보다 이쪽이 오히려 덜 깨진다.

규칙 하나 — **공식 출처에서 확인한 날짜만 적는다.** 월례라서 그럴 것 같다는
식으로 채우지 않는다. 비어 있으면 화면에 "공식 일정 확인" 링크만 뜬다.
"""

from __future__ import annotations

import datetime

# 확인이 임박했음을 알릴 기준. 남은 일정이 이 날 수 안쪽이면 빌드가 경고한다.
WARN_DAYS = 75

BANKS = {
    "PL": {
        "name": "폴란드", "bank": "NBP", "rate": "기준금리",
        "url": ("https://nbp.pl/en/monetary-policy/monetary-policy-council/"
                "schedule-of-mpc-meetings/"),
        "checked": "2026-09-29",
        # NBP 는 이틀에 걸쳐 회의하고 **둘째 날** 결정을 낸다. 공식 일정표는
        # "13-14" 처럼 두 날을 함께 적는데, 여기 적는 것은 결정이 나오는
        # 둘째 날이다.
        #
        # 봇 차단(Imperva)이라 코드가 직접 읽지 못한다. 사용자가 공식
        # 일정표를 열어 옮겨 준 값이다(2026-09-29).
        #
        # 8월(25일)만 하루짜리이고 원문에 별표가 붙어 있었는데 그 각주 내용은
        # 받지 못했다. 이미 지난 날이라 화면에는 나오지 않는다. 2027년 표를
        # 채울 때 8월 처리를 다시 확인할 것.
        "dates": ["2026-01-14", "2026-02-04", "2026-03-04", "2026-04-09",
                  "2026-05-06", "2026-06-02", "2026-07-08", "2026-08-25",
                  "2026-09-09", "2026-10-07", "2026-11-04", "2026-12-02"],
    },
    "CZ": {
        "name": "체코", "bank": "ČNB", "rate": "2주 레포금리",
        "url": "https://www.cnb.cz/en/cnb-news/calendar/",
        "source": ("https://www.cnb.cz/en/cnb-news/news/"
                   "Dates-of-the-CNB-Boards-meetings-in-2026"),
        "checked": "2026-09-29",
        # 공식 공지 "Dates of the CNB Board's meetings in 2026".
        "dates": ["2026-02-05", "2026-03-19", "2026-05-07", "2026-06-18",
                  "2026-08-06", "2026-09-17", "2026-11-05", "2026-12-17"],
    },
    "CH": {
        "name": "스위스", "bank": "SNB", "rate": "정책금리",
        "url": ("https://www.snb.ch/en/the-snb/mandates-goals/"
                "monetary-policy/decisions"),
        "checked": "2026-09-29",
        # SNB 는 3·6·9·12월에 정례 정책평가를 한다. 공식 페이지에 실린 것만
        # 적었다 — 12월 날짜는 아직 그 페이지에 없었다.
        "dates": ["2026-03-19", "2026-06-18", "2026-09-24"],
    },
    "TR": {
        "name": "튀르키예", "bank": "TCMB", "rate": "1주 레포금리",
        "url": ("https://www.tcmb.gov.tr/wps/wcm/connect/en/tcmb+en/"
                "main+menu/core+functions/monetary+policy/"
                "monetary+policy+committee"),
        "checked": "2026-09-29",
        # 공식 2026 페이지의 회의일(요약 공개일은 대개 일주일 뒤라 뺐다).
        "dates": ["2026-01-22", "2026-03-12", "2026-04-22", "2026-06-11",
                  "2026-07-23", "2026-09-10", "2026-10-22", "2026-12-10"],
    },
}


def upcoming(start: datetime.date, end: datetime.date) -> list[dict]:
    """[start, end] 구간에 걸리는 결정일."""
    out = []
    for code, bank in BANKS.items():
        for d in bank["dates"]:
            day = datetime.date.fromisoformat(d)
            if start <= day <= end:
                out.append({
                    "date": d, "kind": "policy", "area": code,
                    "who": f"{bank['name']} {bank['bank']}",
                    "what": f"통화정책 결정 ({bank['rate']})",
                    "url": bank["url"],
                })
    return out


def health(today: datetime.date) -> list[str]:
    """표가 말라 가는 곳을 알린다. 빌드 로그에 그대로 찍는다."""
    msgs = []
    for bank in BANKS.values():
        left = [d for d in bank["dates"]
                if datetime.date.fromisoformat(d) >= today]
        tag = f"{bank['name']} {bank['bank']}"
        if not bank["dates"]:
            msgs.append(f"  [빈 칸] {tag} — 공식 일정을 확인해 채워야 한다: "
                        f"{bank['url']}")
        elif not left:
            msgs.append(f"  [만료] {tag} — 남은 일정이 없다. {bank['url']}")
        elif (datetime.date.fromisoformat(left[-1]) - today).days < WARN_DAYS:
            msgs.append(f"  [곧 만료] {tag} — 마지막 일정이 {left[-1]} 이다. "
                        f"다음 해 일정을 채워야 한다. {bank['url']}")
    return msgs
