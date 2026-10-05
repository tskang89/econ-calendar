# -*- coding: utf-8 -*-
"""향후 일주일 일정을 공식 페이지에서 모은다.

처음에는 두 곳(ECB·Destatis)만 받아 왔다. 지금은 열 곳에서 받아 오고,
**폴란드 NBP 하나만** 손으로 적은 표를 쓴다 — Imperva 봇 차단이라 코드로는
어떤 수를 써도 돌아선다(policy_dates.py 에 까닭을 적었다).
받아 오는 곳이라도 실패하면 그 나라는 표로 떨어진다.

  ECB      이사회·통화정책회의 일정. <dt>날짜</dt><dd>설명</dd> 짜임이라
           그대로 읽힌다.
  Destatis 독일 지표 발표일정. 결과 한 덩어리가 c-result 블록이고 그 안에
           제목·기준기간·발표일이 들어 있다.

유로지역 지표(HICP·GDP) 발표일은 넣지 못했다. Eurostat 의 release calendar
페이지가 자바스크립트로 그려지고, 공개 API 에 캘린더 경로가 없다. 독일
소비자물가가 유로지역 속보치보다 대개 하루 앞서므로 Destatis 쪽으로 어느
정도는 가늠할 수 있다.
"""

from __future__ import annotations

import datetime
import html
import json
import pathlib
import re
import time

import requests

ECB_URL = "https://www.ecb.europa.eu/press/calendars/mgcgc/html/index.en.html"
DESTATIS_URL = ("https://www.destatis.de/SiteGlobals/Forms/Suche/Termine/"
                "DE/Terminsuche_Formular.html?nn=250582")
EUROSTAT_PAGE = "https://ec.europa.eu/eurostat/news/release-calendar"
EUROSTAT_JSON = "https://ec.europa.eu/eurostat/o/calendars/eventsJson"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
TIMEOUT = 40

# 재시도를 네 번, 간격도 늘렸다(3·6·9초, 모두 합쳐 18초).
#
# 2026-10-02 에 한국은행이 502 를 한 번 돌려주었다. 그날 네 번 돈 빌드 가운데
# 한 번만 그랬고 나머지는 멀쩡했다 — 몇 초짜리 장애였는데 2·4·6초로는 넘기지
# 못했다. 하필 그 판이 배포돼 '한국은행 일정을 받지 못했다'가 화면에 떴다.
#
# 빌드는 하루 한 번 30초쯤 도는 것이라 몇십 초 더 기다리는 것은 값이 싸다.
# 반대로 한 번 실패하면 그 일정이 하루 내내 빠진 채로 걸려 있다.
RETRIES = 4


class ScheduleError(RuntimeError):
    pass


class CachedSchedule(Exception):
    """받지는 못했지만 저장해 둔 것이 있다. 일정과 받은 날을 함께 들고 간다."""

    def __init__(self, events: list[dict], fetched: str | None, why: str):
        super().__init__(why)
        self.events = events
        self.fetched = fetched
        self.why = why


def _get(url: str, tries: int = RETRIES) -> str:
    """tries 를 1 로 주면 한 번만 본다. 없을 수도 있는 쪽(내년 공지처럼
    404 가 정상인 주소)에 30초를 쓰지 않으려는 것이다."""
    last = None
    for attempt in range(tries):
        try:
            resp = requests.get(url, timeout=TIMEOUT,
                                headers={"User-Agent": UA})
        except requests.RequestException as exc:
            last = exc
        else:
            if resp.status_code == 200:
                resp.encoding = resp.apparent_encoding or resp.encoding
                return resp.text
            last = f"HTTP {resp.status_code}"
        if attempt + 1 < tries:          # 마지막 판 뒤에는 쉴 까닭이 없다
            time.sleep(3 * (attempt + 1))
    raise ScheduleError(f"{url.split('/')[2]}: {last}")


# ------------------------------------------------------------------ ECB
# 통화정책과 관계없는 회의도 한 목록에 섞여 있다. 무엇이 금리 결정인지
# 구분해 표시해야 하므로 설명 문구로 가른다.
# 'non-monetary policy meeting' 이 'monetary policy meeting' 을 품고 있다.
# 앞에 non- 이 붙지 않은 것만 골라야 한다 — 그러지 않으면 통화정책과
# 무관한 이사회가 '금리 결정일'로 올라간다.
_ECB_POLICY = re.compile(r"(?<!non-)monetary policy meeting", re.I)
_ECB_PRESSER = re.compile(r"press conference", re.I)


def ecb_events() -> list[dict]:
    doc = _get(ECB_URL)
    pairs = re.findall(r"<dt>\s*(\d{2}/\d{2}/\d{4})\s*</dt>\s*"
                       r"<dd>\s*(.*?)\s*</dd>", doc, re.S)
    if not pairs:
        raise ScheduleError("ECB: <dt>/<dd> 짜임이 바뀌었다 — 하나도 못 읽었다")
    out = []
    for raw, desc in pairs:
        d, m, y = raw.split("/")
        text = html.unescape(re.sub(r"<[^>]+>", " ", desc))
        text = re.sub(r"\s+", " ", text).strip()
        out.append({
            "date": f"{y}-{m}-{d}",
            "kind": "policy" if _ECB_POLICY.search(text) else "meeting",
            "area": "EZ",
            "who": "ECB",
            "what": _ecb_ko(text),
            "url": ECB_URL,
        })
    return out


def _ecb_ko(text: str) -> str:
    """ECB 일정 문구를 우리말로. 못 알아본 것은 원문 그대로 둔다."""
    if _ECB_POLICY.search(text):
        base = "통화정책회의"
        if _ECB_PRESSER.search(text):
            return base + " 결정·기자회견 (둘째 날)"
        if re.search(r"day 1", text, re.I):
            return base + " (첫째 날)"
        return base
    if re.search(r"non-monetary policy meeting", text, re.I):
        return "이사회 (통화정책 외)"
    if re.search(r"General Council", text, re.I):
        return "일반이사회"
    return text


# ------------------------------------------------------------------ Destatis
_BLOCK = re.compile(r'<div\s+class="c-result c-result--event-preview.*?'
                    r'(?=<div\s+class="c-result c-result--event-preview|</body)',
                    re.S)
_HEAD = re.compile(r'class="c-result__heading">(.*?)</h3>', re.S)
_PERIOD = re.compile(r"<strong>Berichtzeitraum</strong>\s*:\s*([^<]+)")
_DAY = re.compile(r"<strong>Ver\w*ffentlichungstermin</strong>\s*:\s*"
                  r"(\d{2})\.(\d{2})\.(\d{4})")

