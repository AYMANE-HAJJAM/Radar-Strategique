from app.bot.keyboards.constants import RADAR_CODES
from app.core.radar_registry import RADARS


def parse_callback(data):
    if data == 'menu':
        return 'menu', None
    if not isinstance(data, str):
        raise ValueError('Invalid callback')
    action, separator, code = data.partition(':')
    if action in {'pending', 'approved', 'rejected', 'runs'} and code in RADAR_CODES:
        return action, code
    if not separator or action not in {'radar', 'search', 'news', 'history'} or code not in RADARS:
        raise ValueError('Invalid callback')
    return action, code
