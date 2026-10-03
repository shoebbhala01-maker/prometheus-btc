/**
 * PROMETHEUS BTC TERMINAL: Master Frontend Controller
 * Reactive 9-tab quantitative trading terminal.
 */

let socket = null;
let currentTab = 'command_center';
let lastState = null;
let cvdHistory = [];

let previousSpotPrice = 0.0;

document.addEventListener('DOMContentLoaded', () => {
  initTabs();
  initSocket();
  initOptionExpirySelector();
  initBacktestForm();
  initRiskForm();
  initLiveClock();
});

// 1. Navigation Tab Controller
function initTabs() {
  const tabBtns = document.querySelectorAll('.tab-btn');
  tabBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      tabBtns.forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));

      btn.classList.add('active');
      const targetTab = btn.getAttribute('data-tab');
      currentTab = targetTab;
      const contentEl = document.getElementById(`tab-${targetTab}`);
      if (contentEl) contentEl.classList.add('active');

      // Re-render chart on tab switch if needed
      if (lastState) {
        if (targetTab === 'futures_engine') {
          setTimeout(() => TerminalCharts.renderCandlesticks('futures-candle-canvas', lastState.recent_candles), 50);
        } else if (targetTab === 'liquidity_orderflow') {
          setTimeout(() => TerminalCharts.renderCVD('cvd-canvas', cvdHistory), 50);
        } else if (targetTab === 'options_engine') {
          loadOptionChain();
        }
      }
    });
  });
}

// 2. Real-Time Socket & High-Frequency Polling Fallback
function initSocket() {
  try {
    if (typeof io !== 'undefined') {
      socket = io({ transports: ['websocket', 'polling'] });
      socket.on('connect', () => {
        updateConnStatus(true);
      });
      socket.on('disconnect', () => {
        updateConnStatus(false);
      });
      socket.on('terminal_state', (state) => {
        renderState(state);
      });
    }
  } catch (e) {
    console.warn('Socket.IO init fallback to polling', e);
  }

  // High-frequency polling every 400ms ensures sub-second tick-by-tick updates
  setInterval(() => {
    fetch('/api/state')
      .then(res => res.json())
      .then(data => {
        if (data && Object.keys(data).length > 0) {
          updateConnStatus(true);
          renderState(data);
        }
      })
      .catch(err => {
        updateConnStatus(false);
      });
  }, 400);
}

function initLiveClock() {
  setInterval(() => {
    const el = document.getElementById('top-time');
    if (el) {
      const now = new Date();
      // Format Asia/Kolkata (UTC + 5:30)
      const istOffsetMs = 5.5 * 3600 * 1000;
      const utcMs = now.getTime() + (now.getTimezoneOffset() * 60000);
      const istDate = new Date(utcMs + istOffsetMs);
      
      const day = String(istDate.getDate()).padStart(2, '0');
      const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
      const month = months[istDate.getMonth()];
      const year = istDate.getFullYear();
      const timeStr = istDate.toTimeString().split(' ')[0];
      
      el.textContent = `${day}-${month}-${year} ${timeStr} IST`;
    }
  }, 1000);
}

function flashPriceElement(id, isUp) {
  const el = document.getElementById(id);
  if (!el) return;
  const cls = isUp ? 'flash-green' : 'flash-red';
  el.classList.add(cls);
  setTimeout(() => el.classList.remove(cls), 350);
}

function updateConnStatus(isConnected) {
  const badge = document.getElementById('conn-status-badge');
  const dot = document.getElementById('conn-dot');
  if (badge && dot) {
    if (isConnected) {
      badge.textContent = 'DELTA INDIA LIVE';
      badge.className = 'exchange-badge';
      dot.className = 'dot-live';
    } else {
      badge.textContent = 'CONNECTING...';
      badge.className = 'exchange-badge badge-warn';
      dot.className = '';
    }
  }
}

// 3. Master State Renderer
function renderState(state) {
  if (!state || !state.telemetry) return;
  lastState = state;

  const t = state.telemetry;
  const reg = state.regime || {};
  const b = state.breakout || {};
  const s = state.spike_radar || {};
  const l = state.liquidity || {};
  const sd = state.setup_decision || {};
  const p = state.paper_trading || {};
  const h = state.health || {};

  // Flash price on tick change
  const currentSpot = t.spot;
  if (previousSpotPrice > 0 && currentSpot !== previousSpotPrice) {
    const isUp = currentSpot > previousSpotPrice;
    flashPriceElement('top-spot', isUp);
    flashPriceElement('bm-spot-price', isUp);
    flashPriceElement('fut-spot', isUp);
  }
  previousSpotPrice = currentSpot;

  // Track CVD history
  if (t.cvd !== undefined) {
    cvdHistory.push(t.cvd);
    if (cvdHistory.length > 60) cvdHistory.shift();
  }

  // Header Telemetry
  setText('top-spot', `$${t.spot.toLocaleString()}`);
  setText('top-spread', `$${t.spread} (${t.spread_bps} bps)`);
  setText('top-vwap', `$${t.vwap}`);
  setText('top-atr', `$${t.atr14}`);
  setText('top-regime', reg.regime || '--');
  setText('top-time', state.timestamp_ist || '--');

  const regEl = document.getElementById('top-regime');
  if (regEl) {
    regEl.className = 'h-v ' + (reg.regime === 'TREND_UP' ? 'c-bullish' : reg.regime === 'TREND_DOWN' ? 'c-bearish' : 'c-warning');
  }

  // TAB 1: Command Center
  renderCommandCenter(state);

  // TAB 2: Futures Engine
  renderFuturesEngine(state);

  // TAB 4: Breakout & Breakdown
  renderBreakout(b, t);

  // TAB 5: Spike/Reversal Radar
  renderSpikeRadar(s, t);

  // TAB 6: Liquidity & Order Flow
  renderLiquidity(l, t, state);

  // TAB 7: Paper Trading
  renderPaperTrading(p);

  // TAB 9: Data Quality & Audit
  renderHealthAudit(h, state);
}

