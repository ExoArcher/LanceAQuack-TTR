# calculate.py
"""
/calculate command — suit point calculator for LanceAQuack TTR.

Usage: /calculate <suit> <level> <current_points>
Examples:
  /calculate CC 4 40
  /calculate RobberBaron 48 2200
  /calculate RB2.0 48 2200
  /calculate TBC2.0 48 5200
"""
from __future__ import annotations
import math
import discord
from discord import app_commands

# ── Currency names per faction ────────────────────────────────────────────────
CURRENCY = {
    "sellbot": "Merits",
    "cashbot": "Cogbucks",
    "lawbot":  "Jury Notices",
    "bossbot": "Stock Options",
}

FACTION_EMOJI = {
    "sellbot": "\U0001f4bc",
    "cashbot": "\U0001f4b0",
    "lawbot":  "\u2696\ufe0f",
    "bossbot": "\U0001f454",
}

# ── Activity definitions ──────────────────────────────────────────────────────
# (display_name, min_pts, max_pts)   — 2.0 suits earn double per run
ACTIVITIES = {
    "sellbot": [
        ("Scrap Factory (Short Route)",  390, 410),
        ("Scrap Factory (Long Route)",   609, 638),
        ("Steel Factory (Short Route)",  867, 950),
        ("Steel Factory (Long Route)",  1525,1630),
    ],
    "cashbot": [
        ("Coin Mint",    702,  807),
        ("Dollar Mint", 1100, 1300),
        ("Bullion Mint",1674, 1842),
    ],
    "lawbot": [
        ("DA Office A (Junior Wing)",  781,  889),
        ("DA Office B",                980, 1200),
        ("DA Office C",               1300, 1500),
        ("DA Office D (Senior Wing)", 1854, 2082),
    ],
    "bossbot": [
        ("The First Fairway (Front 3)",  906,  975),
        ("Middle Six Golf Course",      1400, 1700),
        ("The Final Fringe (Back 9)",   2165, 2305),
    ],
}

# ── Suit point tables ─────────────────────────────────────────────────────────
# Format: { canonical_key: { level: required_points } }
# canonical_key = (faction, suit_id)
# "Maxed" levels (50) are excluded — check is done before lookup.

SUIT_POINTS = {}

def _add(faction, suit_id, data):
    SUIT_POINTS[(faction, suit_id)] = data

# SELLBOT
_add("sellbot","CC",   {1:20,2:30,3:40,4:50,5:200})
_add("sellbot","TELE", {2:40,3:50,4:60,5:70,6:300})
_add("sellbot","ND",   {3:60,4:80,5:100,6:120,7:500})
_add("sellbot","GH",   {4:100,5:130,6:160,7:190,8:800})
_add("sellbot","MS",   {5:160,6:210,7:260,8:310,9:1300})
_add("sellbot","TF",   {6:260,7:340,8:420,9:500,10:2100})
_add("sellbot","MING", {7:420,8:550,9:680,10:810,11:3400})
_add("sellbot","MH",   {
    8:680,9:890,10:1100,11:1310,12:5500,13:680,14:5500,
    15:680,16:890,17:1100,18:1310,19:5500,20:680,21:890,22:1100,23:1310,
    24:1520,25:1730,26:1940,27:2150,28:2360,29:5500,30:680,31:890,32:1100,
    33:1310,34:1520,35:1730,36:1940,37:2150,38:2360,39:5500,40:680,41:890,
    42:1100,43:1310,44:1520,45:1730,46:1940,47:2150,48:2360,49:5500,
})

# CASHBOT
_add("cashbot","SC",      {1:40,2:50,3:60,4:70,5:300})
_add("cashbot","PP_CASH", {2:60,3:80,4:100,5:120,6:500})
_add("cashbot","TW",      {3:100,4:130,5:160,6:190,7:800})
_add("cashbot","BC",      {4:160,5:210,6:260,7:310,8:1300})
_add("cashbot","NC",      {5:260,6:340,7:420,8:500,9:2100})
_add("cashbot","MB",      {6:420,7:550,8:680,9:810,10:3400})
_add("cashbot","LS",      {7:680,8:890,9:1100,10:1310,11:5500})
_add("cashbot","RB",      {
    8:1100,9:1440,10:1780,11:2120,12:8900,13:1100,14:8900,
    15:1100,16:1440,17:1780,18:2120,19:8900,20:1100,21:1440,22:1780,23:2120,
    24:2460,25:2800,26:3140,27:3480,28:3820,29:8900,30:1100,31:1440,32:1780,
    33:2120,34:2460,35:2800,36:3140,37:3480,38:3820,39:8900,40:1100,41:1440,
    42:1780,43:2120,44:2460,45:2800,46:3140,47:3480,48:3820,49:8900,
})

