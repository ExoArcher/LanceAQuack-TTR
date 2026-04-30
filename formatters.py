# -*- coding: utf-8 -*-
"""
formatters.py — Discord embed builders for LanceAQuack TTR.

IMPORTANT DISCORD EMBED RULES applied here:
  - <t:unix:R> timestamps render ONLY in descriptions and field values,
    NOT in footer text.  All "Updated" timestamps go in descriptions.
  - Total embed size limit = 6000 chars.  Doodle descriptions are
    truncated before they hit that limit.

Official TTR API field names used throughout:
  invasions    {"invasions": {district: {type, progress, asOf}}, "lastUpdated"}
  population   {"populationByDistrict": {district: int}, "totalPopulation", "lastUpdated"}
  fieldoffices {"fieldOffices": {zone_id: {department, difficulty (0-indexed),
                                  annexes, open, expiring}}, "lastUpdated"}
  sillymeter   {"state": "Active"|"Reward"|"Inactive",
                "hp": 0-5000000, "rewards": [str×3],
                "rewardDescriptions": [str×3], "winner": str|null,
                "rewardPoints": {team:int}|null,
                "nextUpdateTimestamp": int, "asOf": int}
  doodles      {district: {playground: [{dna, traits, cost}]}}
               (top-level IS the district dict; cost not price)
"""
from __future__ import annotations

import os
import time
from typing import Any

import discord
from dotenv import load_dotenv

load_dotenv()

# ── Custom emoji from .env ────────────────────────────────────────────────────
JELLYBEAN   = os.getenv("JELLYBEAN_EMOJI",  "🫙")
COG_EMOJI   = os.getenv("COG_EMOJI",        "⚙️")
SAFE_EMOJI  = os.getenv("SAFE_EMOJI",       "🛡️")
INFINITE    = os.getenv("INFINITE_EMOJI",   "♾️")

STAR_PERFECT = os.getenv("STAR_PERFECT", "⭐")
STAR_AMAZING = os.getenv("STAR_AMAZING", "⭐")
STAR_GREAT   = os.getenv("STAR_GREAT",   "🌟")
STAR_GOOD    = os.getenv("STAR_GOOD",    "✨")
STAR_OK      = os.getenv("STAR_OK",      "💫")
STAR_BAD     = os.getenv("STAR_BAD",     "🗑️")

# ── Constants ─────────────────────────────────────────────────────────────────
MEGA_SAFE_DISTRICTS = frozenset({
    "Blam Canyon", "Gulp Gulch", "Whoosh Rapids", "Zapwood", "Welcome Valley",
})

SILLY_MAX_HP = 5_000_000

# Embed description safety limit — leaves headroom under Discord's 6000-char total cap
_DESC_LIMIT = 3_800

# ── Field Office zone IDs (official API lookup table) ─────────────────────────
ZONE_NAMES: dict[str, str] = {
    "3100": "Walrus Way",         "3200": "Sleet Street",
    "3300": "Polar Place",
    "4100": "Alto Avenue",        "4200": "Baritone Boulevard",
    "4300": "Tenor Terrace",
    "5100": "Elm Street",         "5200": "Maple Street",
    "5300": "Oak Street",
    "9100": "Lullaby Lane",       "9200": "Pajama Place",
}

_PLAYGROUND_EMOJI: dict[str, str] = {
    "Toontown Central":    "🌐",
    "Donald's Dock":       "⚓",
    "Daisy Gardens":       "🌼",
    "Minnie's Melodyland": "🎵",
    "The Brrrgh":          "❄️",
    "Donald's Dreamland":  "🌙",
}

