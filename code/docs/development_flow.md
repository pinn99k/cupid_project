# SIA — MVP 개발 순서 (갈라쇼용)

> 작성일: 2026-05-10 | 개정: 2026-05-15  
> 대상: AI팀 + 풀스택 + 기계공  
> 목표: 갈라쇼 3분 시연 — 끊기지 않는 것이 전부다

**이 문서는 갈라쇼 MVP 구현 문서다.**  
최종 제품 비전(스마트폰 온디바이스, 실외 독립 동작)은 `SIA_TechFlow_Vision.md` 참고.  
MVP에서 비전과 의도적으로 다른 부분은 아래 표 참고.

| 항목         | MVP (이 문서)          | 최종 비전                |
| ---------- | ------------------- | -------------------- |
| 연산 중심      | 노트북 서버              | 스마트폰 온디바이스           |
| YOLO 실행 위치 | 노트북 (GPU/CPU)       | 폰 (TFLite / Core ML) |
| STT        | 브라우저 Web Speech API | 온디바이스 Whisper        |
| 네트워크       | 5GHz 핫스팟 LAN        | 모바일 데이터 + 클라우드       |
| 대시보드       | React (관람자 시연용)     | 부모 앱 (운영용)           |
| 지팡이 BLE/진동 | 제외                  | 포함                   |

---

## 목표 재정의

> "완벽한 파이프라인 구현"이 아니라 **"갈라쇼 3분 동안 끊기지 않는 시연"** 이 목표다.

|기준|기존|변경|
|---|---|---|
|우선순위|확장성, 동기화 정확도|시연 생존, 시청각 임팩트|
|실패 대응|코드로 예외 처리|환경 통제 + Fallback으로 우회|
|구현 방향|정석 아키텍처|동작하는 최소 구조|

---

## 핵심 결정사항

### 결정 1. 로컬 오디오 Fallback 전략 채택

**결정**: 실시간 LLM 생성 외에 대화 패턴 20개를 TTS mp3로 미리 생성해 서버에 저장. 대시보드에 숨긴 Fallback 버튼으로 즉시 재생 가능하게 유지.

**근거**: 갈라쇼 3분 시연 중 LLM API 지연 또는 네트워크 불안정으로 응답이 오지 않을 경우, 아이가 걷는 동안 침묵이 발생한다. 이는 프로젝트 핵심 가치(AI가 항상 함께한다)를 훼손하고 심사위원 신뢰를 잃는 가장 치명적인 실패 시나리오다.

**구조**: 실시간 LLM 성공 시 그게 나오고, 실패 시 Fallback 자동 전환. 대시보드에 숨긴 수동 트리거 버튼 추가.

```python
# 핵심 루프 구조
def demo_loop():
    while True:
        distance = get_latest_distance()
        # 1순위: 물리 센서 (AI 의존 없음, 지연 없음)
        if distance < 30.0:
            play_local_audio("warn_emergency.wav")
            continue
        # 2순위: YOLO 감지
        frame = get_latest_frame()
        objects = yolo_detect(frame)
        if "stairs" in objects:
            play_local_audio("warn_stairs.wav")
            continue
        # 3순위: 실시간 LLM (학습 모드)
        if learning_mode:
            narrate_with_llm(objects)  # 실패 시 Fallback 재생
```

**Fallback 카테고리 (20개)**

|카테고리|수량|예시|
|---|---|---|
|위험 경고|5|"멈춰!", "조심해, 앞에 뭔가 있어"|
|칭찬·격려|5|"잘하고 있어!", "대단해!"|
|세션 시작·종료|3|"시작하자!", "오늘 잘했어"|
|대기 버퍼|4|"잠깐만, 보고 있어", "기다려봐"|
|갈라쇼 전용|3|시나리오 맞춤 대사|

**생성 방법**: OpenAI TTS 스크립트 1회 실행으로 전부 생성. 이후 파일 재생만 하므로 추가 비용 없음.

**담당**

