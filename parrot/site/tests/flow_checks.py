"""The longer sections of tests/test_sound_symbols.py: a first visit with what is on screen alone, the visitors'
usability matrix, false triggers, robustness, and the parrot with no words yet. `T` is that module (its page
helpers); every section writes its rows into the report and returns whether it passed."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

import room

RUN = 3        # right answers running that count as understood
TRIALS = 10    # at most, a question


def pad(x, before=0.25, after=0.3):
    return np.concatenate([np.zeros(int(before * 16000), np.float32), np.asarray(x, np.float32), np.zeros(int(after * 16000), np.float32)])


class Room:
    """A visitor's microphone: clean, or a laptop's in a room (noise all the time at `snr` dB below the voice's
    usual level, each utterance band-limited, reverberated and moved up to 6 dB either way)."""

    def __init__(self, T, page, cond: str, seed: int):
        self.T, self.page, self.cond, self.rng = T, page, cond, np.random.default_rng(seed)
        self.snr = {"clean": None, "lap20": 20.0, "lap10": 10.0}[cond]
        self.level = 0.11  # the loud part of a take at peak 0.5, about
        if self.snr is not None:  # the room's noise, all the time, from before anything is said
            bed = room.noise_like(16000 * 20, self.rng) * self.level / (10 ** (self.snr / 20))
            T.hear_loop(page, bed)
            page.wait_for_timeout(4000)  # the ear learns the room's level

    def say(self, take: Path) -> dict:
        x = self.T.read16(take)
        gain = 0.0
        if self.snr is not None:
            gain = float(self.rng.uniform(-6, 6))
            x = room.laptop(x, self.rng, snr_db=99.0, gain_db=gain)
        got = self.T.hear(self.page, pad(x))
        got.update(speech_end=got["startedAt"] + 1000 * (0.25 + len(x) / 16000), gain_db=round(gain, 1))
        return got


# --- the say-back's delay --------------------------------------------------------------------------------
SAY_BACK_MS = 1500         # each say-back starts within this of the end of the utterance
SAY_BACK_MEDIAN_MS = 1200  # and the middle one of a pass within this
FIRST_HEARD = ("apple", "cup", "white", "what_colour", "what_is_this", "where_is_it")


def first_hearings(pw, a, T, voice: Path, busy: int) -> dict:
    """Listen to me, a fresh page: several utterances in a voice in no record, each heard for the first time. Each
    is kept as one utterance and said back about a second after its end. `busy`: that many processes keep a core
    busy each meanwhile (a loaded machine)."""
    burners = [subprocess.Popen([sys.executable, "-c", "while True: pass"]) for _ in range(busy)]
    try:
        takes = T.takes(voice)
        browser, ctx, page, logs, t0 = T.open_page(pw, a.url, a.out / "quiet.wav")
        mic = Room(T, page, "clean", seed=1)
        T.set_flow(page, "listen")
        rows = []
        for key in FIRST_HEARD:
            T.quiet_for(page)
            page.wait_for_timeout(600)
            t = T.now(page)
            sound = mic.say(takes[key][0])
            got = T.heard_after(page, t, 15)
            page.wait_for_timeout(2600)
            said = page.evaluate("(t) => window.parrotPage.flow.said.filter((s) => s.at > t && s.echo)", t)
            ms = round(said[0]["at"] - sound["speech_end"]) if said else None
            rows.append({"key": key, "heard": len(got), "first_heard": bool(got) and not got[0].get("known"), "said_back": bool(said) and bool(got) and said[0]["slot"] == got[0]["slot"],
                         "said_back_ms": ms, "ok": len(got) == 1 and bool(said) and said[0]["slot"] == got[0]["slot"] and ms is not None and ms <= SAY_BACK_MS})
        ctx.close(); browser.close()
    finally:
        for b in burners:
            b.kill()
    ms = [r["said_back_ms"] for r in rows if r["said_back_ms"] is not None]
    median = None if not ms else round(float(np.median(ms)))
    return {"busy_processes": busy, "load_1min": round(os.getloadavg()[0], 1), "rows": rows, "said_back_ms": {"min": min(ms) if ms else None, "median": median, "max": max(ms) if ms else None},
            "ok": all(r["ok"] for r in rows) and median is not None and median <= SAY_BACK_MEDIAN_MS}


def _spoken_since(page, t):
    return page.evaluate("(t) => (window.parrotPage.trained.spoken || []).filter((s) => s.at > t && s.answer)", t)


# --- a first visit ---------------------------------------------------------------------------------------
def first_visit(pw, a, T) -> dict:
    """Only what is on screen is used: the switch, the question list and Ask, the Pistachio button; and the
    visitor's own voice."""
    voice = sorted(p for p in a.voices.iterdir() if p.is_dir())[0]
    takes = T.takes(voice)
    browser, ctx, page, logs, t0 = T.open_page(pw, a.url, a.out / "quiet.wav")
    steps = []
    seen = lambda sel: page.is_visible(sel)  # noqa: E731
    steps.append({"step": "the switch, the question list, Ask, Pistachio and the microphone button are on screen",
                  "ok": all(seen(s) for s in ("#flow-mode .seg[data-flow=listen]", "#flow-mode .seg[data-flow=curious]", "#ask-preset", "#ask-form button[type=submit]", "#ask-nut", "#ask-mic")),
                  "mic": page.evaluate("document.body.dataset.mic")})
    page.click("#flow-mode .seg[data-flow=listen]")
    page.wait_for_timeout(700)
    steps.append({"step": "Listen to me pressed: the question list goes, the parrot looks at you", "ok": page.evaluate("window.parrotPage.flow.mode") == "listen" and not seen("#ask-preset") and not page.evaluate("document.getElementById('you-focus').hidden")})
    t = T.now(page)
    T.hear(page, pad(T.read16(takes["apple"][0])))
    ear = False
    for _ in range(40):
        ear = ear or page.evaluate("document.body.dataset.hearing") == "1"
        page.wait_for_timeout(50)
    got = T.heard_after(page, t, 20)
    page.wait_for_timeout(3000)
    said = page.evaluate("(t) => window.parrotPage.flow.said.filter((s) => s.at > t)", t)
    steps.append({"step": "a word said: the ear's sign lights while it is said; it is kept as one utterance and said back", "ear_sign": ear, "heard": len(got),
                  "taken_for": got[0].get("word") if got else None, "said_back": bool(said and said[0]["echo"]), "ok": ear and len(got) == 1 and bool(said and said[0]["echo"])})
    page.click("#flow-mode .seg[data-flow=curious]")
    steps.append({"step": "Curious pressed: the question list is back", "ok": page.evaluate("window.parrotPage.flow.mode") == "curious" and seen("#ask-preset")})
    T.quiet_for(page)
    serial = page.evaluate("window.parrotPage.trained.serial")
    t_ask = T.now(page)
    page.select_option("#ask-preset", index=0)
    page.click("#ask-form button[type=submit]")
    sub, turn = "", False
    for _ in range(60):
        sub = sub or page.evaluate("document.getElementById('subtitle').hidden ? '' : document.getElementById('subtitle').textContent")
        turn = turn or page.evaluate("document.body.dataset.turn") == "parrot"
        page.wait_for_timeout(50)
    last = T.answer_after(page, serial, 60)
    bubble = page.evaluate("(t) => { const b = window.parrotPage.flow.bubble; return b && b.at > t && b.who === 'it' ? b.text : ''; }", t_ask)  # the answer shown by the parrot (it goes after three seconds)
    steps.append({"step": "a question asked: its words as a subtitle, the parrot's turn shown, the answer by the parrot", "subtitle": sub.strip(), "turn_sign": turn,
                  "answer": last["said"] if last else None, "bubble": bubble, "ok": bool(last and last["right"] and sub and turn and bubble == " ".join(last["said"]))})
    t = T.now(page)
    page.click("#ask-nut")
    dop = False
    for _ in range(80):
        dop = dop or page.evaluate("!!document.querySelector('.scan-box.dopamine.on')")
        page.wait_for_timeout(50)
    paid = page.evaluate("(t) => (window.parrotPage.flow.linked || []).filter((l) => l.at > t).length", t)
    steps.append({"step": "a pistachio: the dopamine box lights, the lesson is taken", "dopamine_sign": dop, "links_paid": paid, "pistachios": page.evaluate("document.getElementById('pistachios').textContent"), "ok": dop and paid >= 1})
    ctx.close(); browser.close()
    return {"voice": voice.name, "steps": steps, "ok": all(s["ok"] for s in steps), "log": logs[-40:]}


