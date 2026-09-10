"""
버스 좌석 여유(혼잡도) 예측 - 데이터 파이프라인 & GBM 학습 스크립트
==================================================================

"내가 과연 탈 수 있을까?" 프로젝트의 좌석 여유 확률 모델을 학습하는
전체 과정(데이터 적재 -> 재차인원/혼잡도 라벨 계산 -> 피처 엔지니어링 ->
시간 기준 학습/검증 분리 -> GBM 학습 -> 웹앱용 결과 내보내기)을 보여준다.

지금은 실제 데이터가 없어서 generate_sample_ridership()이 만든 합성 데이터로
전체 파이프라인이 잘 동작하는지 확인하는 용도였는데, 실제 OA-12913 2026년 7월분
CSV를 직접 받아서 열어보니 애초에 예상했던 것과 스키마가 꽤 달랐다. 아래는 실제
파일을 열어보고 확인한 내용과, 그에 맞춰 이 스크립트를 어떻게 바꿨는지 정리한 것.

실제 CSV(월별 집계, wide format) 구조 — 직접 다운로드해서 확인:
  사용년월(YYYYMM, "202607" 같은 월 단위 문자열 - 일자 아님), 노선번호, 노선명,
  표준버스정류장ID, 버스정류장ARS번호, 역명, 그리고 "00시승차총승객수"/
  "00시하차총승객수"부터 "23시승차총승객수"/"23시하차총승객수"까지 시간대별
  승하차 쌍(48개 컬럼, 0시만 "00시"이고 1~23시는 앞자리 0 없이 "1시"~"23시"),
  마지막으로 교통수단타입코드/교통수단타입명(예: "051"/"서울심야버스")과
  등록일자. 인코딩은 cp949(=euc-kr).

애초에 가정했던 것(아래 COLUMN_MAP, 일자별 long format + 정류장 순번)과
실제로 다른 점 두 가지, 그리고 이 스크립트가 그걸 어떻게 반영했는지:

1. 일자별이 아니라 "그 달 전체 합계"다. 요일(dow)/평일-주말 구분을 이 파일
   하나만으로는 만들 수 없다 (서울 열린데이터광장에 요일별로 쪼갠 버전이
   따로 있는지 찾아봤지만 없는 것으로 확인됨). 그래서 실제 데이터 경로에서는
   dow/is_weekend 피처를 아예 뺐다 — 대신 이 데이터셋은 월별 파일이 여러 달치
   쌓여 있으니(2015년~2026년 7월까지), 나중에 여러 달을 모으면 "월별" 변동
   정도는 학습할 수 있다.
2. 정류장 순번(stop_seq) 필드가 없다. 표준버스정류장ID/ARS번호는 노선 내
   순서와 무관한 전국 공통 정류장 ID라서(실제로 402번 노선 데이터를 순서대로
   찍어보면 ID가 노선 순서와 무관하게 뒤죽박죽이었다), 있는 그대로는 "이
   정류장이 노선의 몇 번째냐"를 알 수 없다 → 원래 설계인 "정류장 순서대로
   누적 승하차 = 재차인원"을 그대로 계산할 수 없다. 정확한 순번은 서울
   TOPIS나 국가대중교통정보센터(TAGO)의 "노선별경유정류소목록조회" API로
   별도 발급받아야 한다(data.go.kr 서비스키 필요 - ODsay 때와 비슷한 절차).
   지금은 그 작업 없이, 정류장의 그 시간대 "승차인원 자체"를 재차인원의
   근사치로 쓴다(approximate_onboard_from_boarding 참고) — 진짜 재차인원보다
   낮게 잡히는 쪽으로 치우친 근사치라는 걸 알고 쓰는 것.

실제 데이터로 파이프라인을 돌리려면:

1. 서울 열린데이터광장에서 데이터를 월별 CSV로 다운로드한다.
   - 서울시 버스노선별 정류장별 시간대별 승하차 인원 정보 (OA-12913)
     https://data.seoul.go.kr/dataList/OA-12913/S/1/datasetView.do
2. `python bus_congestion_pipeline.py 경로/파일.csv` 로 실행하면
   main_real()이 자동으로 위 실제 스키마를 파싱해서 돌아간다 (인자를 안 주면
   기존처럼 합성 데이터 데모 main()이 돈다).
3. ROUTE_INFO에 실제 관심 노선의 버스 타입(일반/광역)과 등록 승차정원을 채운다.
   (버스회사/지자체 공개자료, 차량 제원 등으로 확인. 정확한 숫자를 모르면 그
   차종의 일반적인 정원을 위키/나무위키에서 찾아 근사해도 된다. 참고: 실제
   CSV의 교통수단타입명 컬럼으로 그 노선이 일반/광역/마을/심야 중 뭔지는
   자동으로 확인할 수 있다 — bus_type_real 컬럼.)

중요: 일반버스와 광역버스는 "정원"의 의미 자체가 다르다.
- 광역버스(직행좌석버스 등)는 2014년 세월호 사고 이후 도입된 입석금지 제도로
  입석이 금지되어 있고(국토교통부 훈령, 2023년 도로교통법 시행령 개정으로
  전 차종에 등록 승차정원 100% 이내로 강화 적용), 정원을 넘기면 정류장에
  무정차로 통과한다. 즉 정원 = 좌석수에 가깝고, 그 순간 "혼잡"이 아니라
  "탑승 불가"가 된다.
- 일반버스(시내/간선/지선버스)는 애초에 입석을 전제로 설계돼서 등록
  승차정원 자체가 좌석+입석을 합친 훨씬 큰 숫자다. 서울시가 안내판에 쓰는
  "좌석수의 1.5배 = 혼잡" 기준은 이 일반버스의 "불쾌감 수준"을 나타내는
  지표이지, 광역버스에 그대로 적용하면 안 된다.
그래서 이 스크립트는 버스 타입별로 라벨링 기준과 임계값을 다르게 둔다.

필요한 패키지: pandas, numpy, scikit-learn, lightgbm
    pip install pandas numpy scikit-learn lightgbm
"""

