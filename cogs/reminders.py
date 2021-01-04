"""
Cog to manage reminders for users.

This used to rest within general.py but it seems like it'd be better on its own.

The reminder system will run on a two-tiered update system, with a larger update window and a smaller one.
The full update (larger window) will process all active tags to determine if any would expire before the next large
update window.
If so, then the events will be moved to the smaller system. This system will be cached by the bot, and will be updated
much more frequently (likely every second). If an event's time is hit, it will be removed from the system, and a message
will be sent to the user.

database structure:

config:
    reminders:
        all: <set of all reminders' UUIDs>
        active: <set of UUIDs in active status>
        soon: <set of UUIDs in soon status>
        objects:
            uuid: {Reminder hashmap object}


user:
    <user id>
        reminders:
            active: <set of timestamps which the user has reminders set for>


"""
import re
import time
import datetime
from typing import List, Tuple

import discord
from discord.ext import commands
from discord.ext.commands import Bot
from uuid import uuid4
import logging

from cogs.utils import checks

log = logging.getLogger()

T_CacheElem = Tuple[int, dict]


class Reminder:
    pattern = re.compile(r"(\d+)\s+((?:second|minute|hour|day|week|month|year))")

    def __init__(self, argument: str, _from_ts: bool = False):
        # Make sure the pattern exists somewhere in the string

        if _from_ts:
            return

        timeframe = {}

        start_ix = 2000
        end_ix = 0
        found_match = False

        for match in re.finditer(self.pattern, argument):
            found_match = True
            duration, unit = match.groups()
            start_ix = min(match.start(), start_ix)
            end_ix = max(match.end(), end_ix)
            if unit in timeframe:
                raise commands.BadArgument("You seem to have specified {} more than once.".format(unit))

            timeframe[unit] = int(duration)

        if not found_match:
            raise commands.BadArgument("You're missing a timeframe.")

        # Perform some sanity checks TODO

        # Build timedelta

        # Weeks are tricky since we want to factor in years for good measure
        weeks = (timeframe.get("week", 0) +
                 (4 * timeframe.get("month", 0)) +
                 (52 * timeframe.get("year", 0)))

        self.timedelta = datetime.timedelta(
            seconds=timeframe.get("second", 0),
            minutes=timeframe.get("minute", 0),
            hours=timeframe.get("hour", 0),
            days=timeframe.get("day", 0),
            weeks=weeks if weeks else 0,
        )

        if self.timedelta.days > (365 * 2):  # max length of 2 years
            raise commands.BadArgument("Length must be less than 2 years.")

        self._reminder_body = self._build_reminder_body(argument, start_ix)

        # Now let's find the actual message inside

    def __gt__(self, other):
        if isinstance(other, Reminder):
            return self.timedelta > other.timedelta
        return NotImplemented

    def __lt__(self, other):
        if isinstance(other, Reminder):
            return self.timedelta < other.timedelta
        return NotImplemented


    @classmethod
    def from_unix_timestamp(cls, timestamp: str, message: str):
        """
        Create a reminder object from a unix timestamp and its associated offset from now
        """

        new_inst = cls("", True)

        dt = datetime.datetime.fromtimestamp(float(timestamp))
        new_inst.timedelta = dt - datetime.datetime.now()
        new_inst._reminder_body = new_inst._build_reminder_body(message)

        return new_inst

    @staticmethod
    def _build_reminder_body(argument_text: str, starting_ix=None):
        # Strip a leading "to"

        if not starting_ix:
            starting_ix = len(argument_text)

        reminder_body = argument_text[:starting_ix].strip()

        if reminder_body.startswith("to "):
            reminder_body = reminder_body[3:]

        if reminder_body.endswith(" in"):
            reminder_body = reminder_body[:-3]

        return reminder_body

    @property
    def reminder_body(self) -> str:
        return self._reminder_body

    @property
    def message(self) -> str:
        return self._reminder_body

    @property
    def years(self):
        return self.timedelta.days // 365

    @property
    def months(self):
        now = datetime.datetime.now()
        then = now + self.timedelta
        return (then.month - now.month) % 12

    @property
    def weeks(self):
        return (self.timedelta.days // 7) % 52

    @property
    def days(self):
        return self.timedelta.days % 7

    @property
    def hours(self):
        return (self.timedelta.seconds // 3600) % 24

    @property
    def minutes(self):
        return (self.timedelta.seconds // 60) % 60

    @property
    def seconds(self):
        return self.timedelta.seconds % 60

    @property
    def exp_time(self):
        return datetime.datetime.now() + self.timedelta

    def human_readable_time(self) -> str:
        output_string = []

        fields = [
            ("year", self.years),
            ("month", self.months),
            ("week", self.weeks),
            ("day", self.days),
            ("hour", self.hours),
            ("minute", self.minutes),
            ("second", self.seconds)
        ]

        for unit, value in fields:
            if value:
                output_string.append("{} {}{}".format(value, unit, "s" if value != 1 else ""))

        return ", ".join(output_string)


class ReminderCache:
    """
    Self-enclosed queue object to manage a bunch of reminders.
    Tries to be a bit more efficient than a regular old list.
    """

    def __init__(self, events: List[T_CacheElem] = None):
        """
        Create a new reminder cache.
        :param events: List of tuples consisting of all events that should be firing soon.
        Tuples are formatted as (unix_ts, event_key).
        """

        self._iter_ix = 0

        if events:
            self._queue_arr = list(sorted(events, key=lambda t: int(t[0]), reverse=True))
        else:
            self._queue_arr = []

    def pop(self) -> T_CacheElem:
        return self._queue_arr.pop()

    def peek(self) -> T_CacheElem:
        return self._queue_arr[-1]

    def clear(self):
        self._queue_arr = []

    def __len__(self):
        return len(self._queue_arr)

    def __bool__(self):
        return len(self._queue_arr) != 0

    def __iter__(self):
        self._iter_ix = len(self._queue_arr) - 1

    def __next__(self) -> T_CacheElem:
        if self._iter_ix <= 0:
            res = self._queue_arr[self._iter_ix]
            self._iter_ix -= 1
            return res
        else:
            raise StopIteration

    # def _bin_insert(self, elem, lb, ub):
    #
    #     elem_ts, _ = elem
    #
    #     if lb >= ub:
    #         if elem_ts >

    # def _insert(self, elem: T_CacheElem):
    #     """
    #     Perform a binary search to find the best place to insert the new reminder.
    #     :param elem: Key to insert.
    #     """
    #
    #     ts, key = elem
    #
    #     if len(self._queue_arr) == 0:
    #         self._queue_arr.append(elem)
    #         return
    #
    #     upper_bound = len(self._queue_arr) - 1
    #     lower_bound = 0
    #     mid_ix = None
    #
    #     while upper_bound >= lower_bound:
    #         mid_ix = (lower_bound + upper_bound) // 2
    #         mid_ts, _ = self._queue_arr[mid_ix]
    #
    #         # I'm aware these comparisons seem reversed
    #         # I want bigger numbers at the start of the array
    #         if ts == mid_ts:
    #             return mid_ix + 1
    #         elif ts < mid_ts:
    #             lower_bound = mid_ix + 1
    #
    #         else:
    #             upper_bound = mid_ix - 1
    #
    #     return mid_ix

    def add(self, elem: T_CacheElem):
        """
        Add an element to the queue.
        As it should be sorted, we can use a binary search and be more efficient than
        just default list insert
        """

        # Since we're already doing a linear insert, the time complexity won't be slammed
        # too hard by also performing a linear search

        # read: reverse binary insert is hared

        # new_ix = self._insert(elem)

        if not self._queue_arr:
            self._queue_arr.append(elem)
            return

        for i in reversed(range(len(self._queue_arr))):

            queue_ts, _ = self._queue_arr[i]
            if queue_ts >= elem[0]:
                self._queue_arr.insert(i + 1, elem)
                break

        else:
            self._queue_arr.insert(0, elem)

    def __str__(self):
        return self._queue_arr.__str__()

    def __repr__(self):
        return "<{}> {}".format(self.__class__.__name__, self.__str__())


class Reminders(commands.Cog):
    ACTIVE_KEY = "config:reminders:active"
    SOON_KEY = "config:reminders:soon"

    def __init__(self, bot: Bot):
        self.bot = bot
        self.config = bot.config
        self.update_window = datetime.timedelta(minutes=2)
        self.max_reminders = 50
        self._reminder_cache = ReminderCache()
        self._unsent_reminders = ReminderCache()

    async def _dispatch_reminder(self, reminder: dict):
        """
        Send a discord message with the given reminder object.
        """
        output_message = "<@{}>, you asked me to remind you to **{}**!"
        try:

            chan_id = int(reminder["channel_id"])

            chan = self.bot.get_channel(chan_id)

            # rem_obj = Reminder.from_unix_timestamp(reminder["exp_time"], reminder["message"])

            if not chan:
                chan = await self.bot.fetch_channel(chan_id)

            if not chan:
                log.error("Couldn't find channel for reminder.")
                return

            await chan.send(output_message.format(reminder["user_id"], reminder["message"]))

        except Exception:
            log.exception("Exception when trying to send message")

    def _add_to_soon_queue(self, tag: str):
        """
        Utility function to handle all the logic of adding an event to the soon queue, including caching.

        The soon queue will be cached on the bot to prevent DB lookups every second.
        The cache will be a sorted queue
        """

        reminder_obj_key = "config:reminders:objects:{}".format(tag)

        obj = self.config.hgetall(reminder_obj_key)
        obj["tag"] = tag

        self.config.sadd(self.SOON_KEY, tag)
        self._reminder_cache.add((int(obj["exp_time"]), obj))

    def _add_reminder_to_db(self, ctx, reminder: Reminder):
        """
        Handle the logic to ensure a reminder object is properly stored in the database.
        """

        reminder_tag = str(uuid4())

        user_key = "user:{}:reminders".format(ctx.author.id)
        user_active_key = "{}:active".format(user_key)
        new_reminder_key = "config:reminders:objects:{}".format(reminder_tag)

        # Add to user key

        exp_ts = str(int(reminder.exp_time.timestamp()))

        new_reminder_config = {
            "channel_id": str(ctx.channel.id),
            "user_id": str(ctx.author.id),
            "message": reminder.reminder_body,
            "exp_time": exp_ts,
            "tag": reminder_tag
        }

        self.config.sadd(user_active_key, reminder_tag)
        self.config.hmset(new_reminder_key, new_reminder_config)

        # Add user ID to bot's config key

        if reminder.timedelta < self.update_window:
            self._add_to_soon_queue(reminder_tag)
        else:
            self.config.sadd(self.ACTIVE_KEY, reminder_tag)

    def _delete_from_db(self, tag: str):
        """
        Delete a reminder from the database. Purges it from the soon and active queues, as well as the user's key.

        :param tag: reminder tag in UUID form.
        """
        tracked_objs_key = "config:reminders:objects"
        obj_key = "{}:{}".format(tracked_objs_key, tag)

        user_id = self.config.hget(obj_key, "user_id")

        user_key = "user:{}:reminders:active".format(user_id)

        self.config.delete(obj_key)
        self.config.srem(self.SOON_KEY, tag)
        self.config.srem(self.ACTIVE_KEY, tag)  # for good measure
        self.config.srem(user_key, tag)

        log.info("Event with tag {} was deleted from reminders db".format(tag))

    def _full_update(self):
        """
        Run through all timestamps and update them, making sure to move any soon-to-expire reminders to soon.
        """

        # TODO Add mechanism where any events still in the reminder cache are dispatched before clearing it

        if self._reminder_cache:
            for event_tup in self._reminder_cache:
                self._unsent_reminders.add(event_tup)
                log.info("Re-queueing event {} that was missed during during full update".format(event_tup))

        self._reminder_cache.clear()

        tracked_objs_active = self.config.smembers(self.ACTIVE_KEY)
        tracked_objs_key = "config:reminders:objects"
        # Tracked events are user IDs, let's run through

        seconds_til_next_full = self.update_window.total_seconds()

        for tag in tracked_objs_active:
            ts = self.config.hget("{}:{}".format(tracked_objs_key, tag), "exp_time")
            # Check if the event would happen before the next full update window
            if int(ts) - time.time() < seconds_til_next_full:
                # Move this event to soon
                self.config.srem(self.ACTIVE_KEY, tag)
                self._add_to_soon_queue(tag)

    async def _soon_update(self):
        """
        Check for and update timestamps which are expiring soon. Dispatch events for those which are expiring
        """
        # Instead of searching through, we should be able to take advantage of hashing timestamps
        # Since we update every second, there's nothing saying that we can't just fetch the current second as a dict
        # key from the cache.
        # I'd be worried about missing events, though, so let's make sure we catch any past events as well.

        events_remaining = len(self._reminder_cache) > 0
        missed_events_remaining = len(self._unsent_reminders) > 0

        while events_remaining:
            try:
                next_event = self._reminder_cache.peek()
            except IndexError:
                break
            if next_event[0] <= int(time.time()):
                next_event = self._reminder_cache.pop()
                event_ts, event_obj = next_event
                try:
                    await self._dispatch_reminder(event_obj)
                    self._delete_from_db(event_obj["tag"])
                except discord.Forbidden:
                    log.info("Got Forbidden on dispatch, deleting event {}".format(event_obj["tag"]))
                    self._delete_from_db(event_obj["tag"])
                except Exception:
                    log.error("Failed to dispatch SOON event {}, re-enqueuing".format(event_obj["tag"]))
                    self._unsent_reminders.add(next_event)
            else:
                events_remaining = False

        # If we've missed any events for some reason, let's make sure we at least give them one more shot.
        # these will always yield to events that haven't happened yet.

        while missed_events_remaining:
            next_event = self._unsent_reminders.pop()
            event_ts, event_obj = next_event
            try:
                await self._dispatch_reminder(event_obj)
            except Exception as e:
                err_msg = "Failed to dispatch SOON event {} after retrying, deleting".format(event_obj["tag"])
                if not isinstance(e, discord.Forbidden):
                    log.exception(err_msg)
                else:
                    log.error(err_msg)
            finally:
                self._delete_from_db(event_obj["tag"])

    def _get_user_reminders(self, ctx) -> List[Tuple[Reminder, dict]]:
        """
        Get a formatted list of reminders for a user, sorted by expiration.
        """
        user_id = ctx.author.id
        user_key = "user:{}:reminders:active".format(user_id)

        if not self.config.exists(user_key):
            return []

        rems = []

        # Build rems as a tuple of (reminder object, database object)

        for tag in self.config.smembers(user_key):
            obj_key = "config:reminders:objects:{}".format(tag)
            db_obj = self.config.hgetall(obj_key)
            rem_obj = Reminder.from_unix_timestamp(db_obj["exp_time"], db_obj["message"])
            rems.append((rem_obj, db_obj))

        new_rems = list(sorted(rems, key=lambda r: r[0].exp_time))

        return new_rems

    def list_reminders(self, ctx) -> List[str]:

        user_rems = self._get_user_reminders(ctx)
        output = []

        for reminder_obj, database_obj in user_rems:
            output.append("<#{}>: **{}** in {}".format(database_obj["channel_id"],
                                                       reminder_obj.message,
                                                       reminder_obj.human_readable_time()))

        return output

    @commands.group(invoke_without_command=True, aliases=["remindme", "rm"])
    async def reminder(self, ctx, *, reminder: Reminder):
        """
        Functionality for reminders. Call !help reminder for associated commands.
        """
        # Do some database stuff here

        message = "I'll remind you to '{}' in {}.".format(reminder.reminder_body,
                                                          reminder.human_readable_time())

        self._add_reminder_to_db(ctx, reminder)
        await ctx.send(message)

    @reminder.command(aliases=["ls"])
    async def list(self, ctx):
        """
        List a user's reminders
        """

        reminder_msg = "\n".join(self.list_reminders(ctx))

        if not reminder_msg:
            reminder_msg = "You don't have any active reminders."

        await ctx.send(reminder_msg)

    @checks.sudo()
    @reminder.command()
    async def clear(self, ctx):
        """
        Clear all of a user's reminders.
        Use with caution!
        """
        user_id = ctx.author.id
        user_key = "user:{}:reminders:active".format(user_id)
        for tag in self.config.smembers(user_key):
            self._delete_from_db(tag)

        await ctx.send("Your reminders have been deleted.")

    @checks.sudo()
    @reminder.command()
    async def delete(self, ctx):
        """
        Delete a reminder.
        Should show an interactive prompt to allow the user to delete one that they want to. Since users may have
        multiple duplicate reminders, make sure we delete the one we want to.
        """

        def message_check(msg):
            return msg.author == ctx.message.author and msg.channel == ctx.channel

        base_msg = "Please reply with the number of the reminder you want to delete, or `exit` to quit."
        invalid_resp_msg = "Invalid response, please reply with the number of the reminder to delete, or `exit`."

        reminders = self._get_user_reminders(ctx)

        if not reminders:
            await ctx.send("You don't have any active reminders.")
            return

        selected_reminder = None

        output = [base_msg]

        for i, tup in enumerate(reminders, start=1):
            output.append("`{}`: **{}** in {}".format(i, tup[0].message, tup[0].human_readable_time()))

        base_msg_content = "\n".join(output)

        own_msg = await ctx.send(base_msg_content)

        while selected_reminder is None:

            response_msg = await self.bot.wait_for("message", check=message_check, timeout=600)

            if response_msg is None or response_msg.content == "exit":
                return

            try:
                selection = int(response_msg.content)
            except ValueError:
                await own_msg.edit(content=base_msg_content + "\n\n" + invalid_resp_msg)
                continue

            if not 0 < selection <= len(reminders):
                await own_msg.edit(content=base_msg_content + "\n\n" + "Number appears to be out of range.")

            else:
                selected_reminder = reminders[selection - 1]

        rem_obj, db_dict = selected_reminder

        tag = db_dict["tag"]

        log.info("Deleting reminder with tag {}".format(tag))

        self._delete_from_db(tag)

        await own_msg.edit(content="Reminder to '{}' deleted successfully.".format(rem_obj.message))

    @commands.Cog.listener()
    async def on_timer_update(self, seconds: int) -> None:
        await self._soon_update()

        if seconds % int(self.update_window.total_seconds()) == 0:
            # log.info("Performing full update")
            self._full_update()

        # TODO Hashmap method is fast but inconsistent since the bot sometimes skips a second or two


def setup(bot):
    bot.add_cog(Reminders(bot))
