#!/usr/bin/env python
import logging
import argparse
import json
import re
from datetime import datetime

from bs4 import BeautifulSoup
from bs4.element import NavigableString
import warnings
warnings.filterwarnings("ignore", category=UserWarning, module='bs4')

import requests
import requests_cache
requests_cache.install_cache('/tmp/python-requests_cache')

logger = logging.getLogger('tapp')

base_url = 'http://www.presidency.ucsb.edu'

def reencode_response(response):
    '''
    Re-interpret the encoding on the fly if specified as a meta header, e.g.:

        <META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=windows-1251">

    If the Content-Type is not specified in the HTTP headers, Python requests
    defaults to ISO-8859-1, which is close to TAPP's usual windows-1251, but not
    quite the same.
    '''
    content_type = re.search(r'<meta.+charset=([a-z0-9-]+)', response.content, re.I)
    if content_type:
        encoding = content_type.group(1)
        logger.debug('Setting encoding to "%s"', encoding)
        response.encoding = encoding
    return response

def get_soup(url):
    logger.info('Fetching "%s"', url)
    response = reencode_response(requests.get(url))
    return BeautifulSoup(response.text)

def iter_paragraphs(element):
    '''
    Loop over `element`'s children, treating each child as a paragraph if it's a
    string, or each of that child's children as a paragraph if it's an element.

    And yes, they really do nest a bunch of paragraphs inside a span!
    '''
    for child in element.children:
        if isinstance(child, NavigableString):
            yield unicode(child)
        else:
            for subchild in child.children:
                if isinstance(subchild, NavigableString):
                    yield unicode(subchild)
                else:
                    yield subchild.get_text()

def read_paper(pid):
    url = base_url + '/ws/index.php?pid=' + pid
    soup = get_soup(url)
    # the HTML they generate is awkward, to say the least
    author, title = soup.find('title').get_text().split(': ', 1)
    date_string = soup.find('span', class_='docdate').string
    date = datetime.strptime(date_string, '%B %d, %Y')
    timestamp = date.date().isoformat()

    displaytext = soup.find('span', class_='displaytext')
    paragraphs = [paragraph.strip() for paragraph in iter_paragraphs(displaytext) if not paragraph.isspace()]
    text = '\n'.join(paragraphs)

    paper = dict(author=author, title=title.strip('.'), timestamp=timestamp, source=url, text=text)

    displaynotes = soup.find('span', class_='displaynotes')
    note = displaynotes.get_text(' ') or None
    if note:
        # remove "Note: " prefix if present
        paper['note'] = re.sub(r'^note:\s+', '', note, flags=re.I)

    return paper

def get_pids(soup):
    for anchor in soup.select('a[href*="index.php?pid="]'):
        yield anchor['href'].split('=')[-1]

def get_paragraph_lines(p):
    for child in p.children:
        if child.name == 'br':
            continue
        elif isinstance(child, NavigableString):
            yield unicode(child)
        else:
            yield child.get_text()

def get_2016_election():
    soup = get_soup(base_url + '/2016_election.php')
    container = soup.find('td', class_='doctext').find_parent('table')
    for td in container.find_all('td', class_='doctext'):
        paragraphs = td.find_all('p')
        if len(paragraphs) > 0:
            info_paragraph, links_paragraph = paragraphs
            # get candidate information
            lines = [line.strip() for line in get_paragraph_lines(info_paragraph)
                if line.strip() not in (u'Candidacy Declared:', 'Status:', '')]
            name, title, candidacy_declared, status = lines
            candidate = dict(name=name, title=title, candidacy_declared=candidacy_declared, status=status)
            # get links to speeches
            logger.info('Fetching papers for candidate "%r"', candidate)
            for anchor in links_paragraph.find_all('a'):
                category = anchor.get_text()
                logger.info('Fetching papers from category "%s"', category)
                sub_soup = get_soup(base_url + '/' + anchor['href'])
                pids = get_pids(sub_soup)
                for pid in pids:
                    yield pid


def print_papers(pids):
    for pid in pids:
        paper = read_paper(pid)
        print json.dumps(paper, sort_keys=True, ensure_ascii=False)

def fetch_command(opts):
    print_papers(opts.args)

def inaugurals_command(opts):
    soup = get_soup(base_url + '/inaugurals.php')
    pids = get_pids(soup)
    print_papers(pids)

def election2016_command(opts):
    pids = get_2016_election()
    print_papers(pids)

def main():
    commands = dict(fetch=fetch_command, inaugurals=inaugurals_command, election2016=election2016_command)

    parser = argparse.ArgumentParser(
        description='Scrape The American Presidency Project website (http://www.presidency.ucsb.edu/)',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('-v', '--verbose', action='store_true', help='Log extra information')
    parser.add_argument('command', choices=commands, help='Command')
    parser.add_argument('args', nargs='*', help='Arguments to command')
    opts = parser.parse_args()

    logging.basicConfig(level=logging.INFO if opts.verbose else logging.WARN)

    command = commands[opts.command]
    command(opts)

if __name__ == '__main__':
    main()
