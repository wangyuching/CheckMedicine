import os
from gtts import gTTS

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

# 建立用來存放音檔的資料夾
output_dir = "medicine_voice_prompts"
os.makedirs(output_dir, exist_ok=True)

print("開始生成語音檔案...")

for num, text in audio_texts.items():
    # lang='zh-TW' 確保使用台灣繁體中文發音
    tts = gTTS(text=text, lang='zh-TW', slow=False)
    filename = f"{num}.mp3"
    filepath = os.path.join(output_dir, filename)
    
    tts.save(filepath)
    print(f"已生成: {filepath}")

print("\n所有語音檔案生成完畢！")