# --- the visitors' matrix ------------------------------------------------------------------------------
def visitor(pw, a, T, voice: Path, cond: str) -> dict:
    takes = T.takes(voice)
    said_as = json.loads((voice / "wer.json").read_text()) if (voice / "wer.json").exists() else {}
    browser, ctx, page, logs, t0 = T.open_page(pw, a.url, a.out / "quiet.wav")
    mic = Room(T, page, cond, seed=abs(hash((voice.name, cond))) % 2**31)
    out: dict = {"voice": voice.name, "cond": cond, "listen": [], "curious": {}}
    (a.out / "said_back").mkdir(exist_ok=True)
    # (a) Listen to me: each utterance kept whole, and said back
    T.set_flow(page, "listen")
    for key in ("apple", "cup", "white", "what_colour", "what_is_this", "where_is_it"):
        T.quiet_for(page)
        page.wait_for_timeout(600)
        t = T.now(page)
        sound = mic.say(takes[key][0])
        got = T.heard_after(page, t, 15)
        page.wait_for_timeout(3200)
        said = page.evaluate("(t) => window.parrotPage.flow.said.filter((s) => s.at > t && s.echo)", t)
        row = {"key": key, "take": takes[key][0].name, "heard": len(got), "frames": got[0]["frames"] if got else None, "said_back": bool(said), "visitor_reads": said_as.get(takes[key][0].stem, {}).get("heard"),
               "said_back_ms": round(said[0]["at"] - sound["speech_end"]) if said else None}  # from the end of the visitor's utterance to the start of the say-back
        if said:
            y = T.parrot_audio(page, said[0]["id"])
            if y is not None:
                f = a.out / "said_back" / f"{voice.name}_{cond}_{key}.wav"
                T.write_wav(f, np.concatenate([np.zeros(4800), y / (np.abs(y).max() + 1e-9) * 0.9, np.zeros(4800)]))
                row["file"] = str(f)
        out["listen"].append(row)
        print("  listen", json.dumps({k: row[k] for k in ("key", "heard", "said_back", "said_back_ms")}), flush=True)
    # (b) Curious: each short question until it is answered right RUN times running
    T.set_flow(page, "curious")
    for q, kinds in T.SHORT.items():
        rows, streak = [], 0
        for trial in range(TRIALS):
            kind = kinds[trial % len(kinds)]
            T.quiet_for(page)
            page.wait_for_timeout(500)
            T.focus_on(page, kind)
            page.wait_for_timeout(400)
            serial = page.evaluate("window.parrotPage.trained.serial")
            t = T.now(page)
            take = takes[q][(trial + 1) % len(takes[q])]
            sound = mic.say(take)
            got = T.heard_after(page, t, 15)
            last = T.answer_after(page, serial, 30) if got and got[0].get("words") and len(got[0]["words"]) > 1 else None
            want = T.expected_of(page, q, kind)
            row = {"trial": trial, "take": take.name, "focus": kind, "want": want, "heard": len(got), "taken_for": (got[0].get("word") or got[0].get("guess")) if got else None,
                   "guessed": bool(got and not got[0].get("word")), "said": last["said"] if last else [], "right": bool(last and " ".join(last["said"]) == want)}
            spoken = _spoken_since(page, t)
            if spoken:
                row["answer_ms"] = round(spoken[0]["at"] - sound["speech_end"])
            if row["right"]:  # the trainer's pistachio, for a right answer only
                page.click("#ask-nut"); page.wait_for_timeout(2600)
            streak = streak + 1 if row["right"] else 0
            rows.append(row)
            print("  curious", q, json.dumps({k: row.get(k) for k in ("trial", "focus", "heard", "taken_for", "guessed", "said", "want", "right", "answer_ms")}), flush=True)
            if streak >= RUN:
                break
        start = len(rows) - streak if streak >= RUN else None
        out["curious"][q] = {"reached": streak >= RUN, "trials_before_the_run": start, "pistachios_before_the_run": None if start is None else sum(r["right"] for r in rows[:start]),
                             "not_heard": sum(r["heard"] != 1 for r in rows), "rows": rows}
    out["log"] = logs[-60:]
    ctx.close(); browser.close()
    return out


