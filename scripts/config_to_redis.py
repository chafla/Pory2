"""transfer stuff from json datafiles into redis db"""

from cogs.utils.redis_config import RedisConfig
from cogs.utils.config import Config

rconfig = RedisConfig()
config = Config("config.json")

# image lists


def retro_load_albums_to_redis():
    n = config.get("album_lists")
    for name, album_ids in n.items():
        rconfig.sadd("img:albums:{}:ids".format(name), *album_ids)


def meme_channel_blacklist():
    c = config.get("meme_channel_blacklist")
    rconfig.sadd("config:rate_limits:chan_blacklist", *c)


def friend_codes():
    fc_config = Config("friend_codes.json")
    for user_id in fc_config:
        fc_info = fc_config.get(user_id)
        for key, val in fc_info.items():
            if key in ["3DS", "Switch"]:
                rconfig.set("user:{}:fc:{}:code".format(user_id, key), val)
            elif "ign" in key:
                if "3DS" in key:
                    rconfig.hmset("user:{}:fc:3DS:ign".format(user_id), val)  # pretty sure I only support 3ds


def rate_limits_and_misc():
    misc_config = Config("misc.json")
    cooldown_coeffs = misc_config.get("cooldown_coeffs")
    for chan_id, value in cooldown_coeffs.items():
        rconfig.set("chan:{}:rate_limits:cooldown_ratio".format(chan_id), float(value))
    counters = misc_config.get("counters")["Porygon2"]
    for command, uses in counters.items():
        rconfig.zadd("misc:rate_limits:counters", int(uses), command)


def mod():
    reminders = config.get("mod_server_reminders")
    for ts, content in reminders.items():
        rconfig.hmset("config:mod:reminders:{}".format(ts), content)


def role_blacklist():
    for name, ids in config.get("role_blacklist").items():
        rconfig.sadd("admin:role_blacklist:{}".format(name), *ids)


def spreadsheet_stuff():
    reg_config = Config("regulars.json")
    rconfig.set("config:regulars:last_checked_row", reg_config.get("last_checked_row", 2))

    rconfig.set("config:ban_appeals:last_checked_row", config.get("appeals_last_checked_row", 2))


def uwuconomy():
    for user_id, count in config.get("uwuconomy").items():
        rconfig.set("user:{}:uwuconomy".format(user_id), count)


if __name__ == "__main__":
    friend_codes()
