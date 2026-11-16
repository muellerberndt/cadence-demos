"""Sounds as symbols, end to end on the real page (headless Chromium).

The ear's unit is the utterance: a word or a whole spoken phrase. Sections (--only NAME[,NAME]):

presets   The shipped voice. Every preset question's clip (a woman's natural sentence) plays into the ear, twice
          round. Checked: the utterance is taken for its meaning by its record's link (no guess); every word is
          known as it is spoken (the hearing layer's follower), with the delay after the word begins in the
          clip; the trained brain's answer is right, said with a sound linked to the word, in the parrot's own
          rendering, read by Whisper as the word; the time from the end of the question to the start of the
          answer; a pistachio after an answer pays the brain's lesson and the links.
mic       The microphone itself (the browser's fake device plays a file in a loop): in Listen to me a
          visitor's word is kept as one utterance and said back within a second of the keeping. Then six
          utterances in that voice, each heard for the first time, timed from the utterance's end: each is
          said back within 1.5 s and the middle one within 1.2 s, with the machine as found and again with
          every core kept busy (--busy N processes).
first     A first visit with what is on screen alone: Listen to me, a word, said back; the switch to Curious; a
          question asked; a pistachio; the signs on screen at each step (the ear, the turn, the answer) and
          the line under the buttons that says what to try next (press Ask; say a word; a pistachio if the
          answer was right). Then,
          in the visitor's own voice (a voice in no record): a question, answered right when understood, and
          when guessed the hint by the Pistachio button (a pistachio if right, else say it again), a right
          guess paid and the question understood when asked again; and a sound it cannot make out (the
          visitor's question played backwards): a ? by the parrot and the hint to say it again.
visitors  The usability matrix: voices the parrot never heard, through a laptop microphone's simulation
          (tests/room.py: 100 Hz to 7 kHz, a mild room, noise at 20 and 10 dB below the speech, the level moved
          6 dB either way). Per voice: (a) Listen to me: each utterance kept whole and said back, the parrot's
          output read by Whisper; (b) Curious: the trials and pistachios until "What colour?", "What is this?"
          and "Where is it?" are answered right three times running; the time from the end of each question
          to the start of the answer.
false     Sounds that are no speech (a cough, a breath, typing, a click, a door, a scrape, a fan, a hum, a ring, a
          clap) in both modes, and the parrot's own voice coming back from the loudspeaker (25 s in which it
          says words by itself, then four questions answered): none may be kept as an utterance, said back
          or answered, and no word it says by itself is stopped as if another voice came in.
robust    The microphone refused; a reload in the middle of an exchange; a sound arriving while it speaks; the
          switch pressed at any moment. After each the page answers a preset.
nowords   The parrot with no words yet: sounds taught in Listen to me, then in Curious the pistachios until it
          says "cup" for the cup, and until "What colour?" is answered right.

    python tests/test_sound_symbols.py --url http://localhost:8842/ --out DIR --voices DIR
        [--only presets,mic,...] [--whisper PYTHON] [--video] [--rounds N] [--conditions clean,lap20,lap10]
        [--busy N]

--voices DIR holds one folder a visitor (takes <key>_<k>.wav with meta.json), voices the starting memory never
heard. Writes DIR/report.json (and with --video the page's video and its sound).
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import time
import wave
from pathlib import Path

import numpy as np
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
import room  # noqa: E402

ARGS = ["--use-angle=metal", "--enable-gpu", "--ignore-gpu-blocklist", "--autoplay-policy=no-user-gesture-required"]
FAKE = ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"]
SAME = {"wood": {"would"}, "no": {"know"}, "right": {"write", "rite"}, "red": {"read"}, "blue": {"blew"}, "colour": {"color"}}
SITE = Path(__file__).resolve().parents[1]
QUESTIONS = json.loads((SITE / "voice" / "questions.json").read_text())
WORLD = {"apple": "apple", "block": "block", "cup": "cup", "key": "key", "greenball": "ball"}
SHORT = {"what_colour": ["block", "cup", "key", "apple"], "what_is_this": ["key", "apple", "cup"], "where_is_it": ["cup", "greenball", "apple", "block", "key"]}


def write_wav(path: Path, x: np.ndarray, rate: int = 16000) -> None:
    x = np.clip(np.asarray(x, np.float32), -1, 1)
    with wave.open(str(path), "wb") as fh:
        fh.setnchannels(1); fh.setsampwidth(2); fh.setframerate(rate); fh.writeframes((x * 32767).astype(np.int16).tobytes())


def read16(path: Path, peak: float = 0.5) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(path), "-ac", "1", "-ar", "16000", "-f", "s16le", "-"], capture_output=True, check=True).stdout
    a = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
    return a / (np.abs(a).max() + 1e-9) * peak


def takes(folder: Path) -> dict[str, list[Path]]:
    meta = json.loads((folder / "meta.json").read_text())["takes"]
    out: dict[str, list[Path]] = {}
    for name, m in meta.items():
        out.setdefault(m.get("key") or name.rsplit("_", 1)[0], []).append(folder / f"{name}.wav")
    return out


# --- the page ---------------------------------------------------------------------------------------------
def open_page(pw, url: str, mic_wav: Path | None, video: Path | None = None, mic: bool = True, wait_words: bool = True):
    args = ARGS + (FAKE + ([f"--use-file-for-fake-audio-capture={mic_wav}"] if mic_wav else []) if mic else [])
    browser = pw.chromium.launch(headless=True, args=args)
    ctx = browser.new_context(viewport={"width": 1600, "height": 900}, **({"permissions": []} if not mic else {}),
                              **({"record_video_dir": str(video), "record_video_size": {"width": 1600, "height": 900}} if video else {}))
    page = ctx.new_page()
    page.set_default_timeout(900000)
    t0 = time.time()
    page.video_t0 = t0  # the video starts with the page
    logs: list[str] = []
    page.on("console", lambda m: logs.append(f"{time.time() - t0:7.2f} {m.type}: {m.text}"[:400]) if "[ear]" in m.text or "[voice]" in m.text or m.type == "error" else None)
    page.on("pageerror", lambda e: logs.append(f"{time.time() - t0:7.2f} PAGE ERROR: {e}"[:600]))
    page.goto(url, wait_until="domcontentloaded")
    ready(page, wait_words)
    return browser, ctx, page, logs, t0


def ready(page, wait_words: bool = True) -> None:
    page.wait_for_function("document.body.dataset.ready === '1' && window.parrotPage?.state?.brainReady", timeout=1200000)
    page.wait_for_function("document.body.dataset.brain === 'trained'", timeout=300000)
    if wait_words:
        page.wait_for_function("window.parrotPage.soundPcm.size > 10", timeout=300000)
    page.evaluate("window.parrotPage.audio.unlock()")
    page.wait_for_function("window.parrotPage.audio.ctx?.state === 'running'", timeout=60000)
    page.mouse.move(4, 896)  # the pointer out of the picture


def start_recording(page) -> None:
    """The page's own sound output (the questions' voice and the parrot's voice), recorded in the page."""
    page.evaluate("""async () => { const A = window.parrotPage.audio; await A.unlock(); const r = new MediaRecorder(A.tap(), { mimeType: 'audio/webm' });
        window._chunks = []; r.ondataavailable = (e) => window._chunks.push(e.data); r.start(500); window._rec = r; window._recAt = Date.now(); }""")