# LAWBOT
_add("lawbot","BF",       {1:60,2:80,3:100,4:120,5:500})
_add("lawbot","BLOOD",    {2:100,3:130,4:160,5:190,6:800})
_add("lawbot","DT",       {3:160,4:240,5:260,6:310,7:1300})
_add("lawbot","AC",       {4:260,5:340,6:420,7:500,8:2100})
_add("lawbot","BACKSTAB", {5:420,6:550,7:680,8:810,9:3400})
_add("lawbot","SD",       {6:680,7:890,8:1100,9:1310,10:5500})
_add("lawbot","LE",       {7:1110,8:1440,9:1780,10:2120,11:8900})
_add("lawbot","BW",       {
    8:1780,9:2330,10:2880,11:3430,12:14400,13:1780,14:14400,
    15:1780,16:2330,17:2880,18:3430,19:14400,20:1780,21:2330,22:2880,23:3430,
    24:3980,25:4530,26:5080,27:5630,28:6180,29:14400,30:1780,31:2330,32:2880,
    33:3430,34:3980,35:4530,36:5080,37:5630,38:6180,39:14400,40:1780,41:2330,
    42:2880,43:3430,44:3980,45:4530,46:5080,47:5630,48:6180,49:14400,
})

# BOSSBOT
_add("bossbot","FL",      {1:100,2:130,3:160,4:190,5:800})
_add("bossbot","PP_BOSS", {2:160,3:210,4:260,5:310,6:1300})
_add("bossbot","YM",      {3:260,4:340,5:420,6:500,7:2100})
_add("bossbot","MM",      {4:420,5:550,6:680,7:810,8:3400})
_add("bossbot","DS",      {5:680,6:890,7:1100,8:1310,9:5500})
_add("bossbot","HH",      {6:1100,7:1400,8:1780,9:2120,10:8900})
_add("bossbot","CR",      {7:1780,8:2330,9:2880,10:3430,11:14400})
_add("bossbot","TBC",     {
    8:2880,9:3770,10:4660,11:5500,12:23330,13:2880,14:23300,
    15:2800,16:3770,17:4660,18:5500,19:23330,20:2880,21:3770,22:4660,23:5500,
    24:6440,25:7330,26:8220,27:9110,28:10000,29:23330,30:2880,31:3770,32:4660,
    33:5500,34:6440,35:7330,36:8220,37:9110,38:10000,39:23330,40:2880,41:3770,
    42:4660,43:5500,44:6440,45:7330,46:8220,47:9110,48:10000,49:23330,
})

# 2.0 suits: same point requirements — only activity efficiency doubles.
# Valid 2.0 suit IDs per faction:
V2_SUITS = {
    "sellbot": {"MH"},
    "cashbot": {"RB"},
    "lawbot":  {"BW"},
    "bossbot": {"TBC"},
}

# Suit display names
SUIT_NAMES = {
    ("sellbot","CC"):      "Cold Caller",
    ("sellbot","TELE"):    "Telemarketer",
    ("sellbot","ND"):      "Name Dropper",
    ("sellbot","GH"):      "Glad Hander",
    ("sellbot","MS"):      "Mover & Shaker",
    ("sellbot","TF"):      "Two-Face",
    ("sellbot","MING"):    "The Mingler",
    ("sellbot","MH"):      "Mr. Hollywood",
    ("cashbot","SC"):      "Short Change",
    ("cashbot","PP_CASH"): "Penny Pincher",
    ("cashbot","TW"):      "Tightwad",
    ("cashbot","BC"):      "Bean Counter",
    ("cashbot","NC"):      "Number Cruncher",
    ("cashbot","MB"):      "Money Bags",
    ("cashbot","LS"):      "Loan Shark",
    ("cashbot","RB"):      "Robber Baron",
    ("lawbot","BF"):       "Bottom Feeder",
    ("lawbot","BLOOD"):    "Bloodsucker",
    ("lawbot","DT"):       "Double Talker",
    ("lawbot","AC"):       "Ambulance Chaser",
    ("lawbot","BACKSTAB"): "Back Stabber",
    ("lawbot","SD"):       "Spin Doctor",
    ("lawbot","LE"):       "Legal Eagle",
    ("lawbot","BW"):       "Big Wig",
    ("bossbot","FL"):      "Flunky",
    ("bossbot","PP_BOSS"): "Pencil Pusher",
    ("bossbot","YM"):      "Yesman",
    ("bossbot","MM"):      "Micromanager",
    ("bossbot","DS"):      "Downsizer",
    ("bossbot","HH"):      "Head Hunter",
    ("bossbot","CR"):      "Corporate Raider",
    ("bossbot","TBC"):     "The Big Cheese",
}

