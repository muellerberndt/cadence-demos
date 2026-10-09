// The page's promise, tried end to end in headless Chrome over the DevTools protocol:
// the league wakes, a fight runs, a robot's brain can be inspected, the fight ends, the brains
// are saved in IndexedDB, and a reload restores them. Usage: node check_page.mjs [url] [out.png]
import { spawn } from "node:child_process";
import { writeFileSync } from "node:fs";

const url = process.argv[2] || "http://localhost:4173/";
const shot = process.argv[3] || "check.png";
const chrome = process.env.CHROME || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const port = 9333;
const proc = spawn(chrome, [`--remote-debugging-port=${port}`, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--window-size=1300,1900", "--user-data-dir=/tmp/claude-501/chrome-check", "about:blank"], { stdio: "ignore" });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function target() {
  for (let i = 0; i < 50; i++) {
    try { const list = await (await fetch(`http://localhost:${port}/json`)).json(); const t = list.find((x) => x.type === "page"); if (t) return t; } catch {}
    await sleep(200);
  }
  throw new Error("no chrome target");
}
const t = await target();
const ws = new WebSocket(t.webSocketDebuggerUrl);
await new Promise((r) => (ws.onopen = r));
let id = 0; const waiting = new Map(); const logs = [];
ws.onmessage = (e) => {
  const m = JSON.parse(e.data);
  if (m.id && waiting.has(m.id)) { waiting.get(m.id)(m); waiting.delete(m.id); }
  if (m.method === "Runtime.consoleAPICalled" && (m.params.type === "error" || m.params.type === "warning")) logs.push(m.params.args.map((a) => a.value ?? a.description).join(" "));
  if (m.method === "Runtime.exceptionThrown") logs.push("EXCEPTION " + (m.params.exceptionDetails.exception?.description || m.params.exceptionDetails.text));
};
const send = (method, params = {}) => new Promise((r) => { const i = ++id; waiting.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
const evalJs = async (expr) => { const r = await send("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true }); return r.result?.result?.value; };
async function until(expr, label, timeout = 120000) {
  const t0 = Date.now();
  while (Date.now() - t0 < timeout) { if (await evalJs(expr)) { console.log(`ok   ${label} (${((Date.now() - t0) / 1000).toFixed(1)} s)`); return; } await sleep(500); }
  throw new Error(`timeout: ${label}`);
}
const text = () => evalJs("document.body.innerText");
try {
  await send("Runtime.enable"); await send("Page.enable");
  await send("Page.navigate", { url });
  const t0 = Date.now();
  let lastStatus = "";
  while (!(await evalJs(`/standings/i.test(document.body.innerText)`))) {
    const st = await evalJs(`(document.querySelector("main p")||{}).textContent || ""`);
    if (st && st !== lastStatus) { console.log(`     status: ${st} (${((Date.now() - t0) / 1000).toFixed(0)} s)`); lastStatus = st; }
    if (Date.now() - t0 > 240000) throw new Error(`timeout: the league woke up (last status: ${lastStatus})`);
    await sleep(1000);
  }
  console.log(`ok   the league woke up (${((Date.now() - t0) / 1000).toFixed(1)} s)`);
  await until(`(()=>{const m=document.body.innerText.match(/moment (\\d+) \\//); return m && +m[1] >= 60;})()`, "a fight is running (60 moments shown)", 120000);
  const ms = (await text()).match(/brains ([\d.]+) ms\/moment/);
  console.log(`info brains at ${ms ? ms[1] : "?"} ms/moment in Pyodide`);
  // select a robot from the standings and expect the inspector
  await evalJs(`document.querySelector("aside button").click()`);
  await until(`!!document.querySelector("section canvas[width='1240']")`, "the brain inspector opened for a robot", 10000);
  // full speed to the end of the fight
  await evalJs(`[...document.querySelectorAll("button")].find(b => b.textContent.includes("as fast")).click()`);
  await until(`/fight over/i.test(document.body.innerText)`, "the fight ended", 600000);
  const summary = (await text()).match(/fight over\s+(.+?) takes the ring/i);
  console.log(`info winner: ${summary ? summary[1] : "?"}`);
  await until(`document.body.innerText.includes("saved after the last fight")`, "the brains were saved in this browser", 60000);
  const stored = await evalJs(`new Promise(res => { const r = indexedDB.open("cadence-showcase-league", 1); r.onsuccess = () => { const tx = r.result.transaction("league", "readonly"); const g = tx.objectStore("league").get("brains"); g.onsuccess = () => res(g.result ? Object.keys(g.result).length : 0); }; r.onerror = () => res(-1); })`);
  console.log(`ok   IndexedDB holds ${stored} brains`);
  await send("Page.captureScreenshot").then((r) => writeFileSync(shot, Buffer.from(r.result.data, "base64")));
  // reload: the brains come back
  await send("Page.navigate", { url });
  await until(`document.body.innerText.includes("restored from your last visit")`, "a reload restored the brains", 180000);
  const errors = logs.filter((l) => !/favicon/.test(l));
  console.log(errors.length ? `warn console: ${errors.slice(0, 5).join(" | ")}` : "ok   no console errors");
  console.log("PASS");
} catch (err) {
  console.log("FAIL", err.message);
  const tx = (await text()) || ""; const i = tx.indexOf("The league in this browser");
  console.log("page text:", tx.slice(0, 300).replace(/\n+/g, " | "), " ... ", i >= 0 ? tx.slice(i, i + 300).replace(/\n+/g, " | ") : "(no league panel)");
  console.log("console:", logs.slice(0, 10).join(" | "));
  process.exitCode = 1;
} finally {
  ws.close(); proc.kill();
}
