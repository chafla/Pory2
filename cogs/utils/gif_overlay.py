# Let's pull a gif apart, and for each and every frame mask the thinking face over it

from io import BytesIO
import os
import uuid

from typing import Dict, Union, Tuple, Generator

import imageio
import PIL
from PIL import Image

# From https://gist.github.com/almost/d2832d0998ad9dfec2cacef934e7d247


def analyseImage(im: Image.Image) -> Dict[str, Union[Tuple[int, int], str]]:
    """
    Pre-process pass over the image to determine the mode (full or additive).
    Necessary as assessing single frames isn't reliable. Need to know the mode
    before processing all frames.
    """
    results = {
        'size': im.size,
        'mode': 'full',
    }
    try:
        while True:
            if im.tile:
                tile = im.tile[0]
                update_region = tile[1]
                update_region_dimensions = update_region[2:]
                if update_region_dimensions != im.size:
                    results['mode'] = 'partial'
                    break
            im.seek(im.tell() + 1)
    except EOFError:
        pass
    im.seek(0)
    return results


def getFrames(
        im: Image.Image, mask: Union[str, BytesIO]
) -> Generator[Image.Image, None, None]:
    """Iterate the GIF, extracting each frame."""

    mode = analyseImage(im)['mode']

    p = im.getpalette()
    last_frame = im.convert('RGBA')
    cutout = Image.open(mask).convert("RGBA")
    # outline = Image.open("templates/thinking_mask.png")

    try:
        while True:
            """
            If the GIF uses local colour tables, each frame will have its own palette.
            If not, we need to apply the global palette to the new frame.
            """
            if not im.getpalette():
                im.putpalette(p)

            new_frame = Image.new('RGBA', im.size)

            """
            Is this file a "partial"-mode GIF where frames update a region of a different size to the entire image?
            If so, we need to construct the new frame by pasting it on top of the preceding frames.
            """
            if mode == 'partial':
                new_frame.paste(last_frame)

            new_frame.paste(im, (0, 0), im.convert('RGBA'))
            new_frame_masked = Image.new("RGBA", cutout.size)
            resize_ratio = max(cutout.width / im.width, cutout.height / im.height)  # May be reversed

            # Change the overlay_img to the width of the new image; .resize() just returns the image
            new_frame = new_frame.resize(
                (int(new_frame.width * resize_ratio), int(new_frame.height * resize_ratio)),
                PIL.Image.ANTIALIAS)

            new_frame_masked.paste(new_frame, ((new_frame_masked.size[0] - new_frame.size[0]) // 2, 0))
            new_frame_masked.paste(cutout, (0, 0), cutout)

            yield new_frame_masked

            last_frame = new_frame_masked
            im.seek(im.tell() + 1)
    except EOFError:
        pass


def processImage(
        path: Union[str, BytesIO], mask: Union[str, BytesIO], verbose: bool=False
) -> str:
    image_paths = []
    im = Image.open(path)
    if "gif" not in im.format.lower():
        raise RuntimeError("Image format must be a gif")

    try:
        dur_ms = im.duration
    except AttributeError:
        dur_ms = 50

    for (i, frame) in enumerate(getFrames(im, mask)):
        if verbose:
            print("saving %s frame %d, %s %s" % (path, i, im.size, im.tile))
        new_img = BytesIO()
        frame.save(new_img, 'PNG')
        new_img.seek(0)
        image_paths.append(new_img)

    imgs = []
    for filename in image_paths:
        imgs.append(imageio.imread(filename))
    gif_output_path = '{}.gif'.format(uuid.uuid4())
    imageio.mimsave(gif_output_path, imgs, duration=dur_ms / 1000)
    for filename in image_paths:
        if not isinstance(filename, BytesIO):
            os.remove(filename)

    if verbose:
        print("gif saved to {}".format(gif_output_path))

    return gif_output_path


def main() -> None:
    processImage('OH_SHIT_GOD_NO.gif', "templates/thinking_small.png")


if __name__ == "__main__":
    main()
