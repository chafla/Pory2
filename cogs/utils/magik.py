"""Do some image manips"""
import ctypes
from wand.image import Image
from wand.api import library

# Thanks https://stackoverflow.com/questions/38541457/how-to-motion-blur-with-imagemagick-using-wand

library.MagickRotationalBlurImage.argtypes = (ctypes.c_void_p,
                                              ctypes.c_double)


class CustomImage(Image):
    def radial_blur(self, angle=0.0):
        library.MagickRotationalBlurImage(self.wand, angle)
