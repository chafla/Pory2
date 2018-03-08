"""image manipulations"""

import PIL
import PIL.Image
from .utils import rate_limits, checks, rgb_transform, gif_overlay, utils
from .utils.magik import CustomImage
from glob import glob
import os.path
from os import remove
import aiohttp
import io
import discord
from discord.ext import commands
import numpy as np
import cv2
from random import randint
import math
from uuid import uuid4

# TODO Make these work with attachments


class Manips:

    VALID_PARAMS = ["rad_blur_degrees", "cas_intensity"]

    def __init__(self, bot):
        self.bot = bot

        self.blacklisted_channels = [278043765082423296]
        self._channel_cooldowns = []
        self.config = bot.config
        self._parameter_cache = self.config.hgetall("config:manips:params")

    @staticmethod
    def add_more_jpeg(base_path, *, output_path=None, quality=5):
        base_img = PIL.Image.open(base_path)
        base_img.save(output_path, "JPEG", quality=quality)
        if isinstance(output_path, io.BytesIO):
            base_path.seek(0)

    @staticmethod
    def overlay_sunglasses(base_img_path):
        output_fp = "sunglasses.png"
        base_img = PIL.Image.open(base_img_path)
        sunglasses_overlay = PIL.Image.open("templates/glasses.png")

        eyes = Manips.find_eyes(base_img_path, (base_img.height + base_img.width) // 2)

        # We know the eyes' positions on the base picture so we can do some basic trig to determine the angle
        # to rotate the sunglasses

        eyes = sorted(eyes, key=lambda eye: eye[1], reverse=True)  # Sort by x value

        dist = math.sqrt(math.pow(eyes[1][0] - eyes[0][0], 2) + math.pow(eyes[1][1] - eyes[0][1], 2))

        theta = math.degrees(math.atan((eyes[1][0] - eyes[0][0]) / (eyes[1][1] - eyes[0][1])))

        # scaling

        resize_ratio = (dist / sunglasses_overlay.width) * 2

        sunglasses_overlay = sunglasses_overlay.resize(
            (int(resize_ratio * sunglasses_overlay.width), int(resize_ratio * sunglasses_overlay.height)),
            PIL.Image.ANTIALIAS)

        sunglasses_overlay = sunglasses_overlay.rotate(int(90 + theta), resample=PIL.Image.BICUBIC, expand=True)

        shift = int(resize_ratio * abs((theta * 0.75)))

        base_img.paste(sunglasses_overlay, (int(eyes[0][0] - shift), eyes[0][1]) if eyes[0][0] > eyes[1][0] else (
                        int(eyes[1][0] - shift), eyes[1][1]), sunglasses_overlay)

        base_img.save(output_fp, format="PNG")
        return output_fp

    @staticmethod
    def find_eyes(image_path, base_img_size):
        """Find eyes, returning an (x, y, w, h) tuple of the two largest"""
        # TODO Make this a filter_eyes thing that also checks relative coords
        eye_cascade = cv2.CascadeClassifier('templates/cascades/haarcascade_eye.xml')
        cv2_img = cv2.imread(image_path)
        gray = cv2.cvtColor(cv2_img, cv2.COLOR_BGR2GRAY)

        image_path = eye_cascade.detectMultiScale(gray)
        largest_eyes = sorted(image_path, key=lambda eye: eye[3], reverse=True)[:min(3, len(image_path))]

        # Find the eyes that are the most similar in size and

        size_thresh = base_img_size // 15
        for i in range(len(largest_eyes)):
            for j in range(len(largest_eyes[i:])):
                if i == j:
                    continue
                elif abs(largest_eyes[i][3] - largest_eyes[j][3]) < size_thresh:
                    return largest_eyes[i], largest_eyes[j]

    @staticmethod
    def add_lens_flare_to_eyes(image_path, output_fp):

        base_image = PIL.Image.open(image_path)
        lens_flare = PIL.Image.open("templates/overlays/lens_flare.png")

        # Create a new image for output
        new_img = PIL.Image.new("RGB", (base_image.width, base_image.height))
        new_img.paste(base_image, (0, 0))

        # Scan through all the eyes detected in the image
        # TODO Only use the largest two\
        # Find eyes up here before we do any major filtering on the image
        filtered_eyes = Manips.find_eyes(image_path, (new_img.height + new_img.width) // 2)

        # Add red overlay

        new_img = rgb_transform.RGBTransform().mix_with((255, 0, 0), factor=.4).applied_to(new_img)

        image_mod = np.array(new_img)
        open_cv_image = image_mod[:, :, ::-1].copy()  # Thanks github
        # dimensions need to be odd for opencv to work
        # width = new_img.width if new_img.width % 2 == 1 else new_img.width + 1
        # height = new_img.height if new_img.width % 2 == 1 else new_img.width + 1
        # open_cv_image = cv2.GaussianBlur(open_cv_image, (width, height), 1.7)

        # Adding motion blur because why not

        motion_blur_size = ((new_img.height + new_img.width) // 2) // 13

        kernel_motion_blur = np.zeros((motion_blur_size, motion_blur_size))
        kernel_motion_blur[int((motion_blur_size - 1) / 2), :] = np.ones(motion_blur_size)
        kernel_motion_blur /= motion_blur_size

        open_cv_image = cv2.filter2D(open_cv_image, -1, kernel_motion_blur)

        open_cv_image = cv2.cvtColor(open_cv_image, cv2.COLOR_BGR2RGB)

        pil_im = PIL.Image.fromarray(open_cv_image)  # Convert back so we can paste in

        if filtered_eyes is not None:
            for (x, y, w, h) in filtered_eyes:
                # resize_ratio = min(w / lens_flare.width, h / base_image.height)
                overlay_img = lens_flare.resize(
                    (w * 3, h * 3),
                    PIL.Image.ANTIALIAS)
                shift_amt = new_img.width // 75
                pil_im.paste(overlay_img, (x - h + shift_amt, y - w + shift_amt), overlay_img)

        # new_img.save(output_fp)
        pil_im.save(output_fp, format="PNG")
        output = io.BytesIO()
        pil_im.save(output, format="PNG")
        output.seek(0)
        return output

    @staticmethod
    def add_overlay_template(base_path, overlay_path, output_path):
        base_img = PIL.Image.open(base_path)
        overlay_img = PIL.Image.open(overlay_path)

        # Let's use the same scaling magic we used for *ify

        resize_ratio = min(base_img.width / overlay_img.width, base_img.height / overlay_img.height)

        # Change the overlay_img to the width of the new image; .resize() just returns the image
        overlay_img = overlay_img.resize(
            (int(overlay_img.width * resize_ratio), int(overlay_img.height * resize_ratio)),
            PIL.Image.ANTIALIAS)

        # create a new blank canvas
        new_img = PIL.Image.new("RGB", (base_img.width, base_img.height))

        new_img.paste(base_img, (0, 0))
        new_img.paste(overlay_img, (base_img.width - overlay_img.width, base_img.height - overlay_img.height),
                      overlay_img)  # Mask it with the original image itself

        new_img.save(output_path)
        output = io.BytesIO()
        new_img.save(output, format="PNG")
        new_img.seek(0)
        return output

    @staticmethod
    def add_image_underneath(base_image_path, overlay_fp, output_fp):
        """
        Add a template image underneath a base image, stretching out the template so that it fits.
        :param base_image_path: Image data, in bytes form or filepath form.
        :param overlay_fp: File-like object or file path for an overlay
        :param output_fp: Destination file path.
        :return:
        """
        base_img = PIL.Image.open(base_image_path)
        overlay_img = PIL.Image.open(overlay_fp)

        # We want to change width to width of new canvas, and scale height
        resize_ratio = min(base_img.width/overlay_img.width, base_img.height/overlay_img.height)

        # Change the overlay_img to the width of the new image; .resize() just returns the image
        overlay_img = overlay_img.resize((int(overlay_img.width * resize_ratio), int(overlay_img.height * resize_ratio)),
                                         PIL.Image.ANTIALIAS)

        # create a new blank canvas
        new_img = PIL.Image.new("RGB", (base_img.width, base_img.height + overlay_img.height))

        # Add images to it
        new_img.paste(base_img)
        new_img.paste(overlay_img, (0, base_img.height))  # Top corner at bottom corner

        # Output to a file
        new_img.save(output_fp)
        output = io.BytesIO()
        new_img.save(output, format="PNG")
        new_img.seek(0)
        return output

    @staticmethod
    def add_more_jpeg(base_path, output_path, quality=5):
        base_img = PIL.Image.open(base_path)
        base_img.save(base_path, "JPEG", quality=quality)
        base_img.save(output_path, "JPEG", quality=quality)
        if isinstance(base_path, io.BytesIO):
            base_path.seek(0)

    @staticmethod
    async def download_image_to_bytes(url):
        img_bytes = io.BytesIO()
        with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                while True:
                    chunk = await resp.content.read(10)
                    if not chunk:
                        break
                    img_bytes.write(chunk)
        img_bytes.seek(0)
        return img_bytes

    @staticmethod
    async def download_image_to_file(url, dest_path):
        with open(dest_path, "wb") as outfile:
            with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    while True:
                        chunk = await resp.content.read(10)
                        if not chunk:
                            break
                        outfile.write(chunk)

            outfile.seek(0)

    async def add_jpeg(self, ctx, image_url):
        image_url = await self._get_image_url(ctx, image_url)

        dest_path = "{}.png".format(ctx.command.name)
        async with ctx.typing():
            base_bytes = await self.download_image_to_bytes(image_url)
            self.add_more_jpeg(base_bytes, quality=randint(1, 2))
        await ctx.send(file=discord.File(base_bytes, dest_path))

    async def add_image_template(self, ctx, image_url, template):

        image_url = await self._get_image_url(ctx, image_url)

        dest_path = "{}.png".format(ctx.command.name)
        async with ctx.typing():
            base_bytes = await self.download_image_to_bytes(image_url)
            self.add_image_underneath(base_bytes, template, dest_path)

        await ctx.send(file=discord.File(dest_path))
        remove(dest_path)

    @staticmethod
    def _get_avatar_url(user):
        """Pull the right avatar url type, since magick breaks down with .webp"""
        if user.avatar.startswith("a"):
            url = user.avatar_url_as(format="gif")
        else:
            url = user.avatar_url_as(format="png")

        return url.split("?")[0]  # we really don't care about the size, chop it off

    @staticmethod
    async def _get_image_url(ctx, image_url=None, ignore_own_avatar=False):
        if image_url == "^":
            async for msg in ctx.message.channel.history(limit=1, before=ctx.message):
                try:
                    return msg.attachments[0].url
                except IndexError:
                    image_url = utils.check_urls(msg.clean_content)
                    if not image_url:
                        if ignore_own_avatar:
                            raise RuntimeError("Previous message contains no actionable data.")
                        else:
                            return Manips._get_avatar_url(ctx.message.author)
                    else:
                        return image_url
        elif ctx.message.mentions:
            return Manips._get_avatar_url(ctx.message.mentions[0])
        elif image_url is not None:
            return image_url.strip("<>")
        elif ctx.message.attachments:
            return ctx.message.attachments[0].url
        else:
            return Manips._get_avatar_url(ctx.message.author) if not ignore_own_avatar else None

    @staticmethod
    def _list_templates():
        output = "Templates: \n%s"
        template_names = []
        for name in glob("templates/*"):
            name = os.path.split(name)
            name = str(name).rsplit(".")[0]
            template_names.append(name)

        return output % str(template_names).strip("[]")

    @checks.sudo()
    @commands.command(aliases=["manip_flags", "manip_config"])
    async def set_manip_flag(self, ctx, key: str, value: str):
        if key in self.VALID_PARAMS:
            self.config.hset("config:manips:params", key, value)
            self._parameter_cache[key] = value
            await ctx.send("\N{OK HAND SIGN}")
        else:
            await ctx.send("Invalid key.")

    @checks.sudo()
    @commands.command()
    async def think_mask(self, ctx, image_url: str):
        image_url = await self._get_image_url(ctx, image_url, ignore_own_avatar=True)
        img = await self.download_image_to_bytes(await self._get_image_url(ctx, image_url))
        async with ctx.typing():
            outfile = gif_overlay.processImage(img, "templates/thinking_small.png")
        await ctx.send(file=discord.File(outfile))
        remove(outfile)

    @checks.sudo()
    @commands.command(hidden=True)
    async def template(self, ctx, name: str, image_url: str=None):
        if name in ["help", "list"]:
            await ctx.send(self._list_templates())
            return
        try:
            await self.add_image_template(ctx, image_url, "templates/{}.png".format(name))
        except FileNotFoundError:
            raise commands.BadArgument("Template not found. Use !{} help for templates.".format(ctx.command.name))

    @checks.sudo()
    @commands.command()
    async def add_template(self, ctx, name: str, image_url: str=None):
        fp = "templates/{}.png".format(name)
        image_url = await self._get_image_url(ctx, image_url, ignore_own_avatar=True)
        # Overlays should only ever be PNGs, let's make sure
        await self.download_image_to_file(image_url, fp)
        if "png" not in PIL.Image.open(fp).format.lower():
            remove(fp)
            await ctx.send("File-type must be a png.")
        else:
            await ctx.send("Successfully added new template.")

    @commands.command()
    async def angery(self, ctx, *, image_url: str=None):
        rate_limits.MemeCommand.check_rate_limit(ctx, cooldown_group="heavymanips",
                                                 priority_blacklist=self.blacklisted_channels)

        async with ctx.typing():
            image_url = await self._get_image_url(ctx, image_url)
            await self.download_image_to_file(image_url, "lens_flare_temp.png")

            self.add_lens_flare_to_eyes("lens_flare_temp.png", "angery.png")
        await ctx.send(file=discord.File("angery.png"))
        remove("angery.png")

    @commands.command()
    async def needsmorejpeg(self, ctx, *, image_url: str=None):
        """Do I look like I know what a jpeg is?"""

        rate_limits.MemeCommand.check_rate_limit(ctx, cooldown_group="manips",
                                                 priority_blacklist=self.blacklisted_channels)
        image_url = await self._get_image_url(ctx, image_url)

        async with ctx.typing():
            base_bytes = await self.download_image_to_bytes(image_url)
            self.add_more_jpeg(base_bytes, output_path="more.jpeg", quality=randint(1, 2))
            await ctx.send(file=discord.File("more.jpeg"))
        remove("more.jpeg")

    @checks.is_regular()
    @commands.command(pass_context=True)
    async def hammer(self, ctx, *, image_url: str = None):
        rate_limits.MemeCommand.check_rate_limit(ctx, cooldown_group="manips",
                                                 priority_blacklist=self.blacklisted_channels)

        async with ctx.typing():

            image_url = await self._get_image_url(ctx, image_url)

            image_bytes = await self.download_image_to_bytes(image_url)
            self.add_overlay_template(image_bytes, "templates/overlays/switch_hammer.png", "hammer.png")

        await ctx.send(file=discord.File("hammer.png"))
        remove("hammer.png")

    @checks.is_regular()
    @commands.command()
    async def ifunnify(self, ctx, image_url: str=None):
        rate_limits.MemeCommand.check_rate_limit(ctx, cooldown_group="manips",
                                                 priority_blacklist=self.blacklisted_channels)

        await self.add_image_template(ctx, image_url, "templates/ifunny.png")

    @checks.is_regular()
    @commands.command()
    async def fugify(self, ctx, image_url: str=None):
        rate_limits.MemeCommand.check_rate_limit(ctx, cooldown_group="manips",
                                                 priority_blacklist=self.blacklisted_channels)

        await self.add_image_template(ctx, image_url, "templates/fug.png")

    @commands.command(hidden=True)
    async def hotify(self, ctx, image_url: str=None):
        rate_limits.MemeCommand.check_rate_limit(ctx, cooldown_group="manips")
        await self.add_image_template(ctx, image_url, "templates/thatshot.png")

    @checks.is_regular()
    @commands.command(pass_context=True)
    async def typing(self, ctx, image_url: str=None):
        rate_limits.MemeCommand.check_rate_limit(ctx, cooldown_group="manips",
                                                 priority_blacklist=self.blacklisted_channels)

        await self.add_image_template(ctx, image_url, "templates/typing.png")

    @checks.is_regular()
    @commands.command(hidden=True, enabled=False)
    async def sunglasses(self, ctx, image_url: str=None):
        rate_limits.MemeCommand.check_rate_limit(ctx, cooldown_group="manips",
                                                 priority_blacklist=self.blacklisted_channels)
        image_url = await self._get_image_url(ctx, image_url)
        async with ctx.typing():
            base_bytes = await self.download_image_to_bytes(image_url)
            fp = self.overlay_sunglasses(base_bytes)

            await ctx.send(file=discord.File(fp))

    @checks.is_regular()
    @commands.command()
    async def rad_blur(self, ctx, image_url: str=None):
        rate_limits.MemeCommand.check_rate_limit(ctx, cooldown_group="manips",
                                                 priority_blacklist=self.blacklisted_channels)

        image_url = await self._get_image_url(ctx, image_url)

        async with ctx.typing():
            base_bytes = await self.download_image_to_bytes(image_url)
            with CustomImage(file=base_bytes) as img:
                rotation = int(self._parameter_cache.get("rad_blur_degrees", 10))
                img.radial_blur(rotation)
                f = io.BytesIO()
                img.save(file=f)
                f.seek(0)

        await ctx.send(file=discord.File(f, filename="blur.png"))

    @commands.command()
    async def cas(self, ctx, image_url: str=None):
        rate_limits.MemeCommand.check_rate_limit(ctx, cooldown_group="manips",
                                                 priority_blacklist=self.blacklisted_channels)

        image_url = await self._get_image_url(ctx, image_url)
        async with ctx.typing():
            base_bytes = await self.download_image_to_bytes(image_url)
            with CustomImage(file=base_bytes) as img:
                intensity = int(self._parameter_cache.get("cas_intensity", 4))
                original_width = img.width
                original_height = img.height
                img.liquid_rescale(int(img.width // intensity), int(img.height // intensity))
                img.liquid_rescale(original_width, original_height)
                f = io.BytesIO()
                img.save(file=f)
                f.seek(0)

        await ctx.send(file=discord.File(f, filename="blur.png"))


def setup(bot):
    bot.add_cog(Manips(bot))
