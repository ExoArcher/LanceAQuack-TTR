# -*- coding: utf-8 -*-
"""
formatters.py — Discord embed builders for LanceAQuack TTR.

All field names match the OFFICIAL TTR public API documentation exactly.
  https://github.com/toontown-rewritten/api-doc

API shapes:
  invasions    {"invasions": {district: {"type": str, "progress": "N/M",
                               "asOf": int}}, "lastUpdated": int}
  population   {"populationByDistrict": {district: int},
                "totalPopulation": int, "lastUpdated": int}
  fieldoffices {"fieldOffices": {zone_id: {"department": str,
                                  "difficulty": int,   ← zero-indexed
                                  "annexes": int,      ← NOT annexesRemaining
                                  "open": bool,
                                  "expiring": int|null}},
                "lastUpdated": int}
  sillymeter   {"state": "Active"|"Reward"|"Inactive",
                "hp": int,                             ← 0-5,000,000
                "rewards": [str, str, str],            ← team names
                "rewardDescriptions": [str, str, str], ← team descriptions
                "winner": str|null,                    ← only in "Reward"
                "rewardPoints": {team: int}|null,      ← only in "Reward"
                "nextUpdateTimestamp": int,
                "asOf": int}
  doodles      {district: {playground: [{"dna": str,
                                         "traits": [str],
                                         "cost": int}]}}
               ← top-level IS the district dict, no wrapper key
               ← cost field is "cost" NOT "price"
"""
from __future__ import annotations

import os
import time
from typing import Any

import discord
from dotenv import load_dotenv

load_dotenv()

# ── Custom emoji IDs from .env ────────────────────────────────────────────────
JELLYBEAN   = os.getenv("JELLYBEAN_EMOJI",  "🫙")   # singular: JELLYBEAN_EMOJI
COG_EMOJI   = os.getenv("COG_EMOJI",        "⚙️")
SAFE_EMOJI  = os.getenv("SAFE_EMOJI",       "🛡️")
INFINITE    = os.getenv("INFINITE_EMOJI",   "♾️")

STAR_PERFECT = os.getenv("STAR_PERFECT", "⭐")
STAR_AMAZING = os.getenv("STAR_AMAZING", "⭐")
STAR_GREAT   = os.getenv("STAR_GREAT",   "🌟")
STAR_GOOD    = os.getenv("STAR_GOOD",    "✨")
STAR_OK      = os.getenv("STAR_OK",      "💫")
STAR_BAD     = os.getenv("STAR_BAD",     "🗑️")

# ── Districts immune to Mega Invasions ────────────────────────────────────────
MEGA_SAFE_DISTRICTS = frozenset({
    "Blam Canyon", "Gulp Gulch", "Whoosh Rapids", "Zapwood", "Welcome Valley",
})

# ── Field Office zone ID → street name ───────────────────────────────────────
# Source: official TTR API documentation zone ID lookup table.
# These are the ONLY zones where field offices appear.
ZONE_NAMES: dict[str, str] = {
    # The Brrrgh streets
    "3100": "Walrus Way",
    "3200": "Sleet Street",
    "3300": "Polar Place",
    # Minnie's Melodyland streets
    "4100": "Alto Avenue",
    "4200": "Baritone Boulevard",
    "4300": "Tenor Terrace",
    # Daisy Gardens streets
    "5100": "Elm Street",
    "5200": "Maple Street",
    "5300": "Oak Street",
    # Donald's Dreamland streets
    "9100": "Lullaby Lane",
    "9200": "Pajama Place",
}

# ── Playground display emoji ──────────────────────────────────────────────────
_PLAYGROUND_EMOJI: dict[str, str] = {
    "Toontown Central":    "🌐",
    "Donald's Dock":       "⚓",
    "Daisy Gardens":       "🌼",
    "Minnie's Melodyland": "🎵",
    "The Brrrgh":          "❄️",
    "Donald's Dreamland":  "🌙",
}