import json

import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.metrics import accuracy_score, classification_report, f1_score

RANDOM_SEED = 42
np.random.seed(RANDOM_SEED)

# ---------------------------------------------------------------------------
# 0. 설정 - 실제 데이터로 바꿀 때 이 블록만 고치면 된다
# ---------------------------------------------------------------------------

# 실제 CSV 컬럼명이 다르면 여기 오른쪽 값만 바꾸면 된다.
COLUMN_MAP = {
    "route": "노선명",
    "stop_seq": "정류장순번",
    "stop_name": "정류장명",
    "date": "사용일자",
    "hour": "시간대",
    "boarding": "승차인원",
    "alighting": "하차인원",
}

# 노선별 버스 타입과 "등록 승차정원"(자동차등록증 기준 - 실제로는 차종/노선별로
# 직접 조사해서 채워야 한다). registered_capacity의 의미가 타입에 따라 다르다:
#   - 일반: 좌석 + 입석을 합친 등록 정원 (보통 65~100 사이, 차종에 따라 다름)
#   - 광역: 입석 금지라 등록 정원이 곧 좌석수에 가깝다 (보통 40~45)
ROUTE_INFO = {
    "402": {"bus_type": "일반", "registered_capacity": 80},
    "7014": {"bus_type": "일반", "registered_capacity": 65},  # 마을/지선버스는 차체가 작아 정원도 적음
    "143": {"bus_type": "일반", "registered_capacity": 90},
    "M4434": {"bus_type": "광역", "registered_capacity": 45},  # 실존 광역급행버스(동탄2신도시~강남역), 정원은 이 등급 통상치로 가정
}
# 실제 2026년 7월 OA-12913 파일로 위 4개 노선을 직접 조회해본 결과:
#   - "402", "143"은 있음(각각 110행, 114행 - 왕복 정류장 전부 합친 개수로 보임).
#   - "7014"는 0행 — 이 데이터셋(서울시 버스 전체, 666개 노선)에 없다. 노선번호
#     표기가 다르거나(마을버스는 지역명이 붙는 등) 실제로 원하는 노선이 아닐 수
#     있으니, 정확한 노선번호를 다시 확인해볼 것.
#   - "M4434"는 0건 — M버스(광역급행)는 서울시가 아니라 경기도 관할 노선이라
#     애초에 서울시 OA-12913 데이터셋 범위 밖이다. 이 노선을 실 데이터로 쓰려면
#     경기데이터드림 등 별도 출처가 필요하다.

