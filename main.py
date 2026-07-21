import html
import json
import os
from datetime import datetime

import requests

TOPLIST_ID = "3778678"
DATA_FILE = "data.json"
REQUEST_TIMEOUT_SECONDS = 10
SONG_LIMIT = 50
TG_SONG_LIMIT = 30
MAX_HISTORY_DAYS = 90

WEATHER_MAP = {
    0: "☀️ 晴",
    1: "🌤 大部晴朗",
    2: "⛅ 多云",
    3: "☁️ 阴",
    45: "🌫 雾",
    48: "🌫 冻雾",
    51: "🌦 小毛毛雨",
    53: "🌦 中毛毛雨",
    55: "🌧 大毛毛雨",
    56: "🌧 小冻毛毛雨",
    57: "🌧 强冻毛毛雨",
    61: "🌧 小雨",
    63: "🌧 中雨",
    65: "🌧 大雨",
    66: "🌨 小冻雨",
    67: "🌨 强冻雨",
    71: "🌨 小雪",
    73: "❄️ 中雪",
    75: "❄️ 大雪",
    77: "🌨 雪粒",
    80: "🌦 小阵雨",
    81: "🌧 中阵雨",
    82: "⛈ 强阵雨",
    85: "🌨 小阵雪",
    86: "❄️ 强阵雪",
    95: "⛈ 雷雨",
    96: "⛈ 雷雨 + 小冰雹",
    99: "⛈ 雷雨 + 大冰雹",
}

def wind_direction(deg):
    if deg is None:
        return "未知风向"
    dirs = [
        "北风",
        "东北风",
        "东风",
        "东南风",
        "南风",
        "西南风",
        "西风",
        "西北风"
    ]
    return dirs[round(deg / 45) % 8]

def fetch_songs():
    url = f"https://music.163.com/api/playlist/detail?id={TOPLIST_ID}"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        resp = requests.get(
            url,
            headers=headers,
            timeout=REQUEST_TIMEOUT_SECONDS
        )
        resp.raise_for_status()
        data = resp.json()
        tracks = data.get("result", {}).get("tracks", [])
        songs = []
        for track in tracks[:SONG_LIMIT]:
            song_id = track.get("id")
            name = track.get("name") or "未知歌曲"
            artists = track.get("ar") or track.get("artists") or []
            artist = (
                " / ".join(
                    a.get("name", "")
                    for a in artists
                    if a.get("name")
                )
                or "未知歌手"
            )
            songs.append(
                {
                    "id": song_id,
                    "name": name,
                    "artist": artist,
                }
            )
        return songs
    except requests.RequestException as e:
        print("fetch_songs request error:", e)
    except ValueError as e:
        print("fetch_songs json error:", e)
    return []

def get_weather():
    try:
        url = "https://api.open-meteo.com/v1/forecast"
        latitude = float(os.environ["LATITUDE"])
        longitude = float(os.environ["LONGITUDE"])
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "timezone": "Asia/Shanghai",
            "current": (
                "temperature_2m,"
                "apparent_temperature,"
                "weather_code,"
                "wind_speed_10m,"
                "wind_direction_10m,"
                "relative_humidity_2m,"
                "pressure_msl"
            ),
            "daily": (
                "weather_code,"
                "temperature_2m_max,"
                "temperature_2m_min,"
                "precipitation_probability_max,"
                "sunrise,"
                "sunset"
            ),
            "forecast_days": 7,
        }
        response = requests.get(
            url,
            params=params,
            timeout=REQUEST_TIMEOUT_SECONDS
        )
        response.raise_for_status()
        data = response.json()
        cur = data.get("current", {})
        temp = cur.get("temperature_2m")
        feel = cur.get("apparent_temperature")
        code = cur.get("weather_code")
        wind = cur.get("wind_speed_10m")
        wind_dir = cur.get("wind_direction_10m")
        hum = cur.get("relative_humidity_2m")
        pressure = cur.get("pressure_msl")
        text = WEATHER_MAP.get(code, f"❓ 未知天气({code})")
        daily = data.get("daily", {})
        max_t = daily.get("temperature_2m_max", [])
        min_t = daily.get("temperature_2m_min", [])
        rain = daily.get("precipitation_probability_max", [])
        codes = daily.get("weather_code", [])
        forecast_days = min(
            3,
            len(max_t),
            len(min_t),
            len(rain),
            len(codes)
        )
        forecast_lines = []
        for i in range(forecast_days):
            w = WEATHER_MAP.get(codes[i], f"❓ 未知天气({codes[i]})")
            forecast_lines.append(
                f"D{i+1} {w} {min_t[i]}-{max_t[i]}°C 🌧{rain[i]}%"
            )
        forecast_text = "\n".join(forecast_lines) or "暂无预报"
        return (
            f"{text} {temp}°C（体感 {feel}°C）\n"
            f"💧 湿度 {hum}%\n"
            f"🌬 风速 {wind}km/h {wind_direction(wind_dir)}\n"
            f"🌪 气压 {pressure}hPa\n\n"
            f"📅 未来3天\n"
            f"{forecast_text}"
        )
    except KeyError as e:
        return f"缺少环境变量: {e}"
    except (requests.RequestException, ValueError) as e:
        print("weather error:", e)
        return "天气获取失败"