_SILLY_TEAM_DESC: dict[str, str] = {
    "The Silliest":      "Toons are at peak silliness — everything is funnier than usual!",
    "United Toon Front": "All Toons unite under one banner for maximum toony power.",
    "Resistance Rangers":"The Resistance strikes back! Defenders of Toontown stand ready.",
    "Toon Troopers":     "Toon Troopers march forward, gags at the ready.",
    "Bean Counters":     "The Cogbucks are flowing — Cashbots beware of extra-savvy Toons.",
    "Daffy Dandies":     "Extra flair and extra laughs — style is the weapon of choice.",
    "Nature Lovers":     "Toons in harmony with Toontown's greenery. Flower power!",
    "Schemers":          "Toons with a plan. Watch out, Cogs — these Toons mean business.",
    "Tech Savvy":        "Gadgets, gizmos, and gags — these Toons have all the tools.",
    "Jokemasters":       "Puns, pratfalls, and punchlines — the funniest Toons in town.",
}

_TRAIT_RANK: dict[str, int] = {
    "Rarely Tired":          0,
    "Always Affectionate":   1, "Always Playful":    1,
    "Often Affectionate":    2, "Often Playful":     2,
    "Rarely Affectionate":   3, "Rarely Playful":    3,
    "Sometimes Affectionate":4, "Sometimes Playful": 4,
    "Pretty Calm":           5, "Pretty Excitable":  5,
    "Often Tired":           8, "Always Tired":      9,
    "Often Bored":           8, "Always Bored":      9,
    "Often Cranky":          8, "Always Cranky":     9,
    "Often Lonely":          8, "Always Lonely":     9,
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _updated_line() -> str:
    """
    Returns a 'Updated <t:unix:R>' string for embedding in a description.

    NOTE: Discord renders <t:unix:R> only in message content, embed descriptions,
    and embed field values — NOT in embed footer text.
    Always append this to the embed description, never use set_footer() with it.
    """
    return f"*Updated <t:{int(time.time())}:R>*"


def _safe_get(data: dict | None, *keys: str, default: Any = None) -> Any:
    cur = data
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k, default)
    return cur


def _fallback_desc(name: str) -> str:
    low = name.lower()
    for key, desc in _SILLY_TEAM_DESC.items():
        if key.lower() in low:
            return desc
    return ""


def _ts(unix: int | float | None) -> str:
    if not unix:
        return ""
    return f"<t:{int(unix)}:R>"


def _truncate_desc(parts: list[str], separator: str = "\n\n",
                   limit: int = _DESC_LIMIT) -> tuple[str, int]:
    """
    Join parts with separator, stopping before the total exceeds limit.
    Returns (joined_text, number_of_parts_omitted).
    """
    lines: list[str] = []
    total = 0
    omitted = 0
    for i, part in enumerate(parts):
        addition = (len(separator) if lines else 0) + len(part)
        if total + addition > limit:
            omitted = len(parts) - i
            break
        lines.append(part)
        total += addition
    return separator.join(lines), omitted


# ══════════════════════════════════════════════════════════════════════════════
# Embed 1 — Districts & Invasions
# ══════════════════════════════════════════════════════════════════════════════