|작업|담당|난이도|
|---|---|---|
|TTS mp3 생성 스크립트|AI팀|★☆☆|
|`play_local(filename)` 재생 함수|AI팀|★☆☆|
|LLM 실패 시 Fallback 자동 전환|AI팀|★☆☆|
|대시보드 수동 트리거 버튼|풀스택|★☆☆|

---

### 결정 2. STT를 서버 Whisper → 브라우저 Web Speech API로 교체

**결정**: 서버에서 Whisper를 실행하는 대신, React 대시보드(브라우저)에서 Web Speech API로 STT 처리 후 텍스트만 서버로 전송.

**왜 이게 더 나은가 — 쉽게 설명:**

서버 Whisper 방식은 마이크로 녹음한 음성 파일(.wav)을 통째로 서버에 보내서 텍스트로 바꾼다. 파일을 만들고, 보내고, 처리하고, 결과를 돌려받는 과정이 있어서 2~4초 걸린다.

Web Speech API는 브라우저(Chrome)에 이미 내장된 음성 인식 기능이다. 마이크에 대고 말하면 브라우저가 실시간으로 텍스트를 만들어준다. 파일 저장도, 서버 전송도 필요 없다. 그래서 0.3~0.5초면 된다.

```
Whisper 흐름:  마이크 → wav 저장 → 서버 전송 → Whisper 처리 → 텍스트 반환 (2~4초)
Web Speech:   마이크 → 브라우저 실시간 인식 → 텍스트 → WebSocket → 서버 (0.3~0.5초)
```

갈라쇼에서 아이가 "앞에 뭐 있어?"라고 말했는데 4초 뒤에 응답이 오면 대화처럼 보이지 않는다. 0.5초면 자연스러운 대화가 된다.

**단점 및 유의사항**:

- Chrome에서만 안정적으로 동작한다. 시연 노트북 브라우저 사전 확인 필수.
- 대시보드를 띄운 노트북이 마이크를 직접 받아야 한다.
- 골전도 이어폰 마이크 → (Bluetooth) → 노트북 → 브라우저 경로를 사전 테스트해야 한다.
- 오프라인에서 동작하지 않는다. (MVP에서는 핫스팟 LAN이므로 문제 없음)

---

### 결정 3. LLM을 Groq API로 교체 검토

**결정**: OpenAI 대신 Groq API(Llama-3) 사용 검토. 최종 확정은 팀 판단.

**근거**: OpenAI gpt-4o-mini 평균 응답 시간은 1~3초. Groq API(Llama-3-8b)는 0.3~0.5초. 갈라쇼 시연에서 대화 응답 지연은 직접적인 임팩트 감소로 이어진다. Groq는 무료 티어 제공으로 비용 부담도 없다.

**유의사항**: Groq는 OpenAI와 API 스펙이 유사하지만 완전히 동일하지 않다. 프롬프트 결과물 품질 차이가 있을 수 있으므로 실제 대화 품질 비교 테스트 후 확정 권장. 모델명 등 스펙은 변경될 수 있으므로 Groq 공식 문서 확인 필요.

**판단 기준**: Phase 1 Step 1-5에서 OpenAI로 먼저 구현. 응답이 3초 초과하면 Groq 교체.

---

### 결정 4. 네트워크 격리 (5GHz 핫스팟 전용망)

**결정**: 갈라쇼 현장에서 공용 Wi-Fi 사용 금지. 시연자 스마트폰의 5GHz 핫스팟을 전용망으로 사용.

**네트워크 토폴로지**:

```
[시연자 스마트폰] ← 5GHz 핫스팟 제공 + 모바일 데이터(LLM API 호출용)
       │
       ├── ESP32-CAM 연결 (영상 스트리밍, 거리/버튼 HTTP POST)
       └── 노트북 연결 (서버 + 대시보드)
              │
              └── 노트북에서 LLM API 호출 → 스마트폰 모바일 데이터 경유 → 인터넷
```

**근거**: 갈라쇼 현장은 관람자 수십 명이 동일 Wi-Fi를 사용한다. 5GHz 핫스팟은 2.4GHz 대비 간섭이 적고, 1m 이내 폐쇄망 구성 시 안정성이 확보된다. 비용 없이 실행 가능하고 효과가 크다.

