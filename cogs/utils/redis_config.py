"""Interface with redis for config"""

import redis
import json
import logging

log = logging.getLogger()


class RedisConfig(redis.StrictRedis):

    def __init__(self, config_fp="redis_config.json"):

        try:
            with open(config_fp, "r", encoding="utf-8") as config_raw:
                _config = json.load(config_raw)
        except Exception as e:
            log.exception("Failed to load redis config")
            raise e
        # Note: This may result in weird exceptions

        super().__init__(**_config)

    def parse_response(self, connection, command_name, **options):
        """"Parses a response from the Redis server"""
        response = connection.read_response()
        if response == "True":
            return True
        elif response == "False":
            return False
        elif command_name in self.response_callbacks:
            return self.response_callbacks[command_name](response, **options)
        return response

    def _get_dict_structure_recursive(self, obj: dict, output_dict: dict, cur_path=""):
        """Recursively traverse the dictionary and convert it to a particular cur_path"""
        if isinstance(obj, dict):
            for k, v in obj.items():
                cur_path = (cur_path + ":" + k) if cur_path else k
                if not isinstance(v, dict):
                    output_dict[cur_path] = v
                else:
                    self._get_dict_structure_recursive(v, output_dict, cur_path)
            return output_dict

    def set_dict(self, main_key, obj, as_hash=False):
        if not isinstance(obj, dict):
            obj = obj.__dict__()
        for k, v in self._get_dict_structure_recursive(obj, {}):
            k = "%s:%s" % main_key, k
            if isinstance(v, (list, tuple)):
                self.rpush(k, *v)
            elif as_hash:
                k = str(k).replace(":", "_")
                self.hset(main_key, k, v)
            else:
                self.set(k, str(v))

    def get_and_format_key(self, name):
        type = self.type(name)
        if type == "string":
            return self.get(name)
        elif type == "list":
            return self.lrange(name, 0, -1)
        elif type == "set":
            # Should I keep this a set or make it a list?
            return self.smembers(name)
        elif type == "zset":
            return self.zrevrange(name, 0, -1)
        elif type == "hash":
            return self.hgetall(name)