# ── Name resolution ───────────────────────────────────────────────────────────
# Maps lowercase normalised input -> list of (faction, suit_id) candidates
# Multiple candidates mean disambiguation is needed.

_NAME_MAP: dict[str, list[tuple[str,str]]] = {
    # SELLBOT
    "coldcaller":     [("sellbot","CC")],
    "cold caller":    [("sellbot","CC")],
    "cc":             [("sellbot","CC")],
    "telemarketer":   [("sellbot","TELE")],
    "tele":           [("sellbot","TELE")],
    "namedropper":    [("sellbot","ND")],
    "name dropper":   [("sellbot","ND")],
    "nd":             [("sellbot","ND")],
    "gladhander":     [("sellbot","GH")],
    "glad hander":    [("sellbot","GH")],
    "gh":             [("sellbot","GH")],
    "mover&shaker":   [("sellbot","MS")],
    "mover & shaker": [("sellbot","MS")],
    "movershaker":    [("sellbot","MS")],
    "mover and shaker":[("sellbot","MS")],
    "ms":             [("sellbot","MS")],
    "twoface":        [("sellbot","TF")],
    "two-face":       [("sellbot","TF")],
    "two face":       [("sellbot","TF")],
    "tf":             [("sellbot","TF")],
    "themingler":     [("sellbot","MING")],
    "the mingler":    [("sellbot","MING")],
    "mingler":        [("sellbot","MING")],
    "mrhollywood":    [("sellbot","MH")],
    "mr. hollywood":  [("sellbot","MH")],
    "mr hollywood":   [("sellbot","MH")],
    "hollywood":      [("sellbot","MH")],
    "mh":             [("sellbot","MH")],
    # TM is ambiguous (Telemarketer or Mingler — resolved by level in lookup)
    "tm":             [("sellbot","TELE"), ("sellbot","MING")],
    # CASHBOT
    "shortchange":    [("cashbot","SC")],
    "short change":   [("cashbot","SC")],
    "sc":             [("cashbot","SC")],
    "pennypincher":   [("cashbot","PP_CASH")],
    "penny pincher":  [("cashbot","PP_CASH")],
    "tightwad":       [("cashbot","TW")],
    "tw":             [("cashbot","TW")],
    "beancounter":    [("cashbot","BC")],
    "bean counter":   [("cashbot","BC")],
    "bc":             [("cashbot","BC")],
    "numbercruncher": [("cashbot","NC")],
    "number cruncher":[("cashbot","NC")],
    "nc":             [("cashbot","NC")],
    "moneybags":      [("cashbot","MB")],
    "money bags":     [("cashbot","MB")],
    "mb":             [("cashbot","MB")],
    "loanshark":      [("cashbot","LS")],
    "loan shark":     [("cashbot","LS")],
    "ls":             [("cashbot","LS")],
    "robberbaron":    [("cashbot","RB")],
    "robber baron":   [("cashbot","RB")],
    "rb":             [("cashbot","RB")],
    # LAWBOT
    "bottomfeeder":   [("lawbot","BF")],
    "bottom feeder":  [("lawbot","BF")],
    "bf":             [("lawbot","BF")],
    "bloodsucker":    [("lawbot","BLOOD")],
    "doubletalker":   [("lawbot","DT")],
    "double talker":  [("lawbot","DT")],
    "dt":             [("lawbot","DT")],
    "ambulancechaser":[("lawbot","AC")],
    "ambulance chaser":[("lawbot","AC")],
    "ac":             [("lawbot","AC")],
    "backstabber":    [("lawbot","BACKSTAB")],
    "back stabber":   [("lawbot","BACKSTAB")],
    "spindoctor":     [("lawbot","SD")],
    "spin doctor":    [("lawbot","SD")],
    "sd":             [("lawbot","SD")],
    "legaleagle":     [("lawbot","LE")],
    "legal eagle":    [("lawbot","LE")],
    "le":             [("lawbot","LE")],
    "bigwig":         [("lawbot","BW")],
    "big wig":        [("lawbot","BW")],
    "bw":             [("lawbot","BW")],
    # BS ambiguous within lawbot — resolved by level
    "bs":             [("lawbot","BLOOD"), ("lawbot","BACKSTAB")],
    "b":              [("lawbot","BLOOD")],
    # BOSSBOT
    "flunky":         [("bossbot","FL")],
    "fl":             [("bossbot","FL")],
    "pencilpusher":   [("bossbot","PP_BOSS")],
    "pencil pusher":  [("bossbot","PP_BOSS")],
    "yesman":         [("bossbot","YM")],
    "ym":             [("bossbot","YM")],
    "y":              [("bossbot","YM")],
    "micromanager":   [("bossbot","MM")],
    "mm":             [("bossbot","MM")],
    "downsizer":      [("bossbot","DS")],
    "ds":             [("bossbot","DS")],
    "headhunter":     [("bossbot","HH")],
    "head hunter":    [("bossbot","HH")],
    "hh":             [("bossbot","HH")],
    "corporateraider":[("bossbot","CR")],
    "corporate raider":[("bossbot","CR")],
    "cr":             [("bossbot","CR")],
    "thebigcheese":   [("bossbot","TBC")],
    "the big cheese": [("bossbot","TBC")],
    "bigcheese":      [("bossbot","TBC")],
    "big cheese":     [("bossbot","TBC")],
    "tbc":            [("bossbot","TBC")],
    # PP is ambiguous across factions
    "pp": [("cashbot","PP_CASH"), ("bossbot","PP_BOSS")],
}