**사전 확인**: 시연자 스마트폰의 5GHz 핫스팟 지원 여부, 모바일 데이터 잔량.

---

### 결정 5. ESP32-CAM GPIO 핀 재배치

**왜 이게 필요한가 — 쉽게 설명:**

ESP32-CAM 보드는 카메라가 이미 많은 핀을 차지하고 있어서 자유롭게 쓸 수 있는 GPIO 핀이 거의 없다. 그런데 우리는 초음파 센서(HC-SR04P)에 2개, 버튼에 1개, 총 3개 핀이 추가로 필요하다.

다행히 이 보드에는 SD카드 슬롯용 핀(GPIO 12, 13, 14, 15)이 있는데, 우리 프로젝트에서 SD카드는 사용하지 않는다. 그래서 이 핀들을 초음파 센서와 버튼에 재활용하는 것이다.

**결정**:

|핀|원래 용도|재배치 용도|
|---|---|---|
|GPIO 12 또는 13|SD카드 슬롯|HC-SR04P Trig|
|GPIO 14 또는 15|SD카드 슬롯|HC-SR04P Echo|
|GPIO 2 또는 4|LED/Flash|버튼 입력|

**주의사항**:

- 펌웨어에 SD카드 초기화 코드가 남아있으면 핀 충돌이 발생한다. 반드시 제거해야 한다.
- 실제 보드에서 핀 배치 검증 필요 (기계공 담당).
- GPIO 2는 부트 모드와 관련이 있어 풀업/풀다운 주의.

---

## 시스템 구조 (확정)

```
ESP32-CAM (목걸이 디바이스)
  ├── MJPEG 영상 스트리밍 → Wi-Fi → 서버
  ├── HC-SR04P 거리 → HTTP POST → 서버
  └── 버튼 신호 → HTTP POST → 서버

골전도 이어폰
  └── 오디오 출력 ← Bluetooth ← 노트북

서버 (노트북, 프로토타입)
  ├── YOLO 객체 감지
  ├── YOLO bbox 후처리 → 방향(좌/정면/우) + 상대 거리(near/mid/far) 추출
  ├── HC-SR04P 정면 거리(cm) + YOLO 정면 객체 매칭
  ├── 위험 판단 (거리 < 30cm → 즉시 경고)
  ├── 로컬 오디오 즉시 재생 (1순위)
  ├── enriched 감지 결과 → LLM → 공간 묘사 → TTS (2순위)
  └── FastAPI + WebSocket → 대시보드

React 대시보드 (갈라쇼용)
  ├── Web Speech API → STT → WebSocket → 서버
  ├── 대화 말풍선 + 카메라 피드 + 단계 표시
  └── 숨긴 Fallback 버튼 (수동 오디오 트리거)
```

### YOLO 공간 정보 추출 (bbox 후처리)

YOLO는 객체 라벨과 바운딩 박스(bbox) 좌표만 반환한다. 방향이나 거리는 직접 제공하지 않는다. 하지만 bbox 좌표를 후처리하면 방향과 대략적 거리를 추출할 수 있다. 추가 모델이나 비용 없이 코드 몇 줄로 구현 가능하다.

**방향 추출 — bbox x좌표 기반**

카메라가 아이 몸에 고정되어 있으므로, 화면의 왼쪽은 현실의 왼쪽이다. 바운딩 박스의 가로 중심점이 화면 어디에 위치하는지로 방향을 판단한다.

```
화면 가로를 3등분:
|  왼쪽 (left)  |  정면 (center)  |  오른쪽 (right)  |
0%             33%              66%               100%

bbox 중심점 = (x + w/2) / 프레임_가로_픽셀
→ 33% 미만이면 "left", 33~66%면 "center", 66% 초과면 "right"
```

**거리 추정 — bbox 면적비 기반**

같은 물체라도 가까이 있으면 카메라에 크게 찍히고, 멀리 있으면 작게 찍힌다. 바운딩 박스가 화면에서 차지하는 면적 비율로 대략적 거리를 추정한다.

