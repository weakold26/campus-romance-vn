/* =========================================================
   audio.js — WebAudio 로 만드는 배경음과 효과음
   외부 음원 없이 코드로만 합성합니다.
   ========================================================= */
(function (global) {
  'use strict';

  var ctx = null;
  var master = null;
  var bgmBus = null;
  var sfxBus = null;
  var delay = null;
  var filter = null;
  var timer = null;
  var moodName = 'silent';
  var enabled = true;
  var bgmOn = true;
  var started = false;
  var nextTime = 0;
  var step = 0;
  var current = null;

  /* 무드별 코드 진행과 멜로디 */
  var MOODS = {
    title: {
      bpm: 66, wave: 'sine', pad: 0.05, pluck: 0.055, bass: 0.04,
      chords: [[53, 60, 65, 69], [50, 57, 62, 65], [48, 55, 60, 64], [55, 62, 67, 71]],
      bells: [[77, 81, 84, 81], [74, 77, 81, 77], [72, 76, 79, 76], [79, 83, 86, 83]],
      every: 8
    },
    day: {
      bpm: 92, wave: 'triangle', pad: 0.036, pluck: 0.05, bass: 0.038,
      chords: [[55, 62, 67, 71], [53, 60, 65, 69], [50, 57, 62, 65], [52, 59, 64, 67]],
      bells: [[79, 83, 86, 83], [77, 81, 84, 81], [74, 77, 81, 77], [76, 79, 83, 79]],
      every: 6
    },
    study: {
      bpm: 58, wave: 'sine', pad: 0.045, pluck: 0.038, bass: 0.042,
      chords: [[53, 60, 65, 69], [55, 62, 67, 70], [48, 55, 60, 64], [50, 57, 62, 65]],
      bells: [[72, 77, 81], [74, 79, 82], [76, 79, 84], [74, 77, 81]],
      every: 12
    },
    warm: {
      bpm: 74, wave: 'triangle', pad: 0.046, pluck: 0.052, bass: 0.042,
      chords: [[53, 60, 64, 67], [55, 62, 65, 69], [52, 59, 64, 67], [50, 57, 62, 65]],
      bells: [[76, 79, 84, 88], [79, 83, 86, 91], [76, 79, 84, 88], [74, 79, 83, 86]],
      every: 8
    },
    night: {
      bpm: 62, wave: 'sine', pad: 0.05, pluck: 0.04, bass: 0.05,
      chords: [[48, 55, 60, 63], [45, 52, 57, 60], [50, 57, 62, 65], [43, 50, 55, 58]],
      bells: [[72, 75, 79, 84], [69, 72, 76, 81], [74, 77, 81, 86], [67, 71, 74, 79]],
      every: 10
    },
    festival: {
      bpm: 104, wave: 'triangle', pad: 0.032, pluck: 0.048, bass: 0.04,
      chords: [[50, 57, 62, 66], [52, 59, 64, 67], [55, 62, 67, 71], [57, 64, 69, 72]],
      bells: [[74, 78, 81, 86], [76, 79, 84, 88], [79, 83, 86, 91], [81, 84, 88, 93]],
      every: 6
    },
    tense: {
      bpm: 98, wave: 'sawtooth', pad: 0.024, pluck: 0.026, bass: 0.044,
      chords: [[45, 52, 57], [45, 51, 58], [43, 50, 55], [45, 52, 57]],
      bells: [[69], [70], [67], [69]],
      every: 16
    }
  };

  function freq(m) { return 440 * Math.pow(2, (m - 69) / 12); }

  function init() {
    if (ctx) return ctx;
    var C = global.AudioContext || global.webkitAudioContext;
    if (!C) return null;
    ctx = new C();

    master = ctx.createGain();
    master.gain.value = 0.85;
    master.connect(ctx.destination);

    filter = ctx.createBiquadFilter();
    filter.type = 'lowpass';
    filter.frequency.value = 2600;
    filter.Q.value = 0.5;
    filter.connect(master);

    delay = ctx.createDelay(1.4);
    delay.delayTime.value = 0.38;
    var fb = ctx.createGain();
    fb.gain.value = 0.24;
    var wet = ctx.createGain();
    wet.gain.value = 0.28;
    delay.connect(fb); fb.connect(delay);
    delay.connect(wet); wet.connect(filter);

    bgmBus = ctx.createGain();
    bgmBus.gain.value = 0;
    bgmBus.connect(filter);
    bgmBus.connect(delay);

    sfxBus = ctx.createGain();
    sfxBus.gain.value = 0.9;
    sfxBus.connect(master);
    return ctx;
  }

  /* 첫 사용자 조작에서 호출 — 브라우저 정책상 이때 열어야 합니다. */
  function unlock() {
    var c = init();
    if (!c) return;
    if (c.state === 'suspended') c.resume();
    started = true;
    if (bgmOn && moodName !== 'silent') startLoop();
  }

  function startLoop() {
    if (timer || !ctx) return;
    nextTime = ctx.currentTime + 0.06;
    step = 0;
    timer = setInterval(schedule, 140);
  }

  function stopLoop() {
    if (timer) { clearInterval(timer); timer = null; }
  }

  function schedule() {
    if (!ctx || !current) return;
    var m = current;
    var beat = 60 / m.bpm;
    while (nextTime < ctx.currentTime + 0.9) {
      playStep(m, step, nextTime, beat);
      nextTime += beat;
      step++;
    }
  }

  function playStep(m, i, t, beat) {
    var bar = Math.floor(i / 4) % m.chords.length;
    if (i % 4 === 0) {
      var chord = m.chords[bar];
      for (var k = 0; k < chord.length; k++) {
        pad(freq(chord[k]), beat * 3.9, m.pad * (k === 0 ? 1.12 : 0.78), t + k * 0.012);
      }
      bass(freq(chord[0] - 12), beat * 3.6, m.bass, t);
    }
    if (i % 2 === 0) {
      var scale = m.bells[bar];
      var n = scale[(Math.floor(i / 2)) % scale.length];
      if ((i / 2) % m.every !== 0 || m.every < 8) {
        pluck(freq(n), beat * 2.4, m.pluck, t + 0.02);
      }
    }
    if (m === MOODS.tense && i % 4 === 2) {
      thump(t, 0.9);
    }
  }

  function pad(f, dur, vol, t) {
    var o = ctx.createOscillator();
    var o2 = ctx.createOscillator();
    var g = ctx.createGain();
    o.type = current.wave;
    o2.type = 'sine';
    o.frequency.value = f;
    o2.frequency.value = f * 1.004;
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(vol, t + Math.min(1.2, dur * 0.4));
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    o.connect(g); o2.connect(g); g.connect(bgmBus);
    o.start(t); o2.start(t);
    o.stop(t + dur + 0.05); o2.stop(t + dur + 0.05);
  }

  function pluck(f, dur, vol, t) {
    var o = ctx.createOscillator();
    var g = ctx.createGain();
    o.type = 'triangle';
    o.frequency.setValueAtTime(f, t);
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(vol, t + 0.02);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    o.connect(g); g.connect(bgmBus);
    o.start(t); o.stop(t + dur + 0.03);
  }

  function bass(f, dur, vol, t) {
    var o = ctx.createOscillator();
    var g = ctx.createGain();
    o.type = 'sine';
    o.frequency.setValueAtTime(f, t);
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(vol, t + 0.12);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    o.connect(g); g.connect(bgmBus);
    o.start(t); o.stop(t + dur + 0.05);
  }

  function thump(t, vol) {
    var o = ctx.createOscillator();
    var g = ctx.createGain();
    o.type = 'sine';
    o.frequency.setValueAtTime(72, t);
    o.frequency.exponentialRampToValueAtTime(42, t + 0.22);
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(vol * 0.09, t + 0.01);
    g.gain.exponentialRampToValueAtTime(0.0001, t + 0.32);
    o.connect(g); g.connect(bgmBus);
    o.start(t); o.stop(t + 0.36);
  }

  /* ---------------- public ---------------- */
  function setMood(name) {
    if (name === moodName) return;
    moodName = name;
    if (!ctx) { if (name !== 'silent') init(); }
    if (!ctx) return;
    var target = MOODS[name];
    if (!target) {
      bgmBus.gain.cancelScheduledValues(ctx.currentTime);
      bgmBus.gain.setTargetAtTime(0, ctx.currentTime, 0.4);
      current = null;
      stopLoop();
      return;
    }
    current = target;
    step = 0;
    nextTime = ctx.currentTime + 0.1;
    if (started && bgmOn) {
      bgmBus.gain.cancelScheduledValues(ctx.currentTime);
      bgmBus.gain.setTargetAtTime(0.85, ctx.currentTime, 0.9);
      startLoop();
    }
  }

  function setBgm(on) {
    bgmOn = on;
    if (!ctx) return;
    if (!on) {
      bgmBus.gain.setTargetAtTime(0, ctx.currentTime, 0.3);
      stopLoop();
    } else if (started && moodName !== 'silent') {
      bgmBus.gain.setTargetAtTime(0.85, ctx.currentTime, 0.6);
      startLoop();
    }
  }

  function sfx(kind) {
    if (!enabled) return;
    var c = init();
    if (!c || c.state === 'suspended') return;
    var t = c.currentTime;
    if (kind === 'blip') {
      tone(1120 + Math.random() * 120, 0.016, 'sine', 0.011, t);
    } else if (kind === 'advance') {
      tone(480, 0.05, 'triangle', 0.024, t);
    } else if (kind === 'select') {
      tone(659, 0.06, 'triangle', 0.04, t);
      tone(988, 0.09, 'sine', 0.03, t + 0.05);
    } else if (kind === 'open') {
      tone(880, 0.05, 'sine', 0.026, t);
      tone(1175, 0.08, 'sine', 0.02, t + 0.045);
    } else if (kind === 'chime') {
      [523.25, 659.25, 783.99, 1046.5].forEach(function (f, i) {
        tone(f, 0.7, 'sine', 0.045, t + i * 0.14);
      });
    } else if (kind === 'heart') {
      tone(740, 0.08, 'sine', 0.03, t);
      tone(988, 0.11, 'sine', 0.026, t + 0.06);
    }
  }

  function tone(f, dur, type, vol, t) {
    var o = ctx.createOscillator();
    var g = ctx.createGain();
    o.type = type || 'sine';
    o.frequency.setValueAtTime(f, t);
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(vol || 0.04, t + 0.008);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    o.connect(g); g.connect(sfxBus);
    o.start(t); o.stop(t + dur + 0.02);
  }

  global.VNAudio = {
    unlock: unlock,
    setMood: setMood,
    setBgm: setBgm,
    sfx: sfx,
    setSfx: function (on) { enabled = on; },
    isReady: function () { return !!ctx; },
    debug: function () {
      return { state: ctx ? ctx.state : 'none', mood: moodName, bgmGain: bgmBus ? bgmGain() : 0 };
    }
  };

  function bgmGain() { return bgmBus ? bgmBus.gain.value : 0; }
})(window);
