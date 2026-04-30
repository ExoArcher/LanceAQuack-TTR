# -*- coding: utf-8 -*-
"""
formatters.py — Discord embed builders for LanceAQuack TTR.

Produces three embeds for #tt-information (districts+invasions / field offices
/ silly meter) and a per-playground set for #tt-doodles.

FORMATTERS maps feed_key -> callable(api_data) -> list[discord.Embed].

TTR public API shapes (https://github.com/toontown-rewritten/api-doc):
  invasions    {"invasions": {district: {"type": str, "progress": "N/M",
                               "asOf": int, "mega": bool}}, "asOf": int}
  population   {"populationByDistrict": {district: int},
                "totalPopulation": int, "asOf": int}
  fieldoffices {"fieldOffices": {zone_id: {"department": str,
                                  "difficulty": int, "annexesRemaining": int,
                                  "open": bool, "asOf": int}}, "asOf": int}
  sillymeter   {"winner":    {teamName, description} | null,
                "teams":     [{teamIndex, teamName, description}] | null,
                "nextTeams": [{teamIndex, teamName, description}] | null,
                "phase": "active" | "cooldown" | "sneak-peak",
                "sillymeterPoints": int,       (active phase only)
                "maxSillyMeterPoints": int,    (active phase only)
                "asOf": int}
  doodles      {"doodles": [{name, traits, price, color, playground}],
                "asOf": int}
"""
from __future__ import annotations

import os
import time
from typing import Any

import discord
from dotenv import load_dotenv

load_dotenv()

# ── Custom emoji IDs from .env ────────────────────────────────────────────────
# NOTE: env var is JELLYBEAN_EMOJI (singular, not JELLYBEANS_EMOJI)
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

# ── Districts immune to Mega Invasions ────────────────────────────────────────
MEGA_SAFE_DISTRICTS = frozenset({
    "Blam Canyon", "Gulp Gulch", "Whoosh Rapids", "Zapwood", "Welcome Valley",
})

# ── Field office zone ID → human-readable name ────────────────────────────────
ZONE_NAMES: dict[str, str] = {
    # Toontown Central
    "2000": "Toontown Central",
    "2100": "Silly Street",
    "2200": "Loopy Lane",
    "2300": "Punchline Place",
    # Donald's Dock
    "3000": "Donald's Dock",
    "3100": "Lighthouse Lane",
    "3200": "Seaweed Street",
    "3300": "Barnacle Boulevard",
    # Daisy Gardens
    "4000": "Daisy Gardens",
    "4100": "Elm Street",
    "4200": "Maple Street",
    "4300": "Oak Street",
    # Minnie's Melodyland
    "5000": "Minnie's Melodyland",
    "5100": "Alto Avenue",
    "5200": "Baritone Boulevard",
    "5300": "Tenor Terrace",
    # The Brrrgh
    "6000": "The Brrrgh",
    "6100": "Walrus Way",
    "6200": "Sleet Street",
    "6300": "Polar Place",
    # Donald's Dreamland
    "7000": "Donald's Dreamland",
    "7100": "Lullaby Lane",
    "7200": "Pajama Place",
    # Chip 'n Dale's Acorn Acres
    "9000": "Chip 'n Dale's Acorn Acres",
    # HQ zones
    "9100": "Sellbot HQ",
    "9200": "Cashbot HQ",
    "9300": "Lawbot HQ",
    "9400": "Bossbot HQ",
}

# ── Silly Meter team descriptions ─────────────────────────────────────────────
SILLY_TEAM_DESC: dict[str, str] = {
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


def _team_desc_fallback(name: str | None) -> str:
    """Fuzzy-match a description from our local table if the API didn't provide one."""
    if not name:
        return ""
    low = name.lower()
    for key, desc in SILLY_TEAM_DESC.items():
        if key.lower() in low:
            return desc
    return ""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _updated_footer() -> str:
    """
    Footer text showing when the bot last refreshed this embed.

    Uses the current wall-clock time rather than the API's asOf field,
    because asOf can be stale (e.g. the Silly Meter during cooldown may
    not have changed for hours, giving a misleading 'Updated 5 days ago').
    Discord renders <t:unix:R> as a live-updating relative timestamp.
    """
    return f"Updated <t:{int(time.time())}:R>"


def _safe_get(data: dict | None, *keys: str, default: Any = None) -> Any:
    cur = data
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k, default)
    return cur


def _team_name(team: dict | None) -> str | None:
    """Extract a team name from a team dict. TTR API uses 'teamName' field."""
    if not team:
        return None
    return team.get("teamName") or team.get("name") or None


