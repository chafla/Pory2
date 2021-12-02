"""
Cog for adding moderation notes for a user.

Notes will be tracked per-server and will currently not be purged.

structure:
user:{id}:mod:{guild_id}
    :notes
        :all: list of all timestamp keys associated to a user
        :<timestamp>: timestamp when the note was created, truncated to the second.

Note structure:
{
    "creator": <user who created the note>,
    "datetime": <datetime when the note was created>,
    "user_id": <ID of the user when the note was created>,
    "note_text": <Actual text of the note>,
    "note_type": <keyword of the note>
}

guild:{id}:mod:notes:track_mod_actions: 0/1 if mod actions are tracked or not
"""
import asyncio
from threading import Lock
from typing import Union, Tuple, List, Dict, Any

from discord.ext import commands
from discord.ext.menus import ListPageSource, MenuPages
from cogs.utils.checks import has_manage_roles
import discord
import time

SUPPORTED_KEYWORDS = {"POS", "NEG", "INFO", "KICK", "BAN"}


class InventoryPageSource(ListPageSource):

    def __init__(self, entries: List[discord.Embed]):  # Specify Embeds
        super().__init__(entries, per_page=1)  # Only one embed per message (page)

    async def format_page(self, menu: MenuPages, page: Any):  # Copied from example
        offset = menu.current_page * self.per_page
        return self.entries[offset]


class InventoryMenuPages(MenuPages):

    async def remove_reaction(self, payload: discord.RawReactionActionEvent):
        async with Lock():
            await self.bot.http.remove_reaction(
                payload.channel_id,
                payload.message_id,
                payload.emoji.name,
                payload.member.id
            )

    def reaction_check(self, payload: discord.RawReactionActionEvent):
        """Overriding this method to customize when reactions are processed and
        how they are handled"""

        # Ignore removed reactions since we're removing them
        # if payload.event_type == "REACTION_REMOVE":
        #     return False

        # Not the message we're watching for reactions on
        if payload.message_id != self.message.id:
            return False

        # This is where we can add additional users to be allowed to react
        if payload.user_id in {self.bot.user.id}:
            return False

        # Remove reactions after they're made
        # self.bot.loop.create_task(self.remove_reaction(payload))

        # Right message, right user, so check against buttons and continue
        return payload.emoji in self.buttons


