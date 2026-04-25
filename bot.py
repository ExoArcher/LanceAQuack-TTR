"""TTR Discord bot — multi-guild live feeds for the public TTR APIs.

How it works
------------
1. The bot is invited to one or more Discord servers. Only servers
   whose ID is in the *effective* allowlist (env ``GUILD_ALLOWLIST``
   ∪ runtime allowlist persisted in ``state.json``) are accepted; the
   bot leaves any other guild that tries to add it.
2. In each allowed guild, an admin runs **``/laq-setup``** once. That
   command finds-or-creates the ``Toontown Rewritten`` category plus a
   ``#tt-information`` and ``#tt-doodles`` channel, posts a placeholder
   message in each, and stores the message IDs in ``state.json``.
3. A background task runs every ``$REFRESH_INTERVAL`` seconds, fetches
   the four TTR APIs ONCE, and edits each tracked guild's messages in
   place. The channels stay clean — no new message per tick.
4. A separate sweep task runs every 15 minutes, deleting any stale bot
   messages left behind from crashes or re-runs.

Slash commands
--------------
Server admin (``Manage Server``):
``/laq-setup``    — create channels and start tracking this guild.
``/laq-refresh``  — force an immediate refresh and sweep old messages.
``/laq-teardown`` — stop tracking this guild (channels are NOT deleted).

Bot owner only (``BOT_OWNER_IDS``):
``/laq-announce`` — broadcast a message to every tracked guild.
                    Auto-deletes after 30 minutes; orphans cleaned
                    on the bot's next startup.
``/laq-clear``    — delete every bot message in this server and
                    reset its tracking state.

Panel announcements
-------------------
Create a file called ``panel_announce.txt`` in the bot's working
directory via the hosting panel's File Manager. The bot detects it
within 90 seconds, broadcasts the contents as an announcement to every
tracked guild, then deletes the file automatically.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any

import discord
from discord import app_commands
from discord.ext import tasks

from config import Config
from formatters import FORMATTERS
from ttr_api import TTRApiClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("ttr-bot")

# Persisted channel + message IDs and runtime admin state.
STATE_FILE = Path(__file__).with_name("state.json")
STATE_VERSION = 2

# Drop a file called panel_announce.txt in the panel's File Manager
# to broadcast an announcement to every tracked guild.
ANNOUNCE_FILE = Path(__file__).with_name("panel_announce.txt")

ANNOUNCEMENT_TITLE = "📢 LAQ Bot Announcement"
ANNOUNCEMENT_TTL_SECONDS = 30 * 60


class TTRBot(discord.Client):
    def __init__(self, config: Config) -> None:
        intents = discord.Intents.default()
        intents.guilds = True
        super().__init__(intents=intents)

        self.config = config
        self.tree = app_commands.CommandTree(self)
        self.state: dict[str, Any] = self._load_state()
        self._api: TTRApiClient | None = None
        self._refresh_lock = asyncio.Lock()
        self._state_lock = asyncio.Lock()

    # ---------- state persistence -----------------------------------

    def _load_state(self) -> dict[str, Any]:
        if not STATE_FILE.exists():
            return self._empty_state()
        try:
            raw = json.loads(STATE_FILE.read_text())
        except Exception as e:
            log.warning("Could not load state file: %s", e)
            return self._empty_state()

        if not isinstance(raw, dict) or not raw:
            return self._empty_state()

        version = raw.get("_version")
        if version == STATE_VERSION:
            raw.setdefault("guilds", {})
            raw.setdefault("allowlist", [])
            raw.setdefault("announcements", [])
            return raw

        if all(
            isinstance(v, dict) and "channel_id" in v
            for v in raw.values()
        ):
            if len(self.config.guild_allowlist) == 1:
                only = next(iter(self.config.guild_allowlist))
                log.info("Migrating legacy v0 state to v%d under guild %s", STATE_VERSION, only)
                return {
                    "_version": STATE_VERSION,
                    "guilds": {str(only): raw},
                    "allowlist": [],
                    "announcements": [],
                }
            log.warning("Found legacy v0 state but cannot migrate. Starting fresh.")
            return self._empty_state()

        if all(
            isinstance(v, dict) and not k.startswith("_")
            for k, v in raw.items()
        ):
            log.info("Migrating v1 state to v%d", STATE_VERSION)
            return {
                "_version": STATE_VERSION,
                "guilds": dict(raw),
                "allowlist": [],
                "announcements": [],
            }

        log.warning("Unrecognised state.json shape; starting fresh.")
        return self._empty_state()

    @staticmethod
    def _empty_state() -> dict[str, Any]:
        return {
            "_version": STATE_VERSION,
            "guilds": {},
            "allowlist": [],
            "announcements": [],
        }

    async def _save_state(self) -> None:
        async with self._state_lock:
            try:
                STATE_FILE.write_text(json.dumps(self.state, indent=2))
            except Exception as e:
                log.warning("Could not save state file: %s", e)

    def _guilds_block(self) -> dict[str, dict[str, dict[str, Any]]]:
        return self.state.setdefault("guilds", {})

    def _guild_state(self, guild_id: int) -> dict[str, dict[str, Any]]:
        return self._guilds_block().setdefault(str(guild_id), {})

    def _state_message_ids(self, guild_id: int, key: str) -> list[int]:
        entry = self._guild_state(guild_id).get(key, {}) or {}
        ids = entry.get("message_ids")
        if isinstance(ids, list) and ids:
            return [int(i) for i in ids if isinstance(i, (int, str))]
        legacy = entry.get("message_id")
        if legacy:
            return [int(legacy)]
        return []

    def _set_state(self, guild_id: int, key: str, channel_id: int, message_ids: list[int]) -> None:
        gs = self._guild_state(guild_id)
        gs[key] = {"channel_id": channel_id, "message_ids": message_ids}

    def _runtime_allowlist(self) -> set[int]:
        return {int(x) for x in self.state.get("allowlist", [])}

    def effective_allowlist(self) -> set[int]:
        return set(self.config.guild_allowlist) | self._runtime_allowlist()

    def is_guild_allowed(self, guild_id: int) -> bool:
        return guild_id in self.effective_allowlist()

    def _announcements(self) -> list[dict[str, Any]]:
        return self.state.setdefault("announcements", [])

    async def _record_announcement(
        self, guild_id: int, channel_id: int, message_id: int, expires_at: float
    ) -> None:
        self._announcements().append({
            "guild_id": int(guild_id),
            "channel_id": int(channel_id),
            "message_id": int(message_id),
            "expires_at": float(expires_at),
        })
        await self._save_state()

    # ---------- Discord lifecycle -----------------------------------

    async def setup_hook(self) -> None:
        self._api = TTRApiClient(self.config.user_agent)
        await self._api.__aenter__()

        # Clear any stale globally-registered commands before re-registering.
        self.tree.clear_commands(guild=None)
        self._register_commands()
        await self.tree.sync()

    async def close(self) -> None:
        if self._api is not None:
            await self._api.__aexit__(None, None, None)
        await super().close()

    async def on_ready(self) -> None:
        assert self.user is not None
        log.info("Logged in as %s (id=%s)", self.user, self.user.id)
        log.info(
            "In %d guild(s); env-allowlist=%d entries; "
            "runtime-allowlist=%d entries; owners=%d",
            len(self.guilds),
            len(self.config.guild_allowlist),
            len(self._runtime_allowlist()),
            len(self.config.owner_ids),
        )
        if self.config.owner_ids:
            log.info(
                "Bot-owner IDs loaded: %s",
                ", ".join(str(i) for i in sorted(self.config.owner_ids)),
            )
        else:
            log.warning(
                "BOT_OWNER_IDS is empty — /laq-* owner commands will reject everyone."
            )

        for guild in list(self.guilds):
            if not self.is_guild_allowed(guild.id):
                log.warning("Leaving non-allowlisted guild %s (id=%s)", guild.name, guild.id)
                await self._notify_and_leave(guild)

        live_ids = {str(g.id) for g in self.guilds}
        for gid in list(self._guilds_block().keys()):
            if gid not in live_ids:
                log.info("Pruning state for departed guild %s", gid)
                self._guilds_block().pop(gid, None)

        # Sync commands per-guild (instant propagation) and clear old names.
        for guild in list(self.guilds):
            if not self.is_guild_allowed(guild.id):
                continue
            try:
                self.tree.clear_commands(guild=guild)
                self.tree.copy_global_to(guild=guild)
                await self.tree.sync(guild=guild)
                log.info("Per-guild command sync OK for %s (id=%s)", guild.name, guild.id)
            except Exception:
                log.exception("Per-guild command sync failed for %s (id=%s)", guild.name, guild.id)

        await self._cleanup_announcements_on_startup()
        await self._save_state()

        if not self._refresh_loop.is_running():
            self._refresh_loop.change_interval(seconds=self.config.refresh_interval)
            self._refresh_loop.start()

        if not self._sweep_loop.is_running():
            self._sweep_loop.start()

    async def on_guild_join(self, guild: discord.Guild) -> None:
        if not self.is_guild_allowed(guild.id):
            log.warning("Refusing to join non-allowlisted guild %s (id=%s)", guild.name, guild.id)
            await self._notify_and_leave(guild)
            return
        log.info("Joined allowlisted guild %s (id=%s)", guild.name, guild.id)

    async def on_guild_remove(self, guild: discord.Guild) -> None:
        log.info("Removed from guild %s (id=%s)", guild.name, guild.id)
        self._guilds_block().pop(str(guild.id), None)
        await self._save_state()

    async def _notify_and_leave(self, guild: discord.Guild) -> None:
        msg = (
            "Hi! I'm a private TTR feeds bot and I'm not configured to "
            "operate in your server. The owner needs to add your "
            f"server ID (`{guild.id}`) to the bot's allowlist before re-inviting me."
        )
        try:
            owner = guild.owner or await guild.fetch_member(guild.owner_id)
            if owner is not None:
                await owner.send(msg)
        except Exception as e:
            log.debug("Could not DM owner of %s: %s", guild.name, e)
        try:
            await guild.leave()
        except Exception as e:
            log.warning("Failed to leave guild %s: %s", guild.id, e)

    # ---------- channel + message bootstrapping ---------------------

    async def _ensure_channels_for_guild(self, guild: discord.Guild) -> None:
        category = discord.utils.get(guild.categories, name=self.config.category_name)
        if category is None:
            log.info("Creating category %r in %s", self.config.category_name, guild.name)
            category = await guild.create_category(self.config.category_name)

        for key, channel_name in self.config.feeds().items():
            channel = discord.utils.get(guild.text_channels, name=channel_name)
            if channel is None:
                log.info("Creating channel #%s in %s", channel_name, guild.name)
                channel = await guild.create_text_channel(
                    channel_name,
                    category=category,
                    topic=f"Live TTR {key} feed — auto-updated by bot.",
                )
            await self._ensure_messages(guild.id, key, channel, at_least=1)

        await self._save_state()

    async def _send_placeholder(self, key: str, channel: discord.TextChannel) -> discord.Message:
        placeholder = discord.Embed(
            title=f"Loading {key}…",
            description="Fetching the latest data from TTR.",
            color=0x95A5A6,
        )
        msg = await channel.send(embed=placeholder)
        try:
            await msg.pin(reason="Live TTR feed pin")
        except (discord.Forbidden, discord.HTTPException) as e:
            log.debug("Could not pin message in #%s: %s", channel.name, e)
        return msg

    async def _ensure_messages(
        self, guild_id: int, key: str, channel: discord.TextChannel, at_least: int,
    ) -> list[int]:
        ids = self._state_message_ids(guild_id, key)
        verified: list[int] = []
        for mid in ids:
            try:
                await channel.fetch_message(mid)
                verified.append(mid)
            except discord.NotFound:
                log.info("Stored message %s for %s/%s is gone.", mid, guild_id, key)
            except discord.Forbidden:
                log.warning("No permission to fetch message in #%s", channel.name)
                verified.append(mid)

        while len(verified) < at_least:
            msg = await self._send_placeholder(key, channel)
            verified.append(msg.id)

        self._set_state(guild_id, key, channel.id, verified)
        return verified

    # ---------- announcement cleanup --------------------------------

    async def _delete_announcement_record(self, record: dict[str, Any]) -> None:
        guild_id = int(record.get("guild_id", 0))
        channel_id = int(record.get("channel_id", 0))
        message_id = int(record.get("message_id", 0))
        try:
            channel = self.get_channel(channel_id)
            if isinstance(channel, discord.TextChannel):
                try:
                    msg = await channel.fetch_message(message_id)
                    await msg.delete()
                except discord.NotFound:
                    pass
                except discord.Forbidden:
                    log.warning("No permission to delete announcement %s in #%s", message_id, channel.name)
        except Exception:
            log.exception("Failed deleting announcement record %s/%s/%s", guild_id, channel_id, message_id)
        self._announcements()[:] = [
            r for r in self._announcements()
            if int(r.get("message_id", -1)) != message_id
        ]

    async def _cleanup_announcements_on_startup(self) -> None:
        for record in list(self._announcements()):
            await self._delete_announcement_record(record)

        for guild_id_str, gs in list(self._guilds_block().items()):
            try:
                guild_id = int(guild_id_str)
            except ValueError:
                continue
            info = gs.get("information")
            if not info:
                continue
            channel = self.get_channel(int(info.get("channel_id", 0)))
            if not isinstance(channel, discord.TextChannel):
                continue
            try:
                async for msg in channel.history(limit=100):
                    if msg.author.id != (self.user.id if self.user else 0):
                        continue
                    if not msg.embeds:
                        continue
                    if ANNOUNCEMENT_TITLE in (msg.embeds[0].title or ""):
                        try:
                            await msg.delete()
                            log.info("Deleted orphan announcement %s in %s/#%s", msg.id, guild_id, channel.name)
                        except (discord.Forbidden, discord.NotFound):
                            pass
            except discord.Forbidden:
                log.debug("No permission to read history in %s/#%s", guild_id, channel.name)
            except Exception:
                log.exception("Orphan-announcement scan failed in %s/#%s", guild_id, getattr(channel, "name", "?"))

    # ---------- stale-message sweep --------------------------------

    def _channel_keep_ids(self, guild_id: int, channel_id: int) -> set[int]:
        keep: set[int] = set()
        gs = self._guild_state(guild_id)
        for entry in gs.values():
            if int(entry.get("channel_id", 0)) != channel_id:
                continue
            for mid in entry.get("message_ids", []) or []:
                try:
                    keep.add(int(mid))
                except (TypeError, ValueError):
                    pass
        for record in self._announcements():
            if int(record.get("channel_id", 0)) == channel_id:
                try:
                    keep.add(int(record.get("message_id", 0)))
                except (TypeError, ValueError):
                    pass
        return keep

    async def _sweep_channel_stale(
        self, channel: discord.TextChannel, *, keep_ids: set[int], history_limit: int = 200,
    ) -> int:
        if self.user is None:
            return 0
        bot_id = self.user.id
        deleted = 0
        try:
            async for msg in channel.history(limit=history_limit):
                if msg.author.id != bot_id:
                    continue
                if msg.id in keep_ids:
                    continue
                try:
                    await msg.delete()
                    deleted += 1
                except discord.NotFound:
                    pass
                except discord.Forbidden:
                    log.debug("Forbidden deleting own msg %s in #%s", msg.id, channel.name)
                except discord.HTTPException as e:
                    log.debug("HTTP error deleting %s in #%s: %s", msg.id, channel.name, e)
        except discord.Forbidden:
            log.debug("No Read Message History in #%s; skipping sweep", channel.name)
        return deleted

    async def _sweep_guild_stale(self, guild_id: int) -> int:
        total = 0
        gs = self._guild_state(guild_id)
        seen_channels: set[int] = set()
        for entry in gs.values():
            channel_id = int(entry.get("channel_id", 0))
            if channel_id in seen_channels or channel_id == 0:
                continue
            seen_channels.add(channel_id)
            channel = self.get_channel(channel_id)
            if not isinstance(channel, discord.TextChannel):
                continue
            keep = self._channel_keep_ids(guild_id, channel_id)
            total += await self._sweep_channel_stale(channel, keep_ids=keep)
        return total

    async def _sweep_expired_announcements(self) -> None:
        now = time.time()
        expired = [r for r in list(self._announcements()) if float(r.get("expires_at", 0)) <= now]
        for record in expired:
            await self._delete_announcement_record(record)
        if expired:
            await self._save_state()

    # ---------- panel file announcement ----------------------------

    async def _check_panel_announce(self) -> None:
        """Check for panel_announce.txt and broadcast its contents if found.

        To send an announcement from the hosting panel:
        1. Open the File Manager tab in the Cybrancee panel.
        2. Create a new file called ``panel_announce.txt``.
        3. Type your announcement text inside and save.
        The bot will pick it up within 90 seconds, broadcast it to every
        tracked guild, and delete the file automatically.
        """
        if not ANNOUNCE_FILE.exists():
            return
        try:
            text = ANNOUNCE_FILE.read_text(encoding="utf-8").strip()
            ANNOUNCE_FILE.unlink()
        except Exception as e:
            log.warning("Could not read/delete panel_announce.txt: %s", e)
            return
        if not text:
            return
        log.info("Panel announcement detected — broadcasting: %s", text[:80])
        sent, failed, guilds_touched = await self._broadcast_announcement(text)
        log.info(
            "Panel announcement complete: %d message(s) across %d guild(s), %d failed.",
            sent, guilds_touched, failed,
        )

    # ---------- the poll loop --------------------------------------

    @tasks.loop(seconds=60)
    async def _refresh_loop(self) -> None:
        try:
            await self._sweep_expired_announcements()
        except Exception:
            log.exception("Announcement sweep failed")
        try:
            await self._check_panel_announce()
        except Exception:
            log.exception("Panel announce check failed")
        await self._refresh_once()

    @_refresh_loop.before_loop
    async def _before_loop(self) -> None:
        await self.wait_until_ready()

    @tasks.loop(minutes=15)
    async def _sweep_loop(self) -> None:
        """Periodic stale-message sweep — removes orphaned bot messages every 15 minutes."""
        for guild_id_str in list(self._guilds_block().keys()):
            try:
                guild_id = int(guild_id_str)
            except ValueError:
                continue
            if not self.is_guild_allowed(guild_id):
                continue
            if self.get_guild(guild_id) is None:
                continue
            try:
                swept = await self._sweep_guild_stale(guild_id)
                if swept:
                    log.info("Periodic sweep removed %d stale message(s) in guild %s", swept, guild_id)
            except Exception:
                log.exception("Periodic sweep failed for guild %s", guild_id)

    @_sweep_loop.before_loop
    async def _before_sweep_loop(self) -> None:
        await self.wait_until_ready()

    _API_KEYS = ("invasions", "population", "fieldoffices", "doodles")

    async def _fetch_all(self) -> dict[str, dict | None]:
        if self._api is None:
            return {k: None for k in self._API_KEYS}
        results = await asyncio.gather(
            *(self._api.fetch(k) for k in self._API_KEYS),
            return_exceptions=True,
        )
        api_data: dict[str, dict | None] = {}
        for k, r in zip(self._API_KEYS, results):
            if isinstance(r, BaseException):
                log.warning("Fetch %s raised: %s", k, r)
                api_data[k] = None
            else:
                api_data[k] = r
        return api_data

    async def _refresh_once(self) -> None:
        if self._api is None:
            return
        async with self._refresh_lock:
            api_data = await self._fetch_all()
            for guild_id_str in list(self._guilds_block().keys()):
                try:
                    guild_id = int(guild_id_str)
                except ValueError:
                    continue
                if not self.is_guild_allowed(guild_id):
                    continue
                guild = self.get_guild(guild_id)
                if guild is None:
                    continue
                for feed_key in self.config.feeds():
                    try:
                        await self._update_feed(guild_id, feed_key, api_data)
                    except Exception:
                        log.exception("Failed updating %s/%s", guild_id, feed_key)
            await self._save_state()

    async def _update_feed(
        self, guild_id: int, feed_key: str, api_data: dict[str, dict | None],
    ) -> None:
        entry = self._guild_state(guild_id).get(feed_key)
        if not entry:
            return
        channel = self.get_channel(int(entry["channel_id"]))
        if not isinstance(channel, discord.TextChannel):
            return

        formatter = FORMATTERS.get(feed_key)
        if formatter is None:
            log.warning("No formatter registered for feed %r", feed_key)
            return
        embeds = formatter(api_data)
        if not isinstance(embeds, list):
            embeds = [embeds]
        if not embeds:
            return

        ids = await self._ensure_messages(guild_id, feed_key, channel, at_least=len(embeds))

        kept_ids: list[int] = []
        for mid, embed in zip(ids, embeds):
            try:
                message = await channel.fetch_message(mid)
                await message.edit(embed=embed)
                kept_ids.append(mid)
            except discord.NotFound:
                log.info("Message %s for %s/%s vanished mid-edit; reposting.", mid, guild_id, feed_key)
                new_msg = await channel.send(embed=embed)
                try:
                    await new_msg.pin(reason="Live TTR feed pin")
                except (discord.Forbidden, discord.HTTPException):
                    pass
                kept_ids.append(new_msg.id)

        for mid in ids[len(embeds):]:
            try:
                message = await channel.fetch_message(mid)
                blank = discord.Embed(description="*(no data for this tier right now)*", color=0x95A5A6)
                await message.edit(embed=blank)
                kept_ids.append(mid)
            except discord.NotFound:
                pass

        self._set_state(guild_id, feed_key, channel.id, kept_ids)

    # ---------- announcement broadcast helper -----------------------

    async def _broadcast_announcement(self, text: str) -> tuple[int, int, int]:
        embed = discord.Embed(
            title=ANNOUNCEMENT_TITLE,
            description=text,
            color=0xF1C40F,
        )
        embed.set_footer(text=f"This message will auto-delete in {ANNOUNCEMENT_TTL_SECONDS // 60} minutes.")

        expires_at = time.time() + ANNOUNCEMENT_TTL_SECONDS
        sent = 0
        failed = 0
        guilds_touched: set[int] = set()
        for guild_id_str, gs in list(self._guilds_block().items()):
            try:
                guild_id = int(guild_id_str)
            except ValueError:
                continue
            for feed_key in self.config.feeds():
                entry = gs.get(feed_key)
                if not entry:
                    continue
                channel = self.get_channel(int(entry.get("channel_id", 0)))
                if not isinstance(channel, discord.TextChannel):
                    continue
                try:
                    msg = await channel.send(embed=embed)
                    await self._record_announcement(guild_id, channel.id, msg.id, expires_at)
                    sent += 1
                    guilds_touched.add(guild_id)
                    log.info("Announcement posted to %s/#%s (msg=%s)", guild_id, channel.name, msg.id)
                except (discord.Forbidden, discord.HTTPException) as e:
                    log.warning("Failed to broadcast to %s/#%s: %s", guild_id, channel.name, e)
                    failed += 1
        return sent, failed, len(guilds_touched)

    # ---------- slash commands --------------------------------------

    def _register_commands(self) -> None:

        # ---- /laq-setup ----
        @self.tree.command(
            name="laq-setup",
            description="Create the TTR feed channels in this server and start tracking them.",
        )
        @app_commands.default_permissions(manage_guild=True)
        @app_commands.guild_only()
        async def laq_setup(interaction: discord.Interaction) -> None:
            guild = interaction.guild
            if guild is None:
                await interaction.response.send_message("This command must be used inside a server.", ephemeral=True)
                return
            if not self.is_guild_allowed(guild.id):
                await interaction.response.send_message(
                    f"This server isn't on the bot's allowlist. Ask the bot owner to add `{guild.id}`.",
                    ephemeral=True,
                )
                return

            await interaction.response.defer(ephemeral=True, thinking=True)
            swept = 0
            try:
                await self._ensure_channels_for_guild(guild)
                api_data = await self._fetch_all()
                for feed_key in self.config.feeds():
                    try:
                        await self._update_feed(guild.id, feed_key, api_data)
                    except Exception:
                        log.exception("Initial refresh failed for %s/%s", guild.id, feed_key)
                swept = await self._sweep_guild_stale(guild.id)
                if swept:
                    log.info("laq-setup swept %d stale message(s) in %s", swept, guild.id)
                await self._save_state()
            except discord.Forbidden:
                await interaction.followup.send(
                    "I'm missing permissions. Make sure I have **Manage Channels**, "
                    "**Send Messages**, and **Embed Links** in this server, then try again.",
                    ephemeral=True,
                )
                return

            channels_msg = ", ".join(f"#{name}" for name in self.config.feeds().values())
            tail = f" Cleaned up {swept} old message(s)." if swept else ""
            await interaction.followup.send(
                f"All set! Tracking **{channels_msg}**. They'll refresh "
                f"every {self.config.refresh_interval} seconds.{tail}",
                ephemeral=True,
            )

        # ---- /laq-refresh ----
        @self.tree.command(
            name="laq-refresh",
            description="Force an immediate refresh of all TTR feeds and remove old messages.",
        )
        @app_commands.default_permissions(manage_guild=True)
        @app_commands.guild_only()
        async def laq_refresh(interaction: discord.Interaction) -> None:
            await interaction.response.defer(ephemeral=True, thinking=True)
            await self._refresh_once()
            swept = 0
            if interaction.guild is not None:
                try:
                    swept = await self._sweep_guild_stale(interaction.guild.id)
                except Exception:
                    log.exception("Stale-message sweep failed for %s", interaction.guild.id)
                if swept:
                    await self._save_state()
            tail = f" Cleaned up {swept} old message(s)." if swept else ""
            await interaction.followup.send(f"Refreshed.{tail}", ephemeral=True)

        # ---- /laq-teardown ----
        @self.tree.command(
            name="laq-teardown",
            description="Stop tracking TTR feeds here. Channels are kept; delete them manually if you want.",
        )
        @app_commands.default_permissions(manage_guild=True)
        @app_commands.guild_only()
        async def laq_teardown(interaction: discord.Interaction) -> None:
            guild = interaction.guild
            if guild is None:
                await interaction.response.send_message("This command must be used inside a server.", ephemeral=True)
                return
            existed = self._guilds_block().pop(str(guild.id), None) is not None
            await self._save_state()
            if existed:
                await interaction.response.send_message(
                    "Stopped tracking this server. The channels still exist; delete them manually if you'd like.",
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    "Nothing to tear down — this server isn't being tracked.",
                    ephemeral=True,
                )

        # ---- owner-only guard ----
        async def _reject_non_owner(interaction: discord.Interaction) -> bool:
            if not self.config.is_owner(interaction.user.id):
                log.info(
                    "Rejecting non-owner %s (id=%s) on /%s",
                    interaction.user, interaction.user.id,
                    interaction.command.name if interaction.command else "?",
                )
                await interaction.response.send_message(
                    f"This command is restricted to bot owners. "
                    f"Your user ID `{interaction.user.id}` is not in `BOT_OWNER_IDS`.",
                    ephemeral=True,
                )
                return True
            return False

        # ---- /laq-announce ----
        @self.tree.command(
            name="laq-announce",
            description="Broadcast a message to every tracked server. Auto-deletes after 30 minutes. Owner only.",
        )
        @app_commands.describe(text="The announcement text to send to every tracked server.")
        async def laq_announce(interaction: discord.Interaction, text: str) -> None:
            if await _reject_non_owner(interaction):
                return
            text = text.strip()
            if not text:
                await interaction.response.send_message("Announcement text cannot be empty.", ephemeral=True)
                return

            await interaction.response.defer(ephemeral=True, thinking=True)
            sent, failed, guilds_touched = await self._broadcast_announcement(text)
            tracked_guilds = len(self._guilds_block())
            ttl_min = ANNOUNCEMENT_TTL_SECONDS // 60

            if sent == 0:
                if tracked_guilds == 0:
                    msg = (
                        "Broadcast sent **0** messages — no servers are currently tracked. "
                        "An admin needs to run `/laq-setup` in each server first."
                    )
                else:
                    msg = (
                        f"Broadcast sent **0** messages despite {tracked_guilds} tracked server(s). "
                        "The bot may have lost permission to post in the feed channels. "
                        "Check the console log for details."
                    )
            else:
                msg = (
                    f"Broadcast complete: **{sent}** message(s) posted across "
                    f"**{guilds_touched}** server(s)"
                    + (f", {failed} failed" if failed else "")
                    + f". Each post will auto-delete in {ttl_min} minutes."
                )
            await interaction.followup.send(msg, ephemeral=True)

        # ---- /laq-clear ----
        @self.tree.command(
            name="laq-clear",
            description="Delete every LanceAQuack message from this server and reset its tracking state. Owner only.",
        )
        @app_commands.guild_only()
        async def laq_clear(interaction: discord.Interaction) -> None:
            if await _reject_non_owner(interaction):
                return
            guild = interaction.guild
            if guild is None:
                await interaction.response.send_message("This command must be used inside a server.", ephemeral=True)
                return

            await interaction.response.defer(ephemeral=True, thinking=True)

            bot_id = self.user.id if self.user else 0
            deleted = 0
            no_history: list[str] = []

            for channel in list(guild.text_channels):
                try:
                    async for msg in channel.history(limit=500):
                        if msg.author.id != bot_id:
                            continue
                        try:
                            await msg.delete()
                            deleted += 1
                        except discord.NotFound:
                            pass
                        except discord.Forbidden:
                            log.debug("Forbidden deleting own msg %s in #%s", msg.id, channel.name)
                            break
                        except discord.HTTPException as e:
                            log.debug("HTTP error deleting %s in #%s: %s", msg.id, channel.name, e)
                except discord.Forbidden:
                    no_history.append(f"#{channel.name}")
                except Exception:
                    log.exception("Sweep of #%s failed", channel.name)

            self._guilds_block().pop(str(guild.id), None)
            self._announcements()[:] = [
                r for r in self._announcements()
                if int(r.get("guild_id", 0)) != guild.id
            ]
            await self._save_state()

            parts = [f"deleted **{deleted}** bot message(s)", "tracking state reset — run `/laq-setup` to start again"]
            if no_history:
                preview = ", ".join(no_history[:5])
                more = f" (+{len(no_history) - 5} more)" if len(no_history) > 5 else ""
                parts.append(f"couldn't read history in: {preview}{more}")
            log.info("laq-clear in %s (id=%s): deleted=%d, skipped_channels=%d", guild.name, guild.id, deleted, len(no_history))
            await interaction.followup.send("Done — " + "; ".join(parts) + ".", ephemeral=True)


def main() -> None:
    config = Config.load()
    if not config.guild_allowlist and not config.owner_ids:
        log.warning(
            "Both GUILD_ALLOWLIST and BOT_OWNER_IDS are empty — the bot "
            "cannot be invited to any server and has no admins. Edit your .env."
        )
    bot = TTRBot(config)
    bot.run(config.token, log_handler=None)


if __name__ == "__main__":
    main()
