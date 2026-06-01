import os
import asyncio
from edge_tts import Communicate

# 定義 11 條語音文本
audio_texts = {
    "01": "還沒到服用藥的時段，請放下藥盒，並放置於畫面中",
    "02": "請服用早餐時段的藥。完成後請將蓋子打開、藥盒放置在畫面中",
    "03": "請服用午餐時段的藥。完成後請將蓋子打開、藥盒放置在畫面中",
    "04": "請服用晚餐時段的藥。完成後請將蓋子打開、藥盒放置在畫面中",
    "05": "已服用完早餐時段的藥。請將蓋子打開、藥盒放置在畫面中",
    "06": "已服用完午餐時段的藥。請將蓋子打開、藥盒放置在畫面中",
    "07": "已服用完晚餐時段的藥。請將蓋子打開、藥盒放置在畫面中",
    "08": "準備服用早餐時段的藥。",
    "09": "準備服用午餐時段的藥。",
    "10": "準備服用晚餐時段的藥。",
    "11": "目前非服用藥的時段。"
}

# 建立存放音檔的資料夾
output_dir = "medicine_voice_prompts111"
os.makedirs(output_dir, exist_ok=True)

async def generate_audio():
    print("開始使用 Edge TTS 生成加速語音檔案...")
    
    for num, text in audio_texts.items():
        filepath = os.path.join(output_dir, f"{num}.mp3")
        
        # voice="zh-TW-HsiaoChenNeural" 代表台灣微軟女聲（曉臻）
        # rate="+25%" 代表加速 25% (也就是 1.25 倍速)
        communicate = Communicate(text, voice="zh-TW-HsiaoChenNeural", rate="+5%")
        
        await communicate.save(filepath)
        print(f"已生成 (1.25x): {filepath}")
        
    print("\n所有語音檔案生成完畢！")

# 執行非同步主程式
if __name__ == "__main__":
    asyncio.run(generate_audio())