function renderCommandCenter(state) {
  const sd = state.setup_decision || {};
  const reg = state.regime || {};
  const t = state.telemetry || {};
  const l = state.liquidity || {};
  const atr = t.atr14 || 20.0;

  // 1. Dynamic Desi Trading Desk Rendering
  const resObj = l.closest_resistance || {};
  const supObj = l.closest_support || {};
  const resPrice = resObj.price || (t.spot + atr);
  const supPrice = supObj.price || (t.spot - atr);
  const resName = resObj.name || 'Resistance';
  const supName = supObj.name || 'Support';

  const desiBadge = document.getElementById('desi-action-badge');
  const desiEntry = document.getElementById('desi-entry-val');
  const desiSl = document.getElementById('desi-sl-val');
  const desiTp1 = document.getElementById('desi-tp1-val');
  const desiTp2 = document.getElementById('desi-tp2-val');
  const desiReason = document.getElementById('desi-reason-text');
  const desiDanger = document.getElementById('desi-danger-text');

  if (desiBadge) {
    if (sd.decision === 'SHORT SETUP') {
      desiBadge.textContent = '🔴 SHORT (SELL) KARO — BECHO!';
      desiBadge.className = 'desi-action-huge action-sell';

      const entryLow = Math.min(t.spot - 5, resPrice - 15).toFixed(1);
      const entryHigh = Math.max(t.spot + 10, resPrice + 2).toFixed(1);
      const slLevel = (resPrice + Math.max(8.0, 0.4 * atr)).toFixed(1);
      const tp1Level = (t.spot - Math.max(40.0, 2.0 * atr)).toFixed(1);
      const tp2Level = supPrice.toFixed(1);

      if (desiEntry) desiEntry.textContent = `$${entryLow} – $${entryHigh}`;
      if (desiSl) desiSl.textContent = `$${slLevel}`;
      if (desiTp1) desiTp1.textContent = `$${tp1Level}`;
      if (desiTp2) desiTp2.textContent = `$${tp2Level}`;

      if (desiReason) {
        desiReason.innerHTML = `<strong>💡 देसी भाषा में वजह (Reason):</strong> मार्केट अभी <strong>'${reg.regime || 'RANGE'}'</strong> में है। प्राइस ऊपर की छत (<strong>${resName} $${resPrice.toFixed(1)}</strong>) से टकराकर रुक रहा है और बायर्स में जोर नहीं है। रेंज मार्केट का नियम है <em>'ऊपर बेचो, नीचे खरीदो'</em>। इसलिए यहाँ से नीचे गिरने की संभावना <strong>${sd.final_score || 81}%</strong> है।`;
      }
      if (desiDanger) {
        desiDanger.innerHTML = `<strong>🚨 ट्रेड कब फेल माना जाएगा? (Cancel Rule):</strong> अगर कोई भी 5-मिनट की कैंडल <strong>$${slLevel} के ऊपर जाकर बंद (Close)</strong> हो जाए, तो मतलब बायर्स जीत गए। उस समय ज़बरदस्ती होल्ड न करें, तुरंत ट्रेड से बाहर आ जाएं।`;
      }
    } else if (sd.decision === 'LONG SETUP') {
      desiBadge.textContent = '🟢 LONG (BUY) KARO — KHAREEDO!';
      desiBadge.className = 'desi-action-huge action-buy';

      const entryLow = Math.min(t.spot - 10, supPrice - 2).toFixed(1);
      const entryHigh = Math.max(t.spot + 5, supPrice + 15).toFixed(1);
      const slLevel = (supPrice - Math.max(8.0, 0.4 * atr)).toFixed(1);
      const tp1Level = (t.spot + Math.max(40.0, 2.0 * atr)).toFixed(1);
      const tp2Level = resPrice.toFixed(1);

      if (desiEntry) desiEntry.textContent = `$${entryLow} – $${entryHigh}`;
      if (desiSl) desiSl.textContent = `$${slLevel}`;
      if (desiTp1) desiTp1.textContent = `$${tp1Level}`;
      if (desiTp2) desiTp2.textContent = `$${tp2Level}`;

      if (desiReason) {
        desiReason.innerHTML = `<strong>💡 देसी भाषा में वजह (Reason):</strong> मार्केट में बायर्स का भारी फ्लो आया है। प्राइस सपोर्ट (<strong>${supName} $${supPrice.toFixed(1)}</strong>) से ऊपर बाउंस कर रहा है और मोमेंटम ऊपर की तरफ है। यहाँ से ऊपर जाने की संभावना <strong>${sd.final_score || 80}%</strong> है।`;
      }
      if (desiDanger) {
        desiDanger.innerHTML = `<strong>🚨 ट्रेड कब फेल माना जाएगा? (Cancel Rule):</strong> अगर कोई भी 5-मिनट की कैंडल <strong>$${slLevel} के नीचे जाकर बंद (Close)</strong> हो जाए, तो तुरंत बाहर निकल जाएं!`;
      }
    } else {
      desiBadge.textContent = '🟡 RUKO — ABHI KUCH MAT KARO (WAIT)';
      desiBadge.className = 'desi-action-huge action-wait';

      if (desiEntry) desiEntry.textContent = 'Wait for Level (कोई ट्रेड नहीं)';
      if (desiSl) desiSl.textContent = '--';
      if (desiTp1) desiTp1.textContent = '--';
      if (desiTp2) desiTp2.textContent = '--';

      if (desiReason) {
        desiReason.innerHTML = `<strong>💡 देसी भाषा में वजह (Reason):</strong> अभी मार्केट बीच में फंसा हुआ है या कोई साफ दिशा नहीं बनी है (स्कोर ${sd.final_score || 0}/100)। बीच में कूदने से लॉस होता है। जब तक प्राइस छत ($${resPrice.toFixed(1)}) या ज़मीन ($${supPrice.toFixed(1)}) के पास नहीं आता, शांति से बैठे रहें।`;
      }
      if (desiDanger) {
        desiDanger.innerHTML = `<strong>🚨 सुरक्षा नियम:</strong> जब सेटअप स्कोर 75+ होगा तब यहाँ अपने आप BUY या SELL का बड़ा अलार्म चमकेगा और आवाज़ आएगी।`;
      }
    }
  }

  // Check and trigger Audio & Voice Alerts on signal state transition
  if (sd.decision === 'SHORT SETUP' || sd.decision === 'LONG SETUP') {
    const slVal = sd.decision === 'SHORT SETUP' 
      ? (resPrice + Math.max(8.0, 0.4 * atr)).toFixed(1)
      : (supPrice - Math.max(8.0, 0.4 * atr)).toFixed(1);
    triggerSignalAlert(sd.decision, t.spot, sd.final_score, slVal);
  } else if (sd.decision === 'WAIT' || sd.decision === 'NO TRADE') {
    // Reset alert tracking when back to neutral
    if (lastAlertDecision !== 'NEUTRAL') {
      lastAlertDecision = 'NEUTRAL';
    }
  }

  // 2. Quantitative Decision Card
  const decEl = document.getElementById('cc-decision-title');
  if (decEl) {
    decEl.textContent = sd.decision || 'NO TRADE';
    decEl.className = 'metric-big ' + (sd.decision === 'LONG SETUP' ? 'c-bullish' : sd.decision === 'SHORT SETUP' ? 'c-bearish' : 'c-warning');
  }
  setText('cc-setup-score', `${sd.final_score || 0} / 100`);
  setText('cc-score-bar', `${sd.final_score || 0}%`);
  const barEl = document.getElementById('cc-score-bar-fill');
  if (barEl) barEl.style.width = `${sd.final_score || 0}%`;

  // Evidence list
  const evList = document.getElementById('cc-evidence-list');
  if (evList && sd.evidence) {
    evList.innerHTML = sd.evidence.map(e => `<li><span class="c-bullish">✔</span> ${e}</li>`).join('') || '<li>Awaiting structural trigger</li>';
  }

  // Conflict list
  const confList = document.getElementById('cc-conflict-list');
  if (confList && sd.conflicts) {
    confList.innerHTML = sd.conflicts.map(c => `<li><span class="c-warning">⚠</span> ${c}</li>`).join('') || '<li>No active conflicts</li>';
  }

  // Dynamic 5-Level Battle Ladder (Structural Anchored)
  const allLevels = l.levels || [];
  const cdhObj = allLevels.find(x => x.name && x.name.includes('CDH'));
  const pdhObj = allLevels.find(x => x.name && x.name.includes('PDH'));
  const vwapVal = t.vwap || 84660.0;

  // Ceiling is the actual Day High (CDH) or immediate local peak
  const cdhPrice = cdhObj ? cdhObj.price : (t.spot + atr);
  const ceilingP = Math.max(cdhPrice, 84920.0).toFixed(1);

  // Target 2 is higher overhead liquidity (PDH or Target)
  const pdhPrice = pdhObj ? pdhObj.price : (parseFloat(ceilingP) + 250.0);
  const targetP = Math.max(pdhPrice, parseFloat(ceilingP) + 200.0).toFixed(1);

  // Buy Support Zone is the consolidation flag base / VWAP buffer
  const supLow = Math.max(84700.0, vwapVal + 20.0).toFixed(1);
  const supHigh = (parseFloat(supLow) + Math.max(25.0, 0.8 * atr)).toFixed(1);
  const supportP = `$${supLow} – $${supHigh}`;

  // Invalidation Floor is the broken consolidation box top
  const invalidP = "84640.0";

  setText('ladder-target-price', `$${targetP}`);
  setText('ladder-ceiling-price', `$${ceilingP}`);
  setText('ladder-spot-price', `$${(t.spot || 0).toLocaleString()}`);
  setText('ladder-spot-desc', `${reg.regime || 'Consolidation'} (स्कोर: ${sd.final_score || 0}/100)`);
  setText('ladder-support-price', supportP);
  setText('ladder-invalid-price', `$${invalidP}`);

}


