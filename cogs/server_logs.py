"""Fancy channel logs using rich embeds"""

from discord.ext import commands
from .utils import checks, utils
import discord
from .utils.utils import get_timestamp, download_image
import logging
from asyncio import TimeoutError, sleep
from io import BytesIO

log = logging.getLogger()

colors = {
    "ban": discord.Color.dark_red(),
    "unban": discord.Color.teal(),
    "kick": discord.Color.red(),
    "join": discord.Color.dark_green(),
    "leave": discord.Color.blue(),
    "delete": discord.Color.magenta(),
    "edit": discord.Color.gold(),
    "mention_mods": discord.Color.green(),
    "name_change": discord.Color.purple(),
    "verified": discord.Color.light_grey()
}


class UserType:

    def __init__(self, argument):

        if isinstance(argument, discord.Member):
            self.user_id = argument.id
        elif utils.check_ids(argument):
            self.user_id = argument
        else:
            raise commands.BadArgument


class ServerLogs:

    def __init__(self, bot):
        self.bot = bot
        self.config = bot.config

    @property
    def guild(self):
        return self.bot.get_guild(111504456838819840)

    @property
    def general_modlog(self):
        return self.bot.get_channel(250333879368548352)

    @property
    def priority_modlog(self):
        return self.bot.get_channel(268259704906448896)

    def add_case_number(self, embed):
        """Update the embed with the active case number, and write it out."""
        case_id = self.config.get("admin:mod_case")
        case_id = int(case_id if case_id is not None else 0) + 1
        self.config.set("admin:mod_case", case_id)
        embed.add_field(name="Case", value=str(case_id))
        return embed

    async def send_embed(self, embed, priority=False, **kwargs):
        """Have to use this backwards-ass method because it throws http exceptions."""
        dest_channel = self.general_modlog if not priority else self.priority_modlog
        try:
            await dest_channel.send(embed=embed, **kwargs)
        except discord.HTTPException:
            # Silently swallow the error
            log.exception("Exception occurred when sending embed.\nParams:\n{}".format(embed.fields))

    @staticmethod
    def format_embed(embed, user):
        """Do basic formatting on the embed"""
        embed.set_author(name=user.name, icon_url=user.avatar_url)
        embed.add_field(name="User ID", value=user.id)
        embed.set_footer(text=get_timestamp())
        return embed

    async def _get_last_audit_action(self, action, member):
        async for log_entry in self.guild.audit_logs(action=action, limit=10):
            if log_entry.target.id == member.id:
                # Let's stop at the first entry.
                mod_responsible = log_entry.user
                reason = log_entry.reason if log_entry.reason is not None else "None Given"  # Should be None
                return mod_responsible, reason
        else:
            log.info("_get_last_audit_action() turned up empty for {} with member {}".format(action, member))
            return "Unknown", "None found."

    async def handle_external_embed(self, ctx, action, color=discord.Color.light_grey(), priority=False, member=None,
                                    **kwargs):
        """
        Allow for embeds to be used in other areas as well, with bot.get_cog()
        :param ctx: Context
        :param color: optional color
        :param action: The message to be used in the embed as the title, e.g. "set 18"
        :param kwargs: name/value pairs for new params
        :param priority: Whether or not it should be sent to the priority modlog (mod_action_logs)
        :param member: Optional member target
        :return: Embed object
        """

        member = ctx.message.author if member is None else member

        embed = discord.Embed(title="User {0.name}#{0.discriminator} {1}".format(member, action),
                              color=color)
        embed = self.format_embed(embed, member)

        for name, value in kwargs.items():
            embed.add_field(name=name, value=value)

        await self.send_embed(embed, priority=priority)

    async def on_member_ban(self, guild, user):
        if guild.id == self.guild.id:
            await self.priority_modlog.send("Member {} was banned".format(user.name))  # temporary failsafe

            embed = discord.Embed(title="User {} was banned.".format(str(user)),
                                  color=colors["ban"])

            embed = self.format_embed(embed, user)
            embed = self.add_case_number(embed)

            mod_responsible, reason = await self._get_last_audit_action(discord.AuditLogAction.ban, user)

            # Add reason

            embed.add_field(name="Reason", value=reason if reason else "None given.")
            embed.add_field(name="Mod responsible", value=mod_responsible if mod_responsible else "unknown")

            await self.send_embed(embed, priority=True)

    async def on_member_unban(self, guild, user):
        if guild.id == self.guild.id:
            embed = discord.Embed(title="User {0.name}#{0.discriminator} was unbanned.".format(user))

            embed = self.format_embed(embed, user)
            embed = self.add_case_number(embed)

            mod_responsible, reason = await self._get_last_audit_action(discord.AuditLogAction.unban, user)

            embed.add_field(name="Reason", value=reason if reason else "None given.")
            embed.add_field(name="Mod responsible", value=mod_responsible.name if mod_responsible else "unknown")

            await self.send_embed(embed, priority=True)

    async def on_member_join(self, member):
        if member.guild == self.guild:
            embed = discord.Embed(title="User {0.name}#{0.discriminator} joined.".format(member),
                                  color=colors["join"])

            embed = self.format_embed(embed, member)

            embed.add_field(name="Account created", value=member.created_at)

            await self.send_embed(embed)

    async def on_member_remove(self, member):
        if member.guild == self.guild:

            # We need to check to see if it was a ban, which also triggers the member_remove handle

            leave_was_kick = False

            await sleep(0.5)

            # Check to see if the leave was a kick or just a regular leave

            for log_entry in await self.guild.audit_logs(action=discord.AuditLogAction.kick, limit=1).flatten():
                # Let's stop at the first entry.
                if log_entry.target.id == member.id:  # The leave was a kick
                    leave_was_kick = True
                    try:
                        mod_responsible = getattr(log_entry, "name", "Unknown")
                        reason = getattr(log_entry, "reason", "No reason provided.")
                        embed = discord.Embed(title="User {0} was kicked.".format(str(member)),
                                              color=colors["kick"])

                        embed.add_field(name="Reason", value=reason)
                        embed.add_field(name="Kicked by", value=mod_responsible)
                        break
                    except AttributeError:
                        pass

            else:
                embed = discord.Embed(title="User {0} left.".format(str(member)),
                                      color=colors["leave"])

            embed = self.format_embed(embed, member)

            await self.send_embed(embed, priority=leave_was_kick)

    async def on_message_delete(self, message):
        if message.guild == self.guild:
            reupload = None
            member = message.author
            embed = discord.Embed(title="Message by {0.name}#{0.discriminator} deleted.".format(member),
                                  description="**Attachment included above**" if message.attachments else None,
                                  color=colors["delete"])
            embed = self.format_embed(embed, member)

            embed.add_field(name="Channel", value="#" + message.channel.name)

            if message.content:
                content = message.content if len(message.content) <= 1024 else message.content[:1021] + "..."
                embed.add_field(name="Content", value=content)

            # Try to re-download attached images if possible.
            # The proxy url doesn't 404 immediately unlike the regular URL, so it may be possible to download from it
            # before it goes down as well.

            if message.attachments:
                temp_image = BytesIO()
                attachment = message.attachments[0]
                if attachment.size > 5000000:
                    # caching is important and all, but this will just cause more harm than good
                    return

                try:
                    await download_image(message.attachments[0].proxy_url, temp_image)
                    reupload = discord.File(temp_image, filename="reupload.{}".format(attachment.filename))
                except Exception:
                    log.exception("Encountered exception when downloading attachment.")
                    reupload = None

            await self.send_embed(embed, file=reupload)

    async def on_message_edit(self, before, after):
        if before.guild == self.guild and before.content != after.content and not isinstance(before.channel,
                                                                                             discord.DMChannel):
            member = before.author
            embed = discord.Embed(title="Message by {0.name}#{0.discriminator} edited.".format(member),
                                  color=colors["edit"])
            embed = self.format_embed(embed, member)

            embed.add_field(name="Channel", value="#" + before.channel.name, inline=False)
            embed.add_field(name="Before", value=before.content, inline=False)
            embed.add_field(name="After", value=after.content)

            await self.send_embed(embed)

    async def on_member_update(self, before, after):
        if before.guild == self.guild:
            if before.name != after.name:
                embed = discord.Embed(title="Member {0.name} changed their name to {1.name}.".format(before, after),
                                      color=colors["name_change"])

                embed = self.format_embed(embed, after)

                await self.send_embed(embed)
            if before.roles != after.roles:
                if discord.utils.get(before.roles, name="Verified") is None and \
                        discord.utils.get(after.roles, name="Verified") is not None:
                    embed = discord.Embed(title="Member {0.name} verified themselves.".format(before),
                                          color=colors["verified"])
                    embed = self.format_embed(embed, after)
                    await self.send_embed(embed)

    @checks.is_pokemon_mod()
    @commands.command(hidden=True, pass_context=True)
    async def ban(self, ctx, member: discord.Member, keep_message_history: str=None, *, reason=None):

        def check(message):
            return message.author == ctx.message.author and message.content == "y"

        conf_msg = await ctx.send("Are you sure you want to ban **{}**?\n(`y`/`n`)".format(member.display_name))
        try:
            msg = await self.bot.wait_for("message", check=check, timeout=10)
        except TimeoutError:
            await ctx.send("Cancelled.")
            return
        if msg:
            if keep_message_history == "y":
                days = 0
            else:
                days = 7
            await conf_msg.delete()
            await msg.delete()
            await member.ban(days, reason=reason)
            await ctx.send("\N{HAMMER}")
        else:
            await ctx.send("Cancelled.")

    @checks.is_pokemon_mod()
    @commands.command(hidden=True)
    async def kick(self, ctx, member: discord.Member, *, reason: str):
        await member.kick(reason)
        await ctx.send("\N{WAVING HAND SIGN}")

    @checks.mod_server()
    @commands.command(hidden=True, rest_is_raw=True, aliases=["add_mod_info"])
    async def add_log_note(self, ctx, message_id: str, *, note: str):
        """
        Edit the embed and add info on which mod it came from.
        Expected input should be like id message
        """
        msg = None
        # Check for the last logged case
        if message_id.lower() == "last":
            async for message in ctx.message.channel.history(limit=3):
                if message.author.id == self.bot.user.id and message.embeds:  # Hacky way to check for embeds
                    msg = message

        else:
            # Check it as if it is a message ID
            try:
                msg = ctx.message.channel.get_message(message_id)
            except discord.NotFound or discord.HTTPException:
                pass

            # Check the past messages for one that matches the case number
            if msg is None:
                async for message in ctx.message.channel.history(limit=500):
                    if message.author.id == self.bot.user.id and message.embeds != []:
                        if discord.utils.get(message.embeds[0].fields, case=str(message_id)):
                            msg = message

        if msg is None:
            await ctx.send("Message not found.")
            return

        embed = msg.embeds[0]
        field = discord.utils.get(embed.fields, name="Notes")
        note = "{}: {}".format(ctx.message.author.name, note)

        # We can safely assume that the Notes field would be the last one

        # Edit the field if it exists, or just make a new one
        if field is None:
            embed.add_field(name="Notes", value=note)
        else:
            embed.set_field_at(len(embed.fields) - 1, name="Notes", value=note)
        await msg.edit(embed=embed)
        log.info('User {} added a modnote to embed with ID {}.'.format(ctx.message.author.name, msg.id))

        await ctx.message.delete()

    async def on_message(self, message):
        if len(message.role_mentions) > 0 and discord.utils.get(message.role_mentions, name="Mods") is not None:
            embed = discord.Embed(title="Message by {0.name}#{0.discriminator} mentioned mods.".format(message.author),
                                  color=colors["mention_mods"])
            embed = self.format_embed(embed, message.author)
            embed.add_field(name="Channel", value=message.channel.name)

            await self.send_embed(embed)


def setup(bot):
    bot.add_cog(ServerLogs(bot))