def format_information(
    invasions: dict | None = None,
    population: dict | None = None,
    fieldoffices: dict | None = None,
) -> discord.Embed:
    inv_map = _safe_get(invasions, "invasions") or {}
    pop_map = _safe_get(population, "populationByDistrict") or {}
    total   = _safe_get(population, "totalPopulation") or sum(pop_map.values()) or 0

    embed = discord.Embed(title="🌎  Districts & Invasions", color=0x4FC3F7)

    if not pop_map and not inv_map:
        embed.description = f"*No district data available right now.*\n\n{_updated_line()}"
        return embed

    all_districts = sorted(
        set(pop_map) | set(inv_map),
        key=lambda d: (
            d not in inv_map,
            not inv_map.get(d, {}).get("mega", False),
            -pop_map.get(d, 0),
        ),
    )

    invasion_lines: list[str] = []
    district_lines: list[str] = []

    for district in all_districts:
        pop  = pop_map.get(district, 0)
        inv  = inv_map.get(district)
        safe = f" {SAFE_EMOJI}" if district in MEGA_SAFE_DISTRICTS else ""

        if inv:
            cog_type = inv.get("type", "Unknown")
            progress = inv.get("progress", "?/?")
            mega_tag = " 🚨 **MEGA**" if inv.get("mega") else ""
            invasion_lines.append(
                f"{COG_EMOJI} **{district}**{mega_tag} — {cog_type} `{progress}`"
            )
        else:
            district_lines.append(f"**{district}**{safe} `{pop:,}`")

    sections: list[str] = []
    if invasion_lines:
        sections.append("**⚠️ Active Invasions**\n" + "\n".join(invasion_lines))

    if district_lines:
        pairs: list[str] = []
        for i in range(0, len(district_lines), 2):
            row = district_lines[i]
            if i + 1 < len(district_lines):
                row += "  •  " + district_lines[i + 1]
            pairs.append(row)
        sections.append(
            f"**🏙️ Districts — {total:,} Toons Online**\n" + "\n".join(pairs)
        )

    sections.append(_updated_line())
    embed.description = "\n\n".join(sections) or "*No data available.*"
    return embed


# ══════════════════════════════════════════════════════════════════════════════
# Embed 2 — Field Offices
# ══════════════════════════════════════════════════════════════════════════════

def format_fieldoffices(fieldoffices: dict | None = None) -> discord.Embed:
    fo_map = _safe_get(fieldoffices, "fieldOffices") or {}

    embed = discord.Embed(title="🏢  Sellbot Field Offices", color=0xE74C3C)

    if not fo_map:
        embed.description = f"*No Field Offices are currently active.*\n\n{_updated_line()}"
        return embed

    lines: list[str] = []
    for zone_id, fo in fo_map.items():
        if not isinstance(fo, dict):
            continue

        location = ZONE_NAMES.get(str(zone_id), f"Zone {zone_id}")
        # difficulty is 0-indexed: 0=★, 1=★★, 2=★★★
        stars    = "⭐" * min(3, int(fo.get("difficulty", 0)) + 1)
        annexes  = fo.get("annexes")
        is_open  = fo.get("open", True)
        status   = "🟢 Open" if is_open else "🔴 Closed"

        if annexes is None:
            annex_str = "? annexes remaining"
        elif int(annexes) <= 0:
            exp = fo.get("expiring")
            annex_str = f"Expiring {_ts(exp)}" if exp else "Expiring soon"
        else:
            n = int(annexes)
            annex_str = f"{n} annex{'es' if n != 1 else ''} remaining"

        lines.append(f"**{location}** {stars}\n  {status}  •  {annex_str}")

    body = "\n\n".join(lines) if lines else "*No Field Offices active.*"
    embed.description = f"{body}\n\n{_updated_line()}"
    return embed


# ══════════════════════════════════════════════════════════════════════════════
# Embed 3 — Silly Meter
# ══════════════════════════════════════════════════════════════════════════════