def judge_visitors(rows: list[dict], heard: dict, T) -> dict:
    table = []
    for v in rows:
        back = 0
        for r in v["listen"]:
            if r.get("file"):
                r["parrot_reads"] = heard.get(r["file"]); want = T.words_of(r.get("visitor_reads") or r["key"].replace("_", " "))
                r["read_alike"] = T.words_of(r["parrot_reads"] or "") == want
                back += r["read_alike"]
        ans = [r["answer_ms"] for q in v["curious"].values() for r in q["rows"] if r.get("answer_ms") is not None and r["right"]]
        sb = [r["said_back_ms"] for r in v["listen"] if r.get("said_back_ms") is not None]
        table.append({"voice": v["voice"], "cond": v["cond"], "one_utterance": sum(r["heard"] == 1 for r in v["listen"]), "said_back": sum(r["said_back"] for r in v["listen"]),
                      "said_back_read_alike": back, "of": len(v["listen"]), "said_back_ms_median": None if not sb else round(float(np.median(sb))), "said_back_ms_max": None if not sb else max(sb),
                      **{q: (f"{c['pistachios_before_the_run']} pistachios, {c['trials_before_the_run']} trials" if c["reached"] else f"not in {len(c['rows'])} trials") for q, c in v["curious"].items()},
                      "answer_ms_median": None if not ans else round(float(np.median(ans))), "answer_ms_max": None if not ans else max(ans)})
    sb = [r["said_back_ms"] for v in rows for r in v["listen"] if r.get("said_back_ms") is not None]
    ans = [r["answer_ms"] for v in rows for q in v["curious"].values() for r in q["rows"] if r.get("answer_ms") is not None and r["right"]]
    return {"table": table, "all_reached": all(c["reached"] for v in rows for c in v["curious"].values()),
            "all_one_utterance": all(r["heard"] == 1 for v in rows for r in v["listen"]),
            "said_back_ms": {"median": None if not sb else round(float(np.median(sb))), "max": None if not sb else max(sb), "within_1500": sum(x <= 1500 for x in sb), "of": len(sb)},
            "answer_ms": {"median": None if not ans else round(float(np.median(ans))), "max": None if not ans else max(ans), "within_1500": sum(x <= 1500 for x in ans), "of": len(ans)}}