# 브리핑을 받는 사람이 관심 둘 만한 것만 고른다. 독일 통계청은 하루에도
# 여러 건을 내는데, 지역 통계나 행정 자료까지 실으면 일정표가 길어져
# 정작 중요한 것이 묻힌다.
_KEEP = re.compile(
    r"Verbraucherpreis|Erzeugerpreis|Gro\w*handelspreis|Au\w*enhandel|"
    r"Inlandsprodukt|Bruttoinlandsprodukt|Arbeitsmarkt|Erwerbst|"
    # 'Produktionsindex' 를 넣지 않아 독일 산업생산이 통째로 빠져 있었다
    # (2026-10-05). Destatis 가 제목을 줄였고, 거르는 쪽과 옮기는 쪽 **둘 다**
    # 고쳐야 했는데 옮기는 쪽만 보고 있었다. 이름이 바뀌면 지표가 조용히
    # 사라진다 — 번역이 새는 것보다 이쪽이 나쁘다.
    r"Produktionsindex|Industrieproduktion|Produktion im Produzierenden|"
    r"Auftragseingang|"
    r"Einzelhandel|Umsatz im|Baugenehmigung|Import|Export|"
    r"Verarbeitendes Gewerbe|Dienstleistungen|"
    # 2026-10-05 에 더했다. 임금·노동비용은 ECB 가 물가를 볼 때 가장 눈여겨
    # 보는 것이고, 기업도산과 주거용 부동산 가격도 경기·물가 쪽에 걸린다.
    # 'Lohn' 만으로 잡으면 임금세(Lohnsteuer) 같은 것까지 걸리므로 지수
    # 이름을 그대로 적는다.
    r"Nominallohn|Reallohn|Tarifindex|Arbeitskostenindex|Verdienste|"
    r"Insolvenz|Wohnimmobilien|Baupreise", re.I)


# 독일 통계청 제목을 우리말로. 자주 나오는 것만 옮기고, 없으면 원문을
# 그대로 둔다 — 빠뜨리는 것보다 독일어로라도 보이는 편이 낫다.
_DE_KO = [
    (r"Verbraucherpreisindex", "소비자물가지수"),
    (r"Erzeugerpreise?", "생산자물가"),
    (r"Gro\w*handelspreise?", "도매물가"),
    (r"Index der Au\w*enhandelspreise", "수출입물가지수"),
    (r"Au\w*enhandel", "대외교역"),
    (r"Bruttoinlandsprodukt|Inlandsprodukt", "국내총생산"),
    (r"Monatliche Arbeitsmarktstatistik", "월간 고용통계"),
    (r"Arbeitsmarkt", "고용"),
    # Destatis 가 제목을 'Produktion im Produzierenden Gewerbe' 에서 그냥
    # 'Produktionsindex' 로 줄였다(2026-10-05 확인). 대응표에 없어 10월 7일
    # 발표가 독일어 그대로 화면에 나갔다.
    #
    # 머리에 붙은 것만 잡는다. 'Produktionsindex Bauhauptgewerbe' 같은
    # 변종이 나오면 산업생산으로 잘못 적는 것보다 독일어로 남겨 두는 것이
    # 낫다 — 아래 untranslated() 가 그것을 알려 준다.
    (r"^Produktionsindex|Produktion im Produzierenden Gewerbe|"
     r"Industrieproduktion", "산업생산"),
    (r"Verarbeitendes Gewerbe\s*—\s*Auftragseingangs- und Umsatzindex",
     "제조업 수주·매출"),
    (r"Auftragseingang", "제조업 수주"),
    (r"Einzelhandel\s*—\s*Umsatz", "소매판매"),
    (r"Dienstleistungen\s*—\s*Umsatz, Besch\w*ftigte", "서비스업 매출·고용"),
    (r"Baugenehmigungen?", "건축허가"),
    (r"Nominallohn-?/?Reallohnindex|Nominallohn|Reallohn", "명목·실질임금지수"),
    (r"Tarifindex|Tarifverdienste", "협약임금지수"),
    (r"Arbeitskostenindex", "노동비용지수"),
    (r"Verdienste und Arbeitskosten|Verdienste", "임금·노동비용"),
    (r"Insolvenzen", "기업도산"),
    (r"Preisindizes f\w*r Wohnimmobilien|Wohnimmobilien", "주거용 부동산 가격"),
    (r"Baupreise f\w*r Wohngeb\w*ude|Baupreise", "건축비"),
    (r"Verarbeitendes Gewerbe.*Besch\w*ftigte", "제조업 고용"),
    (r"Auftragsbestand", "제조업 수주잔고"),
    (r"Verarbeitendes Gewerbe", "제조업"),
]
_MONTH_KO = {"Januar": 1, "Februar": 2, "März": 3, "Maerz": 3, "April": 4,
             "Mai": 5, "Juni": 6, "Juli": 7, "August": 8, "September": 9,
             "Oktober": 10, "November": 11, "Dezember": 12}


def _de_title(title: str) -> str:
    for pat, ko in _DE_KO:
        if re.search(pat, title, re.I):
            extra = re.search(r"Vorl\w*ufige|Endg\w*ltige", title, re.I)
            tag = ""
            if extra:
                tag = " 속보치" if extra.group(0).lower().startswith("vorl") \
                    else " 확정치"
            return ko + tag
    return title


def _de_period(text: str) -> str:
    """'August 2026' -> '2026년 8월'. 분기·반기는 그대로 옮긴다."""
    text = text.strip()
    m = re.match(r"(\w+)\s+(\d{4})$", text)
    if m and m.group(1) in _MONTH_KO:
        return f"{m.group(2)}년 {_MONTH_KO[m.group(1)]}월"
    m = re.match(r"(\d)\.\s*Quartal\s+(\d{4})", text)
    if m:
        return f"{m.group(2)}년 {m.group(1)}분기"
    m = re.match(r"(\d)\.\s*Halbjahr\s+(\d{4})", text)
    if m:
        return f"{m.group(2)}년 상반기" if m.group(1) == "1" \
            else f"{m.group(2)}년 하반기"
    return text


# 받아 둔 Destatis 일정. GitHub 러너에서 못 받을 때 쓴다.
#
# destatis.de 가 Azure IP 를 통째로 막는다(2026-10-02 확인). 요청 모양을 여섯
# 가지로 바꿔 봐도 전부 nginx 기본 403 이고, 같은 주소가 프랑크푸르트 사무소
# 회선에서는 200 이다. 헤더로 풀 수 있는 문제가 아니다.
#
# 그래서 받히는 곳에서 받아 저장소에 넣어 두고, 러너는 그것을 쓴다. 발표
# 일정은 몇 달 앞서 공표되고 좀처럼 바뀌지 않으므로 묵은 것이어도 쓸 만하다.
# 다만 언제 받은 것인지는 화면에 밝힌다 — 묵은 자료를 오늘 것처럼 보이게
# 하면 안 된다.
CACHE = pathlib.Path(__file__).resolve().parent.parent / "data" / "destatis.json"


# 저장분이 이만큼 남지 않으면 알린다. 사무소에서 손으로 채워야 하므로
# 넉넉히 앞서 말해야 한다 — 두 달이면 깜빡해도 한 번은 더 눈에 띈다.
CACHE_WARN_DAYS = 60


