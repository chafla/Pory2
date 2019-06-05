"""image manipulations"""

import math
import os.path

from glob import glob
from io import BytesIO
from os import remove
from random import randint, random
from typing import Union, Tuple
# from uuid import uuid4

import aiohttp
import cv2
import discord
import numpy as np
import PIL
import PIL.Image

from discord import Member
from discord.ext import commands
from discord.ext.commands import Bot, Context

from .utils import rate_limits, checks, rgb_transform, gif_overlay, utils
from .utils.magik import CustomImage


# TODO Make these work with attachments


class Manips:

    VALID_PARAMS = ["rad_blur_degrees", "cas_intensity"]

    def __init__(self, bot: Bot) -> None:
        self.bot = bot

        self.blacklisted_channels = [278043765082423296]
        self._channel_cooldowns = []
        self.config = bot.config
        self._parameter_cache = self.config.hgetall("config:manips:params")

    @staticmethod
    def overlay_sunglasses(base_img_path: Union[str, BytesIO]) -> Union[str, BytesIO]:
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
    def find_eyes(
            image_path: str, base_img_size: int
    ) -> Tuple[Tuple[int, int], Tuple[int, int]]:
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
    def add_lens_flare_to_eyes(
            image_path: Union[str, BytesIO],
            output_fp: Union[str, BytesIO]
    ) -> Union[str, BytesIO]:

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
        output = BytesIO()
        pil_im.save(output, format="PNG")
        output.seek(0)
        return output

    @staticmethod
    def add_overlay_template(
            base_path: Union[str, BytesIO],
            overlay_path: Union[str, BytesIO],
            output_path: Union[str, BytesIO]
    ) -> Union[str, BytesIO]:
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
        output = BytesIO()
        new_img.save(output, format="PNG")
        new_img.seek(0)
        return output

    @staticmethod
    def disintegrate(base_image_fp: Union[str, BytesIO]) -> str:
        """
        I don't feel so good, Mr. Stark...
        :param base_image_fp:
        :return:
        """
        if isinstance(base_image_fp, BytesIO):
            # https://stackoverflow.com/questions/46624449/load-bytesio-image-with-opencv
            file_bytes = np.asarray(bytearray(base_image_fp.read()), dtype=np.uint8)
            cv2_img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
        else:
            cv2_img = cv2.imread(base_image_fp)

        # In order to make sure it works pretty consistently across the board, we'll upscale smaller images to at least
        # be 200x

        # TODO surely a cleaner way to do this

        h, w, _ = cv2_img.shape

        if h < 200:
            h_upscale_ratio = 200 / h
        else:
            h_upscale_ratio = 1

        if w < 200:
            w_upscale_ratio = 200 / w
        else:
            w_upscale_ratio = 1

        scaling_ratio = min(h_upscale_ratio, w_upscale_ratio)

        if scaling_ratio != 1:
            cv2_img = cv2.resize(cv2_img, (0, 0), fx=scaling_ratio, fy=scaling_ratio)
            h, w, _ = cv2_img.shape

        cv2_image_tmp = np.copy(cv2_img)

        chunk_amount = 90  # 75 is sweet spot
        chunk_size = max(int((w + h) // 2 // chunk_amount // 2), 3)

        # This value adjusts the base probability needed for a spot to trigger.
        # The lower the value, the higher
        chunk_move_threshold = 0.5

        # 1 / this value represents the point in the image where it'll start dissolving
        starting_fraction = 5

        # Force a chunk to trigger
        force_chunk_trigger = False

        # The starting value is basically 1/3 of the way into the image
        # This matches more with the general idea of the dusting happening partway through the image,
        # and also saves us time in iterations, cutting off 1/3 of the processing time.
        left_threshold = (w - chunk_size) // starting_fraction if starting_fraction != 0 else 0
        for r in range(h - chunk_size, chunk_size - 1, -chunk_size):
            for c in range(w - chunk_size,
                           left_threshold,
                           -chunk_size):
                # One chunk is chunk_size square

                # Randomly determine if we want to even do anything with this chunk
                # Make it random but biased towards values with a greater x

                adjusted_c = left_threshold
                if (random() + (adjusted_c / w) > chunk_move_threshold) or force_chunk_trigger:
                    # if True:
                    t = 1 / (random() * (c / w) * 0.5)

                    # This offset represents
                    offset_amount = int((w / c))
                    # print("offset amount", offset_amount)
                    # The amount that the chunk has moved
                    vert_offset = r - (chunk_size * offset_amount)
                    horiz_offset = c + (chunk_size * offset_amount)

                    if vert_offset == 0:
                        continue

                    # This bit adds a little bit of extra randomness to the offsets of each chunk.
                    # If this isn't added, all chunks tend to fall along the chunk grid.
                    # It should just need to be a tiny nudge.

                    try:

                        # Beyond just shifting pixels, this part tries to prettify the resulting image slightly.
                        # TODO Consider using an alpha channel or just replacing changed pixels with white
                        # or an average of the background color or smth.

                        target_chunk_offset = int(random() * adjusted_c / 3)
                        # Subtract because we want it to go up, negative y
                        vert_offset -= target_chunk_offset
                        horiz_offset += target_chunk_offset

                        if vert_offset < 0:
                            continue

                        # Swap a target region on the temp image with the target chunk location on the original

                        if (c / w) > 0.5:
                            # Add a slight offset to where the chunks get swapped into.
                            # Otherwise, it gets very crowded.

                            tmp_r = r + int(random() * adjusted_c / 3)
                            tmp_c = c + int(random() * adjusted_c / 3)

                            # set a chunk in the new image to the pixels at the target chunk.
                            cv2_image_tmp[tmp_r: tmp_r + chunk_size - 1, tmp_c:tmp_c + chunk_size - 1, :] = \
                                cv2_img[vert_offset:vert_offset + chunk_size - 1,
                                horiz_offset:horiz_offset + chunk_size - 1,
                                :]  # correct

                    except ValueError:
                        # Tends to happen around threshold values which we don't care about anyway
                        # TODO Removing this try/except might be a point to optimize
                        pass

                    try:
                        target_chunk_offset = int(random() * c / 3)
                        # Subtract because we want it to go up, negative y

                        # Swap the target back first
                        vert_offset -= target_chunk_offset
                        horiz_offset += target_chunk_offset

                        cv2_image_tmp[vert_offset:vert_offset + chunk_size - 1,
                        horiz_offset:horiz_offset + chunk_size - 1, :] = \
                            cv2_img[r:r + chunk_size - 1, c:c + chunk_size - 1, :]  # correct
                        # Try to replace the new point with the value at the old one

                        # Create a new offset value so we don't run into it looking too griddy
                    except ValueError:
                        pass

        # Ideally this would be written out to a BytesIO object but it's hard to get that to work with openCV so
        # this'll have to do
        cv2.imwrite("test_out.png", cv2_image_tmp)

        # cv2.imshow("test_out", cv2_image_tmp)
        # cv2.waitKey(0)

        return "test_out.png"

    @staticmethod
    def add_image_underneath(
            base_image_path: Union[str, BytesIO],
            overlay_fp: Union[str, BytesIO],
            output_fp: Union[str, BytesIO]
    ) -> Union[str, BytesIO]:
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
        overlay_img = overlay_img.resize(
            (
                int(overlay_img.width * resize_ratio),
                int(overlay_img.height * resize_ratio)
            ),
            PIL.Image.ANTIALIAS
        )

        # create a new blank canvas
        new_img = PIL.Image.new("RGB", (base_img.width, base_img.height + overlay_img.height))

        # Add images to it
        new_img.paste(base_img)
        new_img.paste(overlay_img, (0, base_img.height))  # Top corner at bottom corner

        # Output to a file
        new_img.save(output_fp)
        output = BytesIO()
        new_img.save(output, format="PNG")
        new_img.seek(0)
        return output

    @staticmethod
    def add_more_jpeg(
            base_path: Union[str, BytesIO],
            output_path: Union[str, BytesIO],
            quality: int=5
    ) -> None:
        base_img = PIL.Image.open(base_path)
        base_img.save(base_path, "JPEG", quality=quality)
        base_img.save(output_path, "JPEG", quality=quality)
        if isinstance(base_path, BytesIO):
            base_path.seek(0)

    @staticmethod
    async def download_image_to_bytes(url: str) -> BytesIO:
        img_bytes = BytesIO()
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                while True:
                    chunk = await resp.content.read(10)
                    if not chunk:
                        break
                    img_bytes.write(chunk)
        img_bytes.seek(0)
        return img_bytes

    @staticmethod
    async def download_image_to_file(url: str, dest_path: str) -> None:
        with open(dest_path, "wb") as outfile:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    while True:
                        chunk = await resp.content.read(10)
                        if not chunk:
                            break
                        outfile.write(chunk)

            outfile.seek(0)

    async def add_image_template(
            self, ctx: Context, image_url: str, template: str
    ) -> None:

        image_url = await self._get_image_url(ctx, image_url)

        dest_path = "{}.png".format(ctx.command.name)
        async with ctx.typing():
            base_bytes = await self.download_image_to_bytes(image_url)
            self.add_image_underneath(base_bytes, template, dest_path)

        await ctx.send(file=discord.File(dest_path))
        remove(dest_path)

    @staticmethod
    def _get_avatar_url(user: Member) -> str:
        """Pull the right avatar url type, since magick breaks down with .webp"""
        # if user.avatar.startswith("a"):
        #     url = user.avatar_url_as(format="gif")
        # else:
        url = user.avatar_url_as(format="png")

        return url.split("?")[0]  # we really don't care about the size, chop it off

    @staticmethod
    async def _get_image_url(
            ctx: Context, image_url: str=None, ignore_own_avatar: bool=False
    ) -> str:
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
    def _list_templates() -> str:
        output = "Templates: \n%s"
        template_names = []
        for name in glob("templates/*"):
            name = os.path.split(name)
            name = str(name).rsplit(".")[0]
            template_names.append(name)

        return output % str(template_names).strip("[]")

    @checks.sudo()
    @commands.command(aliases=["manip_flags", "manip_config"])
    async def set_manip_flag(self, ctx: Context, key: str, value: str) -> None:
        if key in self.VALID_PARAMS:
            self.config.hset("config:manips:params", key, value)
            self._parameter_cache[key] = value
            await ctx.send("\N{OK HAND SIGN}")
        else:
            await ctx.send("Invalid key.")

    @checks.sudo()
    @commands.command()
    async def think_mask(self, ctx: Context, image_url: str) -> None:
        image_url = await self._get_image_url(ctx, image_url, ignore_own_avatar=True)
        img = await self.download_image_to_bytes(await self._get_image_url(ctx, image_url))
        async with ctx.typing():
            outfile = gif_overlay.processImage(img, "templates/thinking_small.png")
        await ctx.send(file=discord.File(outfile))
        remove(outfile)

    @checks.sudo()
    @commands.command()
    async def template(
            self, ctx: Context, name: str, image_url: str=None
    ) -> None:
        if name in ["help", "list"]:
            await ctx.send(self._list_templates())
            return
        try:
            await self.add_image_template(ctx, image_url, "templates/{}.png".format(name))
        except FileNotFoundError:
            raise commands.BadArgument("Template not found. Use !{} help for templates.".format(ctx.command.name))

    @checks.sudo()
    @commands.command()
    async def add_template(
            self, ctx: Context, name: str, image_url: str=None
    ) -> None:
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
    async def angery(self, ctx: Context, *, image_url: str=None) -> None:
        rate_limits.MemeCommand.check_rate_limit(
            ctx, cooldown_group="heavymanips",
            priority_blacklist=self.blacklisted_channels
        )

        async with ctx.typing():
            image_url = await self._get_image_url(ctx, image_url)
            await self.download_image_to_file(image_url, "lens_flare_temp.png")

            self.add_lens_flare_to_eyes("lens_flare_temp.png", "angery.png")
        await ctx.send(file=discord.File("angery.png"))
        remove("angery.png")

    @commands.command()
    async def needsmorejpeg(self, ctx: Context, *, image_url: str=None) -> None:
        """Do I look like I know what a jpeg is?"""

        rate_limits.MemeCommand.check_rate_limit(
            ctx, cooldown_group="manips",
            priority_blacklist=self.blacklisted_channels
        )
        image_url = await self._get_image_url(ctx, image_url)

        async with ctx.typing():
            base_bytes = await self.download_image_to_bytes(image_url)
            self.add_more_jpeg(base_bytes, output_path="more.jpeg", quality=randint(1, 2))
            await ctx.send(file=discord.File("more.jpeg"))
        remove("more.jpeg")

    @checks.is_regular()
    @commands.command()
    async def hammer(self, ctx: Context, *, image_url: str = None) -> None:
        rate_limits.MemeCommand.check_rate_limit(
            ctx, cooldown_group="manips",
            priority_blacklist=self.blacklisted_channels
        )

        async with ctx.typing():

            image_url = await self._get_image_url(ctx, image_url)

            image_bytes = await self.download_image_to_bytes(image_url)
            self.add_overlay_template(image_bytes, "templates/overlays/switch_hammer.png", "hammer.png")

        await ctx.send(file=discord.File("hammer.png"))
        remove("hammer.png")

    @checks.is_regular()
    @commands.command()
    async def ifunnify(self, ctx: Context, image_url: str=None) -> None:
        rate_limits.MemeCommand.check_rate_limit(
            ctx, cooldown_group="manips",
            priority_blacklist=self.blacklisted_channels
        )

        await self.add_image_template(ctx, image_url, "templates/ifunny.png")

    @checks.is_regular()
    @commands.command()
    async def fugify(self, ctx: Context, image_url: str=None) -> None:
        rate_limits.MemeCommand.check_rate_limit(
            ctx, cooldown_group="manips",
            priority_blacklist=self.blacklisted_channels
        )

        await self.add_image_template(ctx, image_url, "templates/fug.png")

    @commands.command(hidden=True)
    async def hotify(self, ctx: Context, image_url: str=None) -> None:
        rate_limits.MemeCommand.check_rate_limit(ctx, cooldown_group="manips")
        await self.add_image_template(ctx, image_url, "templates/thatshot.png")

    @checks.is_regular()
    @commands.command()
    async def typing(self, ctx: Context, image_url: str=None) -> None:
        rate_limits.MemeCommand.check_rate_limit(
            ctx, cooldown_group="manips",
            priority_blacklist=self.blacklisted_channels
        )

        await self.add_image_template(ctx, image_url, "templates/typing.png")

    @checks.is_regular()
    @commands.command(hidden=True, enabled=False)
    async def sunglasses(self, ctx: Context, image_url: str=None) -> None:
        rate_limits.MemeCommand.check_rate_limit(
            ctx, cooldown_group="manips",
            priority_blacklist=self.blacklisted_channels
        )
        image_url = await self._get_image_url(ctx, image_url)
        async with ctx.typing():
            base_bytes = await self.download_image_to_bytes(image_url)
            fp = self.overlay_sunglasses(base_bytes)

            await ctx.send(file=discord.File(fp))

    @checks.is_regular()
    @commands.command()
    async def dissolve(self, ctx: Context, image_url: str=None) -> None:
        image_url = await self._get_image_url(ctx, image_url)
        async with ctx.typing():
            base_bytes = await self.download_image_to_bytes(image_url)
            fp = self.disintegrate(base_bytes)

            await ctx.send(file=discord.File(fp))

    @checks.is_regular()
    @commands.command()
    async def rad_blur(self, ctx: Context, image_url: str=None) -> None:
        rate_limits.MemeCommand.check_rate_limit(
            ctx, cooldown_group="manips",
            priority_blacklist=self.blacklisted_channels
        )

        image_url = await self._get_image_url(ctx, image_url)

        async with ctx.typing():
            base_bytes = await self.download_image_to_bytes(image_url)
            with CustomImage(file=base_bytes) as img:
                rotation = int(self._parameter_cache.get("rad_blur_degrees", 10))
                img.radial_blur(rotation)
                f = BytesIO()
                img.save(file=f)
                f.seek(0)

        await ctx.send(file=discord.File(f, filename="blur.png"))

    @commands.command()
    async def cas(self, ctx: Context, image_url: str=None) -> None:
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
                f = BytesIO()
                img.save(file=f)
                f.seek(0)

        await ctx.send(file=discord.File(f, filename="blur.png"))


def setup(bot: Bot) -> None:
    bot.add_cog(Manips(bot))