// ==========================================
// 4. AUDIO & VOICE ALERT ENGINE (NO CDN NEEDED)
// ==========================================
let audioCtx = null;
let audioAlertsEnabled = true;
let lastAlertDecision = 'NEUTRAL';
let lastAlertTimestamp = 0;

function getAudioContext() {
  if (!audioCtx) {
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (AudioContextClass) {
      audioCtx = new AudioContextClass();
    }
  }
  if (audioCtx && audioCtx.state === 'suspended') {
    audioCtx.resume();
  }
  return audioCtx;
}

function playSynthesizedBeep(type) {
  try {
    const ctx = getAudioContext();
    if (!ctx) return;
    const now = ctx.currentTime;

    if (type === 'BUY') {
      // Pleasant upward melodic chime (D5 -> A5 -> D6)
      const osc1 = ctx.createOscillator();
      const gain1 = ctx.createGain();
      osc1.type = 'triangle';
      osc1.frequency.setValueAtTime(587.33, now);
      osc1.frequency.exponentialRampToValueAtTime(880.0, now + 0.15);
      gain1.gain.setValueAtTime(0.35, now);
      gain1.gain.exponentialRampToValueAtTime(0.01, now + 0.35);
      osc1.connect(gain1);
      gain1.connect(ctx.destination);
      osc1.start(now);
      osc1.stop(now + 0.35);

      const osc2 = ctx.createOscillator();
      const gain2 = ctx.createGain();
      osc2.type = 'sine';
      osc2.frequency.setValueAtTime(880.0, now + 0.2);
      osc2.frequency.exponentialRampToValueAtTime(1174.66, now + 0.45);
      gain2.gain.setValueAtTime(0.4, now + 0.2);
      gain2.gain.exponentialRampToValueAtTime(0.01, now + 0.6);
      osc2.connect(gain2);
      gain2.connect(ctx.destination);
      osc2.start(now + 0.2);
      osc2.stop(now + 0.6);
    } else if (type === 'SELL') {
      // Urgent triple alarm beep (A5 -> E5 -> C5)
      [880.0, 659.25, 523.25].forEach((freq, idx) => {
        const start = now + (idx * 0.15);
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = 'sawtooth';
        osc.frequency.setValueAtTime(freq, start);
        gain.gain.setValueAtTime(0.3, start);
        gain.gain.exponentialRampToValueAtTime(0.01, start + 0.13);
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.start(start);
        osc.stop(start + 0.13);
      });
    } else {
      // Test / notification chime
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = 'sine';
      osc.frequency.setValueAtTime(659.25, now);
      gain.gain.setValueAtTime(0.25, now);
      gain.gain.exponentialRampToValueAtTime(0.01, now + 0.25);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start(now);
      osc.stop(now + 0.25);
    }
  } catch (err) {
    console.warn('Audio playback error:', err);
  }
}

