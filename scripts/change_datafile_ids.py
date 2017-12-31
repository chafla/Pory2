"""Change all active datafile IDs from str to int"""
import re


def id_sub(match):
    return match.group(1)

for file in ["config.json", "countdowns.json",
             "image_list_cache.json", "lounge_config.json",
             "eggs.json"]:

    with open(file, "r", encoding="utf-8") as config_raw:
        config = config_raw.read()
        # The extra tags are so that we change strings in lists but not string keys, since json only supports string
        # keys.
        config_updated = re.sub(r'\"(\d{17,18})\"(?!:)', id_sub, config)

    with open(file, "w", encoding="utf-8") as outfile:
        outfile.write(config_updated)