def stop_recording(page, path: Path) -> float:
    """Saves the page's sound; returns its start in seconds after the video's."""
    b64 = page.evaluate("""() => new Promise((resolve) => { window._rec.onstop = async () => { const b = new Uint8Array(await new Blob(window._chunks).arrayBuffer());
        let s = ''; for (let i = 0; i < b.length; i += 8192) s += String.fromCharCode.apply(null, b.subarray(i, i + 8192)); resolve(btoa(s)); }; window._rec.stop(); })""")
    path.write_bytes(base64.b64decode(b64))
    return page.evaluate("window._recAt") / 1000 - page.video_t0


def now(page) -> float:
    return page.evaluate("performance.now()")


def set_flow(page, mode: str) -> None:
    page.click(f"#flow-mode .seg[data-flow={mode}]")
    page.wait_for_function(f"window.parrotPage.flow.mode === '{mode}'")


def focus_on(page, kind: str) -> None:
    """The thing in focus, as a click on it sets it."""
    page.evaluate("""(kind) => { const P = window.parrotPage; const t = [...P.room.things.values()].find((x) => x.kind === kind);
        P.trained.focus = t.id; P.state.pointed = { id: t.id, until: performance.now() + 9000, cued: 0 }; P.state.focus = { id: t.id, why: 'you pointed at it' }; }""", kind)


