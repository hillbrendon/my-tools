"""Build short definitions for Runes answers (public/runes/definitions.json).

Run by hand after build_runes_words.py:  python scripts/build_runes_definitions.py

Source: WordNet 3.1, Princeton University (https://wordnet.princeton.edu). Its licence allows
use and redistribution with this notice: "WordNet 3.1 Copyright 2011 by Princeton University.
All rights reserved." The full licence is in the WordNet data files.

For each answer, picks the part of speech WordNet sees most often in its tagged texts, then keeps
its first two senses (without example sentences). Words WordNet doesn't know get no definition.
The output is sorted alphabetically so it doesn't reveal the order of daily answers.
"""
import base64
import io
import json
import re
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "public" / "runes"
WORDNET_URL = "https://wordnetcode.princeton.edu/wn3.1.dict.tar.gz"
POS = [("noun", "noun"), ("verb", "verb"), ("adj", "adjective"), ("adv", "adverb")]
MAX_SENSES = 2
MAX_LEN = 140


def main():
    words_js = (ROOT / "words.js").read_text(encoding="utf-8")
    encoded = re.search(r'RUNES_ANSWERS = "([^"]+)"', words_js).group(1)
    joined = base64.b64decode(encoded).decode()
    answers = [joined[i:i + 5] for i in range(0, len(joined), 5)]

    req = urllib.request.Request(WORDNET_URL, headers={"User-Agent": "fenrir-forge definitions builder"})
    with urllib.request.urlopen(req, timeout=120) as r:
        tar = tarfile.open(fileobj=io.BytesIO(r.read()), mode="r:gz")
    files = {Path(m.name).name: tar.extractfile(m).read().decode("latin-1") for m in tar.getmembers() if m.isfile()}

    index = {}  # word -> list of (tagged_count, pos_order, pos, offsets)
    for order, (pos, _) in enumerate(POS):
        for line in files[f"index.{pos}"].splitlines():
            if line.startswith(" "):
                continue  # licence header
            parts = line.split()
            lemma, synset_cnt, ptr_cnt = parts[0], int(parts[2]), int(parts[3])
            tagged = int(parts[5 + ptr_cnt])
            offsets = parts[6 + ptr_cnt:6 + ptr_cnt + synset_cnt]
            index.setdefault(lemma, []).append((tagged, -order, pos, offsets))

    # Irregular forms, e.g. "threw throw" in verb.exc
    irregular = {}
    for pos, label in POS:
        for line in files[f"{pos}.exc"].splitlines():
            parts = line.split()
            if len(parts) >= 2:
                irregular.setdefault(parts[0], (label, parts[1]))

    def gloss(pos, offset, word):
        """Definition for one sense, or None if that sense is a proper name (e.g. Saint Basil)."""
        data = files[f"data.{pos}"]
        start = data.index("\n" + offset + " ") + 1
        line = data[start:data.index("\n", start)]
        fields = line.split(" | ", 1)[0].split()
        lemmas = fields[4:4 + 2 * int(fields[3], 16):2]
        if any(l.lower() == word and l[0].isupper() for l in lemmas):
            return None
        text = line.split(" | ", 1)[1].strip()
        text = re.split(r';\s*"', text)[0].strip().rstrip(";").strip()  # drop example sentences
        if len(text) > MAX_LEN:
            text = text[:MAX_LEN].rsplit(" ", 1)[0] + "…"
        return text[:1].upper() + text[1:]

    out, missing = {}, []
    for w in sorted(answers):
        entries = index.get(w)
        if not entries:
            if w in irregular:
                label, base = irregular[w]
                form = "past tense or past participle" if label == "verb" else "form"
                if label == "noun":
                    form = "plural"
                out[w] = {"pos": label, "senses": [f"{form[:1].upper() + form[1:]} of “{base}”"]}
            else:
                missing.append(w)
            continue
        # Most-used part of speech first; fall back to the next if it only has proper-name senses.
        for _, _, pos, offsets in sorted(entries, reverse=True):
            senses = list(dict.fromkeys(g for g in (gloss(pos, o, w) for o in offsets) if g))[:MAX_SENSES]
            if senses:
                out[w] = {"pos": dict(POS)[pos], "senses": senses}
                break
        else:
            missing.append(w)

    (ROOT / "definitions.json").write_text(json.dumps(out, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    print(f"{len(out)} definitions, {len(missing)} words without one: {' '.join(missing)}")


if __name__ == "__main__":
    main()