def load_history():
    if not os.path.exists(DATA_FILE):
        return {}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print("load_history error:", e)
        return {}

def save_history(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2
        )
        f.write("\n")

def song_key(song):
    song_id = song.get("id")
    if song_id is not None:
        return f"id:{song_id}"
    return (
        f"title:{song.get('name', '')}"
        f" - {song.get('artist', '')}"
    )

def normalize_history_keys(songs):
    keys = []
    for song in songs:
        if isinstance(song, dict):
            keys.append(song_key(song))
        else:
            keys.append(f"legacy:{song}")
    return keys

def compare(today, yesterday_keys):
    result = []
    previous_rank = {
        key: rank
        for rank, key in enumerate(yesterday_keys, 1)
    }
    for rank, song in enumerate(today, 1):
        key = song_key(song)
        old_index = previous_rank.get(key)
        if old_index is None:
            legacy_key = (
                f"legacy:{song['name']}"
                f" - {song['artist']}"
            )
            old_index = previous_rank.get(legacy_key)
        if old_index is None:
            trend = "🆕"
        elif rank < old_index:
            trend = "🔼"
        elif rank > old_index:
            trend = "🔽"
        else:
            trend = "➖"
        result.append(
            {
                "rank": rank,
                "trend": trend,
                "name": song["name"],
                "artist": song["artist"],
                "id": song["id"],
            }
        )
    return result

def song_link(song_id):
    return f"https://music.163.com/#/song?id={song_id}"

def write_readme(items, weather):
    html_items = []
    for item in items:
        url = html.escape(
            song_link(item["id"]),
            quote=True
        )
        text = html.escape(
            f"{item['name']} - {item['artist']}"
        )
        html_items.append(
            f"<li>{item['rank']} {item['trend']} "
            f"<a href='{url}'>{text}</a></li>"
        )
    escaped_weather = html.escape(weather)
    html_content = (
        "# 🎵 网易云热歌榜\n\n"
        f"🌤 天气：{escaped_weather}\n\n"
        f"更新时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        "<ul>\n"
        f"{chr(10).join(html_items)}"
        "\n</ul>\n"
    )
    with open(
        "README.md",
        "w",
        encoding="utf-8"
    ) as f:
        f.write(html_content)

def send_tg(songs, weather):
    token = os.environ.get("TG_TOKEN")
    chat_id = os.environ.get("TG_CHAT_ID")
    if not token or not chat_id:
        print("TG env missing")
        return
    msg = (
        f"🌤 天气：{html.escape(weather)}\n\n"
        "🎵 网易云热歌榜\n\n"
    )
    for i, song in enumerate(
        songs[:TG_SONG_LIMIT],
        1
    ):
        link = html.escape(
            song_link(song["id"]),
            quote=True
        )
        text = html.escape(
            f"{song['name']} - {song['artist']}"
        )
        msg += (
            f"{i}. <a href='{link}'>{text}</a>\n"
        )
    try:
        response = requests.post(
            f"https://api.telegram.org/"
            f"bot{token}/sendMessage",
            data={
                "chat_id": chat_id,
                "text": msg,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.RequestException as e:
        print("tg error:", e)

def main():
    today = fetch_songs()
    if not today:
        print("no data")
        return
    weather = get_weather()
    history = load_history()
    yesterday_key = (
        sorted(history.keys())[-1]
        if history
        else None
    )
    yesterday = (
        history.get(yesterday_key, [])
        if yesterday_key
        else []
    )
    yesterday_keys = normalize_history_keys(
        yesterday
    )
    ranked = compare(
        today,
        yesterday_keys
    )
    today_key = datetime.now().strftime(
        "%Y-%m-%d"
    )
    history[today_key] = today
    history = dict(
        sorted(history.items())[-MAX_HISTORY_DAYS:]
    )
    save_history(history)
    write_readme(
        ranked,
        weather
    )
    send_tg(
        today,
        weather
    )

if __name__ == "__main__":
    main()