# ── Silly Meter max HP ────────────────────────────────────────────────────────
SILLY_MAX_HP = 5_000_000

# ── Silly Meter team descriptions (fallback if API rewardDescriptions missing) ──
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


def _fallback_desc(name: str) -> str:
    low = name.lower()
    for key, desc in _SILLY_TEAM_DESC.items():
        if key.lower() in low:
            return desc
    return ""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _updated_footer() -> str:
    """
    Footer text: "Updated <relative timestamp>".
    Uses current wall-clock time so the footer always shows how recently
    the bot refreshed — API timestamps can be stale for slow-changing data.
    """
    return f"Updated <t:{int(time.time())}:R>"


def _ts_relative(unix: int | float | None) -> str:
    """Discord relative timestamp, or empty string if None."""
    if not unix:
        return ""
    return f"<t:{int(unix)}:R>"


def _safe_get(data: dict | None, *keys: str, default: Any = None) -> Any:
    cur = data
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k, default)
    return cur


# ══════════════════════════════════════════════════════════════════════════════
# Embed 1 — Districts & Invasions
# ══════════════════════════════════════════════════════════════════════════════

def format_information(
    invasions: dict | None = None,
    population: dict | None = None,
    fieldoffices: dict | None = None,
) -> discord.Embed:
    """Districts & Invasions embed (population + invasion data combined)."""
    inv_map = _safe_get(invasions, "invasions") or {}
    pop_map = _safe_get(population, "populationByDistrict") or {}
    total   = _safe_get(population, "totalPopulation") or sum(pop_map.values()) or 0

    embed = discord.Embed(title="🌎  Districts & Invasions", color=0x4FC3F7)

    if not pop_map and not inv_map:
        embed.description = "*No district data available right now.*"
        embed.set_footer(text=_updated_footer())
        return embed

    # Sort: invaded first (mega invasions first), then by population descending
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

    embed.description = "\n\n".join(sections) or "*No data available.*"
    embed.set_footer(text=_updated_footer())
    return embed


# ══════════════════════════════════════════════════════════════════════════════
# Embed 2 — Field Offices
# ══════════════════════════════════════════════════════════════════════════════

def format_fieldoffices(fieldoffices: dict | None = None) -> discord.Embed:
    """
    Sellbot Field Offices embed.

    API field names (per official docs):
      difficulty  zero-indexed (0=1★, 1=2★, 2=3★)
      annexes     remaining annexes (NOT annexesRemaining)
      open        boolean
      expiring    epoch timestamp when FO expires (after last annex defeated)
    """
    fo_map = _safe_get(fieldoffices, "fieldOffices") or {}

    embed = discord.Embed(title="🏢  Sellbot Field Offices", color=0xE74C3C)

    if not fo_map:
        embed.description = "*No Field Offices are currently active.*"
        embed.set_footer(text=_updated_footer())
        return embed

    lines: list[str] = []
    for zone_id, fo in fo_map.items():
        if not isinstance(fo, dict):
            continue

        location = ZONE_NAMES.get(str(zone_id), f"Zone {zone_id}")

        # difficulty is zero-indexed: 0=1★, 1=2★, 2=3★
        difficulty = int(fo.get("difficulty", 0))
        stars      = "⭐" * min(3, difficulty + 1)

        # annexes field (NOT annexesRemaining)
        annexes = fo.get("annexes")
        if annexes is None:
            annex_str = "? annexes remaining"
        elif int(annexes) <= 0:
            expiring = fo.get("expiring")
            if expiring:
                annex_str = f"Expiring {_ts_relative(expiring)}"
            else:
                annex_str = "Expiring soon"
        else:
            n = int(annexes)
            annex_str = f"{n} annex{'es' if n != 1 else ''} remaining"

        is_open = fo.get("open", True)
        status  = "🟢 Open" if is_open else "🔴 Closed"

        lines.append(
            f"**{location}** {stars}\n"
            f"  {status}  •  {annex_str}"
        )

    embed.description = "\n\n".join(lines) if lines else "*No Field Offices active.*"
    embed.set_footer(text=_updated_footer())
    return embed


