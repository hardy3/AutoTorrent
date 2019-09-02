#!/usr/bin/python3
import os
import pprint

import arrow
import requests
import bs4
import feedparser
import re
import json
import pickle
import logging.config
from thread_defence.thread_defence_handler import ThreatDefenceHandler

logging.config.dictConfig(config={
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'default': {
            'format': '%(asctime)s: %(module)22s->%(funcName)-26s - [%(levelname)5s] - %(message)s',
            'datefmt': '[%d-%m-%Y | %H:%M:%S]'
        }
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'default',
            'level': 'DEBUG',
        },
        'file': {
            'class': 'logging.handlers.TimedRotatingFileHandler',
            'filename': '/var/log/auto_torrent/auto_torrent.log',
            #'filename': 'auto_torrent.log',
            # 'mode': 'w',
            'formatter': 'default',
            'when': 'midnight',
            'backupCount': 10,
            'level': 'DEBUG'
        },
    },
    'root': {
        'handlers': ['file', 'console'],
        'level': 'INFO',
    },
})

__location__ = os.path.realpath(os.path.join(os.getcwd(), os.path.dirname(__file__)))
pickle_file_name = os.path.join(__location__,'torrents.pickle')

LOGGER = logging.getLogger(__name__)


class PogCalendar:

    def __init__(self):
        self._month_releases = []

    def parse(self, html_data):
        soup_obj = bs4.BeautifulSoup(html_data.text, features="lxml")
        for div_day in soup_obj.find_all('div', {"class": {'today', 'day'}}):
            date = arrow.get(div_day.select('a')[0].get('title'), "dddd Do MMMM YYYY").date()
            day_releases = {'day': date, 'episodes': []}
            for div_ep in div_day.select('div'):
                series_ref = div_ep.select('input')[0].get('value').split('-')[0]
                series_name, ep_num, ep_title, series_provider = [line.strip() for line in
                                                                  div_ep.text.strip().split("\n")]
                series_provider = series_provider.split('-')[0].strip()
                episode = {'name': series_name, 'number': ep_num, 'provider': series_provider, 'series_ref': series_ref}
                day_releases['episodes'].append(episode)
            self._month_releases.append(day_releases)

    def get_today_releases(self) -> list:
        today_rel = next((x for x in self._month_releases if x['day'] == arrow.now().date()), None)
        return today_rel['episodes']

    def get_month_releases(self):
        return self._month_releases.copy()


def get_pog_calendar() -> PogCalendar:
    with open(os.path.join(__location__,'pog_cookie.json')) as cookie:
        pog_cookie = json.load(cookie)

    get = requests.get('https://www.pogdesign.co.uk/cat/', cookies=pog_cookie)
    LOGGER.info('PogDesign Get response: {}'.format(get.status_code))
    get.raise_for_status()

    calendar = PogCalendar()
    calendar.parse(get)

    return calendar


def save_rarbg_cookie_to_file(cookies: dict):
    with open(os.path.join(__location__,'rarbg_cookie.json'), 'w') as rarbg_cookie_file:
        LOGGER.info("Saving rarbg cookie to file")
        json.dump(cookies, rarbg_cookie_file)


def get_rarbg_cookie(url: str) -> dict:
    rarbg_cookie = {}
    try:
        with open(os.path.join(__location__,'rarbg_cookie.json')) as cookie:
            rarbg_cookie = json.load(cookie)
    except FileNotFoundError:
        LOGGER.info('No rarbg cookie found')
        thread_defence = ThreatDefenceHandler()
        rarbg_cookie = thread_defence.get_cookies(url=url)
        save_rarbg_cookie_to_file(rarbg_cookie)
    else:
        thread_defence = ThreatDefenceHandler(cookies=rarbg_cookie)
        new_rarbg_cookie = thread_defence.get_cookies(url=url)
        if rarbg_cookie != new_rarbg_cookie:
            rarbg_cookie = new_rarbg_cookie
            save_rarbg_cookie_to_file(rarbg_cookie)
    finally:
        return rarbg_cookie