def _resolve_suit(raw: str, level: int) -> tuple[str, str] | None | str:
    """
    Returns (faction, suit_id), None if not found, or an error string if ambiguous.
    """
    raw = raw.strip().lower()
    candidates = _NAME_MAP.get(raw)
    if candidates is None:
        return None
    if len(candidates) == 1:
        return candidates[0]
    # Disambiguate by level: pick the candidate whose level range contains `level`
    valid = [
        c for c in candidates
        if level in SUIT_POINTS.get(c, {})
    ]
    if len(valid) == 1:
        return valid[0]
    if len(valid) == 0:
        return None
    # Still ambiguous — return list as error string
    names = [SUIT_NAMES.get(c, c[1]) for c in valid]
    return f"Ambiguous suit name — did you mean: {', '.join(names)}? Please use the full name."


# ── Activity recommendation ───────────────────────────────────────────────────

def _recommend(needed: int, faction: str, is_v2: bool) -> list[str]:
    """
    Returns up to 4 activity suggestions as formatted strings.
    Each suggestion shows runs needed and expected range.
    """
    acts = ACTIVITIES[faction]
    multiplier = 2 if is_v2 else 1
    options = []
    for name, lo, hi in acts:
        eff_lo = lo * multiplier
        eff_hi = hi * multiplier
        avg    = (eff_lo + eff_hi) / 2
        runs   = math.ceil(needed / avg)
        total_lo = eff_lo * runs
        total_hi = eff_hi * runs
        options.append((runs, name, eff_lo, eff_hi, total_lo, total_hi))
    # Sort: fewest runs first, break ties by highest guaranteed yield
    options.sort(key=lambda x: (x[0], -x[5]))
    lines = []
    for runs, name, eff_lo, eff_hi, total_lo, total_hi in options:
        unit = "run" if runs == 1 else "runs"
        lines.append(
            f"• **{runs}× {name}** "
            f"({eff_lo:,}–{eff_hi:,} pts/run → ~{total_lo:,}–{total_hi:,} total)"
        )
    return lines


# ── Discord command registration ──────────────────────────────────────────────