# ══════════════════════════════════════════════════════════════════════════════
# Embed 3 — Silly Meter
# ══════════════════════════════════════════════════════════════════════════════

def format_sillymeter(sillymeter: dict | None = None) -> discord.Embed:
    """
    Silly Meter embed.  Handles all three official API states:

      Active    Meter is accumulating Silly Particles.
                hp     = current HP (0–5,000,000)
                rewards = [team1, team2, team3] (names)
                rewardDescriptions = [desc1, desc2, desc3]
                nextUpdateTimestamp = next points calculation

      Reward    Meter maxed, rewards active for all of Toontown.
                winner      = winning team name (string)
                rewardPoints = {team: points} for all teams
                nextUpdateTimestamp = when rewards end

      Inactive  Meter cooling down between cycles.
                nextUpdateTimestamp = when Active state resumes
                rewards / rewardDescriptions = teams for NEXT round
    """
    embed = discord.Embed(color=0x9B59B6)

    if not sillymeter:
        embed.title       = "🎭  Silly Meter"
        embed.description = "*Silly Meter data unavailable right now.*"
        embed.set_footer(text=_updated_footer())
        return embed

    state = (sillymeter.get("state") or "Inactive").strip()  # "Active", "Reward", "Inactive"
    hp    = int(sillymeter.get("hp") or 0)
    next_ts = sillymeter.get("nextUpdateTimestamp")

    # rewards and rewardDescriptions are always lists of 3 strings
    rewards:      list[str] = sillymeter.get("rewards") or []
    reward_descs: list[str] = sillymeter.get("rewardDescriptions") or []

    # ── ACTIVE ───────────────────────────────────────────────────────────────
    if state == "Active":
        pct    = max(0, min(100, round(hp / SILLY_MAX_HP * 100)))
        filled = round(pct / 5)
        bar    = "█" * filled + "░" * (20 - filled)
        pts_left = max(0, SILLY_MAX_HP - hp)

        embed.title = "🎭  Silly Meter — Filling Up!"
        embed.description = (
            f"`{bar}` **{pct}%**\n"
            f"**{hp:,}** / **{SILLY_MAX_HP:,}** Silly Points\n"
            f"**{pts_left:,}** points to go!"
            + (f"\nNext update: {_ts_relative(next_ts)}" if next_ts else "")
        )

        if rewards:
            team_lines: list[str] = []
            for i, team_name in enumerate(rewards):
                desc = (
                    reward_descs[i]
                    if i < len(reward_descs)
                    else _fallback_desc(team_name)
                )
                team_lines.append(
                    f"**{team_name}**" + (f"\n*{desc}*" if desc else "")
                )
            embed.add_field(
                name="🏁  Competing Teams",
                value="\n\n".join(team_lines),
                inline=False,
            )

    # ── REWARD ───────────────────────────────────────────────────────────────
    elif state == "Reward":
        winner      = sillymeter.get("winner") or "Unknown"
        reward_pts  = sillymeter.get("rewardPoints") or {}

        embed.title = "🎉  Silly Meter — Rewards Active!"
        embed.description = (
            f"The Silly Meter reached **{SILLY_MAX_HP:,}** Silly Points "
            "and the whole town went absolutely *bananas!* 🎊\n\n"
            f"**Winner: {winner}**\n"
            + (_fallback_desc(winner) and f"*{_fallback_desc(winner)}*\n" or "")
            + (f"\nRewards end: {_ts_relative(next_ts)}" if next_ts else "")
        )

        if reward_pts:
            pts_lines: list[str] = []
            for team_name, pts in sorted(
                reward_pts.items(), key=lambda kv: kv[1], reverse=True
            ):
                crown = "👑 " if team_name == winner else ""
                pts_lines.append(f"{crown}**{team_name}** — {pts:,} points")
            embed.add_field(
                name="📊  Team Scores",
                value="\n".join(pts_lines),
                inline=False,
            )

    # ── INACTIVE ─────────────────────────────────────────────────────────────
    else:
        embed.title = "❄️  Silly Meter — Cooling Down"
        embed.description = (
            "The Silly Meter hit its peak and the whole town went absolutely "
            "*bananas!* 🎉\n\n"
            "The meter needs a moment to cool off from all that toontastic activity. "
            "Once it settles down a brand new round of silliness begins!\n"
            + (f"\nMeter returns: {_ts_relative(next_ts)}" if next_ts else "")
        )

        if rewards:
            team_lines_: list[str] = []
            for i, team_name in enumerate(rewards):
                desc = (
                    reward_descs[i]
                    if i < len(reward_descs)
                    else _fallback_desc(team_name)
                )
                team_lines_.append(
                    f"**{team_name}**" + (f"\n*{desc}*" if desc else "")
                )
            embed.add_field(
                name="🔜  Next Round — Sneak Peek",
                value="\n\n".join(team_lines_),
                inline=False,
            )

    embed.set_footer(text=_updated_footer())
    return embed