def hear(page, samples: np.ndarray, also_out=None) -> dict:
    """A visitor's sound given to the ear along the microphone's own path; when it began and how long it is."""
    x = np.clip(np.asarray(samples, np.float32), -1, 1)
    b64 = base64.b64encode(x.tobytes()).decode()
    return page.evaluate("""async (b64) => { const raw = atob(b64), u = new Uint8Array(raw.length); for (let i = 0; i < raw.length; i++) u[i] = raw.charCodeAt(i);
        const r = await window.parrotPage.audio.hearPcm(new Float32Array(u.buffer), 16000); return { startedAt: r.startedAt, duration: r.duration }; }""", b64)


def hear_loop(page, samples: np.ndarray) -> None:
    """A room's background given to the ear all the time (the samples in a loop)."""
    b64 = base64.b64encode(np.clip(np.asarray(samples, np.float32), -1, 1).tobytes()).decode()
    page.evaluate("""async (b64) => { const raw = atob(b64), u = new Uint8Array(raw.length); for (let i = 0; i < raw.length; i++) u[i] = raw.charCodeAt(i);
        await window.parrotPage.audio.hearPcm(new Float32Array(u.buffer), 16000, { loop: true }); }""", b64)


def quiet_for(page, ms: int = 8000) -> None:
    """Waits until the parrot neither hears, thinks nor speaks."""
    page.wait_for_function("(() => { const P = window.parrotPage; return !P.trained.busy && !P.flow.hearing && !P.flow.asking && !P.audio.ownVoice() && !P.state.lastReply?.saying; })()", timeout=120000)


def heard_after(page, after: float, timeout: float = 20.0) -> list[dict]:
    """The utterances the ear kept after a moment of the page's clock (waits for the first, then a little)."""
    end = time.time() + timeout
    got: list[dict] = []
    while time.time() < end:
        got = page.evaluate("(after) => window.parrotPage.flow.heard.filter((h) => h.at > after)", after)
        if got:
            page.wait_for_timeout(400)
            return page.evaluate("(after) => window.parrotPage.flow.heard.filter((h) => h.at > after)", after)
        page.wait_for_timeout(150)
    return got


def answer_after(page, serial: int, timeout: float = 40.0) -> dict | None:
    """The exchange that follows (trained.last with a newer id), once the parrot is done."""
    end = time.time() + timeout
    while time.time() < end:
        got = page.evaluate("(serial) => { const t = window.parrotPage.trained; return !t.busy && t.last && t.last.id > serial ? t.last : null; }", serial)
        if got:
            return got
        page.wait_for_timeout(150)
    return None


def parrot_audio(page, sound_id: str) -> np.ndarray | None:
    """A sound as the page says it: the parrot's own rendering of the record where it has one, else the record's
    stored sound through the page's parrot voice (rendered offline by the page itself)."""
    b64 = page.evaluate("""async (id) => { const P = window.parrotPage; let kept = P.soundPcm.get(id);
        if (!kept) { const r = await P.sound(+id.slice(4)); kept = r && r.pcm.length ? { pcm: Float32Array.from(r.pcm), rate: r.rate } : null; }
        if (!kept) return null;
        const own = P.ownTake(id); const y = own ? own.pcm : await P.audio.renderParrot(kept.pcm, kept.rate); let b = ''; const u = new Uint8Array(new Float32Array(y).buffer);
        for (let i = 0; i < u.length; i += 8192) b += String.fromCharCode.apply(null, u.subarray(i, i + 8192)); return btoa(b); }""", sound_id)
    return None if b64 is None else np.frombuffer(base64.b64decode(b64), np.float32)