def register_calculate(bot) -> None:
    """Call once from on_ready / setup_commands to add /calculate."""

    @bot.tree.command(
        name="calculate",
        description="Calculate how many points you need to level up your cog suit disguise.",
    )
    @app_commands.describe(
        suit="Suit name or abbreviation — add \'2.0\' for 2.0 suits (e.g. CC, RB, MrHollywood2.0)",
        level="Your current suit level number",
        current_points="How many points you currently have for this level",
    )
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def calculate(
        interaction: discord.Interaction,
        suit: str,
        level: int,
        current_points: int,
    ) -> None:
        # ── Parse 2.0 flag ────────────────────────────────────────────────────
        suit_raw = suit.strip()
        is_v2 = False
        for suffix in ("2.0", "v2", " 2.0", ".2.0"):
            if suit_raw.lower().endswith(suffix):
                is_v2 = True
                suit_raw = suit_raw[: -len(suffix)].strip()
                break

        # ── Resolve suit name ─────────────────────────────────────────────────
        result = _resolve_suit(suit_raw, level)
        if result is None:
            await interaction.response.send_message(
                f"Unknown suit: **{suit}**\n"
                "Use abbreviations like `CC`, `RB`, `TBC`, or the full suit name.\n"
                "Add `2.0` for 2.0 suits, e.g. `RB2.0`.",
                ephemeral=True,
            )
            return
        if isinstance(result, str):
            await interaction.response.send_message(result, ephemeral=True)
            return
        faction, suit_id = result

        # ── Validate 2.0 ──────────────────────────────────────────────────────
        if is_v2 and suit_id not in V2_SUITS.get(faction, set()):
            v2_name = SUIT_NAMES.get((faction, list(V2_SUITS[faction])[0]), "the final suit")
            await interaction.response.send_message(
                f"Only the final suit in each faction has a 2.0 variant.\n"
                f"For {faction.title()}, that\'s **{v2_name}**.\n"
                f"Did you mean `{list(V2_SUITS[faction])[0]}2.0 {level}`?",
                ephemeral=True,
            )
            return

        suit_display = SUIT_NAMES.get((faction, suit_id), suit_id)
        if is_v2:
            suit_display += " 2.0"
        currency  = CURRENCY[faction]
        emoji     = FACTION_EMOJI[faction]
        pts_table = SUIT_POINTS.get((faction, suit_id), {})

        # ── Validate level ────────────────────────────────────────────────────
        if level <= 0:
            await interaction.response.send_message(
                "Level must be a positive number.", ephemeral=True
            )
            return
        if level == 50:
            await interaction.response.send_message(
                f"{emoji} **{suit_display}** at level 50 is **maxed out** — no more {currency} needed! 🐾",
                ephemeral=True,
            )
            return
        if level not in pts_table:
            min_lvl = min(pts_table.keys())
            max_lvl = max(pts_table.keys())
            await interaction.response.send_message(
                f"**{suit_display}** only exists at levels {min_lvl}–{max_lvl} (or 50 when maxed).\n"
                f"You entered level **{level}** — double-check your current level.",
                ephemeral=True,
            )
            return

        required = pts_table[level]
        needed   = max(0, required - current_points)
        pct      = min(100.0, (current_points / required) * 100) if required > 0 else 100.0

        # ── Build embed ───────────────────────────────────────────────────────
        if needed == 0:
            embed = discord.Embed(
                title=f"{emoji} {suit_display} — Level {level} Complete!",
                description=(
                    f"You have **{current_points:,}** {currency} — that\'s enough to level up!\n"
                    f"Head to the {faction.title()} HQ to promote your suit. 🐾"
                ),
                color=0x2ECC71,
            )
        else:
            progress_bar = _progress_bar(pct)
            recs = _recommend(needed, faction, is_v2)
            v2_note = " (2.0 — activities award double points)" if is_v2 else ""

            embed = discord.Embed(
                title=f"{emoji} {suit_display}{v2_note} — Level {level}",
                color=_faction_color(faction),
            )
            embed.add_field(
                name=f"{currency} Progress",
                value=(
                    f"{progress_bar} **{pct:.1f}%**\n"
                    f"Have: **{current_points:,}** / Need: **{required:,}**\n"
                    f"Still needed: **{needed:,}** {currency}"
                ),
                inline=False,
            )
            embed.add_field(
                name="\U0001f4ca Recommended Activities",
                value="\n".join(recs) or "No activity data available.",
                inline=False,
            )

        embed.set_footer(text="LanceAQuack TTR • Suit Calculator")
        await interaction.response.send_message(embed=embed, ephemeral=True)


def _progress_bar(pct: float, length: int = 12) -> str:
    filled = round(pct / 100 * length)
    return "\u2588" * filled + "\u2591" * (length - filled)


def _faction_color(faction: str) -> int:
    return {
        "sellbot": 0xE74C3C,
        "cashbot": 0xF1C40F,
        "lawbot":  0x3498DB,
        "bossbot": 0x2ECC71,
    }.get(faction, 0x95A5A6)
