from zoneinfo import available_timezones

# 列出所有可用的時區數量
print(len(available_timezones()))

# 檢查特定時區是否存在
print("Asia/Taipei" in available_timezones())
