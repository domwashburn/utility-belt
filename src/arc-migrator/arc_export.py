#!/usr/bin/env python3
"""Export Arc sidebar data locally to portable bookmark and document formats."""
import argparse
import csv
import html
import io
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

FORMATS = ('html', 'md', 'json', 'csv', 'tsv', 'txt')


def pairs(value):
    if isinstance(value, dict):
        return [(str(k), v) for k, v in value.items() if isinstance(v, dict)]
    if not isinstance(value, list):
        return []
    result = []
    for i, obj in enumerate(value):
        if isinstance(obj, dict):
            key = value[i - 1] if i and isinstance(value[i - 1], str) else obj.get('id')
            if key:
                result.append((str(key), obj))
    return result


def discover():
    local = Path('StorableSidebar.json')
    candidates = [local, Path.home() / 'Library/Application Support/Arc/StorableSidebar.json']
    base = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / 'AppData/Local'))) / 'Packages'
    candidates.extend(sorted(base.glob('TheBrowserCompany.Arc*/LocalCache/Local/Arc/StorableSidebar.json')))
    found = [p for p in candidates if p.is_file()]
    if len(found) > 1 and not local.is_file():
        raise ValueError('Multiple Arc sidebar files found; choose one with --input: ' + ', '.join(map(str, found)))
    if not found:
        raise ValueError('Arc sidebar not found. Use --input PATH to select StorableSidebar.json or a backup.')
    return found[0]


def parse(data, include_today=False):
    sidebar = data.get('sidebar', {}) if isinstance(data, dict) else {}
    containers = sidebar.get('containers', []) if isinstance(sidebar, dict) else []
    sections = [x for x in containers if isinstance(x, dict) and 'spaces' in x and 'items' in x] if isinstance(containers, list) else []
    if not sections:
        raise ValueError('Unrecognized Arc sidebar structure: no container with spaces and items. No files written.')
    forest, warnings = [], []
    for section in sections:
        spaces, item_pairs = pairs(section['spaces']), pairs(section['items'])
        items = {key: obj for key, obj in item_pairs}
        if not spaces and section['spaces']:
            raise ValueError('Unrecognized Arc spaces structure. No files written.')
        if not items and section['items']:
            raise ValueError('Unrecognized Arc items structure. No files written.')
        by_parent = defaultdict(list)
        for key, obj in item_pairs:
            if obj.get('parentID') is not None:
                by_parent[str(obj['parentID'])].append(key)
        used = set()
        def child_ids(key):
            obj = items.get(key, {})
            ordered = obj.get('childrenIds', obj.get('childrenIDs', []))
            ordered = [str(x) for x in ordered if isinstance(x, str)] if isinstance(ordered, list) else []
            return list(dict.fromkeys(ordered + by_parent.get(key, [])))
        def walk(key, stack):
            if key in stack:
                warnings.append('A cycle in sidebar items was skipped.')
                return []
            obj = items.get(key)
            if obj is None:
                warnings.append('A referenced sidebar item was missing.')
                return []
            used.add(key)
            data = obj.get('data') if isinstance(obj.get('data'), dict) else {}
            children = []
            for child in child_ids(key):
                children.extend(walk(child, stack | {key}))
            tab = data.get('tab')
            if isinstance(tab, dict):
                url = tab.get('savedURL') or tab.get('url')
                title = obj.get('title') or tab.get('savedTitle') or url
                if isinstance(url, str) and url:
                    return [{'type': 'bookmark', 'title': str(title), 'url': url}] + children
                warnings.append('A tab without a saved URL was skipped.')
                return children
            if 'itemContainer' in data:
                return children
            if 'list' in data or 'splitView' in data or (children and obj.get('title')):
                return [{'type': 'folder', 'title': str(obj.get('title') or ('Split View' if 'splitView' in data else 'Untitled folder')), 'children': children}]
            if children:
                warnings.append('An unknown container was flattened; review the output.')
                return children
            if data:
                warnings.append('An unsupported sidebar item was skipped.')
            return []
        # Favorite roots are shared across Spaces; export them once.
        fav_roots = section.get('topAppsContainerIDs', [])
        if isinstance(fav_roots, list):
            favorites = []
            for root in fav_roots:
                if isinstance(root, str):
                    favorites.extend(walk(root, set()))
            if favorites:
                forest.append({'type': 'folder', 'title': 'Favorites', 'children': favorites})
        for number, (_, space) in enumerate(spaces, 1):
            roots = space.get('newContainerIDs', [])
            selected = []
            if isinstance(roots, list):
                for i in range(len(roots) - 1):
                    kind, root = roots[i], roots[i + 1]
                    if isinstance(kind, dict) and isinstance(root, str):
                        if 'pinned' in kind or (include_today and 'unpinned' in kind):
                            selected.append(('Today' if 'unpinned' in kind else 'Pinned', root))
            elif isinstance(roots, dict):
                selected = [(k, v) for k, v in roots.items() if isinstance(v, str) and (k == 'pinned' or (include_today and k == 'unpinned'))]
            if not selected:
                warnings.append('A Space has no recognized pinned root; review the output.')
            children = []
            for kind, root in selected:
                nodes = walk(root, set())
                if kind.lower() in ('today', 'unpinned'):
                    if nodes:
                        children.append({'type': 'folder', 'title': 'Today', 'children': nodes})
                else:
                    children.extend(nodes)
            forest.append({'type': 'folder', 'title': str(space.get('title') or f'Space {number}'), 'children': children})
        # Warn about tabs not reached, excluding Today tabs when not requested.
        missing = sum(1 for k, v in item_pairs if k not in used and isinstance(v.get('data'), dict) and 'tab' in v['data'])
        if missing:
            warnings.append(f'{missing} tab(s) were outside exported roots (may include Today tabs, archived items, or unsupported data).')
    return forest, list(dict.fromkeys(warnings))