# ══════════════════════════════════════════════════════════════════════════════
# Doodles
# ══════════════════════════════════════════════════════════════════════════════

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


def _score_traits(traits: list[str]) -> tuple[str, str]:
    """Return (star emoji, tier label)."""
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

    The TTR doodles API returns:
      {district_name: {playground_name: [{dna, traits, cost}]}}
    The top-level IS the district dict — there is no wrapper 'doodles' key.
    Price field is 'cost' (not 'price').
    """
    updated = _updated_footer()

    # Flatten district → playground → doodle list into {playground: [doodle]}
    by_pg: dict[str, list[dict]] = {}
    if isinstance(doodles, dict):
        for district_name, playgrounds in doodles.items():
            if not isinstance(playgrounds, dict):
                continue
            for pg_name, doodle_list in playgrounds.items():
                if not isinstance(doodle_list, list):
                    continue
                by_pg.setdefault(pg_name, []).extend(doodle_list)

    if not by_pg:
        embed = discord.Embed(
            title="🐾  Doodles",
            description="*No doodles are currently for sale.*",
            color=0xFF6B6B,
        )
        embed.set_footer(text=updated)
        return [embed]

    embeds: list[discord.Embed] = []
    for pg_name, pg_doodles in by_pg.items():
        emoji = _PLAYGROUND_EMOJI.get(pg_name, "🐾")
        embed = discord.Embed(
            title=f"{emoji}  {pg_name} — Doodles for Sale",
            color=0xFF6B6B,
        )
        lines: list[str] = []
        for d in pg_doodles:
            name    = d.get("name", "Unknown Doodle")
            traits  = d.get("traits") or []
            cost    = d.get("cost")        # "cost" is the correct field name
            color   = d.get("color", "")

            star, label = _score_traits(traits)
            trait_str   = "  •  ".join(traits) if traits else "No traits listed"
            cost_str    = f"{JELLYBEAN} {cost:,}" if isinstance(cost, int) else ""
            color_part  = f"*{color}*  " if color else ""

            lines.append(
                f"{star} **{name}** `[{label}]`\n"
                f"  {color_part}{trait_str}\n"
                f"  {cost_str}"
            )

        embed.description = "\n\n".join(lines) if lines else "*None available.*"
        embed.set_footer(text=updated)
        embeds.append(embed)

    return embeds


# ══════════════════════════════════════════════════════════════════════════════
# Top-level feed formatters — called by bot.py _update_feed(feed_key, api_data)
# ══════════════════════════════════════════════════════════════════════════════

def _format_information_feed(api_data: dict) -> list[discord.Embed]:
    """
    3 embeds for #tt-information:
      [0] Districts & Invasions
      [1] Sellbot Field Offices
      [2] Silly Meter
    """
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