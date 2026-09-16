# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The index stems each distinct word once (#2626)."""

from plugin.modules.writer_index.services.index import _MemoStemmer


class Counting:
    def __init__(self):
        self.calls = 0

    def stemWord(self, word):
        self.calls += 1
        return word.rstrip("s")


def test_each_word_is_stemmed_once():
    inner = Counting()
    memo = _MemoStemmer(inner)
    words = ["whales", "whale", "whales", "sea", "whales"]
    assert [memo.stemWord(w) for w in words] == [
        "whale", "whale", "whale", "sea", "whale"]
    assert inner.calls == 3


def test_table_is_bounded():
    inner = Counting()
    memo = _MemoStemmer(inner)
    memo.MAX = 10
    for i in range(25):
        memo.stemWord("w%d" % i)
    assert len(memo._stems) <= 10