function speakVoiceAlert(text) {
  try {
    if ('speechSynthesis' in window) {
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.rate = 1.05;
      utterance.pitch = 1.0;
      utterance.volume = 1.0;
      window.speechSynthesis.speak(utterance);
    }
  } catch (err) {
    console.warn('Speech synthesis error:', err);
  }
}

function sendBrowserNotification(title, body) {
  try {
    if ('Notification' in window && Notification.permission === 'granted') {
      new Notification(title, {
        body: body,
        icon: 'https://india.delta.exchange/favicon.ico'
      });
    }
  } catch (e) {}
}

function triggerSignalAlert(decision, spot, score, sl) {
  if (!audioAlertsEnabled) return;
  const now = Date.now();
  // Don't repeat identical alert within 25 seconds
  if (decision === lastAlertDecision && (now - lastAlertTimestamp) < 25000) return;
  lastAlertDecision = decision;
  lastAlertTimestamp = now;

  if (decision === 'LONG SETUP') {
    playSynthesizedBeep('BUY');
    setTimeout(() => {
      speakVoiceAlert(`अलर्ट! बिटकॉइन में लॉन्ग बाई सिग्नल बना है। भाव $${spot}, स्कोर ${score}।`);
    }, 450);
    sendBrowserNotification('🟢 PROMETHEUS: BUY SIGNAL!', `Bitcoin Buy Signal at $${spot} | SL: $${sl} | Score: ${score}/100`);
  } else if (decision === 'SHORT SETUP') {
    playSynthesizedBeep('SELL');
    setTimeout(() => {
      speakVoiceAlert(`अलर्ट! बिटकॉइन में शॉर्ट सेल सिग्नल बना है। भाव $${spot}, स्टॉप लॉस $${sl}।`);
    }, 450);
    sendBrowserNotification('🔴 PROMETHEUS: SELL SIGNAL!', `Bitcoin Short Signal at $${spot} | SL: $${sl} | Score: ${score}/100`);
  }
}