def rows(nodes, path=()):
    for node in nodes:
        if node['type'] == 'folder':
            yield ('folder', path, node['title'], '')
            yield from rows(node['children'], path + (node['title'],))
        else:
            yield ('bookmark', path, node['title'], node['url'])


def render(fmt, nodes):
    if fmt == 'json':
        return json.dumps({'version': 1, 'items': nodes}, ensure_ascii=False, indent=2) + '\n'
    if fmt in ('csv', 'tsv'):
        out = io.StringIO(newline='')
        writer = csv.writer(out, delimiter=',' if fmt == 'csv' else '\t', lineterminator='\n')
        writer.writerow(['type', 'path_json', 'title', 'url'])
        for kind, path, title, url in rows(nodes):
            writer.writerow([kind, json.dumps(path, ensure_ascii=False), title, url])
        return out.getvalue()
    if fmt == 'html':
        lines = ['<!DOCTYPE NETSCAPE-Bookmark-file-1>', '<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">', '<TITLE>Arc bookmarks</TITLE>', '<H1>Arc bookmarks</H1>', '<DL><p>']
        def emit(items, level):
            for item in items:
                indent = '    ' * level
                title = html.escape(item['title'], quote=True)
                if item['type'] == 'folder':
                    lines.extend([f'{indent}<DT><H3>{title}</H3>', f'{indent}<DL><p>'])
                    emit(item['children'], level + 1)
                    lines.append(f'{indent}</DL><p>')
                else:
                    lines.append(f'{indent}<DT><A HREF="{html.escape(item["url"], quote=True)}">{title}</A>')
        emit(nodes, 1)
        return '\n'.join(lines + ['</DL><p>', ''])
    lines = []
    def emit(items, level):
        for item in items:
            title = item['title'].replace('\n', ' ').replace('\r', ' ')
            indent = '  ' * level
            if fmt == 'md':
                title = title.replace('\\', '\\\\').replace('[', '\\[').replace(']', '\\]')
                if item['type'] == 'folder':
                    lines.append(f'{indent}- **{title.replace("*", chr(92) + "*")}**')
                    emit(item['children'], level + 1)
                else:
                    url = item['url'].replace(' ', '%20').replace('(', '%28').replace(')', '%29')
                    lines.append(f'{indent}- [{title}]({url})')
            elif item['type'] == 'folder':
                lines.append(f'{indent}{title}/')
                emit(item['children'], level + 1)
            else:
                lines.append(f'{indent}{title} — {item["url"]}')
    emit(nodes, 0)
    return '\n'.join(lines) + '\n'


