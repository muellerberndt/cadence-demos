"""The parrot's starting memory of sounds (voice/words.json) and the questions' clips (voice/questions/*.wav,
voice/questions.json), made by hearing with the page's own host code (parrotbrain.host: its cutting of
utterances, records, mixing of takes and sound-to-meaning synapses).

The ear's unit is the utterance. A woman's voice says each answer word alone ("Apple.") and each question as a
natural sentence ("What colour is this?"); only takes Whisper (small.en) reads as their text are used.

1. Each utterance alone: its takes heard one after another (three rounds for a word, two for a phrase), a fresh
   hearing layer for each, so two utterances never fold into one record. For a word the deepest record is kept
   (the sound the parrot says, and of which its own rendering is made); for a phrase every record its takes
   made. Each record keeps where its words begin on its own timeline (`marks`): the timeline is that of the
   take that made the record, and the words' times in that take are Whisper's.
2. One memory: the records loaded as the page loads a saved memory, then each record's link to its meaning
   taught (`SoundMemory.link`): a word's record to the word, a phrase's record to the question its brain was
   taught (PHRASES.json `meaning`, a sequence of its words: "What colour?" and "What colour is this?" both
   to "what colour is this"; "Where is it?" to "where is the <this>", the thing in focus). The lesson is
   repeated until every record reads its meaning at LINK_MIN or more, clear of every other.
3. The questions' clips: for each phrase the take a copy of the memory hears most surely (each take heard once). Each clip
   is then heard RUNS times through a copy of the memory (the same hearing path); the meaning its record
   links to and the words the follower knew as they were spoken are logged.

Other voices (--more DIR ...): the parrot has also heard other people ask the same questions and name the
things, so a visitor's voice finds records near it. Each of their takes is heard once, alone (a record heard
once: kept, linked to its meaning, too shallow to be said back; its audio is not shipped).

    python tools/build_words.py WHEEL_DIR WORDS_DIR PHRASES_DIR PHRASES.json OUT_DIR [PACK_PY] [--more DIR ...]

WORDS_DIR, PHRASES_DIR: takes (<key>_<k>.wav), meta.json and wer.json ({take: {text, heard, words: [{word, start}]}}).
PHRASES.json: {"phrases": {key: {text, meaning, spoken}}, "presets": [{key, focus}]}; `spoken` lists, for each
spoken word, the words of the meaning that begin with it. OUT_DIR gets words.json, questions/<key>.wav,
questions.json and build_report.json.
"""
import json
import re
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

SITE = Path(__file__).resolve().parents[1]
MORE = [Path(a) for a in sys.argv[sys.argv.index("--more") + 1:]] if "--more" in sys.argv else []
if "--more" in sys.argv:
    del sys.argv[sys.argv.index("--more"):]
PACK_PY = Path(sys.argv[6]) if len(sys.argv) > 6 else SITE / "pack" / "py"
sys.path.insert(0, sys.argv[1]); sys.path.insert(0, str(PACK_PY))
from cadence.speech.frontend import log_mel  # noqa: E402
from parrotbrain import host as hostmod  # noqa: E402
from parrotbrain.host import Host  # noqa: E402
from parrotbrain.sounds import CLEAR, code  # noqa: E402
from parrotbrain.trained import question_forms  # noqa: E402

WORDS_DIR, PHRASES_DIR = Path(sys.argv[2]), Path(sys.argv[3])
SPEC, OUT = json.loads(Path(sys.argv[4]).read_text()), Path(sys.argv[5])
PHRASES, PRESETS = SPEC["phrases"], SPEC["presets"]
OUT.mkdir(parents=True, exist_ok=True); (OUT / "questions").mkdir(exist_ok=True)
BRAIN = json.loads((SITE / "pack" / "trained" / "spec.json").read_text())
VOCAB = sorted(w for w in BRAIN["codes"] if not w.startswith("<"))
FORMS, OFFER = question_forms(BRAIN)
UNITS = VOCAB + FORMS
SAME = {"wood": {"would"}, "no": {"know"}, "right": {"write", "rite"}, "red": {"read"}, "blue": {"blew"}}
MODEL = {k: json.loads((d / "meta.json").read_text()).get("model", "") for k, d in (("words", WORDS_DIR), ("phrases", PHRASES_DIR))}
LINK_MIN, RUNS, LESSON, BEFORE = 0.8, 2, 19.0, 0.25
blank = np.zeros(16 * 8 * 3, np.uint8)
norm = lambda t: re.sub(r"[^a-z ]", " ", t.lower().replace("color", "colour")).split()  # noqa: E731