class UserNotes(commands.Cog):

    MOD_NOTE_ID_KEY = "config:mod:notes:id"

    def __init__(self, bot):
        self.bot = bot
        self.config = bot.config

    @staticmethod
    def _ensure_ids(user: Union[str, int, discord.User],
                    guild: Union[str, int, discord.Guild]) -> Tuple[int, int]:
        try:
            user = user.id
        except AttributeError:
            pass

        try:
            guild = guild.id
        except AttributeError:
            pass

        return int(user), int(guild)

    @staticmethod
    def _guild_tracking_key(guild) -> str:
        try:
            guild = guild.id
        except AttributeError:
            pass

        return "guild:{}:mod:notes:track_mod_actions".format(guild)

    def _kicks_bans_tracked(self, guild) -> bool:
        """
        Return true if kicks and bans will be written into mod notes automagically, False if not, or None if there's
        nothing (defaults to false)
        """

        res = self.config.get(self._guild_tracking_key(guild))
        return bool(res)

    def _set_kicks_bans_tracking(self, guild, val: bool):
        """
        Set tracking for kicks and bans
        """
        self.config.set(self._guild_tracking_key(guild), 1 if val else 0)

    def get_next_note_id(self) -> int:
        """
        Increment the serverside note ID and return the new value.
        """
        return int(self.config.incr(self.MOD_NOTE_ID_KEY))

    def note_base_key(self, user, guild):
        user_id, guild_id = self._ensure_ids(user, guild)
        return "user:{}:mod:{}:notes".format(user_id, guild_id)

    def note_list_key(self, user, guild):
        return "{}:all".format(self.note_base_key(user, guild))

    def _get_note_key(self, user, guild, note_ts: str) -> str:
        """
        Get a note key based on ID
        :param user: User to fetch from
        :param guild:
        :param note_ts:
        :return:
        """

        note_key = "{}:{}".format(self.note_base_key(user, guild), note_ts)
        return note_key

    def get_all_notes(self, user, guild) -> List[Dict]:
        """
        Fetch all notes on a given user.
        :param user: User to fetch notes from.
        :param guild: Guild in which the notes are scoped
        :return: List of all note dicts
        """

        all_notes = []

        all_note_timestamps = self.config.smembers(self.note_list_key(user, guild))

        for note_ts in all_note_timestamps:
            all_notes.append(self.config.hgetall(self._get_note_key(user, guild, note_ts)))

        return all_notes

    def add_note(self, creator, user, guild, note_type: str, note_message: str) -> str:
        # Not too many checks needed; dupes are okay
        try:
            creator = creator.id
        except AttributeError:
            pass

        try:
            user = user.id
        except AttributeError:
            pass

        note_type = note_type.upper()

        if note_type not in SUPPORTED_KEYWORDS:
            raise ValueError("Note type should be one of {}".format(SUPPORTED_KEYWORDS))

        # truncate it to seconds
        note_ts = str(int(time.time()))

        note_dict = {
            "creator": creator,
            "datetime": note_ts,
            "user_id": user,
            "note_text": note_message,
            "note_type": note_type.upper(),
            "note_id": self.get_next_note_id()  # ID will be nice to have when we move to sql
        }

        note_key = self._get_note_key(user, guild, note_ts)

        self.config.hmset(note_key, note_dict)
        self.config.sadd(self.note_list_key(user, guild), note_ts)

        return note_ts

    @has_manage_roles()
    @commands.group()
    async def note(self, ctx):
        """
        Mod note functionality
        """

    @has_manage_roles()
    @note.command()
    async def track_mod_actions(self, ctx, on_or_off: str):
        """
        Whether or not to enable automatic tracking of mod actions (kick, ban).
        If enabled, bans will automatically be tracked in the audit log.
        """

        if on_or_off.lower() in {"y", "on"}:
            enable = True
        elif on_or_off.lower() in {"n", "off"}:
            enable = False
        else:
            await ctx.send("Unknown option, try 'on' or 'off'")
            return

        # Check that we actually have the perms to access the audit log
        # we'll allow it, but it'll hurt what we can do
        user_perms = ctx.author.guild_permissions
        if not user_perms.view_audit_log:
            await ctx.send("I am missing permissions to see audit logs, so this functionality will be limited.")

        self._set_kicks_bans_tracking(ctx.guild, enable)
        await ctx.send("Mod actions are now {}tracked.".format("" if enable else "not "))

    @has_manage_roles()
    @note.command()
    async def add(self, ctx, user: discord.Member, note_type: str, *, note_message: str):
        """
        Add a note to a user.
        :param ctx: Context
        :param user: User to attach the note to
        :param note_type: Type of note (pos/neg/info/kick/ban)
        :param note_message: Message to attach as a note
        """

        try:
            note_ts = self.add_note(ctx.author, user, ctx.guild, note_type, note_message)
        except ValueError as e:
            await ctx.send(str(e))
            return

        await ctx.send("Note added for user {} with ID `{}`".format(user, note_ts))

    @has_manage_roles()
    @note.command(aliases=["rm"])
    async def remove(self, ctx, user: discord.Member, note_id: str):
        """
        Remove a note from a user.
        If a tracked modlog exists, this will be written to it.
        :param ctx:
        :param user:
        :param note_id: Timestamp/ID of a user
        :return:
        """

        note_key = self._get_note_key(user, ctx.guild, note_id)
        if not self.config.exists(note_key):
            await ctx.send("That note doesn't exist!")
            return
        else:

            note = self.config.hgetall(note_key)
            # Note in a tracked modlog, just to be safe
            server_logs_cog = self.bot.get_cog("ServerLogs")
            if server_logs_cog:
                await server_logs_cog.handle_external_embed(ctx, "deleted a mod note from {}".format(user.id),
                                                            priority=True, member=ctx.author,
                                                            note_message=note["note_text"])
            self.config.delete(note_key)
            self.config.srem(self.note_list_key(user, ctx.guild), note_id)
            await ctx.send("Note removed.")

    @staticmethod
    def _format_note(note_dict: dict) -> str:
        if len(note_dict["note_text"]) > 150:
            note_dict["note_text"] = note_dict["note_text"][:147] + "..."
        return "__[{note_type}]__\t'**{note_text}**'\t(by <@{creator}> at <t:{datetime}:T>, ID {datetime})".format(
                    **note_dict)

    async def create_menu(self, ctx, title, matched_tag_rows: List[str]):
        pages = list()

        # This will set how many fields are in the embed
        page_length = 5

        row_buckets = [matched_tag_rows[n:n + page_length] for n in range(0, len(matched_tag_rows), page_length)]

        for page_number, page in enumerate(row_buckets):

            # Build embed base with the current page number
            em = discord.Embed(
                title=title,
                description="\n".join(page)
            )

            pages.append(em)

        # Initial message
        msg = await ctx.send(embed=pages[0])

        menu = InventoryMenuPages(
            source=InventoryPageSource(pages),
            timeout=20.0,
            delete_message_after=True,
            clear_reactions_after=True,
            message=msg
        )

        await menu.start(ctx)

    @has_manage_roles()
    @note.command()
    async def list(self, ctx, user: discord.Member, *, args: str = None):
        """
        List all of a user's mod notes
        """

        matched_tags = set()

        if args:
            matched_tags = set([i.upper() for i in args.split()])

        # Fetch the note IDs and sort by them
        user_notes = self.config.smembers(self.note_list_key(user, ctx.guild))
        if not user_notes:
            await ctx.send("User has no notes.")
            return

        output = []

        user_notes = reversed(sorted(user_notes))

        for note_id in user_notes:
            note_key = self._get_note_key(user, ctx.guild, note_id)
            note_dict = self.config.hgetall(note_key)
            if not matched_tags or matched_tags and note_dict["note_type"] in matched_tags:
                output.append(self._format_note(note_dict))

        embed_title = "User Notes for {}".format(user)

        if matched_tags:
            embed_title += " (matching tags {})".format(", ".join(matched_tags))

        if not output and matched_tags:
            output = ["(No notes found)"]

        await self.create_menu(ctx, embed_title, output)

    @note.command()
    async def qlist(self, ctx, user: discord.Member):
        """
        Get a quick summary of a user's notes
        """
        user_notes = self.get_all_notes(user, ctx.guild)
        if not user_notes:
            await ctx.send("User has no notes.")
            return

        note_types = {}

        for note in user_notes:
            type_count = note_types.get(note["note_type"].upper(), 0)
            note_types[note["note_type"].upper()] = type_count + 1

        summary = ["{}: {}".format(k.upper(), v) for k, v in note_types.items()]

        embed = discord.Embed(title="Quick summary for {}".format(user),
                              description="\n".join(summary))

        await ctx.send(embed=embed)

    async def get_audit_log_info(self, target_id: int, guild_id: int,
                                 action: discord.AuditLogAction, limit: int=10) -> Tuple[str, str]:
        """
        Get information from audit logs relating to the last mod action.
        :param target_id: User who the action was performed on.
        :param guild_id: Guild in which the event was triggered
        :param action: Audit log action to look for
        :param limit: Number of logs to search back through
        :return: (mod responsible, reason)
        """
        async for log_entry in self.bot.get_guild(guild_id).audit_logs(action=action, limit=limit):
            if log_entry.target.id == target_id:
                # Let's stop at the first entry.
                mod_responsible = log_entry.user
                reason = log_entry.reason if log_entry.reason is not None else "None Given"  # Should be None
                return mod_responsible, reason
        else:
            return "Unknown", "None found."

    @commands.Cog.listener()
    async def on_member_ban(self, member):
        if not self._kicks_bans_tracked(member.guild):
            return
        try:
            # Check audit logs to see if we can glean why the user was banned
            mod_responsible, reason = await self.get_audit_log_info(member.id, member.guild.id,
                                                                    discord.AuditLogAction.ban)
        except discord.Forbidden:  # No audit log perms
            mod_responsible = self.bot.user.id  # Track an ID anyway since otherwise we might run into issues
            reason = "(Unknown, missing audit log permissions)"

        self.add_note(mod_responsible, member, member.guild, "BAN",
                      "(auto) Reason: {}".format(reason))

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        """
        Kicks and leaves are indistinguishable events, except that kicks leave an audit log event.
        Bans also trigger a remove, so we need to make sure we haven't already tracked that.
        """

        if not self._kicks_bans_tracked(member.guild):
            return

        # wait a second to let multiple events take place
        await asyncio.sleep(1)

        try:
            # Check audit logs to see if we can glean why the user was banned
            mod_responsible, reason = await self.get_audit_log_info(member.id, member.guild.id,
                                                                    discord.AuditLogAction.kick, limit=1)
        except discord.Forbidden:  # No audit log perms
            mod_responsible = self.bot.user.id  # Track an ID anyway since otherwise we might run into issues
            reason = "(Unknown, missing audit log permissions)"

        self.add_note(mod_responsible, member, member.guild, "KICK",
                      "(auto) Reason: {}".format(reason))


def setup(bot):
    bot.add_cog(UserNotes(bot))