# 일반버스: 서울시가 실제 안내판에 쓰는 방식 - 등록정원 대비 비율로 3단계 구분.
# 이건 "탑승 불가"가 아니라 "혼잡한 정도"를 나타내는 편의 지표에 가깝다.
GENERAL_LOW, GENERAL_HIGH = 0.55, 0.85

# 광역버스: 입석이 금지되어 있어 정원 자체가 하드 컷이다. 정원에 가까워질수록
# "혼잡"이 아니라 "이 버스는 못 탈 수도 있다"에 가까우므로 임계값을 훨씬 촘촘하게 둔다.
EXPRESS_LOW, EXPRESS_HIGH = 0.7, 0.95

TEST_LAST_N_DAYS = 14  # 검증은 반드시 "미래" 데이터로 분리한다 (무작위 분리 금지 - 데이터 누수 방지)

FEATURE_COLS = ["dow", "is_weekend", "hour_sin", "hour_cos", "stop_seq", "prev_onboard"]
# route뿐 아니라 bus_type도 특성으로 넣는다. 노선별로 외워버리는 대신,
# "광역버스는 정원 근처에서 확률이 급격히 떨어진다"는 패턴 자체를 모델이
# 학습해서 나중에 처음 보는 노선에도 일반화할 수 있게 하기 위함이다.
CATEGORICAL_COLS = ["route", "bus_type"]
LABEL_ORDER = ["여유", "보통", "혼잡"]


# ---------------------------------------------------------------------------
# 1. 데이터 적재
# ---------------------------------------------------------------------------

# 노선별 정류장 순서 (M4434는 입석금지 광역급행버스 예시: 동탄2신도시 -> 고속도로변 -> 강남권)
ROUTE_STOPS = {
    "402": ["A", "B", "C"],
    "7014": ["A", "D", "E"],
    "143": ["E", "C"],
    "M4434": ["F", "G", "H"],
}


def generate_sample_ridership(n_days=120, routes=None):
    """실제 CSV가 없을 때 파이프라인을 검증하기 위한 합성 데이터.
    일반버스는 출퇴근 피크 + 주말 완화 패턴을, 광역버스(M4434)는 훨씬 좁고
    뾰족한 통근 시간대 피크 + 정원을 넘으면 승차가 거부되는(무정차 통과) 현상을
    흉내낸다. 실제 데이터를 구하면 이 함수 대신 load_real_ridership_csv()를 쓰면 된다."""
    routes = routes or tuple(ROUTE_INFO.keys())
    start_date = pd.Timestamp("2026-01-05")  # 월요일부터 시작
    rng = np.random.default_rng(RANDOM_SEED)

    rows = []
    for d in range(n_days):
        date = start_date + pd.Timedelta(days=d)
        dow = date.dayofweek  # 0=월 ... 6=일
        is_weekend = dow >= 5
        for route in routes:
            stops = ROUTE_STOPS[route]
            info = ROUTE_INFO[route]
            is_express = info["bus_type"] == "광역"
            capacity = info["registered_capacity"]

            for hour in range(5, 24):
                if is_express:
                    # 광역버스: 출퇴근 시간에만 다니는 좁고 뾰족한 피크, 주말엔 수요가 거의 없음
                    rush = np.exp(-0.5 * ((hour - 7.5) / 0.7) ** 2) + np.exp(-0.5 * ((hour - 18.5) / 0.8) ** 2)
                    weekend_damp = 0.1 if is_weekend else 1.0
                    base_riders = 3 + 70 * rush * weekend_damp
                else:
                    rush = np.exp(-0.5 * ((hour - 8) / 1.3) ** 2) + 0.9 * np.exp(-0.5 * ((hour - 18.5) / 1.6) ** 2)
                    weekend_damp = 0.4 if is_weekend else 1.0
                    base_riders = 6 + 40 * rush * weekend_damp

                onboard_so_far = 0  # 이 시간대·이 노선에서 누적 재차인원 (광역버스 정원 캡 계산용)
                for i, stop in enumerate(stops):
                    board_lam = max(0.1, base_riders * (1 - i / len(stops)) + rng.normal(0, 2))
                    alight_lam = max(0.1, base_riders * (i / len(stops) + 0.15) + rng.normal(0, 2))
                    desired_boarding = int(rng.poisson(board_lam))
                    alighting = int(rng.poisson(alight_lam)) if i > 0 else 0
                    onboard_so_far = max(0, onboard_so_far - alighting)

                    if is_express:
                        # 입석금지: 정원을 넘는 순간 초과 승객은 이 버스를 타지 못한다.
                        # (다음 버스를 기다려야 하므로 이 시간대 이 버스의 boarding 기록에는 잡히지 않는다)
                        room = max(0, capacity - onboard_so_far)
                        boarding = min(desired_boarding, room)
                    else:
                        boarding = desired_boarding

                    onboard_so_far += boarding
                    rows.append({
                        "route": route, "stop_seq": i, "stop_name": stop,
                        "date": date, "hour": hour,
                        "boarding": boarding, "alighting": alighting,
                    })
    return pd.DataFrame(rows)


