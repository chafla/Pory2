"""
Utilities for reading/parsing psmd rescue codes.

Big props to /u/ZappedAmpharos for discovering the difference between US/EU rescue codes,
and /u/DeleeciousCheeps for building a nice reference version in js.

Region conversion was cracked by EddyK28

//================================================================================
//  MIT License
//
//  Copyright (c) 2020 EddyK28
//
//  Permission is hereby granted, free of charge, to any person obtaining a copy
//  of this software and associated documentation files (the "Software"), to deal
//  in the Software without restriction, including without limitation the rights
//  to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
//  copies of the Software, and to permit persons to whom the Software is
//  furnished to do so, subject to the following conditions:
//
//  The above copyright notice and this permission notice shall be included in all
//  copies or substantial portions of the Software.
//
//  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
//  IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
//  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
//  AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
//  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
//  OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
//  SOFTWARE.
//================================================================================
"""


from typing import Optional, Tuple, Union

import aiohttp

from cogs.utils.utils import download_image
from io import BytesIO
from PIL import Image
import qrcode
from uuid import uuid4
import os
import logging
from cogs.utils.qr.qr import read_qr


log = logging.getLogger()

api_read_url = "https://api.qrserver.com/v1/read-qr-code/?file"
api_create_url = "https://api.qrserver.com/v1/create-qr-code/"


create_params = {
    "size": "300x300",
    "charset-source": "UTF-8",
    "charset-target": "ISO-8859-1",
    "ecc": "M"
}

index_swaps = {
    2: 49,
    3: 12,
    4: 36,
    8: 26,
    15: 59,
    19: 41,
    29: 31
}

header_const = [0x00, 0x19, 0x59, 0x22, 0x33, 0x12, 0x04, 0x11]


def _create_lookup_table() -> list:
    """
    Create a lookup table which will end up used in the hash function
    """

    table = []

    ix = 0

    while ix < 0x100:
        cur_entry = ix
        for i in range(4):
            if cur_entry & 1:
                tmp = (cur_entry >> 1) ^ 0xEDB88320
            else:
                tmp = (cur_entry >> 1)

            if tmp & 1:
                cur_entry = (tmp >> 1) ^ 0xEDB88320
            else:
                cur_entry = tmp >> 1

        table.append(cur_entry)
        ix += 1

    return table


lookup_table = _create_lookup_table()


def crc_hash(data: list, hash_val: int, lookup_table: list) -> int:
    data_len = len(data)

    if data_len > 0:
        data_ix = 0
        if data_len & 1:
            data_ix += 1  # TODO Does this come before or after the following call?
            v8 = data[data_ix]
            hash_val = lookup_table[(v8 ^ hash_val) & 0xFF] ^ (hash_val >> 8)

        i = data_len >> 1
        while i != 0:
            i -= 1
            byte_1 = (data[data_ix] ^ hash_val) & 0xFF
            byte_2 = data[data_ix + 1]
            data_ix += 2
            v12 = lookup_table[byte_1] ^ (hash_val >> 8)
            hash_val = lookup_table[(byte_2 ^ v12) & 0xFF] ^ (v12 >> 8)

    return ~hash_val


def convert_url(base_url: str) -> str:
    """
    Attempt to shrink the image filesize down if possible.

    This means a shorter download (and processing) time, and also
    tends to improve recognition of larger images.
    """

    if "media.discordapp.net" in base_url:
        return base_url + "?width=300&height=300"
    elif "cdn.discordapp.net" in base_url:
        return base_url
    elif "imgur" in base_url:

        image_url_imgur_parts = base_url.split(".")

        if image_url_imgur_parts[-2][-1] in ["s", "b", "t", "m", "h"]:
            image_url_imgur_parts[-2] = image_url_imgur_parts[-2][:-1] + "l"
        else:
            image_url_imgur_parts[-2] = image_url_imgur_parts[-2] + "l"

        return ".".join(image_url_imgur_parts)
    else:
        return base_url


