import json
import os.path
import re


emoji_locn = os.path.join(os.path.dirname(__file__), 'emojis.json')

emoji_re = re.compile(r'(?<!`)(:([\-\+a-z0-9_]+):)(?!`)')


def to_html(message):
    with open(emoji_locn, 'r') as fh:
        emojis = json.load(fh)
    html = message

    pos = 0
    while True:
        match = emoji_re.search(message[pos:])
        if match is None:
            break
        pos += match.start() + 1
        emoji = match.group(0)
        url = emojis.get(emoji[1:-1])
        if url:
            replacement = '<img class="gh-emoji" src="{}" />'.format(url)
            html = html.replace(match.group(0), replacement)
    return html


if __name__ == '__main__':
    example = 'Hello world: how :are:smile: you? :+1:'

    print(to_html(example))