def load_real_ridership_csv(path, routes=None):
    """OA-12913 실제 CSV(월별/정류장별/시간대별 집계, wide format)를 읽어
    long format으로 바꾼다. COLUMN_MAP은 이 실제 스키마와 안 맞아서(모듈
    docstring 참고) 여기서는 쓰지 않고, 실제 컬럼명을 직접 다룬다.

    반환되는 boarding/alighting은 "그 달 총 승하차 인원 / 그 달 일수"로 나눈
    일평균 추정치다. 실제로는 요일에 따라 편차가 크겠지만(평일 출퇴근 vs
    주말), 이 파일 하나로는 그 편차를 알 수 없어서 평균으로 뭉뚱그린 것 —
    "이 노선·정류장·시간대는 평균적으로 이 정도 탄다"는 근사치로 이해할 것."""
    raw = pd.read_csv(
        path, encoding="cp949",  # 공공데이터 CSV는 보통 cp949(EUC-KR) 인코딩
        dtype={"노선번호": str, "사용년월": str, "표준버스정류장ID": str},
    )
    routes = list(routes or ROUTE_INFO.keys())
    raw = raw[raw["노선번호"].isin(routes)].copy()
    if raw.empty:
        raise ValueError(
            f"CSV에서 관심 노선({routes})을 하나도 찾지 못했습니다. "
            "노선번호 표기(문자열)가 ROUTE_INFO 키와 일치하는지 확인하세요."
        )

    days_in_month = pd.Period(raw["사용년월"].iloc[0], freq="M").days_in_month

    long_rows = []
    for _, row in raw.iterrows():
        for h in range(24):
            b_col = "00시승차총승객수" if h == 0 else f"{h}시승차총승객수"
            a_col = "00시하차총승객수" if h == 0 else f"{h}시하차총승객수"
            long_rows.append({
                "route": row["노선번호"],
                "stop_id": row["표준버스정류장ID"],
                "stop_name": row["역명"],
                "bus_type_real": row.get("교통수단타입명"),
                "month": row["사용년월"],
                "hour": h,
                "boarding_month_total": row[b_col],
                "alighting_month_total": row[a_col],
            })
    df = pd.DataFrame(long_rows)
    df["boarding"] = pd.to_numeric(df["boarding_month_total"], errors="coerce").fillna(0) / days_in_month
    df["alighting"] = pd.to_numeric(df["alighting_month_total"], errors="coerce").fillna(0) / days_in_month
    return df[["route", "stop_id", "stop_name", "bus_type_real", "month", "hour", "boarding", "alighting"]]


def approximate_onboard_from_boarding(df):
    """정류장 순번이 없어 진짜 누적 재차인원(compute_onboard_load)을 쓸 수
    없는 실제 데이터용 근사치. 그 정류장·시간대의 승차인원 자체를 '재차인원'
    대용으로 쓴다.

    주의: 진짜 재차인원 = 이전 정류장들에서 타서 아직 안 내린 사람들의
    누적합이라 항상 그 시간대 boarding 값보다 크거나 같다. 즉 이 근사치는
    실제보다 낮게 잡히는 쪽으로 치우쳐 있다 — "혼잡"으로 잡히는 정류장이
    실제로는 더 있을 수 있다는 뜻. 나중에 TOPIS/TAGO로 정류장 순번을
    확보하면 compute_onboard_load()로 교체할 것."""
    df = df.copy()
    df["onboard"] = df["boarding"]
    return df


