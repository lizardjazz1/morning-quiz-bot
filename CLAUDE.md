# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Morning Quiz Bot — Telegram quiz bot with scoring, achievements, daily scheduling, and web admin panel. Written in Python using python-telegram-bot 22.4+ and FastAPI.

## Commands

```bash
# Run the bot
python bot.py

# Run web admin panel (FastAPI)
python web/run_web.py

# Install dependencies
pip install -r requirements.txt
```

## Architecture

### Entry Points
- `bot.py` / `main.py` — Bot entry point, initializes Application, handlers, job queue
- `web/main.py` — FastAPI REST API for admin dashboard

### Core Components

**Configuration & State:**
- `app_config.py` — Loads settings from `config/quiz_config.json` and `.env`
- `state.py` — `BotState` (global) and `QuizState` (per-chat active quiz session)

**Data Layer:**
- `data_manager.py` — Central data hub for all persistence operations
  - Per-chat data: `data/chats/{chat_id}/` (settings, users, stats)
  - Global data: `data/global/` (all users, categories index)
  - Questions: `data/questions/{Category}.json`
  - System: `data/system/` (subscriptions, cleanup queues)

**Quiz System:**
- `modules/quiz_engine.py` — Poll creation, rate limiting (25 req/sec, 18 req/min per chat)
- `handlers/quiz_manager.py` — Quiz session orchestration, three modes:
  - `single_question` — One poll per session
  - `serial_immediate` — All questions rapid-fire
  - `serial_interval` — Questions with configurable delay

**Managers:**
- `modules/score_manager.py` — Points, achievements, streaks
- `modules/category_manager.py` — Category loading, weighted selection by usage
- `modules/photo_quiz_manager.py` — Image-based quizzes

**Handlers:**
- `handlers/common_handlers.py` — /start, /help, /categories
- `handlers/rating_handlers.py` — /top, /globaltop, /mystats
- `handlers/config_handlers.py` — /admin_settings (ConversationHandler)
- `handlers/daily_quiz_scheduler.py` — APScheduler-based daily quiz triggers
- `handlers/wisdom_scheduler.py` — Daily facts via OpenRouter API (optional)

### Data Flow
```
Telegram → PTB Application → Handlers → Managers → DataManager → JSON files
                          ↓
                     BotState (in-memory)
```

### Key Design Decisions
- **60-second Telegram API timeout** — Required for Russia→EU routing delays
- **Dual state tracking** — In-memory QuizState + persistent JSON via DataManager
- **Per-chat isolation** — Each chat has independent settings, stats, category preferences
- **Moscow timezone hardcoded** — All scheduling uses `Europe/Moscow`

## Configuration

**Required:** `.env` with `BOT_TOKEN=...`

**Optional env vars:**
- `LOG_LEVEL` — DEBUG, INFO, WARNING, ERROR, CRITICAL
- `MODE` — production or testing
- `OPENROUTER_API_KEY` — For wisdom/facts generation

**Config files:**
- `config/quiz_config.json` — Quiz defaults, timeouts, poll limits
- `config/admins.json` — List of admin Telegram user IDs

## Language

The bot interface, questions, and user-facing text are in Russian. Code comments and variable names are in English.