# --- false triggers --------------------------------------------------------------------------------------
def false_triggers(pw, a, T) -> dict:
    browser, ctx, page, logs, t0 = T.open_page(pw, a.url, a.out / "quiet.wav")
    rng = np.random.default_rng(4)
    out: dict = {"sounds": [], "own_voice": {}}
    for mode in ("listen", "curious"):
        T.set_flow(page, mode)
        if mode == "curious":
            T.focus_on(page, "cup")
        for name, fn in room.NOT_SPEECH.items():
            for k in range(2):
                T.quiet_for(page)
                serial = page.evaluate("window.parrotPage.trained.serial")
                t = T.now(page)
                x = fn(rng).astype(np.float32); x = x / (np.abs(x).max() + 1e-9) * float(rng.uniform(0.2, 0.6))
                T.hear(page, pad(x, 0.2, 0.3))
                page.wait_for_timeout(int(1000 * len(x) / 16000) + 2600)
                got = page.evaluate("(t) => window.parrotPage.flow.heard.filter((h) => h.at > t).length", t)
                said = page.evaluate("(t) => window.parrotPage.flow.said.filter((s) => s.at > t && s.echo).length", t)
                answered = page.evaluate("window.parrotPage.trained.serial") > serial
                out["sounds"].append({"mode": mode, "sound": name, "kept": got, "said_back": said, "answered": answered})
        print("  false", mode, json.dumps({n: sum(r["kept"] for r in out["sounds"] if r["sound"] == n and r["mode"] == mode) for n in room.NOT_SPEECH}), flush=True)
    # its own voice from the loudspeaker: the page's output reaches the ear again, later and softer
    T.set_flow(page, "curious")
    page.evaluate("window.parrotPage.audio.loopback(0.5, 0.06)")
    rows = []
    for i in range(4):
        T.quiet_for(page)
        serial = page.evaluate("window.parrotPage.trained.serial")
        t = T.now(page)
        page.select_option("#ask-preset", index=i); page.click("#ask-form button[type=submit]")
        last = T.answer_after(page, serial, 60)
        page.wait_for_timeout(4500)  # its answer sounds, and comes back
        heard = page.evaluate("(t) => window.parrotPage.flow.heard.filter((h) => h.at > t).length", t)
        more = page.evaluate("window.parrotPage.trained.serial") - serial
        rows.append({"question": i, "right": bool(last and last["right"]), "utterances_kept": heard, "exchanges": more})
    out["own_voice"] = {"rows": rows, "ok": all(r["right"] and r["utterances_kept"] == 1 and r["exchanges"] == 1 for r in rows)}
    out["ok"] = out["own_voice"]["ok"] and not any(r["kept"] or r["said_back"] or r["answered"] for r in out["sounds"])
    out["log"] = logs[-40:]
    ctx.close(); browser.close()
    return out


