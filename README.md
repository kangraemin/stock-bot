# Stock Bot

레버리지 ETF 매매 시그널 텔레그램 봇 + 백테스트 프레임워크.

RSI, 볼린저 밴드, EMA, 매크로 필터(구리 SMA) 등 기술적 지표로 매수/매도 타이밍을 판단하고, 매일 텔레그램으로 시그널을 전송합니다. 40+ 실험과 4,500만 파라미터 조합을 검증한 백테스트 엔진을 포함합니다.

## 주요 기능

**알림봇**
- 12종목 매매 시그널 자동 전송 (cron, 매일 장 마감 후)
- `/status` 명령으로 실시간 종목 상태 조회
- VIX term structure, 구리 SMA 필터, ATR 포지션 사이징, 계절성 경고

**백테스트 엔진**
- BB+RSI+EMA 평균회귀 전략 (레버리지 ETF 최적, 타 전략 대비 10배+ 수익)
- 10개 파라미터 그리드 서치 (멀티프로세스, JSON 캐시)
- Walk-Forward / OOS 검증, 포트폴리오 리밸런싱
- HTML 리포트 생성, Sharpe/MDD/CAGR 등 성과 지표

## 대상 종목

| 종목 | 유형 | Buy RSI | 비고 |
|------|------|:-------:|------|
| SOXL | 3x 반도체 | 25 | |
| TQQQ | 3x 나스닥 | 25 | |
| SPXL | 3x S&P500 | 30 | |
| TNA | 3x 소형주 | 35 | 구리 필터, BB 필터 |
| QLD | 2x 나스닥 | 25 | |
| UWM | 2x 소형주 | 25 | 구리 필터 |
| QQQ | 나스닥100 | 25 | Buy only |
| GGLL | 2x 구글 | 30 | Buy only |
| NVDA | 엔비디아 | 35 | Buy only |
| MSTR | BTC 대리 | 30 | Buy only |
| HOOD | 핀테크 | 30 | Buy only |
| COIN | 크립토 | 30 | Buy only |

## 프로젝트 구조

```
stock-bot/
├── alert.py               # 멀티 종목 텔레그램 알림 (메인)
├── alert_soxl.py           # SOXL 단독 알림
├── bot_listener.py         # 텔레그램 봇 리스너 (/status)
├── config.py               # 종목, 수수료, 포트폴리오 프리셋
├── download.py             # yfinance 데이터 다운로드 → parquet
├── backtest/
│   ├── engine.py           # 단일/포트폴리오/fast 백테스트 엔진
│   ├── strategies/         # BB+RSI+EMA, 트렌드팔로우, 브레이크아웃 등
│   ├── grid_search.py      # 파라미터 전수 탐색
│   ├── metrics.py          # Sharpe, Calmar, MaxDD 등 성과 지표
│   ├── runner.py           # CLI 진입점
│   └── report_html.py      # HTML 리포트 생성
├── experiments/            # 40+ 백테스트 실험 스크립트
├── tests/                  # 220+ pytest 테스트
├── analysis/               # 실험 결과 기록
└── data/                   # Parquet 주가 데이터
```

## 설치

```bash
git clone https://github.com/kangraemin/stock-bot.git
cd stock-bot
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 환경 변수

`.env` 파일에 설정:

```env
TELEGRAM_BOT_TOKEN=your-bot-token
TELEGRAM_CHAT_ID=your-chat-id
```

## 사용법

```bash
# 데이터 다운로드
python download.py

# 알림봇 실행
python alert.py

# 텔레그램 봇 리스너
python bot_listener.py

# 백테스트
python -m backtest.runner --symbol TQQQ --period 5y

# 그리드 서치
python -m backtest.runner --grid --symbols SOXL TQQQ --periods 1y 3y 5y

# 테스트
pytest tests/
```

## 배포

Oracle Cloud 인스턴스에서 cron + systemd로 운영:

```bash
# 알림봇 (매일 KST 06:00)
0 21 * * 0-4 cd ~/stock-bot && venv/bin/python alert.py

# 봇 리스너 (systemd 상시 실행)
systemctl start stock-bot-listener
```

## 핵심 백테스트 결론

30종류 실험, 4,500만 파라미터 조합 검증 결과:

- **BB+RSI+EMA**가 레버리지 ETF 최적 전략 (타 전략 대비 10배+ 수익)
- 보수적 RSI 임계값(buy < 25)이 OOS에서도 안정적
- 수익의 90%+가 오버나이트 발생 — 종가 매수/보유가 정답
- 강세장에서는 어떤 타이밍 전략도 Buy & Hold를 못 이김
- 매크로 레짐, VIX term, ATR sizing 등 복잡한 전략은 OOS 대부분 과적합
- 8~9월 회피가 가장 실용적 알파 (파라미터 프리, 구현 간단)

> 실험 상세: `experiments/` 디렉토리 및 `analysis/INDEX.md` 참조

## 기술 스택

- **Python 3.14** / pandas / numpy
- **yfinance** — 주가 데이터
- **ta** — 기술적 지표 (RSI, BB, EMA, ATR)
- **Telegram Bot API** — urllib 직접 사용 (외부 라이브러리 없음)
- **pytest** — 220+ 테스트
