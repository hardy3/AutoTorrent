#!/usr/bin/python3
import os
import pprint

import arrow
import requests
import bs4
import re
import json
import pickle
import logging.config

import rarbgapi

import pdb

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

__location__ = os.path.realpath(os.path.join(
    os.getcwd(), os.path.dirname(__file__)))
pickle_file_name = os.path.join(__location__, 'torrents.pickle')
waiting_list_pickle_file_name = os.path.join(
    __location__, 'waiting_torrents.pickle')

LOGGER = logging.getLogger(__name__)


class PogCalendar:

    def __init__(self):
        self._month_releases = []

    def parse(self, html_data):
        soup_obj = bs4.BeautifulSoup(html_data.text, features="lxml")
        for div_day in soup_obj.find_all('div', {"class": {'today', 'day'}}):
            date = arrow.get(div_day.select('a')[0].get(
                'title'), "dddd Do MMMM YYYY").date()
            day_releases = {'day': date, 'episodes': []}
            for div_ep in div_day.select('div'):
                last_ep = True if 'lastep' in div_ep.select(
                    'span')[0].get('class') else False
                first_ep = True if 'firstep' in div_ep.select(
                    'span')[0].get('class') else False
                series_ref = div_ep.select(
                    'input')[0].get('value').split('-')[0]
                series_name, ep_num, ep_title, series_provider = [line.strip() for line in
                                                                  div_ep.text.strip().split("\n")]
                series_provider = series_provider.split('-')[0].strip()
                episode = {'name': series_name, 'number': ep_num,
                           'provider': series_provider, 'series_ref': series_ref,
                           'last_ep': last_ep, 'first_ep': first_ep}
                day_releases['episodes'].append(episode)
            self._month_releases.append(day_releases)

    def get_today_releases(self) -> list:
        today_rel = next(
            (x for x in self._month_releases if x['day'] == arrow.now().date()), None)
        return today_rel['episodes']

    def get_month_releases(self):
        return self._month_releases.copy()


def get_pog_calendar() -> PogCalendar:
    with open(os.path.join(__location__, 'pog_cookie.json')) as cookie:
        pog_cookie = json.load(cookie)

    get = requests.get('https://www.pogdesign.co.uk/cat/', cookies=pog_cookie)
    LOGGER.info('PogDesign Get response: {}'.format(get.status_code))
    get.raise_for_status()

    calendar = PogCalendar()
    calendar.parse(get)

    return calendar


class Rarbg:

    def __init__(self, retries: int = 3):
        self._client = rarbgapi.RarbgAPI(retries=retries)
        self._searchRetries = retries

    def _search(self, searchString: str) -> list:
        myCategories = [rarbgapi.RarbgAPI.CATEGORY_TV_EPISODES_UHD,
                        rarbgapi.RarbgAPI.CATEGORY_TV_EPISODES_HD,
                        rarbgapi.RarbgAPI.CATEGORY_TV_EPISODES]

        searchResults = []
        searchRetries = 0

        while (len(searchResults) == 0 and searchRetries < self._searchRetries):
            searchResults = self._client.search(
                search_string=searchString, categories=myCategories, extended_response=True)
            searchRetries += 1

        return searchResults

    def get_today_torrent_releases(self, releases: list, saved_torrents: dict) -> [dict, list]:
        waiting_list = []

        for episode in releases:
            # im paying for netflix and disney+, no need to download :)
            if episode['provider'] != 'Netflix' and episode['provider'] != 'Disney+':

                ep_name = '_'.join(
                    ['_'.join(re.split('\s|: ', episode['name'])), episode['number']])
                ep_torrents = saved_torrents.get(ep_name, None)
                if ep_torrents is None:
                    LOGGER.info("ep_torrents empty")
                    ep_torrents = []
                else:
                    # Already in the torrent list
                    continue

                season_number = re.compile(
                    r'(s\d+)e\d+', re.IGNORECASE).search(episode['number']).group(1)
                mySearchString = episode["name"] + " " + season_number
                searchResults = self._search(mySearchString)

                torrent_name_re = re.compile(r'^{:s}.*{:s}\W+.*$'.format('.'.join(re.split('\s|: ', episode['name'])),
                                                                         season_number), re.IGNORECASE)
                validSearchResults = [
                    torrent for torrent in searchResults if torrent_name_re.search(torrent.title)]

                if (len(validSearchResults) == 0 or episode['last_ep']):
                    mySearchString = episode["name"] + " " + episode["number"]
                    searchResults = self._search(mySearchString)

                    torrent_name_re = re.compile(r'^{:s}.*{:s}.*$'.format('.'.join(
                        re.split('\s|: ', episode['name'])), episode['number']), re.IGNORECASE)
                    validSearchResults = [
                        torrent for torrent in searchResults if torrent_name_re.search(torrent.title)]

                elif (not episode['first_ep']):
                    # Downloading complete season
                    continue

                if (len(validSearchResults) > 0):
                    for torrent in validSearchResults:
                        title = torrent.filename

                        torrent_quality_re = re.compile(
                            r'(1080p|720p)', re.IGNORECASE)
                        quality = torrent_quality_re.search(title).group() if torrent_quality_re.search(
                            title) is not None else 'Standard'

                        torrent_rip_type_re = re.compile(
                            r'\.(HDTV|WEB[\w|-]*)\.', re.IGNORECASE)
                        rip_type = torrent_rip_type_re.search(title).group(1) if torrent_rip_type_re.search(
                            title) is not None else 'Undefined'

                        magnet = torrent.download
                        link = torrent.info_page  # ?
                        size = torrent.size/1024/1024
                        seeds = torrent.seeders

                        ep_torrents.append(
                            {'title': title, 'link': link, 'rip_type': rip_type, 'quality': quality, 'size': size,
                             'magnet': magnet, 'seeders': seeds})
                        LOGGER.info('Added: {:s}'.format(title))

                    saved_torrents[ep_name] = ep_torrents
                else:
                    waiting_list.append(episode)
                    LOGGER.info('Added to waiting list: {:s} {:s}'.format(
                        episode['name'], episode['number']))

        LOGGER.info('Done parsing search results')
        return saved_torrents, waiting_list


def main():
    LOGGER.info('Starting Torrent List Generator')
    torrents = {}
    if os.path.isfile(pickle_file_name):
        with open(pickle_file_name, "rb") as pickle_in:
            torrents = pickle.load(pickle_in)
            # pprint.pprint(torrents)

    pog_calendar = get_pog_calendar()
    today_releases = pog_calendar.get_today_releases()

    # For testing:
    #today_releases = [{'name': 'Raised by Wolves', 'number': 's01e01', 'provider': 'HBO'}]

    if os.path.isfile(waiting_list_pickle_file_name):
        with open(waiting_list_pickle_file_name, "rb") as pickle_in:
            today_releases.extend(pickle.load(pickle_in))

    rarbgClient = Rarbg(retries=10)
    [updated_torrents, waiting_list] = rarbgClient.get_today_torrent_releases(
        today_releases, torrents)

    with open(pickle_file_name, "wb") as pickle_out:
        LOGGER.info('Saving updated torrent data')
        pickle.dump(updated_torrents, pickle_out)

    with open(waiting_list_pickle_file_name, "wb") as pickle_out:
        LOGGER.info('Saving waiting list')
        pickle.dump(waiting_list, pickle_out)

    LOGGER.info('Exiting!')
    LOGGER.info('-' * 50)


# ---- ----
if __name__ == '__main__':
    main()
