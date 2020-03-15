"""
Thanks go out to LALO for working this out!

Worth noting that this expects core-3.4.0.jar and javase-3.4.0.jar to be in the path_ext folder.
"""

import subprocess
# import qrcodegen
import re
from typing import Optional
from os import path
from sys import platform

if platform == "win32":
    sep = ";"
else:
    sep = ":"


path_ext = "resources"


def read_qr(fp: str) -> Optional[bytes]:
    # TODO Replace these file calls with a listdir
    core = path.join(path_ext, "core-3.4.0.jar")
    se = path.join(path_ext, "javase-3.4.0.jar")
    cls_file = path.join(path_ext, "QRBytes")
    qr_bytes = subprocess.run(["java", "-cp", sep.join([core, se, path_ext, "."]),
                              "QRBytes", fp], stdout=subprocess.PIPE, stdin=subprocess.PIPE)

    if qr_bytes.stderr:
        print("Error: ", qr_bytes.stderr)
        return None
    hexdata = qr_bytes.stdout.split()[0].decode("UTF-8")
    hexdata = re.sub("^.{3}", "", hexdata)
    hexdata = re.sub("0(EC11)*$", "", hexdata)
    bindata = bytes.fromhex(hexdata)

    return bindata
# text = bindata.decode("UTF-16")
# seg = [qrcodegen.QrSegment.make_bytes(bindata)]
# qr = qrcodegen.QrCode.encode_segments(seg, qrcodegen.QrCode.Ecc.LOW, minversion=9, mask=3, boostecl=False)
# print(text)
