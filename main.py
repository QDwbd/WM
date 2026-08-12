import html
import json
import os
from datetime import datetime, timezone, timedelta

import requests

TOPLIST_ID = "3778678"
DATA_FILE = "data.json"
REQUEST_TIMEOUT_SECONDS = 10
SONG_LIMIT = 50
TG_SONG_LIMIT = 30
MAX_HISTORY_DAYS = 90


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
        "西北风",
    ]
    return dirs[round(deg / 45) % 8]


def fetch_songs():
    url = f"https://music.163.com/api/playlist/detail?id={TOPLIST_ID}"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)
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
                    a.get("name", "") for a in artists if a.get("name")
                )
                or "未知歌手"
            )
            songs.append({"id": song_id, "name": name, "artist": artist})
        return songs
    except requests.RequestException as e:
        print("fetch_songs request error:", e)
    except ValueError as e:
        print("fetch_songs json error:", e)
    return []


def get_qweather(key, location):
    base = "https://k26hf28ja4.re.qweatherapi.com/v7/weather"
    common = {"location": location, "key": key, "lang": "zh"}

    now_resp = requests.get(
        f"{base}/now",
        params=common,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    now_resp.raise_for_status()
    now_data = now_resp.json()
    if now_data.get("code") != "200":
        raise ValueError(f"QWeather now code {now_data.get('code')}")

    daily_resp = requests.get(
        f"{base}/7d",
        params=common,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    daily_resp.raise_for_status()
    daily_data = daily_resp.json()
    if daily_data.get("code") != "200":
        raise ValueError(f"QWeather daily code {daily_data.get('code')}")

    now = now_data["now"]
    temp = now.get("temp")
    feel = now.get("feelsLike")
    weather_text = now.get("text", "未知")
    wind = now.get("windSpeed")
    wind_dir = int(now.get("wind360", 0)) if now.get("wind360") else None
    hum = now.get("humidity")
    pressure = now.get("pressure")

    forecast_lines = []
    for i, day in enumerate(daily_data.get("daily", [])[:3], start=1):
        forecast_lines.append(
            f"D{i} {day.get('textDay', '未知')} "
            f"{day.get('tempMin')}-{day.get('tempMax')}°C"
        )

    forecast_text = "\n".join(forecast_lines) or "暂无预报"

    return (
        f"🌤 天气：{weather_text}\n"
        f"🌡 温度：{temp}°C（体感 {feel}°C）\n"
        f"💧 湿度：{hum}%\n"
        f"🌬 风速：{wind}km/h {wind_direction(wind_dir)}\n"
        f"🌪 气压：{pressure}hPa\n\n"
        f"📅 未来3天\n"
        f"{forecast_text}"
    )


def get_weather():
    key = os.environ.get("WEATHER_API_KEY")
    location = os.environ.get("WEATHER_LOCATION")

    if not key or not location:
        return "缺少天气环境变量: WEATHER_API_KEY/WEATHER_LOCATION"

    try:
        return get_qweather(key, location)
    except Exception as e:
        print("qweather error:", e)
        return f"天气获取失败: {e}"


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
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def song_key(song):
    song_id = song.get("id")
    if song_id is not None:
        return f"id:{song_id}"
    return f"title:{song.get('name', '')} - {song.get('artist', '')}"


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
    previous_rank = {key: rank for rank, key in enumerate(yesterday_keys, 1)}
    for rank, song in enumerate(today, 1):
        key = song_key(song)
        old_index = previous_rank.get(key)
        if old_index is None:
            legacy_key = f"legacy:{song['name']} - {song['artist']}"
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
        url = html.escape(song_link(item["id"]), quote=True)
        text = html.escape(f"{item['name']} - {item['artist']}")
        html_items.append(
            f"<li>{item['rank']} {item['trend']} <a href='{url}'>{text}</a></li>"
        )
    escaped_weather = html.escape(weather).replace("\n", "<br>")
    html_content = (
        "# 🎵 网易云热歌榜\n\n"
        f"{escaped_weather}<br><br>"
        f"更新时间：{(datetime.now(timezone.utc) + timedelta(hours=8)).strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        "<ul>\n"
        f"{chr(10).join(html_items)}"
        "\n</ul>\n"
    )
    with open("README.md", "w", encoding="utf-8") as f:
        f.write(html_content)


def send_tg(songs, weather):
    token = os.environ.get("TG_TOKEN")
    chat_id = os.environ.get("TG_CHAT_ID")
    if not token or not chat_id:
        print("TG env missing")
        return
    msg = f"{html.escape(weather)}\n\n🎵 网易云热歌榜\n\n"
    for i, song in enumerate(songs[:TG_SONG_LIMIT], 1):
        link = html.escape(song_link(song["id"]), quote=True)
        text = html.escape(f"{song['name']} - {song['artist']}")
        msg += f"{i}. <a href='{link}'>{text}</a>\n"
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
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
    yesterday_key = sorted(history.keys())[-1] if history else None
    yesterday = history.get(yesterday_key, []) if yesterday_key else []
    yesterday_keys = normalize_history_keys(yesterday)
    ranked = compare(today, yesterday_keys)
    today_key = datetime.now().strftime("%Y-%m-%d")
    history[today_key] = today
    history = dict(sorted(history.items())[-MAX_HISTORY_DAYS:])
    save_history(history)
    write_readme(ranked, weather)
    send_tg(today, weather)


if __name__ == "__main__":
    main()