def whisper(python: str, files: list[str]) -> dict:
    code = ("import sys, json, mlx_whisper\nout = {}\nfor f in sys.argv[1:]:\n"
            "    out[f] = mlx_whisper.transcribe(f, path_or_hf_repo='mlx-community/whisper-small.en-mlx', language='en')['text'].strip()\n"
            "print(json.dumps(out))\n")
    out: dict = {}
    for i in range(0, len(files), 60):
        out.update(json.loads(subprocess.run([python, "-c", code, *files[i: i + 60]], capture_output=True, text=True, check=True).stdout.strip().splitlines()[-1]))
    return out


def words_of(text: str) -> list[str]:
    return re.sub(r"[^a-z ]", " ", text.lower().replace("color", "colour")).split()


def reads_as(heard: str, word: str) -> bool:
    got = words_of(heard)
    return got == [word] or (len(got) == 1 and got[0] in SAME.get(word, ()))


def expected_of(page, key: str, kind: str) -> str | None:
    """The right answer to a spoken phrase about a thing on the table (the page's own judge, on the phrase's meaning)."""
    return page.evaluate("""([meaning, kind]) => { const P = window.parrotPage; const t = [...P.room.things.values()].find((x) => x.kind === kind);
        const w = P.world(kind); const words = meaning.replace('<this>', w.kind).split(' '); const got = P.expected(words, w.kind, t.id); return got ? got.join(' ') : null; }""",
                         [QUESTIONS["questions"][key]["meaning"], kind])


# --- presets: the shipped voice -----------------------------------------------------------------------------
def ask_presets(page, out: Path, rounds: int, pay: bool = True) -> list[dict]:
    presets = page.evaluate("[...document.querySelectorAll('#ask-preset option')].map((o) => ({ text: o.textContent, key: o.dataset.key, focus: o.dataset.focus || null }))")
    rows = []
    (out / "answers").mkdir(parents=True, exist_ok=True)
    set_flow(page, "curious")
    for r in range(rounds):
        for i, p in enumerate(presets):
            quiet_for(page)
            serial = page.evaluate("window.parrotPage.trained.serial")
            t_ask = now(page)
            began = time.time()
            page.select_option("#ask-preset", index=i)
            page.click("#ask-form button[type=submit]")
            page.mouse.move(4, 896)
            last = answer_after(page, serial, 60)
            q = QUESTIONS["questions"][p["key"]]
            got = page.evaluate("""(t) => { const P = window.parrotPage; return { clip: P.flow.clip, spotted: P.flow.spotted.filter((s) => s.at > t), spoken: (P.trained.spoken || []).filter((s) => s.at > t && s.answer),
                heard: P.flow.heard.filter((h) => h.at > t), bubble: document.getElementById('say-bubble').textContent, subtitle: document.getElementById('subtitle').textContent }; }""", t_ask)
            row = {"round": r, "question": p["text"], "key": p["key"], "focus": p["focus"], "meaning": q["meaning"], "answered": last is not None, "seconds": round(time.time() - began, 1)}
            if last is not None:
                clip0 = got["clip"]["startedAt"]
                want = (q.get("follow") or [])
                spotted = [s["word"] for s in got["spotted"]]
                thing = WORLD.get(p["focus"] or "", None)
                want_words = [w if w != "<this>" else thing for _, w in want]
                delays = [round(s["at"] - (clip0 + 1000 * t)) for s, (t, _) in zip(got["spotted"], want)] if spotted == want_words else []
                first = got["spoken"][0]["at"] if got["spoken"] else None
                row.update(said=last["said"], expected=last["expected"], right=last["right"], taken_for=last["meaning"], guessed=last["guessed"], heard=len(got["heard"]),
                           understood=(not last["guessed"]) and last["meaning"] == q["meaning"], followed=spotted, followed_want=want_words, followed_ok=spotted == want_words,
                           word_delays_ms=delays, stood=last.get("stood"), answer_ms=None if first is None else round(first - (clip0 + 1000 * q["speech_end"])),
                           bubble=got["bubble"])
                clips = []
                for k, s in enumerate(got["spoken"]):
                    y = parrot_audio(page, s["id"])
                    if y is None:
                        continue
                    f = out / "answers" / f"r{r}_{i:02d}_{k}_{s['word']}.wav"
                    write_wav(f, np.concatenate([np.zeros(4800), y / (np.abs(y).max() + 1e-9) * 0.9, np.zeros(4800)]))
                    clips.append({"word": s["word"], "id": s["id"], "own": page.evaluate("(id) => !!window.parrotPage.ownTake(id)", s["id"]), "file": str(f)})
                row.update(answer_sounds=clips, said_with_sound=len(clips) == len(last["said"]) > 0)
                if pay and last["right"]:  # a pistachio for a right answer
                    page.click("#ask-nut"); page.wait_for_timeout(2600)
                    row["paid"] = page.evaluate("(t) => (window.parrotPage.flow.linked || []).filter((l) => l.at > t).map((l) => ({ meaning: l.meaning, link: l.link, guessed: l.guessed }))", t_ask)
            rows.append(row)
            print(json.dumps({k: row.get(k) for k in ("round", "question", "taken_for", "guessed", "said", "expected", "right", "followed_ok", "word_delays_ms", "answer_ms", "seconds")}), flush=True)
    return rows


