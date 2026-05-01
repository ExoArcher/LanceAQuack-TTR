# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the bot

```bash
pip install -r requirements.txt
python bot.py
```

Requires `.env` — copy `.env.example` to `.env` and fill in at minimum `DISCORD_TOKEN` and `GUILD_ALLOWLIST`.

## Architecture

Paws Pendragon is a multi-guild Discord bot that mirrors live Toontown Rewritten API data into Discord channels. One hosted instance serves multiple servers via an allowlist.

### Module responsibilities

| File | Role |
|---|---|
| `bot.py` | `TTRBot` class (subclass of `discord.AutoShardedClient`). Owns the refresh loop, guild allowlist enforcement, state management, all slash commands, sweep loop, announcement system, ban enforcement, and maintenance broadcasts. |
| `config.py` | Loads `.env` into a frozen `Config` dataclass. All env var access goes through here. |
| `ttr_api.py` | Thin async `aiohttp` client for the 5 public TTR endpoints (invasions, population, fieldoffices, doodles, sillymeter). Used as an async context manager. |
| `formatters.py` | Pure functions that convert raw TTR API JSON into `discord.Embed` objects. The `FORMATTERS` dict maps feed key → formatter function; `_update_feed()` in `bot.py` uses it. |
| `calculate.py` | `/calculate` slash command and `build_suit_calculator_embeds()` / `build_faction_thread_embeds()`. Contains all suit point quota tables (V1 and V2), activity point ranges, and the activity planner. Registered into the bot via `register_calculate(bot)`. |
| `Console.py` | Reads stdin in a background task for hosting panel commands (`stop`, `restart`, `maintenance`, `announce`, `rejoin`). Called at startup via `run_console(bot)`. |

### Data flow

1. `_refresh_loop` fires every `REFRESH_INTERVAL` seconds (default 90s), calls `_fetch_all()` to gather all 5 TTR endpoints in parallel, then calls `_update_feed()` for each tracked guild × feed key combo.
2. `_update_feed()` looks up the formatter from `FORMATTERS`, builds embeds, then edits the pinned messages in place using stored message IDs from `state.json`. A 3-second sleep between message edits prevents Discord rate limits.
3. Doodle embeds are throttled to once every 12 hours (`DOODLE_REFRESH_INTERVAL`) unless `/pd-refresh` is used.
4. `_sweep_loop` runs every 15 minutes to delete stale bot messages that aren't in the known message ID set.

### State persistence (`state.json`)

Schema version 2. Top-level keys: `_version`, `guilds`, `allowlist`, `announcements`, `maintenance_msgs`.

`guilds` maps `str(guild_id)` → dict of feed key → `{channel_id, message_ids}`. The bot migrates v0 and v1 state on startup.

The effective guild allowlist is the union of `GUILD_ALLOWLIST` (env) and `state["allowlist"]` (runtime).

### Guild lifecycle

- On join: bot leaves immediately if guild is not on the allowlist, DMing the owner with the closed-access message.
- `/pd-setup`: creates the `Toontown Rewritten` category and `#tt-information`, `#tt-doodles`, `#suit-calculator` channels, posts placeholder embeds, and stores message IDs.
- `/pd-teardown`: removes guild from `state.json`; channels remain.

### Ban management

`banned_users.json` stores `{str(user_id): {reason, banned_at, banned_by, banned_by_id}}`. Helpers `_ban_user()` / `_unban_user()` write to this file and call `_sync_env()` to mirror the list back into `.env` (`BANNED_USER_IDS`). A new ban also triggers `_scan_new_ban()` to immediately check all tracked guilds.

Slash commands: `/pd-ban`, `/pd-unban`, `/pd-banlist` (BOT_ADMIN_IDS only, work from DMs).
Console commands: `ban <user_id> [reason]`, `unban <user_id>`, `banlist`.

### Quarantine system

When a banned user holds elevated permissions (`administrator`, `manage_channels`, `manage_messages`, or `manage_threads`) in a tracked guild — or is the guild owner — that guild is quarantined: live feed updates are suspended and a persistent warning embed is posted to all three bot channels. Bot admins are DM'd on both quarantine and lift.

State stored in `state["quarantined"]`: `{str(guild_id): {triggered_by_user_id, triggered_at, manual, quarantine_msg_ids}}`.
`_quarantine_scan_loop` runs every 30 minutes; clean guilds are only scanned every 6 hours (tracked in `_last_quarantine_scan`).
`_sync_env()` also mirrors the quarantine list into `.env` (`QUARANTINED_GUILD_IDS`) after every change.

Slash commands: `/pd-quarantine`, `/pd-unquarantine`, `/pd-quarantine-list`, `/pd-quarantine-refresh [guild_id]`.
Console commands: `quarantine <guild_id> [reason]`, `unquarantine <guild_id>`, `quarantine-list`, `quarantine-refresh [guild_id]`.

### Auto-update

At startup, `bot.py` compares local `HEAD` to `origin/main`. If behind, it runs `git reset --hard origin/main` and `os.execv`-restarts. This prevents restart loops by comparing hashes before pulling.

## Environment variables

See `.env.example` for all options. Required: `DISCORD_TOKEN`, `GUILD_ALLOWLIST`. Custom emoji IDs (`JELLYBEAN_EMOJI`, `COG_EMOJI`, `STAR_*`, etc.) are used by `formatters.py` for rich embed display.

## Hosting

Deployed on Cybrancee Discord Bot Hosting (`worker: python3 bot.py`). Panel console commands go to stdin, which `Console.py` reads. `panel_announce.txt` dropped in the file manager is picked up within 90 seconds and broadcast to all guilds.
