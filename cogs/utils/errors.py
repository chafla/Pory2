from discord.ext.commands.errors import CommandError


class CommandRateLimited(CommandError):
    """Overriding the default discord command on cooldown.

    :param retry_after: Amount of seconds until command can be used again, modified by the cooldown coeff.
    """

    def __init__(self, retry_after):

        self.retry_after = retry_after
        # Make sure we don't get the "wait one seconds"
        # Also using % because it's slightly more efficient than .format()
        _delay = "%s second%s" % retry_after, "s" if retry_after != 1 else ""
        super().__init__(message="Please wait {} before posting that again.".format(_delay))


class CommandBlacklisted(CommandError):
    """Command is blacklisted in the current context and cannot be used.

    May be better substituted with commands.check.
    """

    def __init__(self, msg=None):
        super().__init__(message=msg)
