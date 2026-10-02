# -*- coding: utf-8 -*-
"""유로지역 밖 중앙은행의 통화정책 결정일 — 손으로 적어 둔 표.

왜 긁어 오지 않는가 (2026-10-02 다시 확인).

  폴란드 NBP   봇 차단(Imperva). 사람이 브라우저로 열어야 내용이 보인다.
  체코 ČNB     일정 페이지가 자바스크립트로 그려진다. 받아 온 문서에는
               날짜가 한 줄도 없다.
  스위스 SNB   **막혀 있지 않다.** 처음에 데이터 포털(단일 페이지 앱)만
               보고 불가라 적었는데, 공보 일정표는 서버가 다 그려 보내고
               코드로도 그냥 열린다. 줄 꼴이 한결같아 자동 수집이 된다.
  튀르키예 TCMB 통화정책위원회 소개 쪽은 리디렉션으로 막히지만, 공보
               일정표(announcements/calendar)는 표째로 열린다. 이쪽도
               자동 수집이 될 자리다.

그래도 지금은 넷 다 손으로 적는다. 정책 결정일은 한 해에 한 번 공표되고
좀처럼 바뀌지 않아, 날마다 긁는 것보다 이쪽이 덜 깨진다. 스위스·튀르키예를
자동으로 돌리려면 받아 오기가 실패했을 때 이 표로 떨어지게 해 두어야 한다.

규칙 하나 — **공식 출처에서 확인한 날짜만 적는다.** 월례라서 그럴 것 같다는
식으로 채우지 않는다. 비어 있으면 화면에 "공식 일정 확인" 링크만 뜬다.
"""

from __future__ import annotations

import datetime

# 확인이 임박했음을 알릴 기준. 남은 일정이 이 날 수 안쪽이면 빌드가 경고한다.
WARN_DAYS = 75

# 공식 일정표에서 날마다 받아 오는 나라(schedule 의 snb_events·tcmb_events·
# cnb_events). 여기 표는 받아 오기가 실패했을 때 떨어질 자리다. 그래서 아래
# 건강 검사가 다 지나기 전까지는 재촉하지 않는다.
#
# 손이 필요한 곳은 **폴란드 하나**다. 2026-10-02 에 다시 다그쳐 보았으나
# requests·curl 모두 Imperva 벽에서 돌아섰고(차단 안내 쪽이 온다),
# WordPress API 는 403, 다른 호스트에도 일정이 없다. 브라우저로 열면 보이니
# 사람이 한 해에 한 번 옮겨 적는다.
AUTO = {"CH", "TR", "CZ"}

BANKS = {
    "PL": {
        "name": "폴란드", "bank": "NBP", "rate": "기준금리",
        "url": ("https://nbp.pl/en/monetary-policy/monetary-policy-council/"
                "schedule-of-mpc-meetings/"),
        "checked": "2026-10-02",
        # NBP 는 이틀에 걸쳐 회의하고 **둘째 날** 결정을 낸다. 공식 일정표는
        # "13-14" 처럼 두 날을 함께 적는데, 여기 적는 것은 결정이 나오는
        # 둘째 날이다.
        #
        # 봇 차단(Imperva)이라 코드가 직접 읽지 못한다("Pardon Our
        # Interruption" 쪽이 돌아온다, 2026-10-02 재확인). 브라우저로 열면
        # 보이므로 그렇게 옮겨 적는다.
        #
        # 8월 25일은 뺐다. 원문 별표의 각주가 "one-day non-decision-making
        # meeting" — 결정을 내리지 않는 하루짜리 회의다. 통화정책 결정일로
        # 실을 것이 아니다. 2027년 표에서도 별표 붙은 달은 같이 뺀다.
        #
        # 2027년 일정은 2026-10-02 현재 아직 올라오지 않았다(2026년 표만 있다).
        "dates": ["2026-01-14", "2026-02-04", "2026-03-04", "2026-04-09",
                  "2026-05-06", "2026-06-02", "2026-07-08",
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
        "source": ("https://www.snb.ch/en/services-events/digital-services/"
                   "event-schedule"),
        "checked": "2026-10-02",
        # SNB 는 3·6·9·12월 목요일에 정례 정책평가를 한다.
        #
        # 위 '통화정책 결정' 페이지에는 **이미 내린 결정만** 실린다. 그래서
        # 9월 29일에 보았을 때 12월 날짜가 없었고 표가 9월에서 끊겼다. 앞날
        # 일정은 다른 쪽, 공보 일정표(source)에 있다 — 12월 10일 09:30
        # 보도자료와 10:00 기자회견이 잡혀 있고 2027년 세 번도 함께 있다.
        # 2027년 12월은 아직 올라오지 않았다.
        "dates": ["2026-03-19", "2026-06-18", "2026-09-24", "2026-12-10",
                  "2027-03-18", "2027-06-24", "2027-09-23", "2027-12-16"],
    },
    "TR": {
        "name": "튀르키예", "bank": "TCMB", "rate": "1주 레포금리",
        "url": ("https://www.tcmb.gov.tr/wps/wcm/connect/en/tcmb+en/"
                "main+menu/core+functions/monetary+policy/"
                "monetary+policy+committee"),
        "source": ("https://www.tcmb.gov.tr/wps/wcm/connect/en/tcmb+en/"
                   "main+menu/announcements/calendar"),
        "checked": "2026-10-02",
        # 'Monetary Policy Committee Decision' 칸만 옮겼다. 같은 표의 요약
        # 공개일(대개 일주일 뒤)·인플레이션보고서·금융안정보고서는 뺐다.
        #
        # 위 url(통화정책위원회 소개 쪽)은 리디렉션으로 막히지만, source 로
        # 둔 공보 일정표는 그대로 열린다. TCMB 는 한 해 반치를 미리 깔아 두어
        # 2027년 6월까지 나와 있다.
        "dates": ["2026-01-22", "2026-03-12", "2026-04-22", "2026-06-11",
                  "2026-07-23", "2026-09-10", "2026-10-22", "2026-12-10",
                  "2027-01-21", "2027-03-18", "2027-04-22", "2027-06-10"],
    },
}


def upcoming(start: datetime.date, end: datetime.date,
             skip: set[str] | None = None) -> list[dict]:
    """[start, end] 구간에 걸리는 결정일.

    skip 에 든 나라는 뺀다. schedule.py 가 받아 오기에 성공한 나라를 여기로
    넘긴다 — 같은 결정일이 두 줄로 올라가지 않게 하려는 것이다.
    """
    out = []
    for code, bank in BANKS.items():
        if skip and code in skip:
            continue
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
    for code, bank in BANKS.items():
        left = [d for d in bank["dates"]
                if datetime.date.fromisoformat(d) >= today]
        tag = f"{bank['name']} {bank['bank']}"
        if not bank["dates"]:
            msgs.append(f"  [빈 칸] {tag} — 공식 일정을 확인해 채워야 한다: "
                        f"{bank['url']}")
        elif not left:
            msgs.append(f"  [만료] {tag} — 남은 일정이 없다. {bank['url']}")
        elif code in AUTO:
            # 받아 오는 나라다. 표는 받아 오기가 실패했을 때 떨어질 자리라
            # 다 지나기 전까지는 재촉하지 않는다. 받아 온 것과 표가 어긋나면
            # schedule.py 가 따로 알린다.
            continue
        elif (datetime.date.fromisoformat(left[-1]) - today).days < WARN_DAYS:
            msgs.append(f"  [곧 만료] {tag} — 마지막 일정이 {left[-1]} 이다. "
                        f"다음 해 일정을 채워야 한다. {bank['url']}")
    return msgs
