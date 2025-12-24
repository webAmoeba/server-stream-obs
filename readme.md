# server-stream-obs

Головной (headless) стример на OBS для бесшовного проигрывания видео с наложением текста (название + таймкод) и субтитров.

---

## Быстрый старт на новом сервере

### 1) Системные зависимости

Минимум для работы:

```bash
apt-get update -y
apt-get install -y obs-studio ffmpeg xvfb pulseaudio
```

Если нужно скачивать торренты:

```bash
make install-torrent
```

> Важно: для воспроизведения мы используем **obs-mpv** (input kind `mpvs_source`). Плагин должен быть установлен в системе. Если его нет — установи/собери (у нас он уже собран и установлен на этом сервере).

---

### 2) Клонировать репозиторий

```bash
git clone <repo> /root/repos/server-stream-obs
cd /root/repos/server-stream-obs
```

---

### 3) Настроить `.env`

Создай/обнови файл `.env` в корне проекта. Пример:

```env
VK_URL="rtmp://..."
VK_KEY="..."
VIDEO_DIR="/root/downloads/Big Bang Theory"
OBS_PASSWORD="..."

OBS_SCENE="Scene"
OBS_MEDIA_SOURCE="Media"
OBS_TEXT_SOURCE="NowPlaying"

VIDEO_EXTS=.mp4
LOOP=1
AUDIO_INDEX=2
SUB_SI=2
OUTPUT_WIDTH=1280
OUTPUT_HEIGHT=720
OUTPUT_FPS=24
STREAM_VIDEO_BITRATE="2000k"
STREAM_AUDIO_BITRATE="160k"
STREAM_PRESET="ultrafast"
TEXT_SIZE=24
```

Пояснения:
- `VIDEO_DIR` — папка с видео (рекурсивный поиск).
- `AUDIO_INDEX`, `SUB_SI` — индексы дорожек (для mpv).
- `OBS_MEDIA_SOURCE` — имя источника медиа в OBS (по умолчанию `Media`).
- `OBS_TEXT_SOURCE` — имя текстового источника (по умолчанию `NowPlaying`).

---

### 4) Установить зависимости и применить конфиги OBS

```bash
make install
```

`make install`:
- создаёт `.venv`
- ставит Python-зависимости
- устанавливает и собирает obs-mpv (плагин для mpv)
- применяет шаблоны OBS из `config/obs` в `~/.config/obs-studio`
- применяет параметры OBS WebSocket (через `obs_prepare.py`)

Если нужно пропустить установку obs-mpv:

```bash
SKIP_OBS_MPV=1 make install
```

Если менялись шаблоны OBS или важные параметры — используйте:

```bash
make reinstall
```

---

### 5) Запустить стрим

```bash
make start
```

Логи:

```bash
make logs
```

---

## Команды Makefile

- `make install` — установка зависимостей, сборка obs-mpv и применение конфигов OBS
- `make reinstall` — стоп сервиса → `make install` → старт (если нужно переустановить/применить конфиги)
- `make start` — запуск сервиса
- `make stop` — остановка сервиса
- `make restart` — быстрый перезапуск (обычно достаточно после правок `.env`/кода)
- `make status` — статус сервиса
- `make logs` — последние логи сервиса
- `make enable` — автозапуск при старте сервера
- `make disable` — отключить автозапуск

### Торренты
- `make install-torrent` — установить `aria2`
- `make download` — скачать `my.torrent` из `/root/my.torrent` в `/root/downloads`

Если нужно другое расположение:

```bash
make download TORRENT_FILE=/path/to/my.torrent DOWNLOAD_DIR=/path/to/downloads
```

---

## Конфиги OBS внутри репозитория

Шаблоны OBS лежат в:

```
config/obs/basic/profiles/Untitled/basic.ini
config/obs/basic/scenes/Untitled.json
```

При `make install`/`make reinstall` они копируются в `~/.config/obs-studio`.

---

## Как формируется текст в левом верхнем углу

Формат:
```
S01E03 01:24/22:24
```

Если файл длиннее часа — будет `HH:MM:SS`.

---

## Если что-то сломалось

1) Проверить логи:
```bash
make logs
```

2) Проверить, что есть доступ к OBS WebSocket (пароль из `.env`).
3) Убедиться, что `mpvs_source` доступен (obs-mpv установлен).
4) Если менялись шаблоны или что-то «залипло» — `make reinstall`.

