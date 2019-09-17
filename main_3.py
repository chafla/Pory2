"""
Porygon2 v.3.0.0a
Written by Luc | ルカリオ#5653 (/u/l_u_c_a_r_i_o)
Rewrite from the ground up of Porygon2 in order to properly take advantage of discord.ext
Finally giving into the inevitable future of OOP after almost a year of coding.
Begun on 11/11/16.

v.4.0.0a
The number scheming is never going to make any sense at this point if I keep forgetting.

Rewriting to account for the new breaking changes in discord.py that's coming up in the rewrite.

'I'm gonna go pour some holy water in my .gitignore' -Porygon2
"""

import asyncio
import logging
import json
import sys
import traceback

from io import StringIO
from time import perf_counter

from discord import Message
from discord.ext.commands import (
    Context, CommandError, NoPrivateMessage, DisabledCommand,
    CheckFailure, CommandNotFound, MissingRequiredArgument,
    CommandInvokeError, UserInputError, BadArgument, AutoShardedBot
)

from cogs.utils.errors import CommandBlacklisted, CommandRateLimited
from cogs.utils.checks import sudo_check
from cogs.utils.redis_config import RedisConfig


loop = asyncio.get_event_loop()


log = logging.getLogger()
log.setLevel(logging.INFO)
handler = logging.FileHandler(filename='pory2.log', encoding='utf-8', mode='a')
formatter = logging.Formatter("{asctime} - {levelname} - {message}", style="{")
handler.setFormatter(formatter)
log.addHandler(handler)


log.info("Instance started.")


def exception_handler(loop, context) -> None:
    """Log all exceptions to our logger while also sending them to stderr"""
    log.error(context["message"],
              exc_info=context["exception"])
    print(context["message"], context["exception"], file=sys.stderr)


loop.set_exception_handler(exception_handler)

prefix = "!"

initial_extensions = [
    'cogs.memes',
    'cogs.image_list',
    'cogs.admin',
    'cogs.general',
    'cogs.logs',
    'cogs.markov',
    'cogs.micspam',
    'cogs.server_logs',
    'cogs.rmd',
    'cogs.quackbot',
    'cogs.polls',
    'cogs.eyes',
    'cogs.uwuconomy',
    'cogs.friend_codes',
    'cogs.ban_appeals',
    'cogs.pm',
    'cogs.manips',
    'cogs.mod',
    'cogs.pokemon_tourney',
    'cogs.utils.help',
    'cogs.github',
]

description = "Memebot written initially for the /r/MysteryDungeon server that has spread elsewhere." \
              "\nWritten by Luc#5653."

try:
    with open('auth.json', 'r+') as json_auth_info:
        auth = json.load(json_auth_info)
except IOError:
    sys.exit("auth.json not found in running directory.")


async def init_timed_events(client: AutoShardedBot) -> None:
    """Create a listener task with a tick-rate of 1s"""

    await client.wait_until_ready()  # Wait for the bot to launch first
    client.secs = 0

    secs = 0  # Keep track of the number of secs so we can access it elsewhere and adjust how often things run
    while True:
        client.dispatch("timer_update", secs)
        await timer_update(secs)
        secs += 1
        client.secs = secs
        await asyncio.sleep(1)


class PoryBot(AutoShardedBot):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance = "Porygon2"
        self.events = []
        self.boo_counter = 1
        self.config = RedisConfig()
        self.loop.create_task(init_timed_events(self))


bot = PoryBot(command_prefix=prefix, description=description, pm_help=True, fetch_offline_members=True)


def log_exception(error: Exception, ctx: Context) -> None:
    # Print out to stderr and log
    sio = StringIO()
    if ctx.command:
        print('In {0.command.qualified_name}:'.format(ctx), file=sys.stderr)
        log.error('In {0.command.qualified_name}:'.format(ctx))
    print('{0.__class__.__name__}: {0}'.format(error), file=sys.stderr)
    traceback.print_tb(error.__traceback__, file=sys.stderr)
    # we use the StringIO object here to allow us to capture the full traceback as it would be printed,
    # and then pass it along.
    traceback.print_tb(error.__traceback__, file=sio)

    log.exception('{0.__class__.__name__}: {0}'.format(error), exc_info=error)

    # Make it write out when something goes wrong, so we have an idea what's going on w/o having to consult logs
    if sudo_check(ctx.message):
        if isinstance(error, CommandInvokeError):
            error = error.original
        exc_output = "🕷️ The last command triggered an exception:\n```py\n{0.__class__.__name__}: {0}\n{1}```".format(
            error, sio.getvalue() if len(sio.getvalue()) < 2000 else "")
        ctx.bot.loop.create_task(ctx.message.author.send(exc_output))


@bot.listen()
async def timer_update(seconds: int) -> int:
    # Dummy listener
    return seconds


@bot.event
async def on_command_error(ctx: Context, error: CommandError) -> None:

    if isinstance(error, NoPrivateMessage):
        await ctx.send('This command cannot be used in private messages.')
    elif isinstance(error, DisabledCommand):
        await ctx.send('This command is disabled and cannot be used.')
    elif isinstance(error, CheckFailure):
        # This caused issues with Meloetta running in the same channel
        # await bot.send_message(ctx.message.author, "You do not have permission to use this command.")
        pass
    elif isinstance(error, CommandNotFound):
        pass
    elif isinstance(error, MissingRequiredArgument):  # This inherits from UserInputError
        await bot.formatter.format_help_for(ctx, ctx.command, "You are missing required arguments.")
    elif isinstance(error, CommandInvokeError):
        log_exception(error, ctx)
    elif isinstance(error, (CommandBlacklisted, CommandRateLimited, UserInputError, BadArgument)):
        await ctx.send(error if error else error.__class__.__name__)
    else:
        log_exception(error, ctx)


@bot.event
async def on_ready() -> None:
    print('Logged in as')
    print(bot.user.name)
    print(bot.user.id)
    log.info("Initialized.")
    bot.owner = bot.get_user(78716152653553664)

    print('------')


@bot.event
async def on_message(message: Message) -> None:

    if message.author.id == bot.user.id:
        return

    if message.content.startswith("!"):
        log.info("Command '{}' called by {} ({})".format(message.content, message.author.name, message.author.id))

    await bot.process_commands(message)

# Starting up

if __name__ == "__main__":
    current_uptime = perf_counter()
    last_reading = 0
    log.info("Loading cogs...")
    for extension in initial_extensions:
        try:
            bot.load_extension(extension)
            last_reading = perf_counter() - current_uptime
            current_uptime = perf_counter()
            log.info("Loaded {} in {:.02f}s.".format(extension, last_reading))

        except Exception as e:
            log.warning('Failed to load extension {}\n{}: {}'.format(extension, type(e).__name__, e))
            log.exception("Traceback:")
            print('Failed to load extension {}\n{}: {}'.format(extension, type(e).__name__, e))

    bot.run(auth["discord"]["token"])