def cache_health(today: datetime.date) -> list[str]:
    """저장분이 말라 가는지 본다.

    주간 자체 점검이 보는 것은 일정표 전체의 마지막 날짜인데, 그 자리는
    일본은행 2027년 일정 같은 것이 채우고 있어 Destatis 저장분이 바닥나도
    드러나지 않는다. 그래서 따로 센다.
    """
    events, fetched = _cache_read()
    if not events:
        return [f"  [빈 칸] Destatis 저장분이 없다 — 사무소에서 "
                f"build/make.py 를 한 번 돌려야 한다. {DESTATIS_URL}"]
    last = max(e["date"] for e in events)
    left = (datetime.date.fromisoformat(last) - today).days
    if left < 0:
        return [f"  [만료] Destatis 저장분이 {last} 에서 끝났다 — 독일 통계청"
                f" 일정이 통째로 빠진다. 사무소에서 build/make.py 를 돌릴 것."]
    if left < CACHE_WARN_DAYS:
        return [f"  [곧 만료] Destatis 저장분이 {last} 까지다({left}일 남음)"
                f" — 사무소에서 build/make.py 를 돌려 채울 것."]
    return []


def _cache_read() -> tuple[list[dict], str | None]:
    """(일정, 받은 날). 파일이 없거나 깨졌으면 ([], None)."""
    try:
        doc = json.loads(CACHE.read_text(encoding="utf-8"))
        return doc.get("events") or [], doc.get("fetched")
    except (OSError, ValueError):
        return [], None


def _cache_write(events: list[dict], today: datetime.date) -> None:
    """받은 것을 저장해 둔 것과 합쳐 쓴다.

    덮어쓰면 안 된다. 평소 빌드는 한 달 치만 받으므로, 한 번 넉넉히 받아
    둔 다섯 달치가 다음 성공 때 한 달치로 줄어든다. 러너가 몇 주씩 이것에
    기대는 구조라 그 축소가 그대로 구멍이 된다.

    지난 일정은 버린다. 쌓아 두면 파일만 커지고 쓸 데가 없다.

    **합치는 열쇠는 날짜다.** 받아 온 것에 들어 있는 날은 그 날의 옛 줄을
    통째로 버리고 새것으로 갈아 치운다. 날짜+제목을 열쇠로 쓰다가
    2026-10-05 에 탈이 났다 — Destatis 가 제목을 바꾸고 내가 대응표를
    고치자 'Produktionsindex · 8월' 과 '산업생산 · 8월' 이 같은 날에 두 줄로
    남았다. 제목은 화면에 보이는 꼴이라 열쇠가 될 수 없다. 이름이 바뀌든
    발표가 취소되든 날짜째로 갈면 함께 잡힌다.

    받아 오지 못한 날은 저장분을 그대로 둔다. 그래서 한 달치만 받는 평소
    빌드가 다섯 달치를 깎지 않는다. 다만 받아 온 구간 안에서 발표가 아예
    없어진 날은 그 날이 지나갈 때까지 저장분에 남는다 — 그 날을 받아 온
    목록에서 알아볼 길이 없다.
    """
    old, _ = _cache_read()
    fresh_days = {e["date"] for e in events}
    keep = [e for e in old
            if e["date"] >= today.isoformat() and e["date"] not in fresh_days]
    keep += [e for e in events if e["date"] >= today.isoformat()]
    keep.sort(key=lambda e: (e["date"], e["what"]))
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(
        {"fetched": today.isoformat(), "events": keep},
        ensure_ascii=False, indent=1), encoding="utf-8")


def destatis_events(keep_all: bool = False, until: str | None = None,
                    max_pages: int = 6) -> list[dict]:
    """독일 통계청 발표일정.

    한 쪽에 여남은 건뿐이라 이레 치는 첫 쪽으로 됐지만 한 달 치는 모자란다.
    쪽을 넘겨 가며 받되, 받은 날짜가 찾는 구간을 넘어서면 멈춘다. 끝까지
    긁을 이유가 없다.

    받히지 않으면 저장해 둔 것을 쓴다. 그때는 ScheduleError 를 내지 않고
    대신 언제 받은 것인지를 호출한 쪽이 알 수 있게 한다 — 일정이 통째로
    빠지는 것보다 며칠 묵은 것이 낫다.
    """
    out: list[dict] = []
    try:
        for page in range(1, max_pages + 1):
            url = DESTATIS_URL + (f"&gtp=245710_list%253D{page}"
                                  if page > 1 else "")
            got = _destatis_page(_get(url), keep_all)
            if not got:
                break
            out += got
            if until and max(e["date"] for e in got) > until:
                break
    except ScheduleError as exc:
        cached, when = _cache_read()
        if not cached:
            raise
        raise CachedSchedule(cached, when, str(exc)) from exc

    if not out:
        cached, when = _cache_read()
        if cached:
            raise CachedSchedule(cached, when, "c-result 블록을 하나도 못 읽었다")
        raise ScheduleError("Destatis: c-result 블록을 하나도 못 읽었다")

    # 받혔으면 저장해 둔다. 러너에서는 늘 막히므로 이 갱신은 사무소에서
    # 손으로 돌릴 때만 일어난다.
    #
    # **저장분에는 걸러내기를 통과한 것만 넣는다.** keep_all 로 받은 것을
    # 그대로 저장하다가 2026-10-05 에 'Baupreise für Wohngebäude' 같은
    # 지역·부문 통계가 저장분에 섞여 공개 페이지에 떴다. keep_all 은 손으로
    # 들여다볼 때 쓰는 뒷문이고, 뒷문으로 본 것이 집에 남으면 안 된다.
    bare = lambda e: {k: v for k, v in e.items() if k != "keep"}
    _cache_write([bare(e) for e in out if e.get("keep", True)],
                 datetime.date.today())
    return [bare(e) for e in out]


def _destatis_page(doc: str, keep_all: bool) -> list[dict]:
    blocks = _BLOCK.findall(doc)
    out = []
    for block in blocks:
        head, day = _HEAD.search(block), _DAY.search(block)
        if not head or not day:
            continue
        title = html.unescape(re.sub(r"<[^>]+>", " ", head.group(1)))
        title = re.sub(r"\s+", " ", title).replace(" — ", " — ").strip()
        keep = bool(_KEEP.search(title))
        if not keep_all and not keep:
            continue
        period = _PERIOD.search(block)
        d, m, y = day.groups()
        what = _de_title(title)
        if period:
            what += f" · {_de_period(html.unescape(period.group(1)))}"
        out.append({
            "date": f"{y}-{m}-{d}",
            "kind": "release",
            "area": "DE",
            "who": "독일 통계청",
            "what": what,
            "url": DESTATIS_URL,
            # 걸러내기를 통과했는지. keep_all 로 받을 때도 이 표를 들고
            # 가야 저장분에는 통과한 것만 넣을 수 있다. 원문 제목은 여기서
            # 버려지므로 나중에 다시 가릴 수가 없다.
            "keep": keep,
        })
    return out


