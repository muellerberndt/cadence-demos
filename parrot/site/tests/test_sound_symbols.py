"""Sounds as symbols, end to end on the real page (headless Chromium, the microphone a fake audio file):

1. Questions: each preset is asked; the man's voice plays and reaches the parrot's ear, the ear
   recognises each word against its records (their links), the trained brain hears the words and
   answers; the answer is said with the sound its memory links to the word. Checked: the words heard
   as sound (no typed stand-in), the answer right, the answer said with a sound, that sound one of the
   woman's records (voice/words.json `speakers`), and each answer's audio (the record's sound through
   the page's parrot voice, rendered by the page) read by Whisper as the word.
2. The microphone: a visitor's "apple" (a voice the parrot never heard) comes in through the fake
   microphone, every few seconds, with the apple in focus. Where the ear does not link it to "apple"
   at once, a pistachio after it does; "apple" heard again lights the apple tag in the brain view.

    python tests/test_sound_symbols.py --url http://localhost:8842/ --out DIR --apple WAV
        [--whisper PYTHON] [--video] [--rounds N] [--skip-mic]

Writes DIR/report.json and DIR/answers/*.wav (with --video also the page's video and sound).
"""
from __future__ import annotations

import argparse
import base64
import json
import re
import subprocess
import sys
import time
import wave
from pathlib import Path

import numpy as np
from playwright.sync_api import sync_playwright

ARGS = ["--use-angle=metal", "--enable-gpu", "--ignore-gpu-blocklist", "--use-fake-ui-for-media-stream",
        "--use-fake-device-for-media-stream", "--autoplay-policy=no-user-gesture-required"]
SAME = {"wood": {"would"}, "no": {"know"}, "right": {"write", "rite"}, "red": {"read"}, "blue": {"blew"}}


def write_wav(path: Path, x: np.ndarray, rate: int) -> None:
    x = np.clip(np.asarray(x, np.float32), -1, 1)
    with wave.open(str(path), "wb") as fh:
        fh.setnchannels(1); fh.setsampwidth(2); fh.setframerate(rate); fh.writeframes((x * 32767).astype(np.int16).tobytes())


def read16(path: Path) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(path), "-ac", "1", "-ar", "16000", "-f", "s16le", "-"], capture_output=True, check=True).stdout
    a = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
    return a / (np.abs(a).max() + 1e-9) * 0.5


def open_page(pw, url: str, mic_wav: Path, video: Path | None):
    browser = pw.chromium.launch(headless=True, args=ARGS + [f"--use-file-for-fake-audio-capture={mic_wav}"])
    ctx = browser.new_context(viewport={"width": 1600, "height": 900}, **({"record_video_dir": str(video), "record_video_size": {"width": 1600, "height": 900}} if video else {}))
    page = ctx.new_page()
    page.set_default_timeout(600000)
    t0 = time.time()
    page.video_t0 = t0  # the video starts with the page
    logs: list[str] = []
    page.on("console", lambda m: logs.append(f"{time.time() - t0:7.2f} {m.type}: {m.text}") if "[ear]" in m.text or "[voice]" in m.text or m.type == "error" else None)
    page.goto(url, wait_until="domcontentloaded")
    page.wait_for_function("document.body.dataset.ready === '1' && window.parrotPage?.state?.brainReady", timeout=900000)
    page.wait_for_function("document.body.dataset.brain === 'trained' && window.parrotPage.soundPcm.size > 10", timeout=300000)
    return browser, ctx, page, logs, t0


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


def wait_idle(page, serial: int) -> dict:
    page.wait_for_function(f"(() => {{ const t = window.parrotPage.trained; return !t.busy && t.serial > {serial} && t.last; }})()", timeout=180000)
    page.wait_for_timeout(1800)  # the answer's sound plays out
    return page.evaluate("""() => { const t = window.parrotPage.trained; return { last: t.last, heard: t.lastHeard, spoken: (t.spoken || []).slice(-4) }; }""")


