# -*- coding: utf-8 -*-
import logging
from typing import TYPE_CHECKING, Any

import discord
from discord import app_commands

if TYPE_CHECKING:
    from bot import TTRBot

log = logging.getLogger("ttr-bot.doodlesearch")


def register_doodlesearch(bot: TTRBot) -> None:
    @bot.tree.command(
        name="doodlesearch",
        description="Search for specific doodles by traits or location.",
    )
    @app_commands.describe(
        trait1="Filter by a specific trait (e.g., 'Rarely Tired', 'Always Playful')",
        trait2="Filter by a second trait",
        trait3="Filter by a third trait",
        trait4="Filter by a fourth trait",
        playground="Filter by a playground (e.g., 'Donald\\'s Dreamland')",
        district="Filter by a district (e.g., 'Splat Summit')"
    )
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def doodlesearch(
        interaction: discord.Interaction, 
        trait1: str = None, 
        trait2: str = None,
        trait3: str = None,
        trait4: str = None,
        playground: str = None,
        district: str = None
    ) -> None:
        if await bot._reject_if_banned(interaction):
            return

        await interaction.response.defer(ephemeral=False, thinking=True)
        try:
            await bot._maybe_welcome(interaction.user)
        except Exception as exc:
            log.warning("Failed to send welcome message: %s", exc)

        if bot._api is None:
            await interaction.followup.send("API client not ready yet.", ephemeral=True)
            return

        try:
            doodle_data = await bot._api.fetch("doodles")
        except Exception as exc:
            log.exception("Failed to fetch doodles: %s", exc)
            await interaction.followup.send("Failed to fetch doodle data.", ephemeral=True)
            return

        # Flatten and filter the doodles
        from Features.Core.formatters.formatters import doodle_priority, doodle_quality, PRIORITY_REST, JELLYBEAN_EMOJI, star_for

        search_traits = [t.lower() for t in (trait1, trait2, trait3, trait4) if t]
        
        results = []
        for dist, playgrounds in (doodle_data or {}).items():
            if district and district.lower() not in dist.lower():
                continue
                
            for pg, doodles in playgrounds.items():
                if playground and playground.lower() not in pg.lower():
                    continue
                    
                for d in doodles:
                    traits = d.get("traits") or []
                    dna = d.get("dna", "")
                    
                    # Filter by all provided traits
                    if search_traits:
                        # Ensure every requested trait exists in the doodle's traits
                        doodle_traits_lower = [t.lower() for t in traits]
                        missing_trait = False
                        for st in search_traits:
                            # Substring match (e.g. "rarely tired" matches "Rarely Tired")
                            if not any(st in dt for dt in doodle_traits_lower):
                                missing_trait = True
                                break
                        if missing_trait:
                            continue

                    results.append((dist, pg, traits, d.get("cost", "?"), dna))

        # Drop "REST" tier doodles if we have a lot of results, unless specifically searching for bad ones
        if len(results) > 7 and not search_traits:
            results = [r for r in results if doodle_priority(r[2]) != PRIORITY_REST]

        # Sort by best traits
        results.sort(key=lambda r: (
            doodle_priority(r[2]),
            -doodle_quality(r[2]),
            r[0].lower(),
            r[1].lower(),
        ))

        # Take Top 7
        top_results = results[:7]

        if not top_results:
            await interaction.followup.send("No doodles found matching those criteria.", ephemeral=True)
            return

        embeds = []
        for dist, pg, traits, cost, dna in top_results:
            embed = discord.Embed(color=0x9124F2)
            
            traits_list = traits or []
            trait_str = ", ".join(traits_list) if traits_list else "Traits not listed"
            
            # Formatting as requested: [trait, trait] [location] [cost]
            stars = "".join(star_for(t, i) for i, t in enumerate(traits_list[:4]))
            
            title_text = f"[{stars}] [{trait_str}] [{dist} · {pg}] [{JELLYBEAN_EMOJI} {cost}]"
            embed.description = f"**{title_text}**"
                
            # Render image
            image_url = f"https://rendition.toontownrewritten.com/render/{dna}/doodle/256x256.png"
            embed.set_image(url=image_url)
            embeds.append(embed)

        # Generate thread name
        trait_names = "".join([f" <{t.title()}>" for t in (trait1, trait2, trait3, trait4) if t])
        thread_name = f"<{interaction.user.display_name}>{trait_names}"

        # If it's a guild text channel, we can create a thread
        if isinstance(interaction.channel, discord.TextChannel):
            try:
                # We send the initial message to the channel to act as the thread starter
                starter_msg = await interaction.followup.send(
                    content=f"Found {len(top_results)} doodles! Creating thread...",
                    wait=True
                )
                
                thread = await starter_msg.create_thread(name=thread_name[:100]) # Discord limits thread names to 100 chars
                
                # Send the embeds into the thread (Discord limits to 10 embeds per message, we have up to 7)
                await thread.send(content="Here are the top results:", embeds=embeds)
                
                # Schedule auto-deletion of the thread and starter message after 10 minutes (600 seconds)
                import asyncio
                async def delete_thread_later():
                    await asyncio.sleep(600)
                    try:
                        await starter_msg.delete()
                    except Exception:
                        pass
                    try:
                        await thread.delete()
                    except Exception:
                        pass
                        
                asyncio.create_task(delete_thread_later())
            except Exception as e:
                log.error("Failed to create thread or send embeds: %s", e)
                # Fallback: just send the embeds in the channel
                await interaction.followup.send(embeds=embeds)
        else:
            # Fallback for DMs or non-text channels
            msg = await interaction.followup.send(
                content=f"Here are the top {len(top_results)} doodles matching your search:",
                embeds=embeds,
                wait=True
            )
            # Try to delete after 10m
            import asyncio
            try:
                asyncio.create_task(msg.delete(delay=600))
            except Exception:
                pass
