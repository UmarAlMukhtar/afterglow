"""The four reference lyric treatments share one truthful timeline."""
from bisect import bisect_right
import re
import math

STYLES = {
    'ship': {'name': 'Ship', 'lens': False, 'icons': False},
    'fisheye': {'name': 'Fisheye', 'lens': True, 'icons': False},
    'fisheye_visual': {'name': 'Fisheye Visual', 'lens': True, 'icons': True},
    'visual': {'name': 'Visual', 'lens': False, 'icons': True},
}

_GROUPS = {
    '♥': 'love loved loving lover heart hearts need needed want wanted desire feel feeling feelings kiss kisses soul souls',
    '◷': 'time times minute minutes second seconds hour hours clock wait waiting late later early yesterday tomorrow forever moment moments',
    '◉': 'eye eyes see seeing seen look looks looking watch watching sight vision',
    '✦': 'light lights lit glow glowing shine shining bright brighter star stars sparkle magic dream dreams',
    '☀': 'sun sunny sunshine day days daylight morning',
    '☾': 'moon night nights midnight dark darkness sleep sleeping asleep',
    '☁': 'cloud clouds cloudy sky skies heaven heavens',
    '♬': 'music song songs sing singing sang sung sound sounds melody rhythm beat beats dance dancing',
    '✈': 'fly flying flight flew away journey travel traveling plane airplane',
    '⌂': 'home house room rooms door doors family hometown',
    '❀': 'flower flowers bloom blooming rose roses garden spring',
    '♧': 'tree trees forest green leaf leaves nature',
    '∞': 'always endless infinite infinity together',
    '✉': 'message messages letter letters write writing telling tell told say says saying said talk talking speak speaking words word',
    '⚄': 'chance chances luck lucky gamble gambling dice',
    '≋': 'wind air blew blowing breath breathe breathing breeze waves wave sea ocean water river rain raining',
    '♨': 'fire flame flames burning burn hot heat warm warmer',
    '☝': 'hand hands touch touching finger fingers swish',
    '➜': 'go going gone move moving run running push pushing road roads way ways street streets',
    '☻': 'smile smiling happy happiness laugh laughing joy glad',
    '☂': 'cry crying tears tear sad sadness storm storms',
    '◆': 'diamond diamonds gold golden rich money treasure',
    '⚑': 'win winning winner victory fight fighting strong stronger strength',
}
ICONS = {word: glyph for glyph, words in _GROUPS.items() for word in words.split()}


def icon_for(word):
    return ICONS.get(re.sub(r'[^\w]', '', word.casefold()), '')


class LyricMotion:
    """Damped vertical motion; large seeks snap instead of crossing many words."""
    def __init__(self):
        self.focus = None
        self.velocity = 0.
        self.last = None

    def sample(self, index, progress, now, reduced=False):
        target = index if reduced else index + .2 * progress
        if self.focus is None or reduced or abs(target-self.focus)>4:
            self.focus, self.velocity, self.last = float(target), 0., now
            return self.focus
        dt = max(0.,min(.05,now-self.last))
        self.last = now
        for _ in range(2):
            step = dt/2
            self.velocity += ((target-self.focus)*55-self.velocity*13.5)*step
            self.focus += self.velocity*step
        return self.focus


def row_drift(index, seconds, reduced=False):
    if reduced:
        return 0,0
    return (.028*math.sin(seconds*.38+index*.73)+.012*math.sin(seconds*.16),
            .006*math.sin(seconds*.22+index*.9))


def scene_rows(document, position, flat=None):
    if document.quality not in ('word', 'estimated'):
        return []
    if flat is None:
        flat = sorted((w for line in document.lines for w in line.words), key=lambda w: w.start)
    index = bisect_right(flat, position, key=lambda w: w.start) - 1
    if index < 0:
        return []
    return [(flat[n].text, n - index,
             n == index and flat[n].start <= position < flat[n].end,
             min(1., max(0., (position - flat[n].start) / max(.001, flat[n].end - flat[n].start))))
            for n in range(max(0, index - 2), index + 1)]
