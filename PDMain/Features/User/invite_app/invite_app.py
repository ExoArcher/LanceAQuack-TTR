"""User App invite command for Paws Pendragon TTR Discord bot.

Provides the `/invite-app` slash command, which DMs users a link to add the bot
to their personal Discord account (User App install). Works in servers, DMs,
group chats, and as a User App with no server membership required.

Command flow:
    1. Check if user is banned (reject with ephemeral message if true)
    2. Build User App install OAuth2 link using bot.user.id
    3. Create embed with invite link and setup instructions
    4. Attempt to send embed via DM
    5. If DM blocked, send ephemeral embed in channel instead

Design patterns:
    - DM-first, ephemeral fallback (graceful DM failure)
    - Ban check before processing
    - No API calls (instant response, all static data)
    - Full async/await with type hints
    - User App compatible (@allowed_installs, @allowed_contexts)
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands

if TYPE_CHECKING:
    from discord import Interaction

log = logging.getLogger("ttr-bot.invite-app")

# Bot User App install link template.
# Uses bot.user.id at runtime to support multiple deployments.
INVITE_APP_LINK_TEMPLATE = (
    "https://discord.com/api/oauth2/authorize"
    "?client_id={bot_id}"
    "&scope=applications.commands"
)

# Fallback hardcoded bot ID (for reference/testing only).
# Real implementation uses bot.user.id at runtime.
_FALLBACK_BOT_ID = "1496971496709689654"


def _build_invite_embed(bot_id: int) -> discord.Embed:
    """Build the User App invite embed with link and instructions.

    Args:
        bot_id: The bot's Discord user ID.

    Returns:
        A formatted discord.Embed with title, link, and setup instructions.
    """
    link = INVITE_APP_LINK_TEMPLATE.format(bot_id=bot_id)

    embed = discord.Embed(
        title="Add Paws Pendragon to Your Account",
        description=(
            f"[Click here to add the bot to your personal Discord account]({link})\n\n"
            "**About the bot**\n"
            "Paws Pendragon TTR is a Toontown Rewritten companion bot. "
            "It delivers live game data — district populations, cog invasions, "
            "active field offices, Silly Meter status, and the full doodle guide — "
            "directly to your DMs from anywhere in Discord.\n\n"
            "**Permissions requested**\n"
            "This is a **User App install** — it does **not** join your server and "
            "requires **no server permissions**. "
            "It adds the slash commands `/ttrinfo`, `/doodleinfo`, `/calculate`, "
            "`/beanfest`, `/helpme`, `/invite-app`, and `/invite-server` to your "
            "personal Discord account, usable in any server, DM, or group chat."
        ),
        color=0x9124F2,
    )
    return embed


async def _send_invite_via_dm(user: discord.abc.User, embed: discord.Embed) -> bool:
    """Attempt to send the invite embed to a user via DM.

    Args:
        user: The Discord user to DM.
        embed: The invite embed to send.

    Returns:
        True if DM was sent successfully, False if blocked or errored.
    """
    try:
        await user.send(embed=embed)
        log.info("Sent invite-app embed to user %s via DM (id=%s)", user, user.id)
        return True
    except discord.Forbidden:
        log.debug("User %s (id=%s) has DMs disabled", user, user.id)
        return False
    except Exception as exc:
        log.warning(
            "Unexpected error sending invite-app DM to user %s (id=%s): %s",
            user, user.id, exc,
        )
        return False


async def _send_invite_ephemeral(
    interaction: Interaction, embed: discord.Embed,
) -> None:
    """Send the invite embed as an ephemeral message in the current channel.

    Args:
        interaction: The Discord interaction to respond to.
        embed: The invite embed to send.
    """
    try:
        await interaction.response.send_message(embed=embed, ephemeral=True)
        log.info(
            "Sent invite-app embed to user %s (id=%s) via ephemeral channel message",
            interaction.user, interaction.user.id,
        )
    except discord.InteractionResponded:
        # Interaction was already responded to, use followup
        try:
            await interaction.followup.send(embed=embed, ephemeral=True)
            log.info(
                "Sent invite-app embed to user %s (id=%s) via ephemeral followup",
                interaction.user, interaction.user.id,
            )
        except Exception as exc:
            log.warning(
                "Failed to send invite-app followup to user %s (id=%s): %s",
                interaction.user, interaction.user.id, exc,
            )
    except Exception as exc:
        log.warning(
            "Failed to send invite-app ephemeral message to user %s (id=%s): %s",
            interaction.user, interaction.user.id, exc,
        )


async def invite_app_command(
    interaction: Interaction,
    reject_if_banned,  # Callable[[Interaction], Coroutine[Any, Any, bool]]
    bot_id: int,
) -> None:
    """Handle the /invite-app slash command.

    Checks if the user is banned, builds the invite embed, attempts to DM it,
    and falls back to ephemeral channel message if DM is blocked.

    Args:
        interaction: The Discord interaction (command invocation).
        reject_if_banned: Async function to check ban status and reject if banned.
                         Returns True if user is banned, False otherwise.
        bot_id: The bot's Discord user ID (used to build the invite link).
    """
    # Check ban status first
    if await reject_if_banned(interaction):
        return

    # Build the invite embed with the bot's ID
    embed = _build_invite_embed(bot_id)

    # Attempt to send via DM first
    dm_sent = await _send_invite_via_dm(interaction.user, embed)

    if dm_sent:
        # DM succeeded, send confirmation message
        try:
            await interaction.response.send_message(
                "Sent invite link to your DMs!",
                ephemeral=True,
            )
        except discord.InteractionResponded:
            # If response already used, skip confirmation
            pass
        except Exception as exc:
            log.warning(
                "Failed to send DM confirmation to user %s (id=%s): %s",
                interaction.user, interaction.user.id, exc,
            )
    else:
        # DM blocked or failed, fall back to ephemeral channel message
        await _send_invite_ephemeral(interaction, embed)


def register_invite_app(
    bot,  # discord.AutoShardedClient or similar
    reject_if_banned,  # Callable[[Interaction], Coroutine[Any, Any, bool]]
) -> None:
    """Register the /invite-app command with the bot.

    Creates the slash command handler and registers it to the bot's command tree.

    Args:
        bot: The Discord bot instance (must have a .tree attribute).
        reject_if_banned: Async callable that checks ban status.
                         Takes Interaction, returns bool (True if banned).

    Example:
        # In bot.py setup:
        register_invite_app(bot, bot._reject_if_banned)
    """
    if not hasattr(bot, "tree"):
        raise ValueError("bot must have a 'tree' attribute (app_commands.CommandTree)")
    if bot.user is None:
        raise ValueError(
            "bot.user is None; ensure bot is fully initialized (e.g., after on_ready)"
        )

    @bot.tree.command(
        name="invite-app",
        description="[User Command] Add Paws Pendragon to your personal Discord account.",
    )
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def invite_app(interaction: Interaction) -> None:
        """User App install command handler.

        Invokes the core invite_app_command logic with the bot's user ID
        and the ban rejection function.
        """
        await invite_app_command(
            interaction,
            reject_if_banned=reject_if_banned,
            bot_id=bot.user.id,
        )

    log.info("Registered /invite-app command")