def ask_presets(page, out: Path, speakers: dict, rounds: int) -> list[dict]:
    presets = page.evaluate("[...document.querySelectorAll('#ask-preset option')].map((o) => ({ text: o.value || o.textContent, focus: o.dataset.focus || null }))")
    rows = []
    (out / "answers").mkdir(parents=True, exist_ok=True)
    for r in range(rounds):
        for i, p in enumerate(presets):
            serial = page.evaluate("window.parrotPage.trained.serial")
            t_ask = page.evaluate("performance.now()")
            began = time.time()
            page.select_option("#ask-preset", index=i)
            page.click("#ask-form button[type=submit]")
            got = wait_idle(page, serial)
            last = got["last"]
            clips = []
            for k, s in enumerate([s for s in got["spoken"] if s["at"] > t_ask]):
                b64 = page.evaluate("""async (id) => { const P = window.parrotPage, kept = P.soundPcm.get(id); if (!kept) return null;
                    const y = await P.audio.renderParrot(kept.pcm, kept.rate); let b = ''; const u = new Uint8Array(new Float32Array(y).buffer);
                    for (let i = 0; i < u.length; i += 8192) b += String.fromCharCode.apply(null, u.subarray(i, i + 8192)); return btoa(b); }""", s["id"])
                if b64 is None:
                    continue
                y = np.frombuffer(base64.b64decode(b64), np.float32)
                f = out / "answers" / f"r{r}_{i:02d}_{k}_{s['word']}.wav"
                write_wav(f, np.concatenate([np.zeros(4800), y / (np.abs(y).max() + 1e-9) * 0.9, np.zeros(4800)]), 16000)
                clips.append({"word": s["word"], "id": s["id"], "speaker": speakers.get(s["id"][4:]), "file": str(f)})
            row = {"round": r, "question": p["text"], "focus": p["focus"], "said": last["said"], "expected": last["expected"], "right": last["right"],
                   "heard_as_sound": got["heard"], "by_sound": bool(got["heard"]) and got["heard"]["heard"] == got["heard"]["expected"],
                   "answer_sounds": clips, "said_with_sound": len(clips) == len(last["said"]) > 0, "seconds": round(time.time() - began, 1)}
            rows.append(row)
            print(json.dumps({k: row[k] for k in ("round", "question", "said", "expected", "right", "by_sound", "said_with_sound")}), flush=True)
    return rows


def whisper(python: str, files: list[str]) -> dict:
    code = ("import sys, json, mlx_whisper\nout = {}\nfor f in sys.argv[1:]:\n"
            "    out[f] = mlx_whisper.transcribe(f, path_or_hf_repo='mlx-community/whisper-small.en-mlx', language='en')['text'].strip()\n"
            "print(json.dumps(out))\n")
    return json.loads(subprocess.run([python, "-c", code, *files], capture_output=True, text=True, check=True).stdout.strip().splitlines()[-1])


def reads_as(heard: str, word: str) -> bool:
    got = re.sub(r"[^a-z ]", " ", heard.lower()).split()
    return got == [word] or (len(got) == 1 and got[0] in SAME.get(word, ()))