def convert_rescue_code(code: str) -> str:
    """
    Convert a rescue code between regions.
    Should be a simple operation regardless
    :param code: rescue code
    :return: Rescue code converted to the other region (US->EU or EU->US).
    """

    code_ls = list(code)

    # Swap values at indices
    for src, dest in index_swaps.items():
        tmp = code_ls[src]
        code_ls[src] = code_ls[dest]
        code_ls[dest] = tmp

    return "".join(code_ls)


async def get_qr_code_bytes(dest_fp: Union[str, BytesIO]) -> Optional[bytes]:
    """
    Try to get a qr code with just the zxing library
    """
    using_temp = False
    temp_fp = ""

    if isinstance(dest_fp, BytesIO):
        temp_fp = "tmp{}.png".format(uuid4())
        with open(temp_fp, "wb") as f:
            f.write(dest_fp.read())
        input_fp = temp_fp
        using_temp = True
    else:
        input_fp = dest_fp
    try:
        ret_bytes = read_qr(input_fp)

        if not ret_bytes:
            return await get_qr_code_bytes_api(dest_fp)
        else:
            return ret_bytes
    finally:
        if using_temp:
            os.remove(temp_fp)


async def get_qr_code_bytes_api(dest_fp: Union[str, BytesIO]) -> Optional[bytes]:
    # POST request to upload the qr code to it
    async with aiohttp.ClientSession() as session:

        form = aiohttp.FormData()

        form.add_field("file", dest_fp, content_type="multipart/form-data", filename="img.png")

        # payload.set_content_disposition("form-data", file="file", filename="file.png", name="file", type="file")
        async with session.post(api_read_url, data=form) as resp:
            if resp.status == 200:
                out_json = await resp.json()
                # Kind of a nasty call but it's guaranteed
                out = out_json[0]["symbol"][0]["data"]
                if not out:
                    print("No data found.")
                    return None

                # Rescue codes are encoded as ISO-8859-1
                # if you start seeing stray 0xC3 and 0xC2 appearing in the character set,
                out_bytes = bytes(out, encoding="ISO-8859-1")
                return out_bytes

            else:
                log.error(await resp.content.read())

# Avert your eyes!
# This hack is due to the fact that zxing is a pain and a half to install on windows!
# I'll probably try to work around it later.
#
# if not USE_API:
#     get_qr_code = get_qr_code_bytes
# else:
#     get_qr_code = get_qr_code_bytes_api


async def convert_qr_code_region(data: bytes) -> bytes:
    """
    Convert the qr code from one region into that from another
    """

    # if isinstance(data, str):
    #     data = data.encode()  # Necessary fallback if we get bytes
    #
    # print(data)

    # Things that I think we'll have to do:
    # swap the region bit
    # find a nice way to swap byte regions

    # swap region bit
    region_byte = data[0x8]
    region_flag = 1 if region_byte == 2 else 1

    # Split the bytes up
    # We're going to take the lazy method of splitting the code up into its components,
    # swapping the corresponding parts of the code,
    # and then rebuilding the bytes by re-encoding the bytes.

    # Find the symbols
    symbols = []
    i = 0x20
    while len(symbols) < 80:
        if data[i] == 0xCE and data[i + 1] == 0x25:
            symbols.append(b"\xCE\x25")
        else:
            symbols.append(bytes([data[i]]))

        i += 2

    # Swap values at indices
    for src, dest in index_swaps.items():
        tmp = symbols[src]
        symbols[src] = symbols[dest]
        symbols[dest] = tmp

    # Go back through and insert nulls after each character that isn't a circle
    # I know this isn't the most efficient way to go about it but he need to have swapped before adding nulls
    # (there is no null byte after circles, it runs right up next to the following char)
    n_symbols = len(symbols)

    full_code = []

    full_code_int = []  # code as int for use in the hash function

    for i in range(n_symbols):
        full_code.append(symbols[i])
        if symbols[i] != b"\xCE\x25":  # Full-circles aren't followed by a null
            full_code_int.append(int.from_bytes(symbols[i], "little"))
            full_code_int.append(0)

            full_code.append(b"\00")
        else:
            full_code_int += [0xCE, 0x25]

    mail_hash = crc_hash(full_code_int, 0xFFFFFFFF, lookup_table)

    code_portion = b""

    # Have to join like this because "".join() removes null bytes
    for sym in full_code:
        code_portion = code_portion + sym

    # Put the other part of the header together here

    header = bytes(header_const) + bytes([region_flag, 0x04, 0x00, 0x00, 0xA0, 0x00])
    header += b"\x00" * 10  # We don't know what these mean, nor do we care

    for i in range(4):
        # Append each byte from the hash
        header += bytes([(mail_hash & (0xFF << (i * 8))) >> i * 8])

    header += bytes([0, 0, 0, 0])

    # header = [bytes([i]) for i in header]

    # Insert the region byte here
    # output_data = data[:0x8] + bytes([region_flag]) + data[0x9:0x20] + code_portion
    output_data = header + code_portion

    return output_data