def main():
    p = argparse.ArgumentParser(description='Export Arc Spaces and nested folders locally, ready for a new browser.', formatter_class=argparse.RawDescriptionHelpFormatter, epilog='Examples:\n  python3 arc_export.py\n  python3 arc_export.py --format html,json,md --today --output ./my-arc\n  python3 arc_export.py --input /path/to/StorableSidebar.json --list')
    p.add_argument('-i', '--input', type=Path, help='Arc sidebar file or backup (auto-detected by default)')
    p.add_argument('-o', '--output', type=Path, default=Path('arc-export'), help='Output directory (default: ./arc-export)')
    p.add_argument('-f', '--format', default='all', help='Comma-separated: html, md, json, csv, tsv, txt, or all (default: all)')
    p.add_argument('--today', action='store_true', help='Include currently open unpinned Today tabs')
    p.add_argument('--combined-only', action='store_true', help='Skip separate folders for each Space')
    p.add_argument('--list', action='store_true', help='Preview Space names and bookmark counts without writing')
    p.add_argument('--force', action='store_true', help='Replace existing output files')
    args = p.parse_args()
    formats = list(FORMATS) if args.format == 'all' else list(dict.fromkeys(x.strip().lower() for x in args.format.split(',')))
    if not formats or any(x not in FORMATS for x in formats):
        p.error('Choose formats from: ' + ', '.join(FORMATS) + ', or all')
    try:
        source = args.input or discover()
        with source.open(encoding='utf-8-sig') as f:
            data = json.load(f)
        nodes, warnings = parse(data, args.today)
        print('\n  ARC EXPORT  /  Your sidebar, portable\n')
        print(f'  Source: {source}')
        for node in nodes:
            count = sum(1 for row in rows([node]) if row[0] == 'bookmark')
            print(f'  • {node["title"]}: {count} links')
        for warning in warnings:
            print(f'  Warning: {warning}', file=sys.stderr)
        if args.list:
            return 0
        # Numbered names avoid collisions, including case-insensitive filesystems.
        groups = [(args.output, nodes)]
        if not args.combined_only:
            for index, node in enumerate(nodes, 1):
                name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', '_', node['title']).strip(' .')
                name = name[:80].rstrip(' .') or 'Untitled'
                groups.append((args.output / 'spaces' / f'{index:02d} - {name}', [node]))
        targets = [(folder / ('arc-bookmarks.' + fmt), fmt, group) for folder, group in groups for fmt in formats]
        if any(path.resolve() == source.resolve() for path, _, _ in targets):
            raise ValueError('Output would overwrite the input file.')
        existing = [path for path, _, _ in targets if path.exists()]
        if existing and not args.force:
            raise ValueError('Output already exists; choose another folder or use --force: ' + ', '.join(map(str, existing)))
        rendered = [(target, render(fmt, group)) for target, fmt, group in targets]
        for target, content in rendered:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding='utf-8', newline='')
            print(f'  ✓ {target}')
        print('\n  Import the HTML file in your new browser’s bookmark manager.\n')
        return 0
    except (ValueError, OSError, json.JSONDecodeError, RecursionError) as e:
        print(f'\n  Error: {e}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