def add_congestion_label_real_relative(df):
    """add_congestion_label()을 실제 데이터에 그대로 썼을 때의 문제를 고치는
    대안: 절대적인 '정원 대비 재차인원 비율' 대신, 같은 노선 안에서 그
    정류장·시간대가 상대적으로 얼마나 붐비는지(백분위)로 라벨을 매긴다.

    이렇게 바꾼 이유(직접 돌려보고 확인한 문제): approximate_onboard_from_boarding()
    이 쓰는 '그 정류장의 시간대별 승차인원'은 하루 종일 그 노선에 다니는 버스
    여러 대 중 그 정류장 한 곳에서 타는 사람 수를 월 평균낸 값이라, 버스 한
    대의 등록 정원(80~90명)과 비교하면 항상 훨씬 작다 — add_congestion_label()
    그대로 쓰면 97%가 "여유"로 몰리고 "보통"/"혼잡" 표본이 너무 적어서(macro F1
    0.33대) 모델이 사실상 아무것도 학습하지 못한다. 정류장 순번을 확보해서
    진짜 재차인원을 계산하기 전까지는, "이 노선 기준으로 상대적으로 붐비는
    시간/정류장"을 라벨로 쓰는 게 이 데이터로 할 수 있는 현실적인 최선이다."""
    df = df.copy()
    info_df = pd.DataFrame(ROUTE_INFO).T.reset_index().rename(columns={"index": "route"})
    df = df.merge(info_df, on="route", how="left")
    df["load_ratio"] = df.groupby("route")["onboard"].rank(pct=True)

    def label(row):
        r = row["load_ratio"]
        if r < GENERAL_LOW:
            return "여유"
        if r < GENERAL_HIGH:
            return "보통"
        return "혼잡"

    df["congestion"] = df.apply(label, axis=1)
    return df


def add_features_real(df):
    """실제 데이터엔 일자가 없어 dow/is_weekend/stop_seq/prev_onboard를 만들
    수 없다 — hour만으로 주기성 피처를 만든다."""
    df = df.copy()
    df["hour_sin"] = np.sin(2 * np.pi * df["hour"] / 24)
    df["hour_cos"] = np.cos(2 * np.pi * df["hour"] / 24)
    return df


FEATURE_COLS_REAL = ["hour_sin", "hour_cos"]
CATEGORICAL_COLS_REAL = ["route", "bus_type"]


def time_based_split_real(df, test_size=0.2):
    """실제 데이터는 한 달치 집계라 '미래 데이터로 검증'할 시간 축 자체가
    없다 — 그래서 무작위 홀드아웃으로 대체한다. 여러 달치를 모으면 이 함수
    대신 다시 time_based_split()을 쓰는 게 맞다."""
    rng = np.random.default_rng(RANDOM_SEED)
    idx = rng.permutation(len(df))
    cut = int(len(df) * (1 - test_size))
    train_idx, test_idx = idx[:cut], idx[cut:]
    return df.iloc[train_idx], df.iloc[test_idx]


# ---------------------------------------------------------------------------
# 2. 재차인원 / 혼잡도 라벨 계산
# ---------------------------------------------------------------------------

def compute_onboard_load(df):
    """정류장 순번 순서대로 누적 승차-하차를 계산해 '재차인원'을 복원한다."""
    df = df.sort_values(["route", "date", "hour", "stop_seq"]).copy()
    df["net_change"] = df["boarding"] - df["alighting"]
    df["onboard"] = df.groupby(["route", "date", "hour"])["net_change"].cumsum()
    df["onboard"] = df["onboard"].clip(lower=0)
    return df