# ------------------------------------------------------------------ Eurostat
# 일정표 페이지는 FullCalendar 로 그려져 문서만 받아서는 날짜가 한 줄도 없다.
# 그 달력이 값을 받아 오는 종점이 아래 주소다. FullCalendar 가 보내는 꼴
# 그대로 start·end 를 ISO 시각(시간대 포함)으로 주고 timeZone 을 붙여야
# 한다 — 'YYYY-MM-DD' 만 주면 200 에 빈 본문이 온다.
#
# isEuroindicator=true 로 좁힌다. 유로지역 주요 지표(물가 속보치·실업률·
# GDP·소매판매 …)만 남아, 브리핑을 받는 사람이 볼 목록이 된다. 이것을 빼면
# 'Statistics Explained' 같은 해설 글까지 섞여 하루에 수십 건이 된다.
_ES_KO = [
    (r"Flash estimate inflation", "유로지역 물가 속보치"),
    (r"^Inflation|HICP", "유로지역 소비자물가"),
    (r"Preliminary flash estimate.*GDP|GDP.*flash", "유로지역 GDP 속보치"),
    (r"\bGDP\b|National accounts", "유로지역 국민계정"),
    (r"Unemployment", "유로지역 실업률"),
    (r"Industrial pro(duction|ducer prices), domestic", "생산자물가(내수)"),
    (r"Industrial production", "산업생산"),
    (r"Industrial producer prices", "생산자물가"),
    (r"Industrial import prices", "수입물가"),
    (r"Services producer prices", "서비스 생산자물가"),
    (r"Services production", "서비스업 생산"),
    (r"Retail trade", "소매판매"),
    (r"Balance of payments", "국제수지"),
    (r"International trade in goods", "상품교역"),
    (r"House price index", "주택가격지수"),
    (r"Building permits", "건축허가"),
    (r"Economic Sentiment Indicator", "경제심리지수(ESI)"),
    (r"sector accounts", "부문별 계정"),
    (r"Labour cost", "노동비용지수"),
    (r"Job vacancy", "빈일자리율"),
    (r"Government (deficit|debt)", "재정수지·정부부채"),
    (r"Interest rates \(3 months\)|Short[- ]term interest", "단기금리(3개월)"),
    # 'gvt' 로만 적어 두어 'Long-term government bond yield' 를 놓쳤다.
    # 2026-10-05 에 새로 넣은 번역 점검이 잡아 준 것이다.
    (r"Long[- ]term (gvt|government) bond yield|Long[- ]term interest",
     "장기 국채금리"),
    (r"Production in construction", "건설생산"),
    (r"Volume of sales|Turnover", "매출"),
    (r"Tourism", "관광"),
    (r"Energy", "에너지"),
]
_ES_PERIOD = re.compile(r"^(\w+)\s+(\d{4})$")
_ES_QUARTER = re.compile(r"^Q(\d)/(\d{4})$")
_ES_MONTH = {"January": 1, "February": 2, "March": 3, "April": 4, "May": 5,
             "June": 6, "July": 7, "August": 8, "September": 9,
             "October": 10, "November": 11, "December": 12}


def _es_title(title: str) -> str:
    for pat, ko in _ES_KO:
        if re.search(pat, title, re.I):
            return ko
    return title


def _es_period(text: str) -> str:
    text = (text or "").strip()
    # 'June 2026 - Q2/2026' 처럼 두 기준을 함께 내는 지표가 있다. 토막마다
    # 따로 옮긴다.
    if " - " in text:
        return " · ".join(_es_period(part) for part in text.split(" - "))
    m = _ES_PERIOD.match(text)
    if m and m.group(1) in _ES_MONTH:
        return f"{m.group(2)}년 {_ES_MONTH[m.group(1)]}월"
    m = _ES_QUARTER.match(text)
    if m:
        return f"{m.group(2)}년 {m.group(1)}분기"
    return text


def eurostat_events(start: datetime.date, end: datetime.date) -> list[dict]:
    # 끝 날짜는 여유를 둔다. FullCalendar 는 구간 밖을 잘라 내므로 하루를
    # 더 얹어야 마지막 날이 빠지지 않는다.
    params = {
        "start": f"{start.isoformat()}T00:00:00+01:00",
        "end": f"{(end + datetime.timedelta(days=1)).isoformat()}T00:00:00+01:00",
        "timeZone": "Europe/Brussels",
        "theme": "", "category": "", "keywords": "",
        "isEuroindicator": "true",
        "authorInclude": "", "authorExclude": "",
    }
    try:
        resp = requests.get(EUROSTAT_JSON, params=params, timeout=TIMEOUT,
                            headers={"User-Agent": UA,
                                     "Accept": "application/json"})
    except requests.RequestException as exc:
        raise ScheduleError(f"Eurostat: {exc}") from exc
    if resp.status_code != 200 or not resp.text.strip():
        raise ScheduleError(
            f"Eurostat: HTTP {resp.status_code}, 본문 {len(resp.text)}자 "
            f"— 종점이나 인자 꼴이 바뀌었을 수 있다")
    rows = resp.json()

    out = []
    for row in rows:
        if not row.get("euroind"):
            continue
        day = (row.get("start") or "")[:10]
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
            continue
        what = _es_title((row.get("title") or "").strip())
        period = _es_period(row.get("period"))
        if period:
            what += f" · {period}"
        if row.get("preliminary"):
            what += " (잠정 일정)"
        out.append({
            "date": day, "kind": "release", "area": "EZ",
            "who": "Eurostat", "what": what, "url": EUROSTAT_PAGE,
        })
    return out


# ------------------------------------------------------------------ 연준
FED_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"

_FED_YEAR = re.compile(r"(\d{4}) FOMC Meetings")
_FED_ROW = re.compile(r"fomc-meeting__month[^>]*><strong>([^<]+)</strong>"
                      r".*?fomc-meeting__date[^>]*>([^<]+)<", re.S)
_FED_MON = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
            "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}


