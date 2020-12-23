"""
Listener for the ban appeals form, to check to see if we have any new form responses. If so,
"""

import datetime
import json
import logging
import re

from typing import List, Optional

import discord
from discord import Guild
from discord.ext import commands
from discord.ext.commands import Bot

from .utils.utils import get_timestamp

# Requires PyOpenSSL to function
import dateutil.tz
import gspread
import gspread.utils
from oauth2client.service_account import ServiceAccountCredentials


log = logging.getLogger()


class BanAppeals(commands.Cog):

    def __init__(self, bot: Bot) -> None:
        self.bot = bot
        self.config = bot.config
        self.gclient = None
        self.wks = None
        self._google_auth("1iNzsBlq8DbTY1Y1NV_dN8vV9Pt4piT5C-RGvN_aC2Bk")

    @property
    def guild(self) -> Guild:
        return self.bot.get_guild(id=111504456838819840)

    def _google_auth(self, sheet_key: str) -> None:
        """Authenticate with google"""
        scope = ['https://spreadsheets.google.com/feeds']
        with open("auth.json", "r", encoding="utf-8") as datafile:
            auth = json.load(datafile)["sheets"]
        self.creds = ServiceAccountCredentials.from_json_keyfile_dict(auth, scope)
        self.gclient = gspread.authorize(self.creds)
        # Open the spreadsheet.
        # Even if link sharing is enabled, the spreadsheet has to be explicitly shared with client.email in auth.json
        self.wks = self.gclient.open_by_key(sheet_key).sheet1

    @staticmethod  # No usage found in project.
    def _timestamp_to_datetime(timestamp: str) -> datetime.datetime:
        """Stuff we have to do because strptime expects padding"""
        ts = [int(i) for i in re.findall("(\d+)", timestamp)]
        return datetime.datetime(
            month=ts[0], day=ts[1], year=ts[2], hour=ts[3],
            minute=ts[4], second=ts[5], tzinfo=dateutil.tz.gettz("ET")
        )

    async def check_appeals(self) -> List[Optional[dict]]:
        """
        Process the document and check to see if there are any changes
        """

        last_checked_row = self.config.get("config:ban_appeals:last_checked_row")
        last_checked_row = int(last_checked_row) if last_checked_row else 2

        last_valid_row = last_checked_row  # Keeping track of the last row that we know has a good value

        updated_appeals = []

        if last_checked_row == self.wks.row_count:
            return []

        # while not last_cell:

        for cell in self.wks.range("A{}:A{}".format(last_checked_row, self.wks.row_count)):  # Skip the first row
            active_row = self.wks.row_values(cell.row)
            if active_row[0] == "":  # End of list
                last_valid_row = cell.row - 1
                break

            # Timestamp is in est

            parts = {
                "Appeal ID": cell.row - 1,
                "Time submitted": active_row[0],
                "Discord Username": active_row[1],
                "Date of ban": active_row[2],
                "Ban reason": active_row[3],
                "Reason for appeal": active_row[4],
                "Contact email": active_row[5]
            }

            if last_valid_row < cell.row:
                # We haven't processed this one yet, let's keep track of it
                updated_appeals.append(parts.copy())

        if last_checked_row != last_valid_row:
            self.config.set("config:ban_appeals:last_checked_row", last_valid_row)

        return updated_appeals

    @commands.Cog.listener()
    async def on_timer_update(self, seconds: int) -> None:
        if seconds % 120 == 0 and seconds != 0:  # Check every two minutes

            if self.creds.access_token_expired:
                self.gclient.login()  # Re-auth if our access tokens expire

            updated_appeals = await self.check_appeals()
            if updated_appeals:

                for appeal in updated_appeals:

                    embed = discord.Embed(color=discord.Color.blue())
                    embed = embed.set_footer(text=get_timestamp())

                    for title, content in appeal.items():
                        embed.add_field(name=title, value=content)

                    mod_log_channel = self.bot.get_channel(268259704906448896)

                    # causes issues when debugging
                    try:
                        await mod_log_channel.send(content="**New ban appeal submitted.**",
                                                   embed=embed)
                    except AttributeError:  # Trying to send to a NoneType channel
                        log.exception("Error occurred sending ban appeals")


def setup(bot: Bot) -> None:
    bot.add_cog(BanAppeals(bot))