def add_congestion_label(df):
    """재차인원 / 등록정원 비율로 혼잡도 등급을 매기되, 버스 타입별로 다른
    기준을 쓴다. 일반버스는 "혼잡하다(불쾌하다)"는 편의 지표에 가깝고,
    광역버스는 정원 근처가 곧 "탑승 불가"에 가까운 하드 컷이라 임계값을
    훨씬 촘촘하게 둔다."""
    df = df.copy()
    info_df = pd.DataFrame(ROUTE_INFO).T.reset_index().rename(columns={"index": "route"})
    df = df.merge(info_df, on="route", how="left")
    df["load_ratio"] = df["onboard"] / df["registered_capacity"]

    def label(row):
        lo, hi = (EXPRESS_LOW, EXPRESS_HIGH) if row["bus_type"] == "광역" else (GENERAL_LOW, GENERAL_HIGH)
        r = row["load_ratio"]
        if r < lo:
            return "여유"
        if r < hi:
            return "보통"
        return "혼잡"

    df["congestion"] = df.apply(label, axis=1)
    return df


# ---------------------------------------------------------------------------
# 3. 피처 엔지니어링
# ---------------------------------------------------------------------------

def add_features(df):
    df = df.copy()
    df["dow"] = df["date"].dt.dayofweek  # 0=월 ... 6=일
    df["is_weekend"] = (df["dow"] >= 5).astype(int)
    df["hour_sin"] = np.sin(2 * np.pi * df["hour"] / 24)
    df["hour_cos"] = np.cos(2 * np.pi * df["hour"] / 24)

    # lag 특성: 같은 노선·정류장의 "한 시간대 전" 재차인원 (버스 밀집 효과 대용)
    df = df.sort_values(["route", "stop_seq", "date", "hour"])
    df["prev_onboard"] = df.groupby(["route", "stop_seq"])["onboard"].shift(1)
    df["prev_onboard"] = df["prev_onboard"].fillna(df["onboard"].median())

    return df


# ---------------------------------------------------------------------------
# 4. 시간 기준 학습/검증 분리 (무작위 분리 금지 - 데이터 누수 방지)
# ---------------------------------------------------------------------------

def time_based_split(df, test_last_n_days=TEST_LAST_N_DAYS):
    cutoff = df["date"].max() - pd.Timedelta(days=test_last_n_days)
    train = df[df["date"] <= cutoff]
    test = df[df["date"] > cutoff]
    return train, test


# ---------------------------------------------------------------------------
# 5. 모델 학습 (LightGBM)
# ---------------------------------------------------------------------------

def train_model(train_df, test_df):
    x_train = pd.get_dummies(train_df[FEATURE_COLS + CATEGORICAL_COLS], columns=CATEGORICAL_COLS)
    x_test = pd.get_dummies(test_df[FEATURE_COLS + CATEGORICAL_COLS], columns=CATEGORICAL_COLS)
    x_test = x_test.reindex(columns=x_train.columns, fill_value=0)  # 노선 원-핫 컬럼 정렬 맞추기

    cat_type = pd.CategoricalDtype(categories=LABEL_ORDER)
    y_train = train_df["congestion"].astype(cat_type).cat.codes
    y_test = test_df["congestion"].astype(cat_type).cat.codes

    model = lgb.LGBMClassifier(
        n_estimators=300,
        learning_rate=0.05,
        num_leaves=15,
        random_state=RANDOM_SEED,
        verbose=-1,
    )
    model.fit(x_train, y_train)

    pred = model.predict(x_test)
    acc = accuracy_score(y_test, pred)
    f1 = f1_score(y_test, pred, average="macro")

    print(f"[검증] 정확도: {acc:.3f} / macro F1: {f1:.3f}")
    print(classification_report(y_test, pred, target_names=LABEL_ORDER, zero_division=0))

    importance = pd.Series(model.feature_importances_, index=x_train.columns).sort_values(ascending=False)
    print("[특성 중요도]")
    print(importance.to_string())

    return model, x_train.columns.tolist()


