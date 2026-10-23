"""Real OCCT shapes exposed in a controlled order; no substitute geometry."""


class OrderedShapes:
    def __init__(self, *, edges=(), faces=(), reverse=False):
        self._edges = list(edges)
        self._faces = list(faces)
        self.reverse = reverse

    def edges(self):
        return list(reversed(self._edges)) if self.reverse else list(self._edges)

    def faces(self):
        return list(reversed(self._faces)) if self.reverse else list(self._faces)