def mic_lesson(page) -> dict:
    """The visitor's "apple" through the fake microphone (looped every few seconds), the apple in focus."""
    page.evaluate("window.parrotPage.audio.unlock()")
    page.wait_for_function("window.parrotPage.audio.ctx?.state === 'running' && window.parrotPage.audio.mic", timeout=60000)
    page.evaluate("""() => { const P = window.parrotPage; const id = [...P.room.things.values()].find((t) => t.kind === 'apple').id;
        P.trained.focus = id; P.state.pointed = { id, until: performance.now() + 1e9 }; P.state.focus = { id, why: 'you pointed at it' }; }""")

    def wait_heard(after: float, timeout: float = 90.0):
        end = time.time() + timeout
        while time.time() < end:
            h = page.evaluate("window.parrotPage.lastHeardSound || null")
            if h and h["at"] > after:
                return h
            page.wait_for_timeout(200)
        return None
    first = wait_heard(page.evaluate("performance.now()"))
    out = {"first": first, "linked": None}
    if first and first.get("word") != "apple":
        page.click("#ask-nut")  # a pistachio pays the sound heard with the apple in focus
        page.wait_for_timeout(2500)
        out["linked"] = page.evaluate("window.parrotPage.lastLinked || null")
        out["again"] = wait_heard(page.evaluate("performance.now()"))
    else:
        out["again"] = first
    page.wait_for_timeout(500)
    out["tag"] = page.evaluate("(() => { const s = window.parrotPage.brain3d.scan; return s.lastHeardTag ? { word: s.lastHeardTag.word, shown: [...document.querySelectorAll('.scan-tag.main')].map((e) => e.textContent) } : null; })()")
    out["apple_lit"] = bool(out["tag"] and out["tag"]["word"] == "apple" and out["again"] and out["again"].get("word") == "apple")
    page.wait_for_timeout(4000)  # the parrot says the word back
    out["said_back"] = page.evaluate("window.parrotPage.trained.last && window.parrotPage.trained.last.imitation ? window.parrotPage.trained.last.said : null")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8842/")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--apple", type=Path, required=True, help="a visitor's 'apple' (a voice the parrot never heard)")
    ap.add_argument("--whisper", default=sys.executable)
    ap.add_argument("--rounds", type=int, default=2)
    ap.add_argument("--video", action="store_true")
    ap.add_argument("--skip-mic", action="store_true")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    site = Path(__file__).resolve().parents[1]
    speakers = json.loads((site / "voice" / "words.json").read_text()).get("speakers", {})
    quiet = a.out / "quiet.wav"; write_wav(quiet, np.zeros(16000 * 600), 16000)
    report: dict = {}
    with sync_playwright() as pw:
        browser, ctx, page, logs, t0 = open_page(pw, a.url, quiet, a.out / "video" if a.video else None)
        report["load_s"] = round(time.time() - t0, 1)
        report["mic_on"] = page.evaluate("document.body.dataset.mic")
        report["brain"] = page.evaluate("document.getElementById('ask-version')?.textContent")
        if a.video:
            page.wait_for_timeout(2000); start_recording(page)
        report["questions"] = ask_presets(page, a.out, speakers, a.rounds)
        report["log_questions"] = logs[:]
        report["ear_events"] = page.evaluate("window.parrotPage.ear().then((r) => r.events)")
        if a.video:
            report["audio_questions_offset"] = stop_recording(page, a.out / "audio_questions.webm")
        ctx.close(); browser.close()
        if a.video:
            report["video_questions"] = str(page.video.path())
        if not a.skip_mic:
            loop = np.concatenate([np.zeros(16000 * 5, np.float32), read16(a.apple), np.zeros(16000 * 3, np.float32)])
            micf = a.out / "mic_apple.wav"; write_wav(micf, loop, 16000)
            browser, ctx, page, logs, t0 = open_page(pw, a.url, micf, a.out / "video" if a.video else None)
            if a.video:
                start_recording(page)
            report["mic"] = mic_lesson(page)
            report["log_mic"] = logs[:]
            if a.video:
                report["audio_mic_offset"] = stop_recording(page, a.out / "audio_mic.webm")
            ctx.close(); browser.close()
            if a.video:
                report["video_mic"] = str(page.video.path())
    files = [c["file"] for q in report["questions"] for c in q["answer_sounds"]]
    heard = whisper(a.whisper, files) if files else {}
    for q in report["questions"]:
        for c in q["answer_sounds"]:
            c["whisper"] = heard.get(c["file"]); c["whisper_ok"] = reads_as(c["whisper"] or "", c["word"])
    qs = report["questions"]
    report["summary"] = {
        "asked": len(qs), "right": sum(bool(q["right"]) for q in qs), "by_sound": sum(q["by_sound"] for q in qs),
        "said_with_sound": sum(q["said_with_sound"] for q in qs), "answer_sounds": len(files),
        "woman": sum(c["speaker"] == "woman" for q in qs for c in q["answer_sounds"]),
        "whisper_ok": sum(c["whisper_ok"] for q in qs for c in q["answer_sounds"]),
        "mic_apple_lit": report.get("mic", {}).get("apple_lit"),
    }
    (a.out / "report.json").write_text(json.dumps(report, indent=1))
    print(json.dumps(report["summary"]), flush=True)
    s = report["summary"]
    ok = (s["right"] == s["asked"] == s["by_sound"] == s["said_with_sound"] and s["whisper_ok"] == s["answer_sounds"] == s["woman"]
          and (a.skip_mic or s["mic_apple_lit"]))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
