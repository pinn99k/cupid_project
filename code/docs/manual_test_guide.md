# 수동 테스트 시나리오 (노트북 단독)

> 기준: **현재 빌드**(Phase 3 통합 전). ESP32 없이 노트북 웹캠·마이크·스피커로 테스트.
> ⚠️ 현재는 호출어 게이팅이 **아직 미적용** → 모든 발화가 LLM을 호출(quota 주의).

---

## 0. 사전 준비

### 0-1. `.env` 키 (필수)
```
GEMINI_API_KEY=...      # TTS. 비어 있으면 서버가 import 단계에서 죽음(tts.py)
GROQ_API_KEY=...        # LLM (LLM_PROVIDER에 맞는 키)
LLM_PROVIDER=groq
LLM_MODEL=llama-3.3-70b-versatile
```

### 0-2. 환경/패키지
```powershell
cd D:\House\CUPID_pj\cupid_project
.\venv\Scripts\Activate.ps1
python -c "from google import genai; import cv2, sounddevice; print('deps OK')"
```

### 0-3. (선택) Fallback 음원 — 위험경고/운영자버튼용
```powershell
python audio/generate_fallback.py    # GEMINI quota 사용, ~2.5분
```
> 안 돌리면: **대화/묘사 음성은 정상**(Gemini 즉석 생성), **위험경고·운영자버튼 음원만 무음**.

---

## 1. 부팅

터미널 A — 서버:
```powershell
python main.py
```
**기대 로그:** `[SIA] 초기화 완료. 프레임 루프 + AI 루프 + 음성 파이프라인 시작.`
- 웹캠 LED 켜짐 / `[VoicePipeline] 파이프라인 시작`

점검: 브라우저 `http://localhost:8000/preflight` → 항목 `true` 확인.
영상: `http://localhost:8000/video_feed` → 웹캠 화면.

터미널 B — 대시보드:
```powershell
cd dashboard
npm install   # 처음 1회
npm run dev
```
→ 표시된 주소(보통 `http://localhost:5173`) 접속.

**PASS 기준:** 대시보드 우상단 연결 상태 "연결됨", 카메라 영상 보임.

---

## 시나리오 1 — 대화 (Stage 1)

| 단계 | 행동 | 기대 결과 |
|------|------|----------|
| 1 | 마이크에 "안녕 시아야" | 채팅에 내 말(오른쪽) → 시아 응답(왼쪽) + 스피커 음성 |
| 2 | "오늘 날씨 어때?" 등 잡담 | 2문장 이내 응답 |
| 3 | 대시보드 관찰 | `listening→processing→responding→listening` 상태 전환 |

**PASS:** 말→텍스트→응답→음성이 한 바퀴 도는가.
**알려진 동작:** 현재는 "시아야" 없이도 응답함(게이팅 Phase 3 전).

---

## 시나리오 2 — 화면 분석 / 자동 묘사 (Stage 2)

| 단계 | 행동 | 기대 결과 |
|------|------|----------|
| 1 | 대시보드에서 **Stage 2(학습) 시작** | `ack` 수신, 카메라 오버레이에 탐지 박스 |
| 2 | 웹캠 앞에 **사람/의자/컵** 등 비추기 | YOLO 탐지 → 잠시 후 시아가 **자동 묘사**("왼쪽에 사람이...") + 음성 |
| 3 | 물체 바꾸기 | 장면 바뀌면 새 묘사(쿨다운 ~20초) |

**PASS:** 웹캠 물체를 YOLO가 잡고, LLM 묘사가 음성으로 나오는가.
**참고:** 묘사는 **자동**(질문 아님). 질문 기반 응답은 Phase 3.

---

## 시나리오 3 — 위험 감지 (Stage 3)

| 단계 | 행동 | 기대 결과 |
|------|------|----------|
| 1 | 대시보드에서 **Stage 3 시작** | 위험 판단 활성 |
| 2 | 웹캠에 **가까이**(크게) 다가가기(사람) | YOLO "near person" → 대시보드 `danger` 배지 + 빨간 표시 |
| 3 | 위험 음성 | `warn_person.wav` 재생 (※ **음원 생성했을 때만**, 아니면 무음+로그 "파일 없음") |

**PASS:** 가까운 사람에 위험 경고가 대시보드에 뜨는가.
**한계(노트북):** 초음파 없음 → **거리 기반 emergency는 안 뜸**(YOLO-near만). 초음파 테스트는 `tools/mock_device.py` 또는 실칩 필요.

---

## 시나리오 4 — 운영자 Fallback / 세션 리셋

| 단계 | 행동 | 기대 결과 |
|------|------|----------|
| 1 | 대시보드 "운영자 Fallback" 펼쳐 버튼 클릭 | 해당 사전녹음 재생(※ 음원 있을 때) |
| 2 | **세션 중지/새 세션** | 채팅·상태 리셋, `ack` |

---

## 알려진 한계 (현재 빌드)

| 항목 | 상태 |
|------|------|
| "시아야" 호출어 게이팅 | ⏸️ 미적용 — 모든 발화가 LLM 호출 (**quota 빨리 소진 주의**) |
| 질문→화면분석→답변 통합(VQA) | ⏸️ Phase 3 |
| 초음파 거리 위험 | ⏸️ 디바이스/mock 필요 |
| 위험경고·운영자 음원 | A0(`generate_fallback.py`) 실행해야 소리남 |

---

## 트러블슈팅

| 증상 | 원인 / 해결 |
|------|------------|
| `ModuleNotFoundError: google` | `pip install -r requirements.txt` (venv에서) |
| 부팅 즉시 죽음(tts) | `.env`의 `GEMINI_API_KEY` 비었음 |
| LLM 응답 없음/429 | LLM 키 누락 또는 무료 quota 초과 → 잠시 후/다른 키 |
| 위험·버튼 무음 | `python audio/generate_fallback.py` 실행 |
| 웹캠 안 잡힘 | `.env` `WEBCAM_INDEX`(0=내장, 1+=외장) 조정 |
| 마이크 안 잡힘 | `python scripts/check_devices.py`로 인덱스 확인 → `MIC_DEVICE_INDEX` |
| 음성 인식 잘 안 됨 | 조용한 환경, 또렷하게. (Google 무료 STT) |
