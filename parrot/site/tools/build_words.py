"""The parrot's starting memory of sounds (voice/words.json) and the preset questions' clips
(voice/questions/*.wav, voice/questions.json), made by hearing with the page's own host code
(parrotbrain.host: its sound cutting, records, mixing of takes and sound-to-word synapses).

1. Each word alone, each speaker alone: the word's takes heard one after another, four rounds for the
   woman's answer words, two for the man's question words, a fresh hearing layer for each, so two words
   never fold into one record. The woman's deepest record of each word is kept (the sound the parrot
   says); every record the man's takes made is kept (the sounds of his questions).
2. One memory: the records loaded as the page loads a saved memory, then each record's link to its
   word taught (`SoundMemory.link`), the lesson repeated until every record reads its word at LINK_MIN
   or more. The takes are not heard again here: a take heard in a memory of every word can fold into a
   near word's record and mix its sound into it.
3. The question clips: for each preset the man's takes of its words (for each word the take a copy of
   the memory hears most surely as the word), one after another with GAP seconds of quiet (slow, clear speech, as one speaks to a bird). Each clip is then heard RUNS times
   through a copy of the memory (the same hearing path), and the recognised words are logged.

Only takes Whisper (small.en) reads as their word are used (each folder's wer.json: {take: {text, heard}}).

    python tools/build_words.py WHEEL_DIR WOMAN_DIR MAN_DIR PRESETS.json OUT_DIR

PRESETS.json: ["what is this", ...]. OUT_DIR gets words.json, questions/<key>.wav, questions.json and
build_report.json.
"""
import json
import re
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

SITE = Path(__file__).resolve().parents[1]
sys.path.insert(0, sys.argv[1]); sys.path.insert(0, str(SITE / "pack" / "py"))
from cadence.speech.frontend import log_mel  # noqa: E402
from parrotbrain.host import Host  # noqa: E402
from parrotbrain.sounds import code, unpack  # noqa: E402

WOMAN, MAN = Path(sys.argv[2]), Path(sys.argv[3])
PRESETS, OUT = json.loads(Path(sys.argv[4]).read_text()), Path(sys.argv[5])
OUT.mkdir(parents=True, exist_ok=True); (OUT / "questions").mkdir(exist_ok=True)
VOCAB = sorted(w for w in json.loads((SITE / "pack" / "trained" / "spec.json").read_text())["codes"] if not w.startswith("<"))
SAME = {"wood": {"would"}, "no": {"know"}, "right": {"write", "rite"}, "red": {"read"}, "blue": {"blew"}, "colour": {"color"}}
GAP, LINK_MIN, RUNS, LESSON = 0.45, 0.8, 5, 19.0
blank = np.zeros(16 * 8 * 3, np.uint8)


def heard_words(text):
    return re.sub(r"[^a-z ]", " ", text.lower()).split()


def takes_of(d, wanted=None):
    meta = json.loads((d / "meta.json").read_text())["takes"]; heard = json.loads((d / "wer.json").read_text())
    out = {}
    for name in meta:
        w = name.rsplit("_", 1)[0]
        if w not in VOCAB or (wanted and w not in wanted):
            continue
        got = heard_words(heard.get(name, {}).get("heard", ""))
        if got == [w] or (len(got) == 1 and got[0] in SAME.get(w, ())):
            out.setdefault(w, []).append(d / f"{name}.wav")
    return out


def read16(path):
    raw = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(path), "-ac", "1", "-ar", "16000", "-f", "s16le", "-"], capture_output=True, check=True).stdout
    a = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
    return a / (np.abs(a).max() + 1e-9) * 0.5


def host():
    return Host({"eye": {"w": 16, "h": 8}, "files": None, "revise": 0.7, "words": VOCAB})