```
면적비 = (bbox_w × bbox_h) / (프레임_가로 × 프레임_세로)

면적비 > 20%  → "near" (가까움)  — 화면의 1/5 이상 차지
면적비 5~20%  → "mid"  (중간)
면적비 < 5%   → "far"  (멀음)   — 화면에 작게 보임
```

이 수치는 정확한 cm 거리가 아니라 "가깝다/멀다" 수준의 추정이다. 정확한 거리가 필요한 위험 경고는 HC-SR04P 초음파 센서를 사용한다.

**초음파 + YOLO 결합**

HC-SR04P는 정면 직선 거리(cm)를 정확히 측정하지만 대상이 뭔지는 모른다. YOLO는 대상이 뭔지 아는데 거리는 모른다. 이 둘을 합치면 "정면 45cm에 의자가 있다"가 된다.

매칭 방법: 초음파는 정면만 측정하므로, YOLO 결과 중 "center" 영역(33~66%)에 있는 객체와 매칭한다. 정면에 객체가 여러 개면 bbox가 가장 큰(가장 가까운) 객체와 매칭한다.

**후처리 코드**

```python
def enrich_yolo_results(detections, frame_w, frame_h, ultrasonic_cm):
    enriched = []
    center_objects = []

    for det in detections:
        cx = (det.x + det.w / 2) / frame_w       # 가로 중심 비율
        area = (det.w * det.h) / (frame_w * frame_h)  # 면적비

        # 방향 판단
        if cx < 0.33:
            direction = "left"
        elif cx > 0.66:
            direction = "right"
        else:
            direction = "center"
            center_objects.append((det.label, area))

        # 거리 추정
        if area > 0.20:
            distance_est = "near"
        elif area < 0.05:
            distance_est = "far"
        else:
            distance_est = "mid"

        enriched.append({
            "label": det.label,
            "direction": direction,
            "distance_est": distance_est,
            "bbox_ratio": round(area, 2),
            "confidence": round(det.conf, 2)
        })

    # 초음파 매칭: 정면 객체 중 가장 큰 것
    ultrasonic_target = None
    if center_objects:
        ultrasonic_target = max(center_objects, key=lambda x: x[1])[0]

    return {
        "objects": enriched,
        "ultrasonic_cm": ultrasonic_cm,
        "ultrasonic_target": ultrasonic_target
    }
```

**한계 (팀 전원 인지 필요)**

- 거리 추정은 "대략"이다. "2m인지 3m인지"는 구분 못 한다. 위험 경고는 반드시 초음파 센서 cm 값을 사용한다.
- 방향은 카메라 기준이다. 아이가 몸을 돌리면 "왼쪽"이 바뀔 수 있다. 카메라가 몸에 고정되어 있으면 실용적으로 문제 없다.
- YOLO는 학습된 클래스(COCO 80종)만 인식한다. "바닥 턱", "맨홀 뚜껑" 같은 건 감지 못 한다. 이것도 초음파 센서가 보완한다.
- 초음파 센서는 정면 좁은 범위만 측정한다. 좌우 물체의 정확한 cm 거리는 bbox 면적비 추정에 의존한다.
- MVP에서는 이 조합으로 충분하다. 객체별 정밀 거리가 필요해지면 단안 깊이 추정(MiDaS) 등을 추후 검토한다.

**제외 확정**

|항목|이유|
|---|---|
|지팡이 BLE / 진동|3단계 교육은 카메라 + AI만으로 진행|
|서버 Whisper STT|Web Speech API로 대체, 속도 우위|
|복잡한 비동기 동기화|시연자 연기로 타이밍 통제|
|부모 앱|데모 범위 초과|
|커스텀 모델 학습|학부 수준 초과|

---

## 인터페이스 계약

> **Phase 1 시작 전에 팀 전체가 이 포맷에 합의해야 한다.**  
> 변경 시 팀 전체 공유 후 수정.

### YOLO 후처리 → 서버 내부 (LLM 입력용)

YOLO 후처리 결과. 이 데이터가 LLM 프롬프트에 들어가서 시아의 공간 묘사를 생성한다.