def takes_of(d, wanted):
    """{key: [(path, whisper words)]}: the takes Whisper reads as their text."""
    meta = json.loads((d / "meta.json").read_text())["takes"]; heard = json.loads((d / "wer.json").read_text())
    out = {}
    for name, m in meta.items():
        key = m.get("key") or name.rsplit("_", 1)[0]
        if key not in wanted:
            continue
        got, text = norm(heard.get(name, {}).get("heard", "")), norm(m["text"])
        if got == text or (len(text) == 1 and len(got) == 1 and got[0] in SAME.get(text[0], ())):
            out.setdefault(key, []).append((d / f"{name}.wav", heard[name].get("words", [])))
    return out


def read16(path):
    raw = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(path), "-ac", "1", "-ar", "16000", "-f", "s16le", "-"], capture_output=True, check=True).stdout
    a = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
    return a / (np.abs(a).max() + 1e-9) * 0.5


def host():
    return Host({"eye": {"w": 16, "h": 8}, "files": None, "revise": 0.7, "words": UNITS, "offer": OFFER})


def feed(h, samples, t, mode=None):
    """Samples through the hearing layer's moments (1,600 samples and ten log-mel frames each, as the page
    sends them); the sounds it heard and the words its follower knew, in order."""
    samples = np.concatenate([samples, np.zeros((-len(samples)) % 1600, np.float32)])
    allf = np.asarray(log_mel(np.concatenate([samples, np.zeros(400, np.float32)])), np.float32)
    got, spotted = [], []
    for i in range(0, len(samples), 1600):
        frames = allf[i // 160: i // 160 + 10]
        if len(frames) < 10:
            break
        t[0] += 1
        o = h.step({"t": t[0], "reward": 0.0, "voice_ok": False, "things": 0, "focus_kind": None, "mode": mode},
                   {"left": blank, "right": blank, "proprio": np.zeros(22, np.float32), "mel": frames.reshape(-1), "pcm": samples[i: i + 1600].astype(np.float32)})
        got += o.get("heard_sounds", [])
        spotted += [{**s, "stream": (t[0] - 1) * 10} for s in o.get("spotted", [])]
    return got, spotted


def pad(a, before=BEFORE, after=0.7):
    return np.concatenate([np.zeros(int(before * 16000), np.float32), a, np.zeros(int(after * 16000), np.float32)])


def marks_of(spoken, whisper_words, take_at, utterance_at, frames):
    """Where each word of the meaning begins on the record's timeline: the spoken words' starts (Whisper's times
    in the take, the first at the record's start), each spoken word's meaning words spread over its span."""
    if len(whisper_words) == len(spoken):
        starts = [max(0, int(round(take_at + 100 * w["start"] - utterance_at))) for w in whisper_words]
    else:  # no word times: an even split
        starts = [int(round(8 + (frames - 16) * k / len(spoken))) for k in range(len(spoken))]
    starts[0] = 0
    starts = [min(s, frames - 1) for s in starts] + [frames]
    out = []
    for k, group in enumerate(spoken):
        for j, w in enumerate(group):
            out.append([int(starts[k] + (starts[k + 1] - starts[k]) * j / len(group)), w])
    return out


report = {"units": len(UNITS), "questions": FORMS}
words = takes_of(WORDS_DIR, set(VOCAB))
phrases = takes_of(PHRASES_DIR, set(PHRASES))
report["word_takes"] = {w: [f.name for f, _ in v] for w, v in words.items()}
report["phrase_takes"] = {w: [f.name for f, _ in v] for w, v in phrases.items()}
missing = [k for k in PHRASES if k not in phrases] + [p["key"] for p in PRESETS if p["key"] not in PHRASES]
print("words", len(words), "phrases", len(phrases), "missing", missing, flush=True)
if missing:
    sys.exit("a phrase has no take Whisper reads as its text")
for key, p in PHRASES.items():
    said = [w for g in p["spoken"] for w in g]
    assert p["meaning"] in FORMS and said == p["meaning"].split()[: len(said)], (key, said)

# 1. each utterance alone
records, origin = [], []
for kind, table, rounds in (("word", words, 3), ("phrase", phrases, 2)):
    for key, files in table.items():
        h, t = host(), [0]
        audio = [read16(f) for f, _ in files]
        owner = {}  # the take that made each record: its timeline is the record's
        for r in range(rounds):
            for k, a in enumerate(audio):
                at = t[0] * 10 + int(BEFORE * 100)
                got, _ = feed(h, pad(a), t)
                if len(got) == 1 and not got[0]["known"]:
                    owner[got[0]["slot"]] = (k, at, h.events[-1]["start"], h.events[-1]["frames"])
            feed(h, np.zeros(16000, np.float32), t)
        saved = h.handle({"command": "memory"})["saved"]["records"]
        if not saved:
            print("no record", kind, key, flush=True); continue
        keep = [int(np.argmax([r["deep"] for r in saved]))] if kind == "word" else range(len(saved))
        for s in keep:
            rec = saved[s]
            if kind == "word":
                rec["marks"], meaning = [[0, key]], key
            else:
                meaning = PHRASES[key]["meaning"]
                k, at, start, frames = owner.get(s, (0, 0, 0, len(rec["frames"])))
                rec["marks"] = marks_of(PHRASES[key]["spoken"], files[k][1] if s in owner else [], at, start, len(rec["frames"]))
            records.append(rec); origin.append({"kind": kind, "key": key, "meaning": meaning, "deep": round(rec["deep"], 2), "frames": len(rec["frames"]), "marks": rec["marks"]})
        print(kind, key, len(files), "takes ->", len(saved), "records", [round(r["deep"], 2) for r in saved], flush=True)

# the other voices: each take heard once, alone
THINGS = sorted(k for k in BRAIN["kinds"] if k in VOCAB)
report["other_voices"] = {}
for d in MORE:
    made = 0
    for kind, table, most in (("word", takes_of(d, set(THINGS)), 1), ("phrase", takes_of(d, set(PHRASES)), 2)):
        for key, files in table.items():
            for f, said in files[:most]:
                h, t = host(), [0]
                at = int(BEFORE * 100)
                got, _ = feed(h, pad(read16(f)), t)
                saved = h.handle({"command": "memory"})["saved"]["records"]
                if len(got) != 1 or len(saved) != 1:
                    print("not one sound", d.name, f.name, flush=True); continue
                rec = saved[0]
                rec["pcm"] = []  # heard, not said: its audio is not shipped
                meaning = key if kind == "word" else PHRASES[key]["meaning"]
                rec["marks"] = [[0, key]] if kind == "word" else marks_of(PHRASES[key]["spoken"], said, at, h.events[-1]["start"], len(rec["frames"]))
                records.append(rec); origin.append({"kind": kind, "key": key, "meaning": meaning, "deep": round(rec["deep"], 2), "frames": len(rec["frames"]), "marks": rec["marks"], "voice": d.name})
                made += 1
    report["other_voices"][d.name] = made
    print("other voice", d.name, made, "records", flush=True)

# 2. one memory, each record linked to its meaning
h = host()
h.handle({"command": "remember", "saved": {"format": 2, "records": records}})
keys = h.mem.records.keys[: h.mem.records.count]
slot_of = [int(np.argmax(keys @ code(np.asarray(r["frames"], np.float64)))) for r in records]  # each record's slot, by its key
assert len(set(slot_of)) == len(records) == h.mem.records.count, (len(set(slot_of)), len(records), h.mem.records.count)
slot_meaning = {slot_of[i]: o["meaning"] for i, o in enumerate(origin)}
kind_of = {str(slot_of[i]): o["kind"] for i, o in enumerate(origin)}
voice_of = {str(slot_of[i]): o.get("voice", "woman") for i, o in enumerate(origin)}
key_of = {str(slot_of[i]): o["key"] for i, o in enumerate(origin)}
print("loaded", h.mem.records.count, "of", len(records), flush=True)
for epoch in range(2000):
    h.mem.synapses.reset(1); h.mem._changed()  # the consolidated links: what a saved memory keeps
    reads = h.mem.reads()
    own = np.array([reads[s][UNITS.index(w)] for s, w in slot_meaning.items()])
    rest = np.array([np.max(np.delete(reads[s], UNITS.index(w))) for s, w in slot_meaning.items()])
    if all(h.mem.word_of(s, reads)[0] == w for s, w in slot_meaning.items()) and own.min() >= LINK_MIN and (own - rest).min() >= 2 * CLEAR:
        break
    for s in np.random.default_rng(epoch).permutation(sorted(slot_meaning)):
        h.mem.link(int(s), slot_meaning[int(s)], LESSON)
report["link_lessons"] = epoch
report["link_min"] = round(float(own.min()), 3)
report["link_clear_min"] = round(float((own - rest).min()), 3)
saved = h.handle({"command": "memory"})["saved"]
links = {str(s): h.mem.word_of(s, reads)[0] for s in range(h.mem.records.count)}
report["records"] = [{"slot": s, "kind": kind_of.get(str(s)), "key": key_of.get(str(s)), "voice": voice_of.get(str(s)), "meaning": links[str(s)], "link": h.mem.word_of(s, reads)[1],
                      "deep": round(float(h.mem.records.deep[s]), 2), "sayable": s in h.mem.sayable(), "marks": h.mem.marks.get(s)} for s in range(h.mem.records.count)]
report["says"] = sorted(w for w in VOCAB if h.mem.recall(w, reads)[0] is not None)
print("lessons", epoch, "min link", report["link_min"], "clear", report["link_clear_min"], "says", len(report["says"]), "words", flush=True)
(OUT / "words.json").write_text(json.dumps({
    "voice": f"the starting sounds, taught by hearing: a woman's voice says each answer word alone ({MODEL['words']}) and each question as a natural sentence ({MODEL['phrases']}); only takes Whisper reads as their text; each utterance's takes heard by the page's hearing layer, then each record linked to its meaning (a word, or the question its brain was taught)" + (f"; and {len(MORE)} other voices heard once each asking the same questions and naming the things (their audio is not shipped)" if MORE else ""),
    "memory": saved, "links": links, "kinds": kind_of, "keys": key_of, "voices": voice_of}))

# 3. the questions' clips: for each phrase the take a copy of the memory hears most surely
qmap, texts, best, follow, ends = {}, {}, {}, {}, {}
hc, tc = host(), [0]
hc.handle({"command": "remember", "saved": saved})
for key in PHRASES:
    scored = []
    for f, _ in phrases[key]:  # each take heard once by a copy of the memory
        got, _ = feed(hc, pad(read16(f)), tc)
        right = len(got) == 1 and got[0].get("word") == PHRASES[key]["meaning"]
        dist = hc.events[-1]["write"]["distance"] if hc.events and hc.events[-1].get("write") else 9.0
        scored.append((-int(right), float(dist or 0.0), f))
    best[key] = min(scored, key=lambda x: (x[0], x[1]))
    clip = np.concatenate([np.zeros(int(0.15 * 16000), np.float32), read16(best[key][2]), np.zeros(int(0.5 * 16000), np.float32)])
    with wave.open(str(OUT / "questions" / f"{key}.wav"), "wb") as fh:
        fh.setnchannels(1); fh.setsampwidth(2); fh.setframerate(16000); fh.writeframes((np.clip(clip, -1, 1) * 32767).astype(np.int16).tobytes())
    qmap[key] = f"questions/{key}.wav"; texts[key] = PHRASES[key]["text"]
    # when each word of the meaning begins in the clip (the spoken words' starts by Whisper, as the marks), for the page's checks
    said = next(w for f, w in phrases[key] if f == best[key][2]); spoken = PHRASES[key]["spoken"]; length = len(read16(best[key][2])) / 16000
    if len(said) == len(spoken):
        starts = [0.0] + [float(w["start"]) for w in said[1:]] + [length]
        follow[key] = [[round(0.15 + starts[k] + (starts[k + 1] - starts[k]) * j / len(g), 3), w] for k, g in enumerate(spoken) for j, w in enumerate(g)]
    ends[key] = round(0.15 + length, 3)
report["clip_takes"] = {k: {"take": v[2].name, "right": bool(-v[0]), "distance": round(v[1], 3)} for k, v in best.items()}
print("clip takes", {k: (v["take"], v["right"]) for k, v in report["clip_takes"].items()}, flush=True)
h2, t2 = host(), [0]
h2.handle({"command": "remember", "saved": saved})
recog = {}
for _ in range(RUNS):
    for key in PHRASES:
        at = t2[0] * 10
        got, spotted = feed(h2, read16(OUT / qmap[key]), t2)
        recog.setdefault(key, []).append({"meaning": [g.get("word") for g in got], "spotted": [s["word"] for s in spotted]})
        feed(h2, np.zeros(8000, np.float32), t2)
report["recognition"] = {k: {"runs": v, "right": sum(r["meaning"] == [PHRASES[k]["meaning"]] for r in v),
                             "spotted_right": sum(r["spotted"] == [w for g in PHRASES[k]["spoken"] for w in g] for r in v)} for k, v in recog.items()}
n = sum(len(v) for v in recog.values())
report["recognition_rate"] = round(sum(v["right"] for v in report["recognition"].values()) / n, 3)
report["spotted_rate"] = round(sum(v["spotted_right"] for v in report["recognition"].values()) / n, 3)
(OUT / "questions.json").write_text(json.dumps({
    "voice": f"a woman's voice ({MODEL['phrases']}), each question a natural sentence",
    "questions": {k: {"text": texts[k], "clip": qmap[k], "meaning": PHRASES[k]["meaning"], "follow": follow.get(k), "speech_end": ends[k]} for k in PHRASES},
    "presets": [{**p, "text": texts[p["key"]], "clip": qmap[p["key"]]} for p in PRESETS]}, indent=1))
(OUT / "build_report.json").write_text(json.dumps(report, indent=1))
print("recognition", report["recognition_rate"], "spotted", report["spotted_rate"], {k: (v["right"], v["spotted_right"]) for k, v in report["recognition"].items()}, flush=True)