def format_sillymeter(sillymeter: dict | None = None) -> discord.Embed:
    """
    Silly Meter embed.  Official API states: Active, Reward, Inactive.
    Key fields:
      state                "Active" | "Reward" | "Inactive"
      hp                   0-5,000,000
      rewards              [team1, team2, team3]  (name strings)
      rewardDescriptions   [desc1, desc2, desc3]
      winner               team name string (only in Reward state)
      rewardPoints         {team: int} (only in Reward state)
      nextUpdateTimestamp  epoch of next state change
    """
    embed = discord.Embed(color=0x9B59B6)

    if not sillymeter:
        embed.title       = "🎭  Silly Meter"
        embed.description = f"*Silly Meter data unavailable right now.*\n\n{_updated_line()}"
        return embed

    state   = (sillymeter.get("state") or "Inactive").strip()
    hp      = int(sillymeter.get("hp") or 0)
    next_ts = sillymeter.get("nextUpdateTimestamp")

    rewards:      list[str] = sillymeter.get("rewards") or []
    reward_descs: list[str] = sillymeter.get("rewardDescriptions") or []

    # ── Active ────────────────────────────────────────────────────────────────
    if state == "Active":
        pct    = max(0, min(100, round(hp / SILLY_MAX_HP * 100)))
        filled = round(pct / 5)
        bar    = "█" * filled + "░" * (20 - filled)
        left   = max(0, SILLY_MAX_HP - hp)

        progress = (
            f"`{bar}` **{pct}%**\n"
            f"**{hp:,}** / **{SILLY_MAX_HP:,}** Silly Points\n"
            f"**{left:,}** points to go!"
            + (f"\n*Next update: {_ts(next_ts)}*" if next_ts else "")
        )

        embed.title       = "🎭  Silly Meter — Filling Up!"
        embed.description = f"{progress}\n\n{_updated_line()}"

        if rewards:
            team_lines: list[str] = []
            for i, name in enumerate(rewards):
                desc = (reward_descs[i] if i < len(reward_descs) else "") or _fallback_desc(name)
                team_lines.append(f"**{name}**" + (f"\n*{desc}*" if desc else ""))
            embed.add_field(
                name="🏁  Competing Teams",
                value="\n\n".join(team_lines),
                inline=False,
            )

    # ── Reward ────────────────────────────────────────────────────────────────
    elif state == "Reward":
        winner     = sillymeter.get("winner") or "Unknown"
        win_desc   = _fallback_desc(winner)
        reward_pts = sillymeter.get("rewardPoints") or {}

        body = (
            "The Silly Meter reached **{:,}** Silly Points and the whole town "
            "went absolutely *bananas!* 🎊\n\n"
            "**Winner: {}**{}\n{}"
        ).format(
            SILLY_MAX_HP,
            winner,
            f"\n*{win_desc}*" if win_desc else "",
            f"\n*Rewards end: {_ts(next_ts)}*" if next_ts else "",
        )

        embed.title       = "🎉  Silly Meter — Rewards Active!"
        embed.description = f"{body}\n\n{_updated_line()}"

        if reward_pts:
            pts_lines = [
                f"{'👑 ' if t == winner else ''}**{t}** — {p:,} points"
                for t, p in sorted(reward_pts.items(), key=lambda kv: kv[1], reverse=True)
            ]
            embed.add_field(name="📊  Team Scores", value="\n".join(pts_lines), inline=False)

    # ── Inactive ──────────────────────────────────────────────────────────────
    else:
        body = (
            "The Silly Meter hit its peak and the whole town went absolutely "
            "*bananas!* 🎉\n\n"
            "The meter needs a moment to cool off from all that toontastic "
            "activity. Once it settles down a brand new round of silliness begins!"
            + (f"\n\n*Meter returns: {_ts(next_ts)}*" if next_ts else "")
        )
        embed.title       = "❄️  Silly Meter — Cooling Down"
        embed.description = f"{body}\n\n{_updated_line()}"

        if rewards:
            team_lines_: list[str] = []
            for i, name in enumerate(rewards):
                desc = (reward_descs[i] if i < len(reward_descs) else "") or _fallback_desc(name)
                team_lines_.append(f"**{name}**" + (f"\n*{desc}*" if desc else ""))
            embed.add_field(
                name="🔜  Next Round — Sneak Peek",
                value="\n\n".join(team_lines_),
                inline=False,
            )

    return embed


# ══════════════════════════════════════════════════════════════════════════════
# Doodles
# ══════════════════════════════════════════════════════════════════════════════

