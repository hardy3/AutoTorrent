import os
import pytesseract
import logging
from PIL import Image

LOGGER = logging.getLogger(__name__)
__location__ = os.path.realpath(os.path.join(os.getcwd(), os.path.dirname(__file__)))

# Get CAPTCHA image & extract text
class CaptchaHandler:

    def __init__(self):
        self.filename = 'solved_captcha.png'

    def get_captcha(self, driver, element):
        LOGGER.info("Getting captcha")
        # now that we have the preliminary stuff out of the way time to get that image :D
        location = element.location
        size = element.size
        # saves screenshot of entire page
        driver.save_screenshot(os.path.join(__location__,self.filename))

        # uses PIL library to open image in memory
        image = Image.open(os.path.join(__location__,self.filename))

        left = location['x']
        top = location['y']
        right = location['x'] + size['width']
        bottom = location['y'] + size['height']

        image = image.crop((left, top, right, bottom))  # defines crop points
        image.save(os.path.join(__location__,self.filename), 'png')  # saves new cropped image
        return self.solve_captcha(os.path.join(__location__,self.filename))

    @staticmethod
    def solve_captcha(img_path):
        try:
            LOGGER.info("Solving captcha")
            solution = pytesseract.image_to_string(Image.open(img_path))
            os.remove(img_path)  # Remove the file after solving
            return solution
        except FileNotFoundError:
            return
