"""Line numbers for the values inside a JSON document.

The shapes tree can point at a line because `rdfio` indexes Turtle by byte
span. The examples tree had no equivalent, so selecting an entity or an
attribute moved nothing -- and `json.load` cannot help: it discards positions.

This is a structural scan rather than a parser. It records where each value
STARTS, keyed by the path of keys and array indices that reaches it, which is
exactly the address an example node already carries.
"""

WHITESPACE = ' \t\r\n'


class _Scanner:
    def __init__(self, text):
        self.text = text
        self.at = 0
        self.lines = [0]
        for index, char in enumerate(text):
            if char == '\n':
                self.lines.append(index + 1)

    def line_of(self, offset):
        low, high = 0, len(self.lines) - 1
        while low < high:
            middle = (low + high + 1) // 2
            if self.lines[middle] <= offset:
                low = middle
            else:
                high = middle - 1
        return low + 1

    def skip(self):
        while self.at < len(self.text) and self.text[self.at] in WHITESPACE:
            self.at += 1

    def string(self):
        """Read a JSON string starting at a quote; returns its value."""
        assert self.text[self.at] == '"'
        self.at += 1
        out = []
        while self.at < len(self.text):
            char = self.text[self.at]
            if char == '\\':
                nxt = self.text[self.at + 1:self.at + 2]
                out.append({'n': '\n', 't': '\t', 'r': '\r', 'b': '\b',
                            'f': '\f', '/': '/', '"': '"',
                            '\\': '\\'}.get(nxt, nxt))
                self.at += 2
                if nxt == 'u':
                    # \uXXXX -- the value does not matter for a path key here,
                    # only that the scan stays aligned.
                    self.at += 4
                continue
            if char == '"':
                self.at += 1
                return ''.join(out)
            out.append(char)
            self.at += 1
        return ''.join(out)

    def scalar(self):
        start = self.at
        while (self.at < len(self.text)
               and self.text[self.at] not in ',}]' + WHITESPACE):
            self.at += 1
        return self.text[start:self.at]

    def value(self, path, out):
        self.skip()
        if self.at >= len(self.text):
            return
        out.setdefault(tuple(path), self.line_of(self.at))
        char = self.text[self.at]

        if char == '{':
            self.at += 1
            while True:
                self.skip()
                if self.at >= len(self.text) or self.text[self.at] == '}':
                    self.at += 1
                    return
                if self.text[self.at] == ',':
                    self.at += 1
                    continue
                key_at = self.at
                key = self.string()
                out[tuple(path + [key])] = self.line_of(key_at)
                self.skip()
                if self.at < len(self.text) and self.text[self.at] == ':':
                    self.at += 1
                self.value(path + [key], out)
        elif char == '[':
            self.at += 1
            index = 0
            while True:
                self.skip()
                if self.at >= len(self.text) or self.text[self.at] == ']':
                    self.at += 1
                    return
                if self.text[self.at] == ',':
                    self.at += 1
                    continue
                self.value(path + [index], out)
                index += 1
        elif char == '"':
            self.string()
        else:
            self.scalar()


def locate(text):
    """{path tuple: 1-based line} for every value and key in the document.

    A path mixes keys and array indices, e.g. (4, 'iff:hasStrength', 0, 'value').
    A key's own line is recorded as well as its value's, because an attribute is
    selected by its name and that is the line a reader wants.
    """
    scanner = _Scanner(text)
    found = {}
    scanner.value([], found)
    return found


def entity_index(text, entity_id):
    """Where an entity with this id sits in the top-level array, or None."""
    import json

    document = json.loads(text)
    if not isinstance(document, list):
        document = [document]
    for index, entity in enumerate(document):
        if isinstance(entity, dict) and \
                str(entity.get('id') or entity.get('@id')) == entity_id:
            return index
    return None