def fed_events() -> list[dict]:
    """FOMC 회의. 결정과 성명은 **둘째 날** 나온다.

    연준 표는 달과 날짜를 따로 적는다. 달을 걸치는 회의는 'Oct/Nov' 에
    '31-1' 처럼 적히는데, 이때 결정일은 뒤쪽 달의 1일이다. 앞 달을 그대로
    쓰면 10월 1일이 되어 한 달을 통째로 어긋난다.

    연도별 묶음이 문서 안에서 연도순으로 놓여 있지 않다(2026 다음이 2025 이고
    2027 은 맨 뒤다). 그래서 묶음 제목의 위치로 구간을 갈라 회의를 붙인다.
    """
    doc = _get(FED_URL)
    marks = sorted((m.start(), int(m.group(1))) for m in _FED_YEAR.finditer(doc))
    if not marks:
        raise ScheduleError("연준: 연도 묶음을 찾지 못했다")

    def year_at(pos: int) -> int | None:
        found = None
        for start, year in marks:
            if start <= pos:
                found = year
            else:
                break
        return found

    out = []
    for m in _FED_ROW.finditer(doc):
        year = year_at(m.start())
        if year is None:
            continue
        months = [_FED_MON.get(p.strip().lower()[:3])
                  for p in m.group(1).split("/")]
        days = re.findall(r"\d+", m.group(2))
        if not months or months[-1] is None or not days:
            continue
        month, day = months[-1], int(days[-1])
        # 'Dec 31-1' 처럼 해를 걸치면 뒤쪽은 다음 해다.
        y = year + 1 if (len(months) > 1 and months[0] == 12 and month == 1) \
            else year
        try:
            date = datetime.date(y, month, day)
        except ValueError:
            continue
        out.append({
            "date": date.isoformat(), "kind": "policy", "area": "US",
            "who": "미국 연준", "what": "FOMC 통화정책 결정 (둘째 날)",
            "url": FED_URL,
        })
    if not out:
        raise ScheduleError("연준: 회의를 하나도 읽지 못했다")
    return out


# ------------------------------------------------------------------ 영란은행
BOE_URL = "https://www.bankofengland.co.uk/monetary-policy/upcoming-mpc-dates"

_BOE_YEAR = re.compile(r"(\d{4})\s+confirmed dates", re.I)
_BOE_DAY = re.compile(
    r"(?:Monday|Tuesday|Wednesday|Thursday|Friday)\s+(\d{1,2})\s+"
    r"(January|February|March|April|May|June|July|August|September|"
    r"October|November|December)", re.I)


def boe_events() -> list[dict]:
    """영란은행 MPC 발표일.

    날짜에 연도가 붙어 있지 않고 '2026 confirmed dates' 같은 제목 아래
    묶여 있다. 제목 위치로 구간을 갈라 연도를 붙인다.
    """
    text = html.unescape(re.sub(r"<[^>]+>", "\n", _get(BOE_URL)))
    marks = sorted((m.start(), int(m.group(1)))
                   for m in _BOE_YEAR.finditer(text))
    if not marks:
        raise ScheduleError("영란은행: 연도 제목을 찾지 못했다")

    out = []
    for m in _BOE_DAY.finditer(text):
        year = None
        for start, y in marks:
            if start <= m.start():
                year = y
            else:
                break
        if year is None:
            continue
        month = _FED_MON[m.group(2).lower()[:3]]
        try:
            date = datetime.date(year, month, int(m.group(1)))
        except ValueError:
            continue
        out.append({
            "date": date.isoformat(), "kind": "policy", "area": "GB",
            "who": "영란은행", "what": "MPC 통화정책 결정 (정책금리)",
            "url": BOE_URL,
        })
    if not out:
        raise ScheduleError("영란은행: 발표일을 하나도 읽지 못했다")
    # 같은 날이 두 번 잡히는 일이 있다(본문과 관련 링크에 같이 적힌다).
    seen, uniq = set(), []
    for e in out:
        if e["date"] not in seen:
            seen.add(e["date"])
            uniq.append(e)
    return uniq


# ------------------------------------------------------------------ 한국은행
BOK_URL = ("https://www.bok.or.kr/portal/singl/crncyPolicyDrcMtg/listYear.do"
           "?mtgSe=A&menuNo=200755")

_BOK_YEAR = re.compile(r"<h3>(\d{4})년</h3>")
_BOK_DAY = re.compile(r"(\d{2})월\s*(\d{2})일\(")


def bok_events(today: datetime.date | None = None) -> list[dict]:
    """한국은행 금융통화위원회 통화정책방향 결정회의.

    해마다 한 쪽이라 올해와 내년을 따로 받는다. 내년 일정은 연말에야 올라
    오므로 빈 쪽이 오는 것이 정상이다 — 그때는 조용히 건너뛴다.
    """
    today = today or datetime.date.today()
    out = []
    for year in (today.year, today.year + 1):
        doc = _get(f"{BOK_URL}&pYear={year}")
        shown = _BOK_YEAR.search(doc)
        if not shown or int(shown.group(1)) != year:
            continue                     # 엉뚱한 해가 왔다 — 쓰지 않는다
        for m in _BOK_DAY.finditer(doc):
            try:
                date = datetime.date(year, int(m.group(1)), int(m.group(2)))
            except ValueError:
                continue
            out.append({
                "date": date.isoformat(), "kind": "policy", "area": "KR",
                "who": "한국은행", "what": "금통위 통화정책방향 결정",
                "url": BOK_URL,
            })
    if not out:
        raise ScheduleError("한국은행: 회의일을 하나도 읽지 못했다")
    return out


# ------------------------------------------------------------------ 일본은행
BOJ_URL = "https://www.boj.or.jp/en/mopo/mpmsche_minu/index.htm"

# 페이지에 해마다 표가 하나씩 있다(<caption>Table : 2026</caption>). 올해와
# 내년이 함께 올라와 있어 한 번만 받으면 된다.
_BOJ_TABLE = re.compile(r"<table.*?</table>", re.S)
_BOJ_YEAR = re.compile(r"<caption[^>]*>.*?(\d{4}).*?</caption>", re.S)
_BOJ_ROW = re.compile(r"<tr.*?</tr>", re.S)
_BOJ_CELL = re.compile(r"<t[dh].*?</t[dh]>", re.S)

# 'Mar. 18 (Wed.), 19 (Thurs.)' 또는 'Apr. 30 (Thurs.), May 1 (Fri.)'.
# 달이 적힌 조각만 달을 바꾸고, 없으면 앞의 달을 이어 쓴다.
_BOJ_DATE = re.compile(
    r"(?:(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s*)?"
    r"(\d{1,2})\s*\(")
_BOJ_MONTH = {m: i for i, m in enumerate(
    ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
     "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"), 1)}


def boj_events(today: datetime.date | None = None) -> list[dict]:
    """일본은행 금융정책결정회의(MPM).

    회의는 이틀에 걸쳐 열리고 **결정은 둘째 날** 발표된다. 그래서 각 행의
    마지막 날짜를 쓴다. 'Apr. 30, May 1' 처럼 달을 넘기는 회의가 있어,
    둘째 조각에 달이 적혀 있으면 그것을 따른다.

    표가 해마다 하나씩이고 올해·내년이 같은 쪽에 있다. 연말에 내년 표가
    없는 동안에는 올해 것만 잡히는데, 그때는 policy_dates 의 건강 검사가
    '곧 만료'로 알려 준다.
    """
    today = today or datetime.date.today()
    doc = _get(BOJ_URL)
    out = []
    for table in _BOJ_TABLE.findall(doc):
        year = _BOJ_YEAR.search(table)
        if not year:
            continue
        y = int(year.group(1))
        if y < today.year:               # 지난 해 표는 볼 것이 없다
            continue
        for row in _BOJ_ROW.findall(table):
            cells = _BOJ_CELL.findall(row)
            if not cells:
                continue
            text = re.sub(r"<[^>]+>", " ", cells[0])
            hits = _BOJ_DATE.findall(text)
            if not hits:
                continue
            month = None
            day = None
            for mon, dd in hits:         # 마지막 조각이 결정일이다
                if mon:
                    month = _BOJ_MONTH[mon]
                day = int(dd)
            if month is None or day is None:
                continue
            try:
                date = datetime.date(y, month, day)
            except ValueError:
                continue
            out.append({
                "date": date.isoformat(), "kind": "policy", "area": "JP",
                "who": "일본은행", "what": "금융정책결정회의 결과 발표",
                "url": BOJ_URL,
            })
    if not out:
        raise ScheduleError("일본은행: 회의일을 하나도 읽지 못했다")
    return out


