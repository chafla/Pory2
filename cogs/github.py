"""Basic github functionality for housekeeping and bug tracking.
This may have issues once we start to deal with how asyncio and requests
don't like to play together"""

import json

import github

from discord.ext import commands
from discord.ext.commands import Bot, Context

from cogs.utils import checks


class GitHub(commands.Cog):

    def __init__(self, bot: Bot) -> None:
        self.bot = bot
        self.client = None
        self.repo = None

        self._github_auth()

    def _github_auth(self) -> None:
        with open("auth.json", "r", encoding="utf-8") as f:
            auth_file = json.load(f)
        self.client = github.Github(auth_file["github"]["token"])
        self.repo = self.client.get_user().get_repo("PorYgon2")

    @checks.sudo()
    @commands.command()
    async def create_issue(
            self, ctx: Context, label_name: str, name: str, *, body: str
    ) -> None:
        """Create a new tracked issue for bug-tracking"""
        valid_labels = ["bug", "enhancement", "none"]
        if label_name.lower() not in valid_labels:
            raise commands.BadArgument("Label must be in {}".format(valid_labels))
        elif label_name.lower() == "none":
            labels = [None]
        else:
            labels = [self.repo.get_label(label_name)]
        new_issue = self.repo.create_issue(name, body, labels=labels)
        await ctx.send("New issue `{0.title}` created at {0.url}.".format(new_issue))


def setup(bot: Bot) -> None:
    bot.add_cog(GitHub(bot))