```json
{
  "objects": [
    {
      "label": "person",
      "direction": "left",
      "distance_est": "near",
      "bbox_ratio": 0.31,
      "confidence": 0.92
    },
    {
      "label": "chair",
      "direction": "center",
      "distance_est": "mid",
      "bbox_ratio": 0.12,
      "confidence": 0.87
    }
  ],
  "ultrasonic_cm": 45,
  "ultrasonic_target": "chair"
}
```

|필드|설명|
|---|---|
|`label`|YOLO 인식 객체명 (COCO 80종)|
|`direction`|bbox x좌표 기반 방향 (left / center / right)|
|`distance_est`|bbox 면적비 기반 거리 추정 (near / mid / far)|
|`bbox_ratio`|화면 점유율 원본값|
|`confidence`|YOLO 인식 신뢰도 (낮으면 LLM이 "뭔가 있는 것 같아"로 톤 조절)|
|`ultrasonic_cm`|HC-SR04P 실측 정면 거리|
|`ultrasonic_target`|초음파 거리와 매칭된 정면 객체 (없으면 null)|

### AI → 대시보드 (WebSocket push)

```json
{
  "type": "danger",
  "object": "stairs",
  "direction": "center",
  "distance_cm": 45,
  "message": "멈춰, 앞에 계단이야",
  "stage": 1,
  "audio_file": "warn_stairs.wav",
  "timestamp": 1715000000000
}
```

```json
{
  "type": "narration",
  "objects": [
    {"label": "person", "direction": "left", "distance_est": "near"},
    {"label": "chair", "direction": "center", "distance_est": "mid"}
  ],
  "message": "왼쪽 가까이에 사람이 있어. 정면에 의자가 보여, 45cm쯤이야.",
  "stage": 2,
  "timestamp": 1715000000000
}
```

### 대시보드 → 서버 (WebSocket or HTTP POST)

```json
{ "event": "start_learning", "stage": 1 }
{ "event": "stop_learning" }
{ "event": "fallback", "audio_file": "fallback_01.wav" }
{ "stt_text": "앞에 뭐 있어?" }
```

`timestamp` 필드를 추가한 이유: 지연 측정용. 서버에서 메시지 생성 시각과 대시보드 수신 시각의 차이로 파이프라인 지연을 측정할 수 있다.

---

## 지연 측정 방법

완료 기준에 "200ms 이내", "3초 이내" 등의 수치가 있다. 측정 없이 "된 것 같다"로 넘어가면 안 된다.

```python
# 모든 파이프라인 입구/출구에 타임스탬프 로그 추가
import time

def log_latency(label):
    print(f"[LATENCY] {label}: {time.time() * 1000:.0f}ms")

# 사용 예시
log_latency("yolo_start")
objects = yolo_detect(frame)
log_latency("yolo_end")        # 차이 = YOLO 처리 시간

log_latency("llm_start")
response = call_llm(prompt)
log_latency("llm_end")         # 차이 = LLM 응답 시간
```

Phase 1 완료 시점에 각 구간 지연을 최소 5회 측정하고 평균값을 기록한다.

---

## 전체 흐름

```
Phase 0   환경 세팅                Day 1~2
Phase 1   파이프라인 최소 연결      Week 1     ← 전체의 핵심
Phase 2   하드웨어 연결            Week 2
Phase 3   기능 완성               Week 3
Phase 4   갈라쇼 준비             Week 4
```

---

## Phase 0 — 환경 세팅

**목표**: 모든 팀원이 동일한 환경에서 코드 실행 가능

|#|작업|STATUS|
|---|---|---|
|0-1|Python 가상환경 + 패키지 설치|⬜ TODO|
|0-2|API 키 .env 설정 + .gitignore 확인|⬜ TODO|
|0-3|YOLO 모델 다운로드 확인|⬜ TODO|
|0-4|웹캠 / 마이크 / 오디오 출력 동작 확인|⬜ TODO|
|0-5|Arduino IDE + ESP32 패키지 설치|⬜ TODO|
|0-6|ESP32-CAM 예제 업로드 + 브라우저 영상 확인|⬜ TODO|
|0-7|GitHub 레포 구조 push|⬜ TODO|
|0-8|**인터페이스 계약 JSON 포맷 팀 합의**|⬜ TODO|