# -------------------------------------------------- 스위스 SNB·튀르키예 TCMB
# 이 둘은 policy_dates.py 의 손으로 적은 표에만 있었다. 막혔다고 적어 둔
# 쪽이 엉뚱한 페이지였기 때문이다(2026-10-02) —
#
#   SNB  '통화정책 결정' 페이지에는 **이미 내린 결정만** 실린다. 앞날
#        일정은 공보 일정표에 있고, 서버가 다 그려 보내므로 그냥 열린다.
#   TCMB 통화정책위원회 소개 쪽은 리디렉션으로 막히지만, 공보 일정표는
#        표째로 열린다.
#
# 표는 지우지 않고 **받아 오기가 실패했을 때 떨어질 자리**로 남긴다. 결정일은
# 한 해에 한 번 공표되는 것이라 묵어도 틀리는 일이 드물고, 통화정책 결정일이
# 통째로 빠지는 것이 제일 나쁘다.
#
# 이름·금리 이름·링크는 policy_dates 의 표에서 가져온다. 같은 기관이 받아 온
# 날과 표에서 온 날에 따라 다르게 적히면 안 된다.
SNB_URL = ("https://www.snb.ch/en/services-events/digital-services/"
           "event-schedule")
TCMB_URL = ("https://www.tcmb.gov.tr/wps/wcm/connect/en/tcmb+en/"
            "main+menu/announcements/calendar")

# '10.12.2026 09:30 Monetary policy assessment of 10 December 2026 (press
# release)'. 같은 날에 보도자료와 기자회견 두 줄이 있어 날짜로 추린다.
_SNB_ROW = re.compile(r"(\d{2})\.(\d{2})\.(\d{4})\s+\d{1,2}:\d{2}\s+"
                      r"Monetary policy assessment", re.I)

# TCMB 표는 한 행이 '결정일 | 요약 공개일 | 인플레이션보고서 | 금융안정보고서'
# 다. 첫 칸만 쓴다. 달 이름이 'January' 처럼 통째로 적혀 앞 세 자만 본다.
_TCMB_HEAD = "MONETARY POLICY COMMITTEE MEETING"
_TCMB_DAY = re.compile(r"^([A-Z][a-z]{2})[a-z]*\s+(\d{1,2}),\s*(\d{4})$")


def _bank_event(code: str, date: datetime.date) -> dict:
    import policy_dates
    bank = policy_dates.BANKS[code]
    return {
        "date": date.isoformat(), "kind": "policy", "area": code,
        "who": f"{bank['name']} {bank['bank']}",
        "what": f"통화정책 결정 ({bank['rate']})",
        "url": bank["url"],
    }


def snb_events() -> list[dict]:
    """스위스 SNB 정례 통화정책평가. 3·6·9·12월 목요일."""
    text = _plain(_get(SNB_URL))
    days = set()
    for dd, mm, yy in _SNB_ROW.findall(text):
        try:
            days.add(datetime.date(int(yy), int(mm), int(dd)))
        except ValueError:
            continue
    if not days:
        raise ScheduleError("스위스 SNB: 정책평가 일자를 하나도 읽지 못했다")
    return [_bank_event("CH", d) for d in sorted(days)]


def tcmb_events() -> list[dict]:
    """튀르키예 TCMB 통화정책위원회 결정일."""
    doc = _get(TCMB_URL)
    at = doc.find(_TCMB_HEAD)
    if at < 0:
        raise ScheduleError("튀르키예 TCMB: 일정표 제목을 찾지 못했다")
    end = doc.find("</table>", at)
    block = doc[at:end if end > 0 else len(doc)]

    days = set()
    for row in re.findall(r"<tr.*?</tr>", block, re.S):
        cells = re.findall(r"<t[dh].*?</t[dh]>", row, re.S)
        if not cells:
            continue
        first = _plain(cells[0]).replace("\xa0", "").strip()
        hit = _TCMB_DAY.match(first)
        if not hit:                     # 머리글 줄과 빈 칸은 여기서 걸린다
            continue
        mon = _BOJ_MONTH.get(hit.group(1))
        if not mon:
            continue
        try:
            days.add(datetime.date(int(hit.group(3)), mon, int(hit.group(2))))
        except ValueError:
            continue
    if not days:
        raise ScheduleError("튀르키예 TCMB: 결정일을 하나도 읽지 못했다")
    return [_bank_event("TR", d) for d in sorted(days)]


# ------------------------------------------------------------------ 체코 ČNB
# 일정 페이지(cnb-news/calendar)는 자바스크립트로 그려진다. 그 안을 들추면
# list-ajax.jsp 라는 주소가 나오고 코드로도 열리지만, 열 건씩 끊어 주어
# 열두 달 뒤를 보려면 수십 번을 불러야 한다.
#
# 그럴 것 없이, ČNB 는 해마다 '다음 해 이사회 일정' 공지를 한 장으로 낸다.
# 그 쪽은 서버가 다 그려 보내고 통화정책 회의일만 한 줄에 모아 둔다 —
# "will be held on the following dates: 5 February 19 March ...".
#
# 올해와 내년 둘을 본다. 내년 공지는 아직 없는 때가 많고(404) 그것은 탈이
# 아니다. 둘 다 못 읽었을 때만 실패로 친다.
CNB_NEWS = ("https://www.cnb.cz/en/cnb-news/news/"
            "Dates-of-the-CNB-Boards-meetings-in-{year}")
_CNB_ANCHOR = "following dates"
_CNB_STOP = "The CNB will publish"
_CNB_MONTH = {m: i for i, m in enumerate(
    ("January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"), 1)}
_CNB_DAY = re.compile(r"(\d{1,2})\s+(" + "|".join(_CNB_MONTH) + r")\b")


