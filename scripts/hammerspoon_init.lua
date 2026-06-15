--[[============================================================================
 SIA 시연용 — 골전도 이어폰 미디어 키(볼륨/재생) → 서버 마이크 토글

 ⚠️ 가운데(전원) 버튼은 bluetoothd 로그에 아무 신호도 안 보내므로 서버 로그로는
    감지 불가(실측 확인). 대신 '시스템 미디어 키'(볼륨 +/-, 재생/일시정지)는
    Hammerspoon 이 가로챌 수 있다. 이 스크립트는 그 키를 잡아 서버의
    /api/toggle_recording 으로 HTTP 요청을 보낸다(=마이크 녹음 토글).

 장점:
 - 화면 포커스(어느 앱이 앞에 있든)와 무관하게 동작 (HTTP 직접 호출).
 - Chrome 을 앞으로 안 둬도 됨 → "터미널 보고 있으면 안 됨" 문제 없음.

 ─────────────────────────────────────────────────────────────────────────────
 설치/활성화
 ─────────────────────────────────────────────────────────────────────────────
 1. Hammerspoon 설치(이미 됨): brew install --cask hammerspoon
 2. 접근성 권한: 시스템 설정 → 개인정보 보호 및 보안 → 손쉬운 사용 →
    Hammerspoon 체크 (없으면 키 가로채기 불가!)
 3. 이 파일을 ~/.hammerspoon/init.lua 로 저장(이미 됨).
 4. Hammerspoon 메뉴바(망치) → Reload Config.
 5. "SIA 토글 준비됨" 알림이 뜨면 성공.

 ─────────────────────────────────────────────────────────────────────────────
 사용
 ─────────────────────────────────────────────────────────────────────────────
 - 서버(main.py)가 localhost:8000 에서 돌고 있어야 함(MANUAL_RECORDING_MODE=true).
 - 이어폰 '볼륨 +' 또는 '볼륨 -' (혹은 '재생/일시정지')를 누르면 → 녹음 토글.
 - 다시 누르면 → 녹음 종료 → STT/응답.
 - 토글 일시정지/재개: Cmd+Opt+H (그동안 볼륨키는 정상 음량 조절로 돌아감).

 ─────────────────────────────────────────────────────────────────────────────
 가운데 버튼이 무슨 키를 내는지 확인하기 (선택)
 ─────────────────────────────────────────────────────────────────────────────
 - DEBUG=true 상태에서 Hammerspoon 메뉴바 → Console 을 열고,
   가운데 버튼을 눌러본다. 콘솔에 [MicToggle] key=XXX 가 찍히면
   그 XXX 를 아래 TRIGGER_KEYS 에 추가하면 가운데 버튼도 토글이 된다.
 - 아무것도 안 찍히면 그 버튼은 OS 로 신호가 안 오는 것(=볼륨키를 쓰세요).
============================================================================]]--

-- ── 설정 ────────────────────────────────────────────────────────────────────
local TOGGLE_URL = "http://localhost:8000/api/toggle_recording"
local DEBUG      = true   -- 콘솔에 눌린 미디어 키 출력(확인 후 false 권장)
local KEYLOG     = "/tmp/hs_mediakeys.log"  -- 눌린 미디어 키를 파일로도 기록(진단용)

-- hs CLI(터미널에서 hs -c "...") 사용을 위한 IPC 모듈 로드.
pcall(function() require("hs.ipc") end)

-- 미디어 키 1건을 파일에 기록(어떤 키가 들어오는지 터미널에서 확인 가능).
local function logKey(line)
    local f = io.open(KEYLOG, "a")
    if f then
        f:write(os.date("%H:%M:%S ") .. line .. "\n")
        f:close()
    end
end

-- 이 미디어 키들을 누르면 녹음 토글(+ 해당 키 소비). 가운데 버튼이 PLAY 를 내면
-- PLAY 가 잡혀 토글된다. 볼륨키도 토글로 쓴다(이어폰에 누를 버튼이 그것뿐이라).
local TRIGGER_KEYS = {
    SOUND_UP   = true,
    SOUND_DOWN = true,
    PLAY       = true,   -- 재생/일시정지(가운데 버튼 후보)
    PLAYPAUSE  = true,
}

-- ── 상태 ────────────────────────────────────────────────────────────────────
local enabled = true
local mediaKeyTap = nil
local lastFire = 0          -- 디바운스(중복 토글 방지)
local DEBOUNCE = 0.6        -- 초

-- ── 토글 요청 ────────────────────────────────────────────────────────────────
local function sendToggle()
    hs.http.asyncPost(TOGGLE_URL, "", {}, function(status, body)
        if DEBUG then
            print(string.format("[MicToggle] toggle HTTP status=%s body=%s",
                tostring(status), tostring(body)))
        end
        if status ~= 200 then
            hs.notify.new({
                title = "SIA 토글 실패",
                informativeText = "서버 응답 " .. tostring(status) .. " — main.py 실행 중인지 확인",
            }):send()
        end
    end)
end

-- ── 미디어 키 핸들러 ─────────────────────────────────────────────────────────
-- 반환값: true → 이벤트 소비(볼륨/재생 안 바뀜) / false → 통과(정상 동작)
local function handleSystemKey(event)
    if not enabled then
        return false
    end

    local ok, data = pcall(function() return event:systemKey() end)
    if not ok or not data or not data.key then
        return false
    end
    local key = data.key

    -- 모든 미디어 키를 콘솔+파일에 기록(가운데 버튼이 무슨 키 내는지 확인용).
    local info = string.format("key=%s down=%s repeat=%s",
        tostring(key), tostring(data.down), tostring(data["repeat"]))
    if DEBUG then print("[MicToggle] " .. info) end
    logKey(info)

    -- 우리가 토글로 쓰는 키가 아니면 그대로 통과(정상 볼륨/재생).
    if not TRIGGER_KEYS[key] then
        return false
    end

    -- 키 '누름(down)' + '비반복'에서만 1회 토글. 디바운스로 중복 방지.
    if data.down and not data["repeat"] then
        local now = hs.timer.secondsSinceEpoch()
        if (now - lastFire) >= DEBOUNCE then
            lastFire = now
            if DEBUG then print("[MicToggle] " .. key .. " → 녹음 토글 요청") end
            sendToggle()
        elseif DEBUG then
            print("[MicToggle] " .. key .. " (디바운스로 무시)")
        end
    end
    -- 토글로 쓰는 키는 항상 소비(볼륨/재생이 같이 바뀌지 않게).
    return true
end

-- ── 이벤트 탭 시작 ───────────────────────────────────────────────────────────
mediaKeyTap = hs.eventtap.new(
    { hs.eventtap.event.types.systemDefined },
    handleSystemKey
)
mediaKeyTap:start()

-- ── 일시정지/재개 (Cmd+Opt+H) ────────────────────────────────────────────────
hs.hotkey.bind({ "cmd", "alt" }, "H", function()
    enabled = not enabled
    local msg = enabled and "활성화" or "일시 정지(볼륨키 정상 동작)"
    print("[MicToggle] enabled=" .. tostring(enabled))
    hs.notify.new({ title = "SIA 토글", informativeText = "스크립트 " .. msg }):send()
end)

-- ── 시작 알림 ────────────────────────────────────────────────────────────────
hs.notify.new({
    title = "SIA 토글 준비됨",
    informativeText = "이어폰 볼륨/재생 키 → 녹음 토글 · 끄기 Cmd+Opt+H",
}):send()

print("[MicToggle] init.lua 로드 완료 — URL=" .. TOGGLE_URL ..
      ", DEBUG=" .. tostring(DEBUG))
