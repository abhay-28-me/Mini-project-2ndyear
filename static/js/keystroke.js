/**
 * keystroke.js  (IMPROVED)
 * ------------------------
 * Captures keystroke timing data from a password input field.
 *
 * Collected data sent to the server:
 *   dwell    : [ms, ...]          — how long each key was held down
 *   flight   : [ms, ...]          — time between key-up and next key-down (pooled)
 *   digraphs : { "A-B": [ms] }   — per key-pair flight times (NEW)
 *                                   matches parse_ikdd.py's digraph feature extraction
 *
 * Usage:
 *   const cap = new KeystrokeCapture(inputElement, expectedPhrase);
 *   cap.start();
 *   // ... user types ...
 *   const data = cap.getData();   // returns null if mistakes detected
 *   cap.reset();
 */

class KeystrokeCapture {

  /**
   * @param {HTMLInputElement} inputEl      - The input field to monitor
   * @param {string|null}      phrase       - Expected phrase (null = any, used for login)
   */
  constructor(inputEl, phrase = null) {
    this._input      = inputEl;
    this._phrase     = phrase;

    // Raw event log: { key, code, event: "down"|"up", t: DOMHighResTimeStamp }
    this._events     = [];

    // Whether any mistake (backspace / wrong char) was made
    this._hasMistake = false;

    // Bound handlers (needed for removeEventListener)
    this._onDown = this._handleDown.bind(this);
    this._onUp   = this._handleUp.bind(this);

    this._running = false;
  }

  // ── Lifecycle ──────────────────────────────────────────────────────────────

  start() {
    if (this._running) return;
    this._input.addEventListener("keydown", this._onDown);
    this._input.addEventListener("keyup",   this._onUp);
    this._running = true;
  }

  stop() {
    this._input.removeEventListener("keydown", this._onDown);
    this._input.removeEventListener("keyup",   this._onUp);
    this._running = false;
  }

  reset() {
    this.stop();
    this._events     = [];
    this._hasMistake = false;
  }

  // ── Event handlers ─────────────────────────────────────────────────────────

  _handleDown(e) {
    if (e.key === "Backspace" || e.key === "Delete") {
      this._hasMistake = true;
      return;
    }
    // Ignore modifier-only presses
    if (["Shift","Control","Alt","Meta","CapsLock","Tab"].includes(e.key)) return;

    this._events.push({ key: e.key, code: e.code, event: "down", t: performance.now() });
  }

  _handleUp(e) {
    if (["Shift","Control","Alt","Meta","CapsLock","Tab",
         "Backspace","Delete"].includes(e.key)) return;

    this._events.push({ key: e.key, code: e.code, event: "up", t: performance.now() });
  }

  // ── Core computation ────────────────────────────────────────────────────────

  /**
   * Process raw events into timing arrays.
   * Returns null if a mistake was detected.
   *
   * @returns {{
   *   dwell    : number[],
   *   flight   : number[],
   *   digraphs : Object.<string, number[]>
   * }|null}
   */
  getData() {
    if (this._hasMistake) return null;
    if (this._events.length < 2) return null;

    const dwell    = [];
    const flight   = [];
    const digraphs = {};   // "KEY_A-KEY_B" → [ms, ...]

    // Build per-key keydown/keyup map
    // We process events in order to correctly handle overlapping keys
    const downMap = {};   // key → timestamp of most recent keydown

    let lastUpKey  = null;
    let lastUpTime = null;

    for (const ev of this._events) {
      if (ev.event === "down") {
        downMap[ev.key] = ev.t;

        // Flight: time from previous key-up to this key-down
        if (lastUpTime !== null) {
          const flightMs = Math.round(ev.t - lastUpTime);
          if (flightMs >= 0 && flightMs < 2000) {   // sanity bounds
            flight.push(flightMs);

            // Per-digraph: lastUpKey → current key
            if (lastUpKey !== null) {
              const pairKey = `${lastUpKey}-${ev.key}`;
              if (!digraphs[pairKey]) digraphs[pairKey] = [];
              digraphs[pairKey].push(flightMs);
            }
          }
        }

      } else {
        // Key up
        if (downMap[ev.key] !== undefined) {
          const dwellMs = Math.round(ev.t - downMap[ev.key]);
          if (dwellMs >= 0 && dwellMs < 2000) {
            dwell.push(dwellMs);
          }
          delete downMap[ev.key];
        }
        lastUpKey  = ev.key;
        lastUpTime = ev.t;
      }
    }

    if (dwell.length < 3) return null;

    return { dwell, flight, digraphs };
  }

  // ── Live stats (for UI display) ────────────────────────────────────────────

  /**
   * Returns live stats without finalising the capture.
   * Safe to call at any time while typing.
   */
  getStats() {
    const data = this._previewData();
    if (!data || data.dwell.length === 0) {
      return { keystrokes: 0, avgDwell: 0, avgFlight: 0 };
    }
    const avg = arr => arr.length ? Math.round(arr.reduce((a,b)=>a+b,0)/arr.length) : 0;
    return {
      keystrokes: data.dwell.length,
      avgDwell:   avg(data.dwell),
      avgFlight:  avg(data.flight),
    };
  }

  /** Same as getData() but ignores the mistake flag — used for live preview only. */
  _previewData() {
    const saved = this._hasMistake;
    this._hasMistake = false;
    const d = this.getData();
    this._hasMistake = saved;
    return d;
  }
}