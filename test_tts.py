import edge_tts
import asyncio

# TEXT = "안녕! 오늘은 거실을 탐험해보자!"

# async def main():
#    communicate = edge_tts.Communicate(
#        TEXT,
#        "ko-KR-SunHiNeural"
#    )

#    await communicate.save("test.mp3")

# asyncio.run(main())

# print("음성 생성 완료")

async def speak(text):
    # 음성 선택 (이게 중요!)
    voice = "ko-KR-JiMinNeural"  # 어린 느낌₩
    
    # 톤/속도 조절
    rate = "+10%"   # 살짝 빠르게
    pitch = "+5Hz"  # 살짝 높게 (어린 느낌)
    
    communicate = edge_tts.Communicate(
        text, 
        voice,
        rate=rate,
        pitch=pitch
    )
    await communicate.save("test2.mp3")

asyncio.run(speak("안녕! 나는 시아야"))