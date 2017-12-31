import asyncio
import json
import os
import uuid

# Copyright (c) 2016 Rapptz


class Config:

    def __init__(self, filename):
        self.filename = filename
        self._data = {}
        self.lock = asyncio.Lock()
        self.loop = asyncio.get_event_loop()

        self.load_from_file()

    def __contains__(self, item):
        return item in self._data

    def __iter__(self):
        for key in self._data:
            yield key

    def __dict__(self):
        return self._data

    def load_from_file(self):
        try:
            with open(self.filename, "r", encoding="utf-8") as datafile:
                self._data = json.load(datafile)
        except FileNotFoundError:
            self._data = {}

    def get(self, key, *args):
        """Retrieves a config entry."""
        return self._data.get(key, *args)

    def _dump(self):
        temp = '{}-{}.tmp'.format(self.filename, uuid.uuid4())
        with open(temp, 'w', encoding='utf-8') as tmp:
            json.dump(self._data.copy(), tmp, separators=(',', ':'))

        # atomically move the file
        os.replace(temp, self.filename)

    async def load(self):
        with await self.lock:
            await self.loop.run_in_executor(None, self.load_from_file)

    async def save(self):
        with await self.lock:
            await self.loop.run_in_executor(None, self._dump)

    async def put(self, key, value):
        """Edits a config entry."""
        self._data[key] = value
        await self.save()

    async def remove(self, key):
        """Removes a config entry."""
        del self._data[key]
        await self.save()

    async def add(self, key, value):
        """Add to an existing list"""
        self._data[key].append(value)
        await self.save()