def judge_presets(rows: list[dict], heard: dict) -> dict:
    for q in rows:
        for c in q.get("answer_sounds", []):
            c["whisper"] = heard.get(c["file"]); c["whisper_ok"] = reads_as(c["whisper"] or "", c["word"])
    sounds = [c for q in rows for c in q.get("answer_sounds", [])]
    delays = [d for q in rows for d in q.get("word_delays_ms", [])]
    ans = [q["answer_ms"] for q in rows if q.get("answer_ms") is not None]
    pct = lambda v, p: None if not v else round(float(np.percentile(v, p)))  # noqa: E731
    return {"asked": len(rows), "answered": sum(q["answered"] for q in rows), "understood": sum(bool(q.get("understood")) for q in rows), "right": sum(bool(q.get("right")) for q in rows),
            "said_with_sound": sum(bool(q.get("said_with_sound")) for q in rows), "answer_sounds": len(sounds), "own_voice": sum(c["own"] for c in sounds),
            "whisper_ok": sum(c["whisper_ok"] for c in sounds), "followed_ok": sum(bool(q.get("followed_ok")) for q in rows),
            "words_followed": len(delays), "word_delay_ms": {"median": pct(delays, 50), "p90": pct(delays, 90), "max": pct(delays, 100), "within_150": sum(d <= 150 for d in delays), "within_250": sum(d <= 250 for d in delays)},
            "answer_ms": {"median": pct(ans, 50), "p90": pct(ans, 90), "max": pct(ans, 100), "under_1500": sum(a <= 1500 for a in ans), "of": len(ans)},
            "paid_links": sum(len(q.get("paid") or []) for q in rows)}