def _cnb_year(year: int) -> set[datetime.date]:
    text = _plain(_get(CNB_NEWS.format(year=year), tries=1))
    at = text.find(_CNB_ANCHOR)
    if at < 0:
        raise ScheduleError(f"체코 ČNB {year}: 일정 문단을 찾지 못했다")
    seg = text[at:]
    stop = seg.find(_CNB_STOP)
    seg = seg[:stop if stop > 0 else 400]
    out = set()
    for day, mon in _CNB_DAY.findall(seg):
        try:
            out.add(datetime.date(year, _CNB_MONTH[mon], int(day)))
        except ValueError:
            continue
    return out


def cnb_events(today: datetime.date | None = None) -> list[dict]:
    """체코 ČNB 통화정책 이사회. 공지 한 장이 한 해를 담는다."""
    today = today or datetime.date.today()
    days: set[datetime.date] = set()
    why = []
    for year in (today.year, today.year + 1):
        try:
            days |= _cnb_year(year)
        except (ScheduleError, ValueError) as exc:
            why.append(str(exc))
    if not days:
        raise ScheduleError("체코 ČNB: " + " / ".join(why))
    return [_bank_event("CZ", d) for d in sorted(days)]


# ------------------------------------------------------------------ 행사
# 발표 일정과 성격이 다르다. 지표는 '무엇이 나오나'이고 이쪽은 '무엇에 갈 수
# 있나'다. 프랑크푸르트 사무소에서 ECB 컨퍼런스는 실제로 참석할 수 있는
# 자리이므로, 숫자 일정만 있는 표에 이것이 빠져 있던 것이 이상했다.
#
# 여러 날에 걸친 행사는 **첫날에만 한 줄** 둔다. 이틀치를 다 찍으면 한 달
# 표에 행사만 스무 줄이 깔려 지표가 묻힌다. 기간은 제목 뒤에 적는다.
ECB_CONF_URL = "https://www.ecb.europa.eu/press/conferences/html/index.en.html"
_CONF_PAIR = re.compile(r"<dt[^>]*>(.*?)</dt>\s*<dd[^>]*>(.*?)</dd>", re.S)
_CONF_DAY = re.compile(r"(\d{2})/(\d{2})/(\d{4})")
_CONF_LINK = re.compile(r"<a[^>]*href=\"([^\"]+)\"[^>]*>(.*?)</a>", re.S)


