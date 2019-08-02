import time
import logging
import os
from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support.expected_conditions import NoSuchElementException
from thread_defence.captcha_handler import CaptchaHandler

LOGGER = logging.getLogger(__name__)
__location__ = os.path.realpath(os.path.join(os.getcwd(), os.path.dirname(__file__)))

class ThreatDefenceHandler:

    def __init__(self, cookies=None):
        if cookies is None:
            cookies = {}
        self.threat_defence = 'threat_defence.php'
        self.options = Options()
        self.options.headless = True
        self.driver = webdriver.Firefox(options=self.options, executable_path=os.path.join(__location__,'geckodriver'))
        self.tries = 0
        self.captcha_handler = CaptchaHandler()
        self.cookies = cookies

    def quit(self):
        self.driver.quit()

    def get_cookies(self, url):
        self.driver.get(url)
        for key, value in self.cookies.items():
            self.driver.add_cookie({"name": key, "value": value})
        LOGGER.info("Checking if thread defence is active.")
        self.driver.get(url)
        if self.threat_defence in self.driver.current_url:
            if self.cookies != {}:
                LOGGER.info("Cookie no longer valid, getting new one")
            LOGGER.info('Threat defense triggered for {0}'.format(self.driver.current_url))
            LOGGER.info('Redirected to: {0}'.format(self.driver.current_url))
            cookies = self.bypass_threat_defense(self.driver.current_url)
            self.driver.close()
            return {c["name"]: c["value"] for c in cookies if c["name"]!=''}  # With cookies of solved CAPTCHA session
        else:
            self.driver.close()
            LOGGER.info("Cookies still valid")
            return self.cookies

    def bypass_threat_defense(self, url):
        LOGGER.info('Number of tries: #{0}'.format(self.tries))
        self.driver.get(url)
        # While loop to decide whether we are on a browser detection (redirect) page or a captcha page
        while self.tries <= 5:  # Current limit is 5 giving pytesseract % of success
            LOGGER.info('Waiting for browser detection')
            time.sleep(10)
            try:
                self.cookies = self.find_solve_submit_captcha()
                break
            except NoSuchElementException:
                LOGGER.info('No CAPTCHA found in page')
            try:
                self.redirect_retry()
                break
            except NoSuchElementException:
                LOGGER.info('No Link in page either. EXITING')
                break
        # If the solution was wrong and we are prompt with another try call method again
        if self.threat_defence in self.driver.current_url:
            self.tries += 1
            LOGGER.info('CAPTCHA solution was wrong. Trying again')
            self.bypass_threat_defense(self.driver.current_url)
        if self.cookies:
            return self.cookies
        exit('Something went wrong')

    # Press retry link if reached a redirect page without captcha
    def redirect_retry(self):
        LOGGER.info('Looking for `retry` link in page')
        link = self.driver.find_element_by_partial_link_text('Click')
        LOGGER.info('Retrying to get CAPTCHA page')
        self.tries += 1
        self.bypass_threat_defense(link.get_attribute('href'))

    def find_solve_submit_captcha(self):
        LOGGER.info('Looking for CAPTCHA image in page')
        # Find
        captcha = self.driver.find_element_by_xpath("//img[contains(@src, 'captcha')]")
        LOGGER.info('Found CAPTCHA image')
        # Solve
        solved_captcha = self.captcha_handler.get_captcha(element=captcha, driver=self.driver)
        LOGGER.info('CAPTCHA solved: {0}'.format(solved_captcha))
        input_field = self.driver.find_element_by_id('solve_string')
        input_field.send_keys(solved_captcha)
        LOGGER.info('Submitting solution')
        # Submit
        self.driver.find_element_by_id('button_submit').click()
        return self.driver.get_cookies()