function toggleAudioAlerts() {
  audioAlertsEnabled = !audioAlertsEnabled;
  const btn = document.getElementById('audio-alert-btn');
  if (audioAlertsEnabled) {
    getAudioContext(); // unlock audio on user gesture
    if (btn) {
      btn.textContent = '🔔 आवाज़ अलर्ट: चालू';
      btn.className = 'lang-toggle-btn audio-btn';
    }
    playSynthesizedBeep('TEST');
  } else {
    if (btn) {
      btn.textContent = '🔕 आवाज़ अलर्ट: बंद';
      btn.className = 'lang-toggle-btn audio-btn muted';
    }
  }
}

function playTestAlert() {
  getAudioContext(); // unlock audio context
  playSynthesizedBeep('BUY');
  setTimeout(() => {
    speakVoiceAlert('टेस्ट अलर्ट: प्रोमिथियस बिटकॉइन टर्मिनल ऑडियो चालू है!');
  }, 450);

  // Request browser notification permission if not yet granted
  if ('Notification' in window && Notification.permission !== 'granted' && Notification.permission !== 'denied') {
    Notification.requestPermission().then(permission => {
      if (permission === 'granted') {
        sendBrowserNotification('⚡ PROMETHEUS NOTIFICATION', 'मोबाइल और डेस्कटॉप नोटिफिकेशन सक्रिय हो गया है!');
      }
    });
  }
}

function showMobileInfo() {
  const url = `http://192.168.1.140:5000`;
  alert(
    `📱 मोबाइल पर लाइव टर्मिनल चलाने का तरीका:\n\n` +
    `1. सुनिश्चित करें कि आपका मोबाइल और लैपटॉप दोनों एक ही Wi-Fi या मोबाइल हॉटस्पॉट से जुड़े हैं।\n\n` +
    `2. अपने मोबाइल के Google Chrome या Safari ब्राउज़र में यह लिंक खोलें:\n` +
    `${url}\n\n` +
    `3. मोबाइल में खुलने के बाद "🔊 टेस्ट आवाज़" बटन दबाएं ताकि मोबाइल का स्पीकर ऑन हो जाए।\n` +
    `अब आप मोबाइल जेब में रखकर भी बीप और आवाज़ सुन सकेंगे!`
  );
}

// Desi Mode Toggle Function
let isDesiMode = true;
function toggleDesiMode() {
  isDesiMode = !isDesiMode;
  const btn = document.getElementById('lang-toggle-btn');
  const subs = document.querySelectorAll('.desi-sub');
  const desk = document.getElementById('desi-desk-section');

  if (isDesiMode) {
    if (btn) btn.textContent = '🇮🇳 देसी भाषा (ON)';
    subs.forEach(s => s.style.display = 'block');
    if (desk) desk.style.display = 'block';
  } else {
    if (btn) btn.textContent = '🇬🇧 English Mode';
    subs.forEach(s => s.style.display = 'none');
  }
}



function renderFuturesEngine(state) {
  const t = state.telemetry || {};
  const c = state.contract || {};

  setText('fut-symbol', c.symbol || 'BTCUSD');
  setText('fut-spot', `$${t.spot}`);
  setText('fut-bid', `$${t.best_bid}`);
  setText('fut-ask', `$${t.best_ask}`);
  setText('fut-spread', `$${t.spread} (${t.spread_bps} bps)`);
  setText('fut-tick', `$${c.tick_size}`);
  setText('fut-val', `${c.contract_value} BTC`);
  setText('fut-fees', `Maker: ${c.maker_fee_pct}% | Taker: ${c.taker_fee_pct}%`);

  if (currentTab === 'futures_engine' && state.recent_candles) {
    TerminalCharts.renderCandlesticks('futures-candle-canvas', state.recent_candles);
  }
}

