"""
Utilities to help with regging. This shouldn't completely replace filling out the form, since a small effort
barrier should hopefully keep people a little more honest.
At the same time, people shouldn't need to keep calling !user_info
"""

from discord.ext import commands
from .utils import checks, messages
import discord
import json
import glob
import re
import logging

# Note: Might need to pip install PyOpenSSL
import gspread
import gspread.utils
from oauth2client.service_account import ServiceAccountCredentials
import dateutil.tz
import dateutil.parser

log = logging.getLogger()

report_output = """
User: {0.name}
Joined at: {0.joined_at}
Acct created at: {0.created_at}
Application filed: {1}
"""

# Sheet is "https://docs.google.com/spreadsheets/d/1w0TOLj-SWXMFf0Hf8Zv7oJxX5oiDsGoEOfJFyt1vtkk/edit#gid=0"


class RegularUtils:

    def __init__(self, bot):
        self.bot = bot
        self.config = bot.config
        self.gclient = None
        self.wks = None
        self._google_auth("1w0TOLj-SWXMFf0Hf8Zv7oJxX5oiDsGoEOfJFyt1vtkk")  # TODO: Update w/ actual form

    @property
    def guild(self):
        return self.bot.get_guild(111504456838819840)

    def _google_auth(self, sheet_key):
        """Authenticate with google"""
        scope = ['https://spreadsheets.google.com/feeds']
        with open("auth.json", "r", encoding="utf-8") as datafile:
            auth = json.load(datafile)["sheets"]
        self.creds = ServiceAccountCredentials.from_json_keyfile_dict(auth, scope)
        self.gclient = gspread.authorize(self.creds)
        # Open the spreadsheet.
        # Even if link sharing is enabled, the spreadsheet has to be explicitly shared with client.email in auth.json
        self.wks = self.gclient.open_by_key(sheet_key).sheet1

    @staticmethod
    def _timestamp_to_datetime(timestamp):
        """Stuff we have to do because strptime expects padding"""
        return dateutil.parser.parse(timestamp, tzinfo=dateutil.tz.gettz("America/New York"))

    @staticmethod
    def find_member_by_username(username, guild):
        """Process the username and discriminator and check to see if we can find a match"""
        return discord.utils.find(lambda m: str(m) == username, guild.members)

    async def process_reg_document(self):
        """
        Process the regular form document and check to see if there are any changes. If so, add them to the tracked
        config file.

        :return: List of member objects that have been added since the document was last checked.
        """

        # Store the last update position in the google doc itself
        last_checked_row = self.config.get("config:regulars:last_checked_row")
        last_checked_row = int(last_checked_row) if last_checked_row else 2
        last_valid_row = last_checked_row  # Keeping track of the last row that we know has a good value

        processed_members = []

        if last_checked_row == self.wks.row_count:
            return []

        # Starting at the last row we checked last time, scan through until we hit a blank cell.
        # If there is a new appeal, post it, and update the value for the last valid row so we don't scan through
        # the document multiple times.
        for cell in self.wks.range("A{}:A{}".format(last_checked_row + 1, self.wks.row_count)):  # Skip the first row
            if cell.value == "":  # End of list
                last_valid_row = cell.row - 1
                break

            # Timestamp is in est

            active_row = self.wks.row_values(cell.row)
            ts = active_row[0]

            parts = {
                "application_id": cell.row - 1,
                "timestamp_from_form": ts,
                "discord_username": active_row[1],
                "reddit_username": active_row[2],
                "joined_date": active_row[3],
                "favorite_pkmn": active_row[4],
                "birthday": active_row[5],
                "age": active_row[6]
            }

            # Check against the server to see if a member w/ their username exists on the server

            member = self.find_member_by_username(active_row[1], self.guild)

            if member:
                parts["discord_id"] = member.id
                parts["discord_joined_at"] = str(member.joined_at)
                parts["discord_created_at"] = str(member.created_at)

                self.wks.update_acell("M{}".format(cell.row), member.id)
                processed_members.append(member)

            else:
                parts["discord_id"] = None
                parts["discord_joined_at"] = None
                parts["discord_created_at"] = None

            if last_valid_row < cell.row:
                log.info("New reg app submitted by {}. Discord verified: {}".format(member.name if member else active_row[1],
                                                                                    member is not None))
                self.config.hmset("config:regulars:apps:{}".format(member.id), parts)

        if last_checked_row != last_valid_row:
            self.config.set("config:regulars:last_checked_row", last_valid_row)

        return processed_members

    # @checks.is_pokemon_mod()
    @commands.command(hidden=True)
    async def generate_report(self, ctx, user_id: str):
        """
        Generate a report on a user, including the amount of messages that they have sent, what channels they talked in,
        how many messages per channel, etc.
        Pull that from the existing logs.
        Might take a while
        """

        # TODO: Only track messages that the user has filled out since a certain date

        if ctx.message.mentions:
            user_id = ctx.message.mentions[0].id

        member = discord.utils.get(self.guild.members, id=user_id)
        if member is None:
            await ctx.send("Member not found in the server.")
            return

        # Get the time that the member filed their confirmation
        elif not self.config.exists("config:regulars:apps:{}".format(user_id)):
            await ctx.send("Reg submission from user not found. Continuing without sub info.")

        else:
            reg_app = self.config.hmgetall("config:regulars:apps:{}".format(user_id))
            output = report_output.format(member, reg_app["timestamp_from_form"])
            await ctx.say(output)

        async with ctx.typing():

            # Generate activity report

            data = {}
            activity_output = ""
            channels = glob.glob("message_cache/channels/*")  # Find a neater solution to just find the filename

            # Get the number of messages the user has posted per channel

            for channel_path in channels:
                try:
                    channel_id = re.findall(r'(\d{17,18})', channel_path)[0]  # Find the ID from the path
                except IndexError:  # If the path has no ID in it
                    continue
                # Get the total number of messages the user has send among channels
                with open(channel_path, "r", encoding="utf-8") as channel_data:
                    data[channel_id] = 0
                    for line in channel_data.readlines():
                        if "({})".format(user_id) in line:  # User id is at the start of most new lines
                            data[channel_id] += 1  # count the total number of lines that they have posted per chan.

            # Get the names of those channels from the server, if they exist.

            for channel_id, message_count in data.items():
                channel_obj = self.bot.get_channel(channel_id)
                if channel_obj is None:
                    channel_name = "[DELETED CHANNEL] (ID: {})".format(channel_id)
                else:
                    channel_name = channel_obj.name

                if data[channel_id] == 0:
                    continue

                activity_output += "{}: **{}** messages\n".format(channel_name, data[channel_id])

                if len(activity_output) > 1900:  # If the message is too long, just send it and make a new one
                    await ctx.send(activity_output)
                    activity_output = ""

            if not activity_output:
                activity_output = "Nothing found."
        await ctx.send(activity_output)

    @checks.r_pokemon()
    @checks.is_pokemon_mod()
    @commands.command(hidden=True)
    async def reset_reg_requests(self):
        """Reset all active regular requests"""
        self.config.delete(*self.config.scan_iter("config:regulars:apps:*"))

    @commands.Cog.listener()
    async def on_timer_update(self, seconds):
        if seconds % 120 == 0:
            if self.creds.access_token_expired:
                self.gclient.login()  # Re-auth if our access tokens expire

            new_apps = await self.process_reg_document()
            for member in new_apps:
                await member.send(messages.reg_confirmation)


def setup(bot):
    bot.add_cog(RegularUtils(bot))
