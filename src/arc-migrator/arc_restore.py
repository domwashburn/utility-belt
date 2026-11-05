#!/usr/bin/env python3
"""Check an Arc export and regenerate bookmark HTML for a browser import."""
import argparse
import csv
import json
import sys
from html.parser import HTMLParser
from pathlib import Path
from arc_export import render, rows


class Bookmarks(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.roots = []
        self.stack = [self.roots]
        self.pending = None
        self.current = None
        self.capture = None
        self.depth = 0

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag == 'dl':
            self.depth += 1
            if self.depth > 1:
                if self.pending is None:
                    raise ValueError('Bookmark folder is missing its heading')
                self.stack.append(self.pending['children'])
                self.pending = None
        elif tag == 'h3':
            self.current = {'type': 'folder', 'title': '', 'children': []}
            self.stack[-1].append(self.current)
            self.pending = self.current
            self.capture = 'title'
        elif tag == 'a':
            href = dict(attrs).get('href')
            if href is None:
                raise ValueError('Bookmark is missing its URL')
            self.current = {'type': 'bookmark', 'title': '', 'url': href}
            self.stack[-1].append(self.current)
            self.capture = 'title'

    def handle_data(self, data):
        if self.capture and self.current is not None:
            self.current[self.capture] += data

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in ('h3', 'a'):
            self.capture = None
        elif tag == 'dl':
            if self.depth > 1:
                self.stack.pop()
            self.depth -= 1


def validate_items(nodes):
    if not isinstance(nodes, list):
        raise ValueError('items must be a list')
    for item in nodes:
        if not isinstance(item, dict) or not isinstance(item.get('title'), str):
            raise ValueError('Every item needs a text title')
        if item.get('type') == 'folder':
            validate_items(item.get('children'))
        elif item.get('type') == 'bookmark':
            if not isinstance(item.get('url'), str) or not item['url']:
                raise ValueError('Every bookmark needs a nonempty URL')
        else:
            raise ValueError('Unknown item type')


def main():
    parser = argparse.ArgumentParser(description='Check an exported archive and optionally regenerate its browser-importable HTML.')
    parser.add_argument('archive', type=Path, help='A Space folder or arc-bookmarks.json')
    parser.add_argument('--prepare', type=Path, metavar='HTML', help='Write a new bookmark HTML file at this path')
    args = parser.parse_args()
    try:
        path = args.archive / 'arc-bookmarks.json' if args.archive.is_dir() else args.archive
        data = json.loads(path.read_text(encoding='utf-8-sig'))
        if not isinstance(data, dict) or data.get('version') != 1:
            raise ValueError('Unsupported archive version')
        nodes = data.get('items')
        validate_items(nodes)
        all_rows = list(rows(nodes))
        print(f"Archive OK: {sum(r[0] == 'bookmark' for r in all_rows)} links, {sum(r[0] == 'folder' for r in all_rows)} folders")
        html_path = path.parent / 'arc-bookmarks.html'
        if html_path.exists():
            parsed = Bookmarks()
            parsed.feed(html_path.read_text(encoding='utf-8-sig'))
            parsed.close()
            if parsed.depth != 0 or parsed.roots != nodes:
                raise ValueError('HTML does not match the JSON hierarchy')
            print('HTML matches the JSON hierarchy.')
        else:
            print('HTML not present; use --prepare to generate it.')
        for extension, delimiter in [('csv', ','), ('tsv', '\t')]:
            csv_path = path.parent / ('arc-bookmarks.' + extension)
            if not csv_path.exists():
                continue
            with csv_path.open(encoding='utf-8-sig', newline='') as f:
                actual = list(csv.reader(f, delimiter=delimiter))
            expected = [['type', 'path_json', 'title', 'url']] + [[kind, json.dumps(parent, ensure_ascii=False), title, url] for kind, parent, title, url in all_rows]
            if actual != expected:
                raise ValueError(f'{extension.upper()} does not match the JSON hierarchy')
            print(f'{extension.upper()} matches the JSON hierarchy.')
        if args.prepare:
            if args.prepare.exists():
                raise ValueError('Output already exists; choose a new filename')
            args.prepare.parent.mkdir(parents=True, exist_ok=True)
            with args.prepare.open('x', encoding='utf-8', newline='') as f:
                f.write(render('html', nodes))
            print(f'Browser bookmark file created: {args.prepare}')
        print('This checks archive consistency, not completeness against Arc or a native Space restore.')
        return 0
    except (ValueError, OSError, RecursionError, csv.Error) as e:
        print(f'Error: {e}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