# --- robustness ------------------------------------------------------------------------------------------
def _ask(page, T, index=0) -> dict | None:
    T.quiet_for(page)
    serial = page.evaluate("window.parrotPage.trained.serial")
    page.select_option("#ask-preset", index=index); page.click("#ask-form button[type=submit]")
    return T.answer_after(page, serial, 60)


def robust(pw, a, T) -> dict:
    out: dict = {}
    voice = sorted(p for p in a.voices.iterdir() if p.is_dir())[0]
    apple = T.read16(T.takes(voice)["apple"][0])
    # 1. the microphone refused
    browser, ctx, page, logs, t0 = T.open_page(pw, a.url, None, mic=False)
    page.wait_for_timeout(1500)
    last = _ask(page, T, 0)
    out["mic_refused"] = {"mic": page.evaluate("document.body.dataset.mic"), "told": page.evaluate("document.getElementById('toast').textContent"), "answered_right": bool(last and last["right"]),
                          "ok": page.evaluate("document.body.dataset.mic") == "off" and bool(last and last["right"])}
    ctx.close(); browser.close()
    browser, ctx, page, logs, t0 = T.open_page(pw, a.url, a.out / "quiet.wav")
    # 2. a reload in the middle of an exchange
    page.select_option("#ask-preset", index=1); page.click("#ask-form button[type=submit]")
    page.wait_for_timeout(900)
    page.reload(wait_until="domcontentloaded"); T.ready(page)
    last = _ask(page, T, 1)
    out["reload"] = {"answered_right": bool(last and last["right"]), "ok": bool(last and last["right"])}
    # 3. a sound arriving while it speaks
    serial = page.evaluate("window.parrotPage.trained.serial")
    page.select_option("#ask-preset", index=0); page.click("#ask-form button[type=submit]")
    page.wait_for_function("window.parrotPage.audio.ownVoice() && window.parrotPage.audio.loudness() > 0", timeout=60000)
    t = T.now(page)
    T.hear(page, pad(apple, 0.0, 0.2))
    page.wait_for_timeout(4000)
    kept = page.evaluate("(t) => window.parrotPage.flow.heard.filter((h) => h.at > t).length", t)
    last = _ask(page, T, 2)
    out["sound_while_speaking"] = {"kept": kept, "busy_after": page.evaluate("window.parrotPage.trained.busy"), "next_right": bool(last and last["right"]), "ok": kept == 0 and bool(last and last["right"])}
    # 4. the switch pressed at any moment: while a question plays, while it thinks, while a word is being said to it
    presses = 0
    for delay in (150, 600, 1200, 2000, 2800):
        T.quiet_for(page)
        page.select_option("#ask-preset", index=3); page.click("#ask-form button[type=submit]")
        page.wait_for_timeout(delay)
        page.click("#flow-mode .seg[data-flow=listen]"); page.wait_for_timeout(120); page.click("#flow-mode .seg[data-flow=curious]"); presses += 2
        page.wait_for_timeout(3000)
    T.set_flow(page, "listen")
    T.hear(page, pad(apple)); page.wait_for_timeout(350)
    page.click("#flow-mode .seg[data-flow=curious]"); page.wait_for_timeout(200); page.click("#flow-mode .seg[data-flow=listen]"); presses += 2
    page.wait_for_timeout(4000)
    T.set_flow(page, "curious")
    last = _ask(page, T, 0)
    out["switch"] = {"presses": presses, "busy_after": page.evaluate("window.parrotPage.trained.busy"), "next_right": bool(last and last["right"]), "ok": bool(last and last["right"])}
    out["ok"] = all(v["ok"] for v in out.values() if isinstance(v, dict))
    out["log"] = logs[-40:]
    ctx.close(); browser.close()
    return out