def feed(h, samples, t):
    """Samples through the hearing layer's moments (1,600 samples and ten log-mel frames each, as the page
    sends them); the sounds it heard, in order."""
    samples = np.concatenate([samples, np.zeros(1600 - len(samples) % 1600, np.float32)])
    allf = np.asarray(log_mel(np.concatenate([samples, np.zeros(400, np.float32)])), np.float32)
    got = []
    for i in range(0, len(samples), 1600):
        frames = allf[i // 160: i // 160 + 10]
        if len(frames) < 10:
            break
        t[0] += 1
        o = h.step({"t": t[0], "reward": 0.0, "voice_ok": False, "things": 0, "focus_kind": None},
                   {"left": blank, "right": blank, "proprio": np.zeros(22, np.float32), "mel": frames.reshape(-1), "pcm": samples[i: i + 1600].astype(np.float32)})
        got += o.get("heard_sounds", [])
    return got


def pad(a, before=0.25, after=0.6):
    return np.concatenate([np.zeros(int(before * 16000), np.float32), a, np.zeros(int(after * 16000), np.float32)])


report = {"vocab": VOCAB}
woman = takes_of(WOMAN)
man_words = sorted({w for q in PRESETS for w in q.split()})
man = takes_of(MAN, set(man_words))
report["woman_takes"] = {w: [f.name for f in v] for w, v in woman.items()}
report["man_takes"] = {w: [f.name for f in v] for w, v in man.items()}
report["man_missing"] = [w for w in man_words if w not in man]
print("woman", len(woman), "words; man", len(man), "words; man missing", report["man_missing"], flush=True)
if report["man_missing"]:
    sys.exit("a preset's word has no take Whisper reads as the word")

# 1. each word alone
records, origin = [], []
for speaker, table, rounds in (("woman", woman, 4), ("man", man, 2)):
    for w, files in table.items():
        h, t = host(), [0]
        audio = [read16(f) for f in files]
        for _ in range(rounds):
            for a in audio:
                feed(h, pad(a), t)
            feed(h, np.zeros(16000, np.float32), t)
        saved = h.handle({"command": "memory"})["saved"]["records"]
        if not saved:
            print("no record", speaker, w, flush=True); continue
        keep = [int(np.argmax([r["deep"] for r in saved]))] if speaker == "woman" else range(len(saved))
        for k in keep:
            records.append(saved[k]); origin.append({"speaker": speaker, "word": w, "deep": round(saved[k]["deep"], 2)})
        print(speaker, w, len(files), "takes ->", len(saved), "records", [round(r["deep"], 2) for r in saved], flush=True)

# 2. one memory, each record linked to its word
h = host()
h.handle({"command": "remember", "saved": {"records": records}})
keys = h.mem.records.keys[: h.mem.records.count]
slot_of = [int(np.argmax(keys @ code(unpack(np.asarray(r["value"], np.float64))))) for r in records]  # each record's slot, by its key
slot_word = {slot_of[i]: o["word"] for i, o in enumerate(origin)}
speaker_of = {str(slot_of[i]): o["speaker"] for i, o in enumerate(origin)}
print("loaded", h.mem.records.count, "of", len(records), flush=True)
for epoch in range(1000):
    h.mem.synapses.reset(1)  # the consolidated links: what a saved memory keeps
    reads = h.mem.reads()
    own = np.array([reads[s][VOCAB.index(w)] for s, w in slot_word.items()])
    if all(h.mem.word_of(s, reads)[0] == w for s, w in slot_word.items()) and own.min() >= LINK_MIN:
        break
    for s in np.random.default_rng(epoch).permutation(sorted(slot_word)):
        h.mem.link(int(s), slot_word[int(s)], LESSON)
report["link_lessons"] = epoch
report["link_min"] = round(float(own.min()), 3)
saved = h.handle({"command": "memory"})["saved"]
links = {str(s): h.mem.word_of(s, reads)[0] for s in range(h.mem.records.count)}
report["records"] = [{"slot": s, "speaker": speaker_of.get(str(s)), "word": links[str(s)], "link": h.mem.word_of(s, reads)[1],
                      "deep": round(float(h.mem.records.deep[s]), 2), "sayable": s in h.mem.sayable()} for s in range(h.mem.records.count)]
report["says"] = {w: speaker_of.get(str(h.mem.recall(w, reads)[0])) for w in VOCAB if h.mem.recall(w, reads)[0] is not None}
print("lessons", epoch, "min link", report["link_min"], "says", report["says"], flush=True)
(OUT / "words.json").write_text(json.dumps({
    "voice": "the starting words, taught by hearing: a woman's voice says each answer word, a man's voice each question word (Chatterbox, Resemble AI, MIT; the man's voice cloned from an Orpheus voice; only takes Whisper reads as the word); each word's takes heard by the page's hearing layer, then each record linked to its word",
    "memory": saved, "links": links, "speakers": speaker_of}))

# 3. the question clips, heard through a copy of the memory. For each word the man's take the memory
# hears most surely as that word (heard alone in a fresh copy: recognised as the word, nearest its record)
qmap, recog = {}, {}
best = {}
for w in man_words:
    scored = []
    for f in man[w]:
        hc, tc = host(), [0]
        hc.handle({"command": "remember", "saved": saved})
        right, dist = 0, []
        for _ in range(3):  # heard three times over, as a preset asked again
            got = feed(hc, pad(read16(f)), tc)
            right += len(got) == 1 and got[0].get("word") == w
            if hc.events and hc.events[-1].get("write"):
                dist.append(hc.events[-1]["write"]["distance"] or 0.0)
        scored.append((-right, float(np.mean(dist)) if dist else 9.0, f))
    best[w] = min(scored, key=lambda x: (x[0], x[1]))[2]
report["clip_takes"] = {w: f.name for w, f in best.items()}
print("clip takes", report["clip_takes"], flush=True)
for q in PRESETS:
    parts = [np.zeros(int(0.3 * 16000), np.float32)]
    for w in q.split():
        parts += [read16(best[w]), np.zeros(int(GAP * 16000), np.float32)]
    clip = np.concatenate(parts + [np.zeros(int(0.5 * 16000), np.float32)])
    key = q.replace(" ", "_")
    with wave.open(str(OUT / "questions" / f"{key}.wav"), "wb") as fh:
        fh.setnchannels(1); fh.setsampwidth(2); fh.setframerate(16000); fh.writeframes((np.clip(clip, -1, 1) * 32767).astype(np.int16).tobytes())
    qmap[q] = f"questions/{key}.wav"
h2, t2 = host(), [0]
h2.handle({"command": "remember", "saved": saved})
for _ in range(RUNS):
    for q in PRESETS:
        recog.setdefault(q, []).append([g.get("word") for g in feed(h2, read16(OUT / qmap[q]), t2)])
        feed(h2, np.zeros(8000, np.float32), t2)
report["recognition"] = {q: {"runs": v, "right": sum(r == q.split() for r in v)} for q, v in recog.items()}
report["recognition_rate"] = round(float(np.mean([r == q.split() for q, v in recog.items() for r in v])), 3)
(OUT / "questions.json").write_text(json.dumps({"questions": qmap, "voice": "a man's voice (Chatterbox, Resemble AI, MIT), each word its own take, joined with short pauses"}, indent=1))
(OUT / "build_report.json").write_text(json.dumps(report, indent=1))
print("recognition", report["recognition_rate"], {q: v["right"] for q, v in report["recognition"].items()}, flush=True)
