#!/usr/bin/python3

# Import the client module
from deluge.ui.client import client
# Import the reactor module from Twisted - this is for our mainloop
from twisted.internet import reactor
import pickle
import os
import logging.config

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
            #'mode': 'w',
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


# We create a callback function to be called upon a successful connection
def on_connect_success(result):
    LOGGER.info("Connection was successful!")

    def on_torrent_added(torrent_id, torrent_title):
        LOGGER.info("{} added to daemon!".format(torrent_title))
        LOGGER.info("Torrent ID: {:s}".format(torrent_id))

    def on_torrent_added_fail(result):
        LOGGER.info(result)

    torrents_to_add = get_torrents_to_add()
    for torrent in torrents_to_add:
        client.core.add_torrent_magnet(torrent['magnet'], {}).addCallback(on_torrent_added,torrent['title'])\
                                                                 .addErrback(on_torrent_added_fail)
    if os.path.isfile(pickle_file_name):
        os.remove(pickle_file_name)
        LOGGER.info("Torrents pickle file removed")

def get_torrents_to_add() -> list:
    torrents = {}
    if os.path.isfile(pickle_file_name):
        with open(pickle_file_name, "rb") as pickle_in:
            torrents = pickle.load(pickle_in)

    magnets = []
    for k, v in torrents.items():
        magnet_title, magnet_link = get_best_torrent_option(v)
        if magnet_title != '':
            magnets.append({"title": magnet_title, "magnet": magnet_link})
        else:
            LOGGER.info("No torrent to add!")

    return magnets


def get_best_torrent_option(torrent_options: list) -> tuple:
    if len(torrent_options) > 0:
        web_rel = [w for w in torrent_options if 'WEB'.casefold() in w.get('rip_type').casefold()]
        hdtv_rel = [h for h in torrent_options if 'HDTV'.casefold() in h.get('rip_type').casefold()]
        if len(web_rel) > 0:
            web_rel.sort(key=lambda k: k['size'], reverse=True)
            for web_t in web_rel:
                if web_t.get('size') < 1500.0:
                    return web_t.get('title'), web_t.get('magnet')
        elif len(hdtv_rel) > 0:
            hdtv_rel.sort(key=lambda k: k['size'])
            for hd_t in hdtv_rel:
                if hd_t.get('size') < 1500.0:
                    return hd_t.get('title'), hd_t.get('magnet')
        else:
            torrent_options.sort(key=lambda k: k['size'], reverse=True)
            for opt in torrent_options:
                if opt.get('size') < 1500.0:
                    return opt.get('title'), opt.get('magnet')

    return '', ''


# We create another callback function to be called when an error is encountered
def on_connect_fail(result):
    LOGGER.info("Connection failed!")
    LOGGER.info("result: {:}".format(result))


def stop_reactor():
    client.disconnect().addCallback(lambda ignore: reactor.stop())
    LOGGER.info('Disconnecting from client')
    LOGGER.info('Stopping reactor')

if __name__ == '__main__':
    LOGGER.info('Starting Deluge Torrent Adder')
    # Connect to a daemon running on the localhost
    # We get a Deferred object from this method and we use this to know if and when
    # the connection succeeded or failed.
    d = client.connect()
    # We add the callback to the Deferred object we got from connect()
    d.addCallback(on_connect_success)
    # We add the callback (in this case it's an errback, for error)
    d.addErrback(on_connect_fail)
    # Manually stop reactor after 5 seconds
    reactor.callLater(5, stop_reactor)
    # Run the twisted main loop to make everything go
    reactor.run()
