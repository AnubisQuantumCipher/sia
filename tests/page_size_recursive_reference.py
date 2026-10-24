"""Frozen original sizing function; shares current text/refusal helpers."""
from siaeventplan import _refuse, _text_size


def _size(value, limit, active=None, depth=0):
    """Admission before serialization/copy/hash, retaining native stat ints."""
    if type(limit) is not int or limit <= 0 or depth > 64:
        _refuse("complete-byte-capacity")
    kind = type(value)
    if value is None:
        size = 4
    elif kind is bool:
        size = 4 if value else 5
    elif kind is int:
        if value.bit_length() > limit:
            _refuse("complete-byte-capacity")
        try:
            size = len(str(value))
        except ValueError:
            _refuse("native-integer-capacity")
    elif kind is str:
        return _text_size(value, limit)
    elif kind in (dict, list):
        if len(value) > limit:
            _refuse("complete-byte-capacity")
        active = set() if active is None else active
        identity = id(value)
        if identity in active:
            _refuse("cyclic-json")
        active.add(identity)
        try:
            size = 2
            for position, item in enumerate(value):
                size += bool(position)
                if kind is dict:
                    size += _text_size(item, limit - size) + 1
                    child = value[item]
                else:
                    child = item
                size += _size(child, limit - size, active, depth + 1)
                if size > limit:
                    _refuse("complete-byte-capacity")
        finally:
            active.remove(identity)
    else:
        _refuse("non-native-json")
    if size > limit:
        _refuse("complete-byte-capacity")
    return size