# --- the microphone itself ----------------------------------------------------------------------------------
def mic_lesson(page) -> dict:
    """A visitor's word through the browser's fake microphone (a file in a loop), in Listen to me: kept as one
    utterance and said back."""
    page.wait_for_function("window.parrotPage.audio.mic", timeout=60000)
    set_flow(page, "listen")
    page.wait_for_timeout(600)
    t0 = now(page)
    got = []
    end = time.time() + 60
    while time.time() < end and not got:  # the first utterance that ended in Listen to me
        got = [h for h in heard_after(page, t0, 30) if h.get("mode") == "listen"]
    page.wait_for_timeout(2500)
    said = page.evaluate("(t) => window.parrotPage.flow.said.filter((s) => s.at > t)", t0)
    back = [round(s["at"] - got[0]["at"]) for s in said if got and s["echo"] and s["slot"] == got[0]["slot"] and s["at"] >= got[0]["at"]]  # (its say-back: the first after it was kept)
    # (the word's end in the looped file is not known on the page's clock: the utterance is kept 0.3 s of quiet after
    # it, and the say-back must follow that within a second; tests with the visitor's sound given to the ear directly
    # time it from the word's end)
    return {"mic_on": page.evaluate("document.body.dataset.mic"), "heard": [{k: h.get(k) for k in ("slot", "word", "known", "frames", "spotted")} for h in got],
            "said_back": said, "said_back_ms_after_the_utterance_was_kept": back[0] if back else None, "ok": bool(back) and 0 <= back[0] <= 1000}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8842/")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--voices", type=Path, help="visitors' takes, one folder a voice")
    ap.add_argument("--whisper", default=sys.executable)
    ap.add_argument("--rounds", type=int, default=2)
    ap.add_argument("--only", default="presets,mic")
    ap.add_argument("--conditions", default="clean,lap20,lap10")
    ap.add_argument("--visitors", default="")
    ap.add_argument("--video", action="store_true")
    ap.add_argument("--busy", type=int, default=os.cpu_count() or 4, help="processes that keep a core busy each in the mic section's loaded pass")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    only = [s for s in a.only.split(",") if s]
    quiet = a.out / "quiet.wav"; write_wav(quiet, np.zeros(16000 * 600))
    report: dict = json.loads((a.out / "report.json").read_text()) if (a.out / "report.json").exists() else {}
    ok = True
    with sync_playwright() as pw:
        if "presets" in only:
            browser, ctx, page, logs, t0 = open_page(pw, a.url, quiet, a.out / "video" if a.video else None)
            report["load_s"] = round(time.time() - t0, 1)
            report["mic_on"] = page.evaluate("document.body.dataset.mic")
            if a.video:
                page.wait_for_timeout(1500); start_recording(page)
            rows = ask_presets(page, a.out, a.rounds)
            report["presets"] = {"rows": rows, "log": logs[:], "ear_events": page.evaluate("window.parrotPage.ear().then((r) => r.events)")}
            if a.video:
                report["audio_presets_offset"] = stop_recording(page, a.out / "audio_presets.webm")
            ctx.close(); browser.close()
            if a.video:
                report["video_presets"] = str(page.video.path())
            files = [c["file"] for q in rows for c in q.get("answer_sounds", [])]
            s = judge_presets(rows, whisper(a.whisper, files) if files else {})
            report["presets"]["summary"] = s
            print("presets", json.dumps(s), flush=True)
            ok &= s["right"] == s["asked"] == s["understood"] == s["said_with_sound"] == s["followed_ok"] and s["whisper_ok"] == s["answer_sounds"] == s["own_voice"]
        if "mic" in only:
            v = sorted(p for p in a.voices.iterdir() if p.is_dir())[0] if a.voices else None
            apple = takes(v)["apple"][0] if v else None
            loop = np.concatenate([np.zeros(16000 * 5, np.float32), read16(apple), np.zeros(16000 * 5, np.float32)])
            micf = a.out / "mic_apple.wav"; write_wav(micf, loop)
            browser, ctx, page, logs, t0 = open_page(pw, a.url, micf)
            report["mic"] = {**mic_lesson(page), "voice": v.name, "log": logs[:]}
            ctx.close(); browser.close()
            # several first hearings, timed from each utterance's end: the machine as found, then with every core kept busy
            import flow_checks
            for name, busy in (("as_found", 0), ("busy", a.busy)):
                report["mic"][name] = flow_checks.first_hearings(pw, a, sys.modules[__name__], v, busy)
                report["mic"]["ok"] = report["mic"]["ok"] and report["mic"][name]["ok"]
                print("mic", name, json.dumps({k: report["mic"][name][k] for k in ("busy_processes", "load_1min", "said_back_ms", "ok")}), flush=True)
            print("mic", json.dumps({k: report["mic"][k] for k in ("mic_on", "said_back_ms_after_the_utterance_was_kept", "ok")}), flush=True)
            ok &= report["mic"]["ok"]
        (a.out / "report.json").write_text(json.dumps(report, indent=1))
        import flow_checks  # the longer sections (tests/flow_checks.py)
        ok &= flow_checks.run(pw, a, only, report, sys.modules[__name__])
    (a.out / "report.json").write_text(json.dumps(report, indent=1))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