**완료 기준**: 전원 패키지 설치 에러 없음 / ESP32-CAM 영상 브라우저 확인 / JSON 포맷 합의 완료

---

## Phase 1 — 파이프라인 최소 연결

**목표**: 노트북 웹캠으로 소리가 나는 루프 완성. ESP32-CAM 없이 먼저.

|Step|작업|1차 담당|STATUS|
|---|---|---|---|
|1-1|웹캠 → YOLO → bbox 원본 출력|AI팀|⬜ TODO|
|1-2|YOLO bbox 후처리 → 방향 + 거리 추정 enriched JSON 생성|AI팀|⬜ TODO|
|1-3|enriched JSON + 초음파 거리 → 위험 판단 룰|AI팀|⬜ TODO|
|1-4|위험 판단 → 로컬 오디오 즉시 재생|AI팀|⬜ TODO|
|1-5|로컬 Fallback 오디오 파일 사전 생성|AI팀|⬜ TODO|
|1-6|enriched JSON → LLM → TTS 공간 묘사 ("왼쪽 가까이 사람, 정면 45cm 의자")|AI팀 + 풀스택|⬜ TODO|
|1-7|Web Speech API → WebSocket → LLM → TTS|풀스택|⬜ TODO|
|1-8|FastAPI + WebSocket 서버 구조|풀스택|⬜ TODO|
|1-9|React 대시보드 기본 구조 + Fallback 버튼|풀스택|⬜ TODO|

> **"전원 같이"의 의미**: 경계 없이 돕되, 각 Step에 1차 담당자가 있어야 아무도 안 하는 상황을 방지한다. 1차 담당이 아닌 사람도 적극 참여.

**완료 기준** (측정 방법 포함)

|기준|목표치|측정 방법|
|---|---|---|
|웹캠 장애물 → 로컬 오디오|200ms 이내|`log_latency()` YOLO 감지 ~ 오디오 재생 시작|
|LLM 응답 → TTS 음성|3초 이내|`log_latency()` LLM 호출 ~ TTS 재생 시작|
|브라우저 음성 → 시아 응답|5초 이내|Web Speech 결과 전송 ~ TTS 재생 시작|
|WebSocket 감지 결과 수신|실시간|대시보드에 메시지 표시 확인|
|Fallback 버튼 → 오디오|즉시|버튼 클릭 ~ 오디오 재생 시작|

**다음 Phase 유의사항**

- Phase 1 완료 전 Phase 2 진입 금지
- LLM 응답이 3초 초과하면 Groq API 교체 검토 (결정 3 참고)
- 위험 감지 루프와 대화 루프 동시 동작 시 충돌 여부 반드시 확인 후 진행
- 각 구간 지연 5회 측정 → 평균값 기록

---

## Phase 2 — 하드웨어 연결

**목표**: 웹캠을 ESP32-CAM으로 교체, HC-SR04P 연결

|Step|작업|담당|STATUS|
|---|---|---|---|
|2-1|ESP32-CAM 스트리밍 펌웨어 (GPIO 재배치 포함)|기계공|⬜ TODO|
|2-2|HC-SR04P 배선 + 거리 측정 펌웨어|기계공|⬜ TODO|
|2-3|버튼 GPIO 연결 + 신호 전송 펌웨어|기계공|⬜ TODO|
|2-4|서버 ESP32-CAM 영상 수신으로 교체|AI / 풀스택|⬜ TODO|
|2-5|서버 거리 데이터 수신 + YOLO 결합|AI|⬜ TODO|
|2-6|버튼 신호 → 서버 모드 전환|풀스택|⬜ TODO|
|2-7|5GHz 핫스팟 환경 전체 연결 테스트|같이|⬜ TODO|

**완료 기준**

|기준|목표치|
|---|---|
|ESP32-CAM 영상으로 YOLO 동작|정상 감지|
|거리 30cm 이내 → 로컬 경고|즉시 재생|
|버튼 → 학습 모드 전환|정상 동작|
|핫스팟 환경 스트리밍|10fps 이상|