async def convert_qr_code(url: str):
    """
    Download a qr code from a url, extract the data from it, and
    change the region from EU/US and vice versa.

    If the conversion is successful, returns a BytesIO object, a string representing the
    region that the code was converted to, and the rescue code
    """

    url = convert_url(url)

    # Download image from url

    img_bytes = BytesIO()

    await download_image(url, img_bytes)

    # Open and compress the qr code here
    img = Image.open(img_bytes)
    img = img.resize((400, 400))
    img.save(img_bytes, format="PNG")
    img_bytes.seek(0)

    orig_bytes = await get_qr_code_bytes(img_bytes)

    if not orig_bytes:
        return

    conv_bytes = await convert_qr_code_region(orig_bytes)

    conv_region_flag = conv_bytes[0x08]

    region = "na" if conv_region_flag is 1 else "eu"

    img_out = BytesIO()

    qr_out = qrcode.make(conv_bytes)
    qr_out.save(img_out, format="PNG")

    img_out.seek(0)

    return img_out, region


def rescue_code_from_bytes(raw_bytes: bytes) -> str:
    """
    Get a string representation of the rescue code from bytes.
    """
    symbols = []
    i = 0x20
    while len(symbols) < 80:
        if raw_bytes[i] == 0xCE and raw_bytes[i + 1] == 0x25:
            symbols.append("@")
        else:
            symbols.append(chr(raw_bytes[i]))

        i += 2

    return "".join(symbols)


async def read_qr_code(url: str) -> Optional[Tuple[str, str]]:
    """
    Read in a qr code and fetch the rescue code.
    :param url: url to fetch the qr code from
    :return: Tuple of
    (String of the rescue code, encoded as per the original code,
    region decoded from code as eu or na)
    """

    url = convert_url(url)

    # Download image from url

    img_bytes = BytesIO()

    await download_image(url, img_bytes)

    # Open and compress the qr code here
    img = Image.open(img_bytes)
    img = img.resize((400, 400))
    img.save(img_bytes, format="PNG")
    img_bytes.seek(0)

    out_bytes = await get_qr_code_bytes(img_bytes)

    if not out_bytes:
        return None

    # Alright, take three.
    # When encoded as ISO-8859-1, the rescue codes always start at 0x20.
    # I was previously encoding as UTF-8, which would incorrectly encode
    # some characters with an extra 0xC3 before them.

    rescue_code = rescue_code_from_bytes(out_bytes)
    # rescue_code_bytes = out_bytes[ix:]

    # Little curiosity:
    # This byte (0x8) is a flag for the region.
    # 0x1 = NA, 0x2 = EU
    region_byte = out_bytes[0x8]

    region = "na" if region_byte == 1 else "eu"

    return rescue_code, region


if __name__ == '__main__':
    print(read_qr_code("https://i.imgur.com/eJEBNg4.jpg"))