def _score_traits(traits: list[str]) -> tuple[str, str]:
    if not traits:
        return STAR_BAD, "Skip"
    if traits[0] == "Rarely Tired":
        return STAR_PERFECT, "Perfect"
    total = sum(_TRAIT_RANK.get(t, 6) for t in traits)
    avg   = total / len(traits)
    for threshold, star, label in [
        (0, STAR_PERFECT, "Perfect"),
        (1, STAR_AMAZING, "Amazing"),
        (3, STAR_GREAT,   "Great"),
        (5, STAR_GOOD,    "Good"),
        (7, STAR_OK,      "OK"),
    ]:
        if avg <= threshold:
            return star, label
    return STAR_BAD, "Skip"


def format_doodles(doodles: dict | None = None) -> list[discord.Embed]:
    """
    Doodle listing embeds, one per playground.

    API structure:  {district: {playground: [{dna, traits, cost}]}}
    Price field is 'cost' (not 'price').
    Each embed is hard-capped to _DESC_LIMIT chars to stay under Discord's
    6000-char total embed size limit.
    """
    updated = _updated_line()

    # Flatten {district → {playground → [doodle]}} → {playground → [doodle]}
    by_pg: dict[str, list[dict]] = {}
    if isinstance(doodles, dict):
        for _district, playgrounds in doodles.items():
            if not isinstance(playgrounds, dict):
                continue
            for pg_name, doodle_list in playgrounds.items():
                if not isinstance(doodle_list, list):
                    continue
                by_pg.setdefault(pg_name, []).extend(doodle_list)

    if not by_pg:
        embed = discord.Embed(
            title="🐾  Doodles",
            description=f"*No doodles are currently for sale.*\n\n{updated}",
            color=0xFF6B6B,
        )
        return [embed]

    embeds: list[discord.Embed] = []
    for pg_name, pg_doodles in by_pg.items():
        emoji = _PLAYGROUND_EMOJI.get(pg_name, "🐾")
        embed = discord.Embed(
            title=f"{emoji}  {pg_name} — Doodles for Sale",
            color=0xFF6B6B,
        )

        # Build each doodle's text entry
        entries: list[str] = []
        for d in pg_doodles:
            name   = d.get("name", "Unknown Doodle")
            traits = d.get("traits") or []
            cost   = d.get("cost")          # "cost" is the correct API field
            color  = d.get("color", "")

            star, label = _score_traits(traits)
            trait_str   = "  •  ".join(traits) if traits else "No traits listed"
            cost_str    = f"{JELLYBEAN} {cost:,}" if isinstance(cost, int) else ""
            color_part  = f"*{color}*  " if color else ""

            entries.append(
                f"{star} **{name}** `[{label}]`\n"
                f"  {color_part}{trait_str}"
                + (f"\n  {cost_str}" if cost_str else "")
            )

        # Fit as many entries as possible within the description limit,
        # reserving space for the updated line
        reserved    = len(updated) + 4   # "\n\n" + updated line
        body, omitted = _truncate_desc(entries, "\n\n", limit=_DESC_LIMIT - reserved)

        if not body:
            body = "*None available.*"

        if omitted:
            body += f"\n\n*… and {omitted} more. Check the Pet Shop in-game!*"

        embed.description = f"{body}\n\n{updated}"
        embeds.append(embed)

    return embeds


# ══════════════════════════════════════════════════════════════════════════════
# Feed formatters — called by bot.py _update_feed
# ══════════════════════════════════════════════════════════════════════════════

def _format_information_feed(api_data: dict) -> list[discord.Embed]:
    """3 embeds: Districts & Invasions, Field Offices, Silly Meter."""
    return [
        format_information(
            invasions=api_data.get("invasions"),
            population=api_data.get("population"),
            fieldoffices=api_data.get("fieldoffices"),
        ),
        format_fieldoffices(fieldoffices=api_data.get("fieldoffices")),
        format_sillymeter(sillymeter=api_data.get("sillymeter")),
    ]


def _format_doodles_feed(api_data: dict) -> list[discord.Embed]:
    return format_doodles(api_data.get("doodles"))


FORMATTERS: dict[str, Any] = {
    "information": _format_information_feed,
    "doodles":     _format_doodles_feed,
}