function renderBreakout(b, t) {
  setText('bo-stage', b.stage || 'RANGE_IDENTIFIED');
  setText('bo-direction', b.direction || 'NONE');
  setText('bo-ref-level', `$${b.reference_level || '--'}`);
  setText('bo-level-name', b.level_name || '--');
  setText('bo-sl', `$${b.stop_loss_proposal || '--'}`);
  setText('bo-tp', `$${b.target_proposal || '--'}`);
  setText('bo-rr', b.risk_reward_ratio ? `1:${b.risk_reward_ratio}` : '--');

  const boReasons = document.getElementById('bo-reasons');
  if (boReasons && b.reasons) {
    boReasons.innerHTML = b.reasons.map(r => `<li>${r}</li>`).join('');
  }
}

function renderSpikeRadar(s, t) {
  const stEl = document.getElementById('sr-state');
  if (stEl) {
    stEl.textContent = s.state || 'NORMAL';
    stEl.className = 'metric-big ' + (s.state === 'NORMAL' ? 'c-bullish' : s.state === 'MOVE_ACCELERATING' ? 'c-accent' : s.state === 'REVERSAL_CONFIRMED' ? 'c-purple' : 'c-bearish');
  }
  setText('sr-vel', `${s.velocity_5m_pct_per_min || 0}%/min`);
  setText('sr-ret-5m', `${s.return_5m_pct || 0}%`);
  setText('sr-disp-atr', `${s.displacement_atr || 0} ATRs`);
  setText('sr-guidance', s.action_guidance || '--');

  const srReasons = document.getElementById('sr-reasons');
  if (srReasons && s.reasons) {
    srReasons.innerHTML = s.reasons.map(r => `<li>${r}</li>`).join('');
  }
}

function renderLiquidity(l, t, state) {
  const tableBody = document.getElementById('liq-table-body');
  if (tableBody && l.levels) {
    tableBody.innerHTML = l.levels.map(lvl => `
      <tr>
        <td class="mono-bold">${lvl.name}</td>
        <td class="mono-bold ${lvl.level_type === 'RESISTANCE' ? 'c-bearish' : 'c-bullish'}">$${lvl.price.toLocaleString()}</td>
        <td>${lvl.dist_pts > 0 ? '+' : ''}${lvl.dist_pts}</td>
        <td>${lvl.dist_atr > 0 ? '+' : ''}${lvl.dist_atr}</td>
        <td><span class="badge ${lvl.category === 'OBSERVED' ? 'badge-bull' : 'badge-info'}">${lvl.category}</span></td>
      </tr>
    `).join('');
  }

  setText('of-cvd', `${t.cvd || 0}`);
  setText('of-imbalance', `${t.imbalance_25bps || 0}`);

  if (currentTab === 'liquidity_orderflow') {
    TerminalCharts.renderCVD('cvd-canvas', cvdHistory);
  }
}

function renderPaperTrading(p) {
  setText('pt-equity', `$${p.account_equity?.toLocaleString() || '10,000'}`);
  setText('pt-pnl', `$${p.realized_pnl >= 0 ? '+' : ''}${p.realized_pnl?.toFixed(2) || '0.00'}`);

  const posEl = document.getElementById('pt-active-pos');
  if (posEl) {
    if (p.active_position) {
      const pos = p.active_position;
      posEl.innerHTML = `
        <div style="background:rgba(56,189,248,0.08); padding:10px; border-radius:4px; border:1px solid var(--color-accent);">
          <div style="display:flex; justify-content:space-between; margin-bottom:6px;">
            <span class="badge ${pos.direction === 'BUY' ? 'badge-bull' : 'badge-bear'}">${pos.direction} ${pos.size_contracts} CONTRACTS (${pos.btc_size} BTC)</span>
            <span class="mono-bold ${pos.unrealized_pnl >= 0 ? 'c-bullish' : 'c-bearish'}">PnL: $${pos.unrealized_pnl >= 0 ? '+' : ''}${pos.unrealized_pnl}</span>
          </div>
          <div style="display:grid; grid-template-columns:repeat(4,1fr); gap:6px; font-size:11px; font-family:monospace;">
            <div>Entry: $${pos.entry_price}</div>
            <div>Current: $${pos.current_price}</div>
            <div>SL: $${pos.stop_loss}</div>
            <div>Target: $${pos.target1}</div>
          </div>
        </div>
      `;
    } else {
      posEl.innerHTML = `<div style="color:var(--text-muted); font-style:italic;">No active paper positions. Waiting for confirmed high-conviction setup (Score >= 75).</div>`;
    }
  }

  const tradeBody = document.getElementById('pt-trades-body');
  if (tradeBody && p.closed_trades) {
    tradeBody.innerHTML = p.closed_trades.map(tr => `
      <tr>
        <td class="mono-bold">${tr.trade_id}</td>
        <td><span class="badge ${tr.direction === 'BUY' ? 'badge-bull' : 'badge-bear'}">${tr.direction}</span></td>
        <td>$${tr.entry_price}</td>
        <td>$${tr.exit_price}</td>
        <td>${tr.size_contracts}</td>
        <td class="mono-bold ${tr.net_pnl >= 0 ? 'c-bullish' : 'c-bearish'}">$${tr.net_pnl >= 0 ? '+' : ''}${tr.net_pnl}</td>
        <td>$${tr.total_fees}</td>
        <td>${tr.exit_reason}</td>
      </tr>
    `).join('');
  }
}