def _format_team_list(teams: list[dict]) -> str:
    """Format a list of team dicts into a compact embed field."""
    lines: list[str] = []
    for t in teams:
        tname = _team_name(t) or "?"
        # Prefer the API-provided description; fall back to our local table
        tdesc = t.get("description") or _team_desc_fallback(tname)
        lines.append(f"**{tname}**" + (f"\n*{tdesc}*" if tdesc else ""))
    return "\n\n".join(lines) or "*No teams listed.*"


# ══════════════════════════════════════════════════════════════════════════════
# Embed 1 — Districts & Invasions
# ══════════════════════════════════════════════════════════════════════════════

def format_information(
    invasions: dict | None = None,
    population: dict | None = None,
    fieldoffices: dict | None = None,
) -> discord.Embed:
    """Districts & Invasions embed."""
    inv_map = _safe_get(invasions, "invasions") or {}
    pop_map = _safe_get(population, "populationByDistrict") or {}
    total   = _safe_get(population, "totalPopulation") or sum(pop_map.values()) or 0

    embed = discord.Embed(title="🌎  Districts & Invasions", color=0x4FC3F7)

    if not pop_map and not inv_map:
        embed.description = "*No district data available right now.*"
        embed.set_footer(text=_updated_footer())
        return embed

    # Sort: invaded first (mega first), then by population descending
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
    """Field Offices embed."""
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

        location   = ZONE_NAMES.get(str(zone_id), f"Zone {zone_id}")
        difficulty = max(1, min(3, int(fo.get("difficulty", 1))))
        stars      = "⭐" * difficulty
        annexes    = fo.get("annexesRemaining")
        is_open    = fo.get("open", True)
        status     = "🟢 Open" if is_open else "🔴 Closed"

        if annexes is None:
            annex_str = "? annexes remaining"
        elif int(annexes) == -1:
            annex_str = f"{INFINITE} Kaboomberg"
        else:
            n = int(annexes)
            annex_str = f"{n} annex{'es' if n != 1 else ''} remaining"

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
    Silly Meter embed.  Handles three TTR API phases:

      active     Meter is filling.  `teams` list holds current teams (first
                 entry is the leader).  `sillymeterPoints` / `maxSillyMeterPoints`
                 give progress.  `winner` is null during this phase.

      cooldown   Meter maxed, resetting.  `winner` holds the last winning team.
                 Points fields are absent.  `nextTeams` previews upcoming round.

      sneak-peak Meter between cycles.  `nextTeams` teases upcoming teams.
                 Both `winner` and `teams` may be null.
    """
    embed = discord.Embed(color=0x9B59B6)

    if not sillymeter:
        embed.title       = "🎭  Silly Meter"
        embed.description = "*Silly Meter data unavailable right now.*"
        embed.set_footer(text=_updated_footer())
        return embed

    raw_phase = (sillymeter.get("phase") or "active").lower()
    if "cooldown" in raw_phase or "cool" in raw_phase:
        phase = "cooldown"
    elif "sneak" in raw_phase:
        phase = "sneak_peek"
    else:
        phase = "active"

    # Extract lists — all may be None in the API response
    teams_list: list[dict]   = sillymeter.get("teams") or []
    winner_dict: dict | None = (
        sillymeter.get("winner")
        if isinstance(sillymeter.get("winner"), dict)
        else None
    )
    next_teams: list[dict]   = sillymeter.get("nextTeams") or []

    # Points only present during active phase
    raw_pts    = sillymeter.get("sillymeterPoints")
    raw_max    = sillymeter.get("maxSillyMeterPoints")
    points     = int(raw_pts) if raw_pts is not None else 0
    max_points = int(raw_max) if raw_max else 0

    # ── ACTIVE ───────────────────────────────────────────────────────────────
    if phase == "active":
        leading   = teams_list[0] if teams_list else {}
        lead_name = _team_name(leading) or "Unknown"
        lead_desc = leading.get("description") or _team_desc_fallback(lead_name)

        if max_points > 0:
            pct      = max(0, min(100, round(points / max_points * 100)))
            filled   = round(pct / 5)
            bar      = "█" * filled + "░" * (20 - filled)
            pts_left = max(0, max_points - points)
            prog     = (
                f"`{bar}` **{pct}%**\n"
                f"**{points:,}** / **{max_points:,}** Silly Points\n"
                f"**{pts_left:,}** points to go!"
            )
        else:
            prog = "*Progress data unavailable.*"

        embed.title = "🎭  Silly Meter — Filling Up!"
        parts = [f"**{lead_name}** is leading the charge!"]
        if lead_desc:
            parts.append(f"*{lead_desc}*")
        parts.append("")
        parts.append(prog)
        embed.description = "\n".join(parts)

        if len(teams_list) > 1:
            embed.add_field(
                name="🏁  Also Competing",
                value=_format_team_list(teams_list[1:]),
                inline=False,
            )

        if next_teams:
            embed.add_field(
                name="👀  Coming Up Next",
                value=_format_team_list(next_teams[:3]),
                inline=False,
            )

    # ── COOLDOWN ─────────────────────────────────────────────────────────────
    elif phase == "cooldown":
        winner_name = _team_name(winner_dict) or "Unknown"
        winner_desc = (
            (winner_dict.get("description") if winner_dict else None)
            or _team_desc_fallback(winner_name)
        )

        embed.title = "❄️  Silly Meter — Cooling Down"
        embed.description = (
            "The Silly Meter reached its peak and the whole town went absolutely "
            "*bananas!* 🎉\n\n"
            "The meter needs a moment to cool off from all that toontastic activity. "
            "Once it settles down a brand new set of Silly Teams will step up to "
            "keep the laughs going.\n\n"
            f"**Last winner:** {winner_name}"
            + (f"\n*{winner_desc}*" if winner_desc else "")
        )

        if next_teams:
            embed.add_field(
                name="🔜  Next Up — Sneak Peek",
                value=_format_team_list(next_teams[:3]),
                inline=False,
            )

    # ── SNEAK PEEK ────────────────────────────────────────────────────────────
    else:
        embed.title = "👀  Silly Meter — Sneak Peek!"
        embed.description = (
            "The meter is gearing up for its next cycle. "
            "Here's a sneak peek at the teams lined up for the next round of silliness!"
        )
        if next_teams:
            embed.add_field(
                name="🎭  Upcoming Teams",
                value=_format_team_list(next_teams[:3]),
                inline=False,
            )
        else:
            embed.description += "\n\n*No lineup announced yet — check back soon!*"

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

_PLAYGROUND_EMOJI: dict[str, str] = {
    "Toontown Central":    "🌐",
    "Donald's Dock":       "⚓",
    "Daisy Gardens":       "🌼",
    "Minnie's Melodyland": "🎵",
    "The Brrrgh":          "❄️",
    "Donald's Dreamland":  "🌙",
}


def _score_traits(traits: list[str]) -> tuple[str, str]:
    """Return (star emoji, tier label) for a list of trait strings."""
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
    """Build the doodle listing embeds, one per playground."""
    doodle_list = _safe_get(doodles, "doodles") or []
    updated     = _updated_footer()

    if not doodle_list:
        embed = discord.Embed(
            title="🐾  Doodles",
            description="*No doodles are currently for sale.*",
            color=0xFF6B6B,
        )
        embed.set_footer(text=updated)
        return [embed]

    by_pg: dict[str, list[dict]] = {}
    for doodle in doodle_list:
        pg = doodle.get("playground", "Unknown")
        by_pg.setdefault(pg, []).append(doodle)

    embeds: list[discord.Embed] = []
    for pg_name, pg_doodles in by_pg.items():
        emoji = _PLAYGROUND_EMOJI.get(pg_name, "🐾")
        embed = discord.Embed(
            title=f"{emoji}  {pg_name} — Doodles for Sale",
            color=0xFF6B6B,
        )
        lines: list[str] = []
        for d in pg_doodles:
            name      = d.get("name", "Unknown Doodle")
            traits    = d.get("traits") or []
            price     = d.get("price")
            clr       = d.get("color", "")

            star, label = _score_traits(traits)
            trait_str   = "  •  ".join(traits) if traits else "No traits listed"
            price_str   = f"{JELLYBEAN} {price:,}" if isinstance(price, int) else ""
            clr_part    = f"*{clr}*  " if clr else ""

            lines.append(
                f"{star} **{name}** `[{label}]`\n"
                f"  {clr_part}{trait_str}\n"
                f"  {price_str}"
            )

        embed.description = "\n\n".join(lines) if lines else "*None available.*"
        embed.set_footer(text=updated)
        embeds.append(embed)

    return embeds or [
        discord.Embed(
            title="🐾  Doodles",
            description="*No doodles are currently for sale.*",
            color=0xFF6B6B,
        )
    ]


# ══════════════════════════════════════════════════════════════════════════════
# Top-level feed formatters — called by bot.py _update_feed
# ══════════════════════════════════════════════════════════════════════════════

def _format_information_feed(api_data: dict) -> list[discord.Embed]:
    """
    Returns 3 embeds for #tt-information:
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