# --- the parrot with no words yet ------------------------------------------------------------------------
def no_words(pw, a, T, voice: Path) -> dict:
    """Sounds taught in Listen to me (each said three times), then in Curious: the pistachios until it says "cup"
    for the cup, and until "What colour?" is answered right (of the white cup and the red apple)."""
    takes = T.takes(voice)
    url = a.url + ("&" if "?" in a.url else "?") + "brain=trained-nowords"
    browser, ctx, page, logs, t0 = T.open_page(pw, url, a.out / "quiet.wav", wait_words=False)
    mic = Room(T, page, "clean", seed=3)
    out: dict = {"voice": voice.name, "start": {"mode": page.evaluate("window.parrotPage.flow.mode"), "sounds": page.evaluate("window.parrotPage.soundPcm.size")}}
    T.set_flow(page, "listen")
    slots: dict[str, set] = {}
    for key in ("cup", "apple", "white", "red", "what_colour"):
        for k in range(3):
            T.quiet_for(page); page.wait_for_timeout(500)
            t = T.now(page)
            mic.say(takes[key][k % len(takes[key])])
            got = T.heard_after(page, t, 15)
            for h in got:
                slots.setdefault(key, set()).add(h["slot"])
            page.wait_for_timeout(2600)
    out["taught"] = {k: sorted(v) for k, v in slots.items()}
    out["can_say"] = page.evaluate("[...window.parrotPage.soundPcm.keys()].filter((k) => k.startsWith('you-')).map((k) => +k.slice(4))")
    T.set_flow(page, "curious")
    # (i) "cup" for the cup: it says sounds by itself; a pistachio when the sound is "cup"
    said, pist, began = [], 0, time.time()
    while time.time() - began < 240:
        T.focus_on(page, "cup")
        t = T.now(page)
        page.wait_for_timeout(1200)
        new = page.evaluate("(t) => window.parrotPage.flow.said.filter((s) => s.at > t && !s.echo)", t)
        for s in new:
            is_cup = s["slot"] in slots.get("cup", set())
            said.append({"slot": s["slot"], "cup": is_cup, "s": round(time.time() - began, 1)})
            if is_cup:
                page.click("#ask-nut"); pist += 1; page.wait_for_timeout(2600)
        if len(said) >= 5 and sum(x["cup"] for x in said[-5:]) >= 4:
            break
    done = len(said) >= 5 and sum(x["cup"] for x in said[-5:]) >= 4
    out["cup_for_the_cup"] = {"reached": done, "sounds_said": len(said), "pistachios": pist, "seconds": round(time.time() - began), "said": said}
    print("  no words: cup for the cup", json.dumps({k: v for k, v in out["cup_for_the_cup"].items() if k != "said"}), flush=True)
    # (ii) "What colour?" of the white cup and the red apple
    rows, streak, pist = [], 0, 0
    for trial in range(40):
        kind, want = (("cup", "white"), ("apple", "red"))[trial % 2]
        T.quiet_for(page); page.wait_for_timeout(500)
        T.focus_on(page, kind); page.wait_for_timeout(400)
        serial = page.evaluate("window.parrotPage.trained.serial")
        t = T.now(page)
        mic.say(takes["what_colour"][trial % len(takes["what_colour"])])
        got = T.heard_after(page, t, 15)
        last = T.answer_after(page, serial, 30) if got and got[0].get("words") and len(got[0]["words"]) > 1 else None
        spoken = _spoken_since(page, t)
        slot = int(spoken[0]["id"][4:]) if spoken and spoken[0].get("id") else None
        right = bool(last and last["said"] == [want] and slot in slots.get(want, set()))
        rows.append({"trial": trial, "focus": kind, "taken_for": (got[0].get("word") or got[0].get("guess")) if got else None, "guessed": bool(got and not got[0].get("word")),
                     "brain_said": last["said"] if last else [], "sound_said": next((k for k, v in slots.items() if slot in v), None), "right": right})
        if right:
            page.click("#ask-nut"); pist += 1; page.wait_for_timeout(2600)
        streak = streak + 1 if right else 0
        print("  no words: what colour", json.dumps(rows[-1]), flush=True)
        if streak >= RUN:
            break
    start = len(rows) - streak if streak >= RUN else None
    out["what_colour"] = {"reached": streak >= RUN, "trials_before_the_run": start, "pistachios_before_the_run": None if start is None else sum(r["right"] for r in rows[:start]), "trials": len(rows), "rows": rows}
    out["log"] = logs[-60:]
    ctx.close(); browser.close()
    return out