def train_model_real(train_df, test_df):
    """train_model()과 거의 같지만 dow/stop_seq/prev_onboard가 없는 실제
    데이터용 피처 집합(FEATURE_COLS_REAL)을 쓴다."""
    x_train = pd.get_dummies(train_df[FEATURE_COLS_REAL + CATEGORICAL_COLS_REAL], columns=CATEGORICAL_COLS_REAL)
    x_test = pd.get_dummies(test_df[FEATURE_COLS_REAL + CATEGORICAL_COLS_REAL], columns=CATEGORICAL_COLS_REAL)
    x_test = x_test.reindex(columns=x_train.columns, fill_value=0)

    cat_type = pd.CategoricalDtype(categories=LABEL_ORDER)
    y_train = train_df["congestion"].astype(cat_type).cat.codes
    y_test = test_df["congestion"].astype(cat_type).cat.codes

    model = lgb.LGBMClassifier(
        n_estimators=300,
        learning_rate=0.05,
        num_leaves=15,
        random_state=RANDOM_SEED,
        verbose=-1,
    )
    model.fit(x_train, y_train)

    pred = model.predict(x_test)
    acc = accuracy_score(y_test, pred)
    f1 = f1_score(y_test, pred, average="macro")

    print(f"[검증] 정확도: {acc:.3f} / macro F1: {f1:.3f}")
    print(classification_report(y_test, pred, target_names=LABEL_ORDER, zero_division=0, labels=sorted(set(y_test) | set(pred))))

    importance = pd.Series(model.feature_importances_, index=x_train.columns).sort_values(ascending=False)
    print("[특성 중요도]")
    print(importance.to_string())

    return model, x_train.columns.tolist()


def export_lookup_table_real(model, feature_cols, routes=None, out_path="congestion_lookup_real.json"):
    """실제 데이터 버전 룩업 테이블. dow가 없으므로 route x hour 조합만
    내보낸다 — 프론트엔드에서 쓰려면 dow 축이 빠졌다는 점을 반영해야 한다
    (예: 요일 무관하게 같은 값을 쓰거나, "이 값은 월 평균이다"라고 표시)."""
    routes = list(routes or ROUTE_INFO.keys())
    bus_types = sorted({info["bus_type"] for info in ROUTE_INFO.values()})
    rows = []
    for route in routes:
        if route not in ROUTE_INFO:
            continue
        info = ROUTE_INFO[route]
        for hour in range(24):
            feat = {
                "hour_sin": np.sin(2 * np.pi * hour / 24),
                "hour_cos": np.cos(2 * np.pi * hour / 24),
            }
            for r in routes:
                feat[f"route_{r}"] = 1 if r == route else 0
            for bt in bus_types:
                feat[f"bus_type_{bt}"] = 1 if bt == info["bus_type"] else 0
            x = pd.DataFrame([feat]).reindex(columns=feature_cols, fill_value=0)
            proba = model.predict_proba(x)[0]
            p_capacity = proba[LABEL_ORDER.index("여유")] + 0.5 * proba[LABEL_ORDER.index("보통")]
            rows.append({
                "route": route, "bus_type": info["bus_type"], "hour": hour,
                "p_capacity": round(float(p_capacity), 4),
            })

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    print(f"\n룩업 테이블 저장 완료: {out_path} ({len(rows)}행, dow 축 없음 - 월 평균 기준)")


# ---------------------------------------------------------------------------
# 6. 웹앱에서 바로 쓸 수 있도록 결과를 룩업 테이블(JSON)로 내보내기
# ---------------------------------------------------------------------------

