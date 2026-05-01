# -*- coding: utf-8 -*-
"""Invite-server command handler for Paws Pendragon TTR bot.

Provides the /invite-server slash command, which DMsusers an OAuth2 server
install link so they can add the bot to their Discord servers. Uses a DM-first,
fallback-to-ephemeral pattern for maximum compatibility.

Command: /invite-server
- Checks if user is banned, rejects if so
- Builds server install link using bot.user.id with required permissions
- Creates embed with link and instructions
- Attempts to DM embed to user; falls back to ephemeral channel message if DM blocked
- No API calls (instant response, all static data)
- Works as User App and in servers/DMs
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands

if TYPE_CHECKING:
    from bot import TTRBot

log = logging.getLogger("ttr-bot")


# Permission bitmasks (from Discord API)
_PERMISSION_SEND_MESSAGES = 2048  # 2^11
_PERMISSION_EDIT_MESSAGES = 2048  # 2^11 (Edit Messages)
_PERMISSION_MANAGE_MESSAGES = 8192  # 2^13
_PERMISSION_MANAGE_CHANNELS = 16  # 2^4

# Combined bitmask for all required permissions
_REQUIRED_PERMISSIONS_BITMASK = (
    _PERMISSION_MANAGE_CHANNELS
    | _PERMISSION_SEND_MESSAGES
    | _PERMISSION_EDIT_MESSAGES
    | _PERMISSION_MANAGE_MESSAGES
)


def _build_invite_link(bot_id: int) -> str:
    """Build the server install OAuth2 invite link.

    Args:
        bot_id: The bot's Discord user ID.

    Returns:
        Complete OAuth2 authorization URL for server install with required permissions.
    """
    return (
        "https://discord.com/api/oauth2/authorize"
        f"?client_id={bot_id}"
        f"&permissions={_REQUIRED_PERMISSIONS_BITMASK}"
        "&scope=bot+applications.commands"
    )


def _create_invite_embed(invite_link: str) -> discord.Embed:
    """Create the invite embed with link and instructions.

    Args:
        invite_link: The OAuth2 authorization URL.

    Returns:
        A formatted Discord embed with server install information.
    """
    embed = discord.Embed(
        title="Add Paws Pendragon to Your Server",
        description=(
            f":link: {invite_link}\n\n"
            "**How to add the bot:**\n"
            "1. Click the link above\n"
            "2. Select the server where you want to add the bot\n"
            "3. Confirm the requested permissions\n\n"
            "**What happens next:**\n"
            "Once the bot joins, a server admin can run `/pd-setup` to create "
            "the `#tt-information`, `#tt-doodles`, and `#suit-calculator` channels "
            "and start receiving live Toontown Rewritten data."
        ),
        color=0x9124F2,
    )
    embed.add_field(
        name="Permissions Requested",
        value=(
            "• **Manage Channels** — Create category and channels for live feeds\n"
            "• **Send Messages** — Post live game data into channels\n"
            "• **Edit Messages** — Update embeds as data changes\n"
            "• **Manage Messages** — Clean up old messages\n"
            "\nThe bot **does not** read general chat messages. "
            "It only operates in the channels it creates."
        ),
        inline=False,
    )
    embed.set_footer(text="Paws Pendragon TTR — Live Toontown Data Discord Bot")
    return embed


async def _send_invite_dm(
    user: discord.abc.User, embed: discord.Embed
) -> bool:
    """Attempt to send the invite embed via DM to the user.

    Args:
        user: The Discord user to DM.
        embed: The embed to send.

    Returns:
        True if DM was sent successfully, False if DM failed (e.g., blocked).
    """
    try:
        await user.send(embed=embed)
        log.info("Sent invite-server link via DM to user %s (id=%s)", user, user.id)
        return True
    except discord.Forbidden:
        log.debug("User %s (id=%s) has DMs blocked; will use ephemeral fallback", user, user.id)
        return False
    except Exception as exc:
        log.warning("Unexpected error sending invite-server DM to %s: %s", user, exc)
        return False


async def invite_server_command(interaction: discord.Interaction) -> None:
    """Handle the /invite-server slash command.

    Builds the server install link, creates an embed, and sends it to the user via DM
    with a fallback to an ephemeral channel message if the DM is blocked.

    This is the core command handler. It is registered into the bot's command tree
    by register_invite_server().

    Args:
        interaction: The slash command interaction from Discord.
    """
    # Ban check: reject immediately if user is banned
    if await interaction.client._reject_if_banned(interaction):  # type: ignore[attr-defined]
        return

    # Build the invite link
    bot = interaction.client
    if bot.user is None:
        await interaction.response.send_message(
            "Bot not yet ready -- try again in a moment.",
            ephemeral=True,
        )
        return

    invite_link = _build_invite_link(bot.user.id)
    embed = _create_invite_embed(invite_link)

    # Try to send via DM
    dm_sent = await _send_invite_dm(interaction.user, embed)

    # Respond to interaction
    if dm_sent:
        await interaction.response.send_message(
            "Sent invite link to your DMs! :mailbox_with_mail:",
            ephemeral=True,
        )
    else:
        # Fallback: send the full embed as ephemeral in the channel
        await interaction.response.send_message(embed=embed, ephemeral=True)
        log.info(
            "Sent invite-server embed as ephemeral fallback to user %s (id=%s)",
            interaction.user,
            interaction.user.id,
        )


def register_invite_server(bot: TTRBot) -> None:
    """Register the /invite-server command with the bot's command tree.

    This function is called during bot initialization to register the command
    as a globally available slash command. The command:
    - Works as both a guild install and User App install
    - Available in servers, DMs, and group chats
    - Supports all allowed interaction contexts

    Args:
        bot: The TTRBot instance to register the command with.
    """

    @bot.tree.command(
        name="invite-server",
        description="[User Command] Add Paws Pendragon TTR to a Discord server.",
    )
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def cmd_invite_server(interaction: discord.Interaction) -> None:
        """Slash command handler (wrapper around invite_server_command)."""
        await invite_server_command(interaction)

    log.info("Registered /invite-server command")