**다음 Phase 유의사항**

- GPIO 핀 충돌 여부는 실물 보드에서만 확인 가능. 펌웨어 먼저 업로드 후 시리얼 로그로 확인.
- Wi-Fi 지연으로 프레임 드롭 발생 시 FRAMESIZE_QVGA(320x240)로 해상도 낮춰서 재테스트.
- 거리 측정값이 불안정하면 최근 3회 평균값 사용 검토.

---

## Phase 3 — 기능 완성

**목표**: 3단계 커리큘럼 동작, 대시보드 완성

|Step|작업|담당|STATUS|
|---|---|---|---|
|3-1|3단계별 LLM 프롬프트 완성|AI|⬜ TODO|
|3-2|상황 분기 (일반/위험/감정케어/미션성공)|AI|⬜ TODO|
|3-3|React 대시보드 완성 (말풍선 + 카메라 + 단계)|풀스택|⬜ TODO|
|3-4|Web Speech API 브라우저 STT 연동|풀스택|⬜ TODO|
|3-5|갈라쇼 Fallback 오디오 20개 완성|AI|⬜ TODO|
|3-6|전체 파이프라인 엔드투엔드 테스트|같이|⬜ TODO|

**완료 기준**

- 단계별 시아 말투 차이 확인
- 위험/일반/감정 분기 정상 동작
- 대시보드 실시간 대화 + 카메라 피드
- Web Speech API 한국어 인식 정상
- Fallback 버튼 → 오디오 즉시 재생

**다음 Phase 유의사항**

- Web Speech API는 Chrome에서만 안정적으로 동작. 시연 노트북 브라우저 사전 확인.
- 프롬프트 품질은 실제 아이 발화 패턴(짧고 불완전한 문장)으로 테스트해야 정확히 평가 가능.
- Fallback 오디오 버튼은 대시보드에서 시각적으로 숨기되 운영자는 인지하고 있어야 함.

---

## Phase 4 — 갈라쇼 준비

**목표**: 시연 3분 연속 성공

|Step|작업|STATUS|
|---|---|---|
|4-1|갈라쇼 시나리오 기반 반복 테스트 (5회 이상)|⬜ TODO|
|4-2|노트북 절전/업데이트/화면보호기 비활성화|⬜ TODO|
|4-3|5GHz 핫스팟 현장 환경 테스트|⬜ TODO|
|4-4|시연 코스 세팅 (카메라 고정 위치, 장애물 배치)|⬜ TODO|
|4-5|드레스 리허설 (안대 착용 + 전체 흐름)|⬜ TODO|

**완료 기준**

- 장애물 감지 → 경고 5회 연속 성공
- 전체 시나리오 3분 이내 끊김 없이 완주
- LLM 실패 시 Fallback 자동 전환 확인
- 대시보드 갈라쇼 화면 정상 출력

---

## 역할 분배 요약

### Phase 1 — 전원 같이 (1차 담당 배정 있음)

경계 없이 소리 나는 루프 하나 뚫는 게 목표. 단, 각 Step에 1차 담당자가 있어야 "아무도 안 하는" 상황을 방지한다.

### Phase 2부터 분리

|파트|내용|
|---|---|
|AI 우선|YOLO + 거리 결합, 프롬프트 설계, Fallback 오디오 생성|
|풀스택 우선|FastAPI + WebSocket, React 대시보드, Web Speech API|
|기계공 우선|ESP32-CAM 펌웨어, HC-SR04P 배선, GPIO 재배치, 하우징|

### 반드시 같이

- Phase 1 전체
- Phase 0-8 인터페이스 계약 JSON 포맷 합의
- Phase 2 Step 2-7 통합 테스트
- Phase 4 드레스 리허설

---

## STATUS 범례

```
⬜ TODO         아직 시작 안 함
🔵 IN PROGRESS  진행 중
✅ DONE         완료 및 검증
❌ BLOCKED      선행 작업 미완료 or 이슈 발생
⚠️ REVIEW       완료했으나 팀 검토 필요
```

---

_— 문서 끝 —_