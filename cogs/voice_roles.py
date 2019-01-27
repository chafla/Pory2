"""Role management for voice channels."""

from asyncio import sleep

import discord

from discord import Member
from discord.ext import commands
from discord.ext.commands import Bot, Context

from .utils import checks


class VoiceRoles:

    def __init__(self, bot: Bot) -> None:
        self.bot = bot
        self.config = bot.config

    @checks.sudo()
    @commands.command(hidden=True)
    async def set_voice_role(
            self, ctx: Context, role_id: str, channel_id: str=None
    ) -> None:
        """Set a certain role as the 'in voice' role for the server.

        Channel_id can be included to set a specific voice role for a channel.
        Note that channel specific settings override universal settings.

        Dict format is as follows:

        voice_roles: {
            "server_id": {
                "universal": false,
                "chan_id": "role_id"
            },

            "another_server_id": {
                "universal": true
            }


        """
        server = ctx.message.guild
        role_pairs = self.config.get("voice_roles")

        if role_pairs is None:
            role_pairs = {}

        if not role_pairs.get(server.id):  # avoid keyerrs
            role_pairs[server.id] = {"universal_role": ""}

        if channel_id is None:
            role_pairs[server.id]["universal_role"] = role_id
        else:
            role_pairs[server.id][channel_id] = role_id

        await self.config.put("voice_roles", role_pairs)

    @staticmethod
    async def add_role(member: Member, role_id: int) -> bool:
        role = discord.utils.get(member.server.roles, id=role_id)
        if not role:
            return False
        else:
            try:
                await member.add_roles(role)
                return True
            except discord.HTTPException:
                return False

    @staticmethod
    async def remove_role(member: Member, role_id: int) -> bool:
        # Has to be forceful because the member object usually isn't updated
        role = discord.utils.get(member.server.roles, id=role_id)

        try:
            await member.remove_roles(role)
            return True
        except discord.HTTPException:
            return False
        except IndexError:
            return True

    async def on_voice_state_update(self, before: Member, after: Member) -> None:
        role_settings = self.config.get("voice_roles").get(before.guild.id)
        server_role_cfg = role_settings.get(before.guild.id)
        if not server_role_cfg:
            return

        before_role_id = role_settings.get(before.voice_channel.id, role_settings.get("universal_role"))
        after_role_id = role_settings.get(after.voice_channel.id, role_settings.get("universal_role"))

        # Three cases: Joining voice, leaving voice, and changing channels.

        if before.voice_channel is None and after.voice_channel is not None and after_role_id:

            # Joining voice for the first time
            await self.add_role(before, before_role_id)

        elif before.voice_channel is not None and after.voice_channel is not None:

            if before.voice_channel == after.voice_channel or before_role_id == after_role_id:
                return
            # TODO: Note that this might not work
            try:
                # Way back when I did this, I had to edit the cache because it
                # wasn't updating the roles.
                await self.remove_role(after, before_role_id)  # Might not work, but we'll just swallow that
                await sleep(0.5)  # Rate limit considerations
                await self.add_role(after, after_role_id)
            except discord.HTTPException:
                pass

        elif before.voice_channel is not None and after.voice_channel is None and before_role_id:

                await self.remove_role(after, before_role_id)


def setup(bot: Bot) -> None:
    bot.add_cog(VoiceRoles(bot))