def run(pw, a, only, report, T) -> bool:
    ok = True
    save = lambda: (a.out / "report.json").write_text(json.dumps(report, indent=1))  # noqa: E731
    if "first" in only:
        report["first"] = first_visit(pw, a, T); save()
        print("first", json.dumps([(s["step"][:40], s["ok"]) for s in report["first"]["steps"]]), flush=True)
        ok &= report["first"]["ok"]
    if "visitors" in only:
        names = [n for n in a.visitors.split(",") if n]
        rows = report.setdefault("visitors", {}).setdefault("rows", [])
        for voice in sorted(p for p in a.voices.iterdir() if p.is_dir() and (not names or p.name in names)):
            for cond in a.conditions.split(","):
                if any(r["voice"] == voice.name and r["cond"] == cond for r in rows):
                    continue
                print("visitor", voice.name, cond, flush=True)
                rows.append(visitor(pw, a, T, voice, cond)); save()
        files = [r["file"] for v in rows for r in v["listen"] if r.get("file")]
        report["visitors"]["summary"] = judge_visitors(rows, T.whisper(a.whisper, files) if files else {}, T); save()
        for row in report["visitors"]["summary"]["table"]:
            print("visitors", json.dumps(row), flush=True)
        ok &= report["visitors"]["summary"]["all_reached"] and report["visitors"]["summary"]["all_one_utterance"]
    if "false" in only:
        report["false"] = false_triggers(pw, a, T); save()
        print("false", json.dumps({"kept": sum(r["kept"] for r in report["false"]["sounds"]), "of": len(report["false"]["sounds"]), "own_voice": report["false"]["own_voice"]["rows"]}), flush=True)
        ok &= report["false"]["ok"]
    if "robust" in only:
        report["robust"] = robust(pw, a, T); save()
        print("robust", json.dumps({k: v["ok"] for k, v in report["robust"].items() if isinstance(v, dict)}), flush=True)
        ok &= report["robust"]["ok"]
    if "nowords" in only:
        names = [n for n in a.visitors.split(",") if n]
        voice = sorted(p for p in a.voices.iterdir() if p.is_dir() and (not names or p.name in names))[0]
        report["nowords"] = no_words(pw, a, T, voice); save()
        print("nowords", json.dumps({k: {kk: vv for kk, vv in v.items() if kk not in ("rows", "said")} for k, v in report["nowords"].items() if k in ("cup_for_the_cup", "what_colour")}), flush=True)
    return ok