def _plain(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


def _span(start: datetime.date, end: datetime.date | None) -> str:
    """'10.5~6' 또는 '10.30~11.1'. 하루짜리면 빈 문자열."""
    if not end or end <= start:
        return ""
    if end.month == start.month:
        return f"{start.month}.{start.day}~{end.day}"
    return f"{start.month}.{start.day}~{end.month}.{end.day}"


def ecb_conference_events(today: datetime.date | None = None) -> list[dict]:
    """ECB 컨퍼런스·세미나.

    <dt> 에 날짜(DD/MM/YYYY, 기간이면 둘), <dd> 에 <a>제목</a><br>장소.
    지난 행사까지 한 쪽에 다 있으므로 오늘 이후만 추린다.
    """
    today = today or datetime.date.today()
    doc = _get(ECB_CONF_URL)
    out = []
    for dt, dd in _CONF_PAIR.findall(doc):
        days = [datetime.date(int(y), int(m), int(d))
                for d, m, y in _CONF_DAY.findall(dt)]
        if not days:
            continue
        start, end = days[0], (days[-1] if len(days) > 1 else None)
        if (end or start) < today:
            continue
        link = _CONF_LINK.search(dd)
        title = _plain(link.group(2)) if link else _plain(dd)
        if not title:
            continue
        where = _plain(dd.split("</a>")[-1]) if link else ""
        url = link.group(1) if link else ECB_CONF_URL
        if url.startswith("/"):
            url = "https://www.ecb.europa.eu" + url
        what = title
        span = _span(start, end)
        if span:
            what += f" · {span}"
        if where:
            what += f" ({where})"
        out.append({"date": start.isoformat(), "kind": "event", "area": "EA",
                    "who": "ECB", "what": what, "url": url})
    if not out:
        raise ScheduleError("ECB 행사: 하나도 읽지 못했다")
    return out


BBK_CONF_URL = "https://www.bundesbank.de/en/bundesbank/research/conferences"
_BBK_ITEM = re.compile(r'<li class="collection__item">(.*?)</li>', re.S)
_BBK_TITLE = re.compile(r'<div class="h3">(.*?)(?:<small|</div>)', re.S)
_BBK_INFO = re.compile(r'<p class="text-eventinfo">(.*?)</p>', re.S)
_BBK_DAY = re.compile(r"(\d{2})\.(\d{2})\.(\d{4})")


def bbk_conference_events(today: datetime.date | None = None) -> list[dict]:
    """분데스방크 연구 컨퍼런스.

    'Upcoming Events' 아래만 읽는다. 그 뒤에 지난 행사가 해마다 쌓여 있어
    통째로 읽으면 과거가 섞인다. 건수는 적다 — 한 해 두어 번이다.
    """
    today = today or datetime.date.today()
    doc = _get(BBK_CONF_URL)
    head = doc.find("Upcoming Events")
    if head < 0:
        raise ScheduleError("분데스방크 행사: 'Upcoming Events' 를 찾지 못했다")
    # 다음 제목(지난 행사 목록)까지만 자른다.
    tail = doc.find("Previous conferences", head)
    block = doc[head:tail if tail > 0 else head + 20000]

    out = []
    for item in _BBK_ITEM.findall(block):
        info = _BBK_INFO.search(item)
        title = _BBK_TITLE.search(item)
        if not info or not title:
            continue
        days = [datetime.date(int(y), int(m), int(d))
                for d, m, y in _BBK_DAY.findall(info.group(1))]
        if not days:
            continue
        start, end = days[0], (days[-1] if len(days) > 1 else None)
        if (end or start) < today:
            continue
        name = _plain(title.group(1))
        if not name:
            continue
        # '29.09.2026 | Frankfurt am Main' 에서 장소만 떼어 낸다.
        where = _plain(info.group(1)).split("|")[-1].strip()
        what = name
        span = _span(start, end)
        if span:
            what += f" · {span}"
        if where and not _BBK_DAY.search(where):
            what += f" ({where})"
        out.append({"date": start.isoformat(), "kind": "event", "area": "DE",
                    "who": "분데스방크", "what": what, "url": BBK_CONF_URL})
    return out          # 없는 날이 있다. 그것은 고장이 아니다.


# ------------------------------------------------------------------ 눈에 띄게
# 한 달 치를 늘어놓으면 쉰 건이 넘는다. 그 가운데 사무소가 반드시 챙겨야 할
# 셋 — 통화정책 결정, GDP, 물가 — 은 굵게 뽑아 둔다. 나머지는 배경이다.
#
# '물가'를 글자 그대로 잡으면 생산자·수입·도매·서비스 물가까지 걸려 마흔
# 남짓 가운데 열여덟이 굵어진다. 그쯤 되면 강조가 아니라 배경이다. 금리를
# 움직이는 것은 소비자물가이므로 거기로 좁힌다.
_MAJOR = re.compile(
    r"GDP|국민계정|국내총생산|소비자물가|인플레이션|HICP|"
    r"유로지역 물가 속보치", re.I)


def untranslated(events: list[dict]) -> list[str]:
    """우리말로 옮기지 못한 제목을 알린다.

    대응표에 없는 제목은 원문을 그대로 내보낸다 — 빠뜨리는 것보다 낫다는
    판단이었다. 그런데 그러면 **조용히** 새어 나간다. 2026-10-05 에
    'Produktionsindex' 가 그렇게 나갔고, 소장님이 화면에서 보고 짚어 주셔야
    알았다. 기관이 제목을 바꿀 때마다 같은 일이 생긴다.

    그래서 한글이 한 자도 없는 제목을 센다. 화면 경고로는 올리지 않는다 —
    읽는 데 지장이 없고, 고칠 사람은 나다. 빌드 로그와 주간 점검에만 남는다.
    """
    msgs = []
    for e in events:
        # 행사는 빼야 한다. ECB·분데스방크 컨퍼런스는 원래 이름이 영어이고
        # 그것이 제 이름이다 — 옮기면 찾아보기가 어려워진다.
        if e.get("kind") != "release":
            continue
        head = e["what"].split(" · ")[0]
        if re.search(r"[가-힣]", head):
            continue
        msgs.append(f"  [번역 없음] {e['who']} {e['date']} — {head!r} "
                    f"를 대응표에 넣어야 한다")
    return msgs


def is_major(event: dict) -> bool:
    # 행사는 굵게 하지 않는다. 굵은 표시는 '시장이 움직이는 것'에만 쓴다 —
    # 제목에 GDP 가 들어간 워크숍이 물가지표처럼 보이면 안 된다.
    if event["kind"] == "event":
        return False
    if event["kind"] == "policy":
        return True
    return bool(_MAJOR.search(event["what"]))


# ------------------------------------------------------------------ 모으기
def month_end(today: datetime.date) -> datetime.date:
    """오늘부터 '한 달 뒤 같은 날'. 그 날이 없는 달이면 그 달 마지막 날."""
    y, m = today.year + (today.month == 12), today.month % 12 + 1
    day = today.day
    while day > 1:
        try:
            return datetime.date(y, m, day)
        except ValueError:
            day -= 1
    return datetime.date(y, m, 1)


def week(today: datetime.date, days: int | None = None,
         log=print) -> tuple[list, list]:
    """(일정, 경고). 오늘부터 한 달까지(days 를 주면 그 날 수만큼)."""
    end = (today + datetime.timedelta(days=days - 1) if days
           else month_end(today))
    events, warn = [], []

    sources = (("ECB", ecb_events),
               ("연준", fed_events),
               ("영란은행", boe_events),
               ("한국은행", lambda: bok_events(today)),
               ("일본은행", lambda: boj_events(today)),
               ("ECB 행사", lambda: ecb_conference_events(today)),
               ("분데스방크 행사", lambda: bbk_conference_events(today)),
               ("Eurostat", lambda: eurostat_events(today, end)),
               ("Destatis", lambda: destatis_events(until=end.isoformat())))
    for name, fn in sources:
        try:
            got = fn()
        except CachedSchedule as exc:
            # 받지는 못했지만 저장해 둔 것이 있다. 통째로 빠지는 것보다 낫다.
            # 다만 언제 받은 것인지를 밝힌다 — 묵은 자료를 오늘 것처럼 보이게
            # 하면 안 된다. 화면 경고에 그대로 실린다.
            got = exc.events
            when = exc.fetched or "날짜 모름"
            warn.append(f"{name} 일정을 받지 못해 {when} 에 받아 둔 것을 쓴다 "
                        f"— {exc.why}")
            log(f"  [대체] {name} — {exc.why} / {when} 저장분 {len(got)}건")
        except (ScheduleError, ValueError) as exc:
            warn.append(f"{name} 일정을 받지 못했다 — {exc}")
            log(f"  [실패] {name} — {exc}")
            continue
        hit = [e for e in got
               if today <= datetime.date.fromisoformat(e["date"]) <= end]
        events += hit
        log(f"  {name:9} 전체 {len(got):3}건 중 이 구간 {len(hit)}건")

    # 유로지역 밖 중앙은행. 스위스·튀르키예는 받아 오고, 받아 온 것이 있으면
    # 그 나라는 표에서 빼 중복을 막는다. 받아 오기가 실패하면 표로 떨어진다 —
    # 그때는 일정이 빠지는 것이 아니라 손으로 적어 둔 것을 쓰는 것이므로,
    # 독자 화면의 '받지 못했습니다' 경고에는 올리지 않는다(make.py 가 '받지
    # 못' 이라는 말로 가른다). 빌드 로그와 주간 점검에만 남긴다.
    import policy_dates
    live = set()
    for code, fn in (("CH", snb_events), ("TR", tcmb_events),
                     ("CZ", lambda: cnb_events(today))):
        tag = f"{policy_dates.BANKS[code]['name']} {policy_dates.BANKS[code]['bank']}"
        try:
            got = fn()
        except (ScheduleError, ValueError) as exc:
            warn.append(f"{tag} 결정일은 적어 둔 표를 쓴다 — 자동 수집 실패: {exc}")
            log(f"  [표 사용] {tag} — {exc}")
            continue
        live.add(code)
        hit = [e for e in got
               if today <= datetime.date.fromisoformat(e["date"]) <= end]
        events += hit
        # 받아 온 것과 표가 어긋나면 알린다. 표는 받아 오기가 실패했을 때
        # 떨어질 자리이므로 묵으면 안 되고, 결정일이 바뀐 것일 수도 있다.
        table = {e["date"] for e in policy_dates.upcoming(today, end)
                 if e["area"] == code}
        if table != {e["date"] for e in hit}:
            warn.append(f"{tag} — 받아 온 결정일과 적어 둔 표가 어긋난다: "
                        f"받은 것 {sorted(e['date'] for e in hit)} / "
                        f"표 {sorted(table)}")
            log(f"  [어긋남] {tag} — 표를 고쳐야 한다")
        log(f"  {tag:9} 받아 온 {len(got):3}건 중 이 구간 {len(hit)}건")

    hit = policy_dates.upcoming(today, end, skip=live)
    events += hit
    log(f"  중앙은행     표에서 이 구간 {len(hit)}건")

    # Eurostat 은 같은 발표를 여러 줄로 내는 일이 있다(같은 날·같은 제목·
    # 같은 기준기간). 화면에서는 한 줄이어야 한다.
    seen, uniq = set(), []
    for e in events:
        key = (e["date"], e["who"], e["what"])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(e)
    events = uniq

    for e in events:
        e["major"] = is_major(e)
    # 같은 날 안에서는 통화정책, 그다음 굵게 뽑은 것, 그다음 기관 이름 순.
    events.sort(key=lambda e: (e["date"], e["kind"] != "policy",
                               not e["major"], e["who"]))
    return events, warn