def export_lookup_table(model, feature_cols, out_path="congestion_lookup.json"):
    """요일 x 시간대 x 노선 조합별 '좌석 여유 확률'을 미리 계산해 JSON으로 저장한다.
    웹앱은 실시간으로 모델을 돌리는 대신 이 표를 그대로 읽어서 보여주면 된다.
    (표 대신 모델을 그대로 배포하고 싶다면, 이 함수 대신 joblib.dump(model, ...)로
    모델 파일을 저장해 백엔드 서버에서 불러 쓰면 된다.)"""
    routes = list(ROUTE_INFO.keys())
    bus_types = sorted({info["bus_type"] for info in ROUTE_INFO.values()})
    rows = []
    for route in routes:
        info = ROUTE_INFO[route]
        for dow in range(7):
            for hour in range(24):
                feat = {
                    "dow": dow, "is_weekend": int(dow >= 5),
                    "hour_sin": np.sin(2 * np.pi * hour / 24), "hour_cos": np.cos(2 * np.pi * hour / 24),
                    "stop_seq": 0, "prev_onboard": 0,
                }
                for r in routes:
                    feat[f"route_{r}"] = 1 if r == route else 0
                for bt in bus_types:
                    feat[f"bus_type_{bt}"] = 1 if bt == info["bus_type"] else 0
                x = pd.DataFrame([feat]).reindex(columns=feature_cols, fill_value=0)
                proba = model.predict_proba(x)[0]  # [여유, 보통, 혼잡] 순서 (LABEL_ORDER)
                p_capacity = proba[LABEL_ORDER.index("여유")] + 0.5 * proba[LABEL_ORDER.index("보통")]
                rows.append({
                    "route": route, "bus_type": info["bus_type"], "dow": dow, "hour": hour,
                    "p_capacity": round(float(p_capacity), 4),
                })

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    print(f"\n룩업 테이블 저장 완료: {out_path} ({len(rows)}행)")
    print("이 JSON 값을 프로토타입의 congestionLogit()/capacityProbability() 자리에 반영하면")
    print("실제 학습 결과가 웹앱에 그대로 표시됩니다.")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    print("1) 데이터 적재 (지금은 샘플 데이터 - 실제 CSV가 있으면 load_real_ridership_csv()로 교체)")
    raw = generate_sample_ridership()
    # raw = load_real_ridership_csv("경로/OA-12913_2026xx.csv")

    print("\n2) 재차인원 계산")
    df = compute_onboard_load(raw)

    print("\n3) 혼잡도 라벨 부여 (버스 타입별 비율)")
    df = add_congestion_label(df)
    print(df.groupby("bus_type")["congestion"].value_counts(normalize=True).round(3).to_string())

    print("\n4) 피처 엔지니어링")
    df = add_features(df)

    print("\n5) 시간 기준 학습/검증 분리")
    train_df, test_df = time_based_split(df)
    print(f"학습: {train_df['date'].min().date()} ~ {train_df['date'].max().date()} ({len(train_df)}행)")
    print(f"검증: {test_df['date'].min().date()} ~ {test_df['date'].max().date()} ({len(test_df)}행)")

    print("\n6) 모델 학습")
    model, feature_cols = train_model(train_df, test_df)

    print("\n7) 웹앱용 룩업 테이블 내보내기")
    export_lookup_table(model, feature_cols)


def main_real(csv_path, routes=None):
    routes = list(routes or ROUTE_INFO.keys())
    print(f"1) 데이터 적재 (실제 OA-12913 CSV: {csv_path}, 관심 노선: {routes})")
    raw = load_real_ridership_csv(csv_path, routes=routes)
    found_routes = sorted(raw["route"].unique())
    missing = [r for r in routes if r not in found_routes]
    print(f"   -> 실제로 데이터에 있는 노선: {found_routes}")
    if missing:
        print(f"   -> [주의] 데이터에 없는 노선(제외하고 진행): {missing}")

    print("\n2) 재차인원 근사 (정류장 순번이 없어 승차인원을 그대로 사용 - 스크립트 상단 docstring 참고)")
    df = approximate_onboard_from_boarding(raw)

    print("\n3) 혼잡도 라벨 부여 (노선 내 상대적 백분위 기준 - 이유는 add_congestion_label_real_relative 참고)")
    df = add_congestion_label_real_relative(df)
    print(df.groupby("bus_type")["congestion"].value_counts(normalize=True).round(3).to_string())

    print("\n4) 피처 엔지니어링 (dow 없음 - hour만)")
    df = add_features_real(df)

    print("\n5) 학습/검증 분리 (시간 축이 없어 무작위 홀드아웃 20%)")
    train_df, test_df = time_based_split_real(df)
    print(f"학습: {len(train_df)}행 / 검증: {len(test_df)}행")

    print("\n6) 모델 학습")
    model, feature_cols = train_model_real(train_df, test_df)

    print("\n7) 웹앱용 룩업 테이블 내보내기 (congestion_lookup_real.json)")
    export_lookup_table_real(model, feature_cols, routes=found_routes)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        main_real(sys.argv[1])
    else:
        main()