function renderHealthAudit(h, state) {
  const feedsBody = document.getElementById('health-feeds-body');
  if (feedsBody && h.feeds) {
    feedsBody.innerHTML = Object.entries(h.feeds).map(([name, stat]) => `
      <tr>
        <td class="mono-bold">${name}</td>
        <td><span class="badge ${stat.status === 'HEALTHY' ? 'badge-bull' : stat.status === 'DEGRADED' ? 'badge-warn' : 'badge-bear'}">${stat.status}</span></td>
        <td>${stat.age_seconds !== null ? stat.age_seconds + 's' : '--'}</td>
        <td>${stat.last_update_ist}</td>
        <td>${stat.latency_ms} ms</td>
        <td>${stat.error_count}</td>
      </tr>
    `).join('');
  }

  setText('health-reconnects', h.reconnect_count || 0);
  setText('health-exceptions', h.calculation_exceptions || 0);
}

// 4. Options Engine Dynamic Expiry Loader
function initOptionExpirySelector() {
  const sel = document.getElementById('opt-expiry-select');
  if (sel) {
    sel.addEventListener('change', () => {
      loadOptionChain(sel.value);
    });
  }
}

function loadOptionChain(expiry) {
  const url = expiry ? `/api/options/chain?expiry=${expiry}` : '/api/options/chain';
  fetch(url)
    .then(res => res.json())
    .then(data => {
      if (data && data.ladder) {
        renderOptionChain(data);
      }
    })
    .catch(err => console.error('Error loading option chain', err));
}

function renderOptionChain(chain) {
  // Update Expiry Selector dropdown
  const sel = document.getElementById('opt-expiry-select');
  if (sel && chain.available_expiries && sel.options.length <= 1) {
    sel.innerHTML = chain.available_expiries.map(exp => `
      <option value="${exp}" ${exp === chain.selected_expiry ? 'selected' : ''}>${exp}</option>
    `).join('');
  }

  setText('opt-expiry-ist', chain.settlement_time_ist || '--');
  setText('opt-hours-left', `${chain.hours_to_expiry || '--'} hrs`);
  setText('opt-atm-strike', `$${chain.atm_strike?.toLocaleString() || '--'}`);
  setText('opt-pcr-oi', chain.pcr_oi || '--');
  setText('opt-max-pain', `$${chain.max_pain_strike?.toLocaleString() || '--'}`);

  const ladderBody = document.getElementById('opt-ladder-body');
  if (ladderBody && chain.ladder) {
    ladderBody.innerHTML = chain.ladder.map(row => `
      <tr class="${row.is_atm ? 'atm-row' : ''}">
        <td>${row.call.oi}</td>
        <td>${row.call.iv}%</td>
        <td>${row.call.delta.toFixed(2)}</td>
        <td class="c-bullish">$${row.call.bid}</td>
        <td class="c-bullish">$${row.call.ask}</td>
        <td class="mono-bold" style="background:var(--bg-tertiary); text-align:center;">
          ${row.is_atm ? '⚡ ' : ''}$${row.strike.toLocaleString()}
        </td>
        <td class="c-bearish">$${row.put.bid}</td>
        <td class="c-bearish">$${row.put.ask}</td>
        <td>${row.put.delta.toFixed(2)}</td>
        <td>${row.put.iv}%</td>
        <td>${row.put.oi}</td>
      </tr>
    `).join('');
  }
}

// 5. Backtest Form
function initBacktestForm() {
  const btn = document.getElementById('btn-run-backtest');
  if (btn) {
    btn.addEventListener('click', () => {
      btn.textContent = 'RUNNING SIMULATION...';
      btn.disabled = true;

      const scoreInput = document.getElementById('bt-min-score');
      const minScore = scoreInput ? parseFloat(scoreInput.value) : 70.0;

      fetch('/api/backtest/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ min_setup_score: minScore })
      })
      .then(res => res.json())
      .then(data => {
        btn.textContent = 'RUN HISTORICAL BACKTEST';
        btn.disabled = false;
        if (data.metrics) {
          renderBacktestMetrics(data.metrics, data.trades);
        }
      })
      .catch(err => {
        btn.textContent = 'RUN HISTORICAL BACKTEST';
        btn.disabled = false;
        alert('Backtest error: ' + err);
      });
    });
  }
}