def get_torrent_file_size(url: str, cookie: dict) -> float:
    get_torrent = requests.get(url, cookies=cookie)
    soup_obj = bs4.BeautifulSoup(get_torrent.text, features="lxml")
    table = soup_obj.select(
        'body > table:nth-child(6) > tr > td:nth-child(2) > div > table > tr:nth-child(2) > td > div > table')
    for tr in table[0].select('tr'):
        for td in tr.select('td', {'class': 'header2'}):
            if td.text.strip() == "Size:":
                size = tr.select('td.lista')[0].text.strip().split()
                return float(size[0]) * 1000 if 'GB' in size[1] else float(size[0])


def get_today_torrent_releases(releases: list, saved_torrents: dict) -> dict:
    LOGGER.info("Getting feed data")
    feed_rarbg = feedparser.parse('https://rarbg.to/rss.php?category=2;18;41')
    feed_rarbg_magnet = feedparser.parse('https://rarbg.to/rssdd_magnet.php?category=2;18;41')
    rarbg_cookie = get_rarbg_cookie("https://rarbg.to/torrents.php?category=2;18;41;49")

    for episode in releases:
        if episode['provider'] != 'Netflix':
            torrent_name_re = re.compile(r'.*{:s}.*{:s}.*'.format('.'.join(episode['name'].split()), episode['number']),
                                         re.IGNORECASE)
            torrent_quality_re = re.compile(r'(1080p|720p)', re.IGNORECASE)
            torrent_rip_type_re = re.compile(r'\.(HDTV|WEB\w*)\.', re.IGNORECASE)

            ep_name = '_'.join(['_'.join(episode['name'].split()), episode['number']])
            ep_torrents = saved_torrents.get(ep_name, None)
            if ep_torrents is None:
                LOGGER.info("ep_torrents empty")
                ep_torrents = []

            found_torrents = [entry for entry in feed_rarbg.entries
                              if torrent_name_re.search(entry.get("title", ""))]

            for torrent in found_torrents:
                if next((opt for opt in ep_torrents if opt.get('title').strip() == torrent.get('title').strip()), None) is None:
                    title = torrent.get('title', '')
                    link = torrent.get('link', '')
                    quality = torrent_quality_re.search(title).group() if torrent_quality_re.search(
                        torrent.get('title', '')) is not None else 'Standard'
                    rip_type = torrent_rip_type_re.search(title).group(1) if torrent_rip_type_re.search(
                        title) is not None else 'Undefined'
                    magnet = \
                        next(item for item in feed_rarbg_magnet.entries if item['title'] == torrent.get("title", ""))[
                            'link']
                    size = get_torrent_file_size(torrent.get("link", ""), rarbg_cookie)
                    ep_torrents.append(
                        {'title': title, 'link': link, 'rip_type': rip_type, 'quality': quality, 'size': size,
                         'magnet': magnet})
                    LOGGER.info('Added: {:s}'.format(title))
                    # pprint.pprint({'title': title, 'link': link, 'rip_type': rip_type, 'quality': quality, 'size': size,
                    #                'magnet': magnet})

            saved_torrents[ep_name] = ep_torrents

    LOGGER.info('Done parsing feed data')
    return saved_torrents


def main():
    LOGGER.info('Starting Torrent List Generator')
    torrents = {}
    if os.path.isfile(pickle_file_name):
        with open(pickle_file_name, "rb") as pickle_in:
            torrents = pickle.load(pickle_in)
            #pprint.pprint(torrents)

    pog_calendar = get_pog_calendar()

    today_releases = pog_calendar.get_today_releases()
    # For testing:
    # today_releases = [{'name': 'MasterChef', 'number': 'S10E21', 'provider': 'HBO'}]
    updated_torrents = get_today_torrent_releases(today_releases, torrents)
    with open(pickle_file_name, "wb") as pickle_out:
        LOGGER.info('Saving updated torrent data')
        pickle.dump(updated_torrents, pickle_out)

    LOGGER.info('Exiting!')
    LOGGER.info('-' * 50)


if __name__ == '__main__':
    main()