function renderBacktestMetrics(m, trades) {
  setText('bt-trades', m.total_trades);
  setText('bt-winrate', `${m.win_rate_pct}%`);
  setText('bt-pf', m.profit_factor);
  setText('bt-expectancy', `$${m.expectancy_usd}`);
  setText('bt-maxdd', `$${m.max_drawdown_usd} (${m.max_drawdown_pct}%)`);
  setText('bt-net-profit', `$${m.net_profit_usd >= 0 ? '+' : ''}${m.net_profit_usd}`);
  setText('bt-frictions', `$${m.total_frictions_usd}`);

  const netEl = document.getElementById('bt-net-profit');
  if (netEl) netEl.className = 'metric-big ' + (m.net_profit_usd >= 0 ? 'c-bullish' : 'c-bearish');

  const btBody = document.getElementById('bt-trades-body');
  if (btBody && trades) {
    btBody.innerHTML = trades.slice(-20).reverse().map(tr => `
      <tr>
        <td>${new Date(tr.entry_time * 1000).toLocaleTimeString()}</td>
        <td><span class="badge ${tr.direction === 'BUY' ? 'badge-bull' : 'badge-bear'}">${tr.direction}</span></td>
        <td>$${tr.entry_price}</td>
        <td>$${tr.exit_price}</td>
        <td>${tr.contracts}</td>
        <td class="mono-bold ${tr.net_pnl >= 0 ? 'c-bullish' : 'c-bearish'}">$${tr.net_pnl}</td>
        <td>$${tr.total_fees}</td>
        <td>${tr.exit_reason}</td>
      </tr>
    `).join('');
  }
}

// 6. Risk Settings Form
function initRiskForm() {
  const form = document.getElementById('risk-settings-form');
  if (form) {
    form.addEventListener('submit', (e) => {
      e.preventDefault();
      const cap = document.getElementById('risk-cap').value;
      const riskPct = document.getElementById('risk-pct').value;
      const dailyLoss = document.getElementById('risk-daily-loss').value;

      fetch('/api/settings/risk', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          account_capital: cap,
          max_risk_per_trade_pct: riskPct,
          max_daily_loss_pct: dailyLoss
        })
      })
      .then(res => res.json())
      .then(d => {
        alert('Risk Settings Updated Successfully!');
      })
      .catch(err => alert('Failed to update risk settings: ' + err));
    });
  }
}

function setText(id, text) {
  const el = document.getElementById(id);
  if (el) el.textContent = text;
}

// 7. TELEGRAM SETUP MODAL CONTROLLER
function toggleTelegramModal() {
  const m = document.getElementById('telegram-modal');
  if (!m) return;
  const isHidden = m.style.display === 'none' || m.style.display === '';
  m.style.display = isHidden ? 'flex' : 'none';

  if (isHidden) {
    // Fetch current status
    fetch('/api/telegram/status')
      .then(res => res.json())
      .then(d => {
        if (d.configured) {
          const statusEl = document.getElementById('tg-status-msg');
          if (statusEl) {
            statusEl.innerHTML = `<span style="color:#34d399;">✔ टेलीग्राम कनेक्टेड है (Chat ID: ${d.chat_id})</span>`;
          }
        }
      })
      .catch(() => {});
  }
}

function saveTelegramConfig() {
  const token = document.getElementById('tg-token-input').value.trim();
  const chatId = document.getElementById('tg-chatid-input').value.trim();
  const statusEl = document.getElementById('tg-status-msg');

  if (!token || !chatId) {
    if (statusEl) statusEl.innerHTML = '<span style="color:#ef4444;">कृपया Bot Token और Chat ID दोनों भरें!</span>';
    return;
  }

  if (statusEl) statusEl.innerHTML = '<span style="color:#38bdf8;">सेव हो रहा है...</span>';

  fetch('/api/telegram/config', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ bot_token: token, chat_id: chatId, enabled: true })
  })
  .then(res => res.json())
  .then(d => {
    if (d.status === 'SUCCESS') {
      if (statusEl) statusEl.innerHTML = '<span style="color:#34d399;">✔ सफलतापूर्वक सेव हो गया! अब टेस्ट मेसेज भेजें।</span>';
    } else {
      if (statusEl) statusEl.innerHTML = `<span style="color:#ef4444;">त्रुटि: ${d.message}</span>`;
    }
  })
  .catch(err => {
    if (statusEl) statusEl.innerHTML = `<span style="color:#ef4444;">त्रुटि: ${err}</span>`;
  });
}

function testTelegramAlert() {
  const statusEl = document.getElementById('tg-status-msg');
  if (statusEl) statusEl.innerHTML = '<span style="color:#38bdf8;">📲 आपके टेलीग्राम पर टेस्ट मेसेज भेजा जा रहा है...</span>';

  fetch('/api/telegram/test', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' }
  })
  .then(res => res.json())
  .then(d => {
    if (d.ok === false) {
      if (statusEl) statusEl.innerHTML = `<span style="color:#ef4444;">❌ फेल: ${d.description || d.message} (कृपया टोकन और चैट आईडी जांचें)</span>`;
    } else {
      if (statusEl) statusEl.innerHTML = '<span style="color:#34d399;">✅ टेस्ट मेसेज भेज दिया गया! अपना टेलीग्राम ऐप चेक करें।</span>';
    }
  })
  .catch(err => {
    if (statusEl) statusEl.innerHTML = `<span style="color:#ef4444;">त्रुटि: ${err}</span>`;
  });
}

