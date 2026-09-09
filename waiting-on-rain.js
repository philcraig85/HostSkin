const TRACE_VISIBLE_DURATION_MS = 6 * 60 * 60 * 1000;
const TRACE_FADING_DURATION_MS = 18 * 60 * 60 * 1000;
const TRACE_RESIDUE_AFTER_MS = TRACE_VISIBLE_DURATION_MS + TRACE_FADING_DURATION_MS;
const TRACE_RECALCULATION_INTERVAL_MS = 60 * 1000;
const STATE_REFRESH_INTERVAL_MS = 5 * 60 * 1000;

const traceContainer = document.querySelector('.waiting-on-rain-trace');
const traceContent = document.querySelector('.waiting-on-rain-trace__content');
const traceTimestamp = document.querySelector('.waiting-on-rain-trace__timestamp');
const waitingField = document.querySelector('.waiting-on-rain-waiting');

let publishedTrace = null;
let temporalRenderTimerStarted = false;

function deterministicWordScore(word, index) {
  let hash = 2166136261;
  const value = `${index}:${word}`;

  for (let characterIndex = 0; characterIndex < value.length; characterIndex += 1) {
    hash ^= value.charCodeAt(characterIndex);
    hash = Math.imul(hash, 16777619);
  }

  return (hash >>> 0) / 4294967296;
}

function renderStaleTraceContent(content, visibleWordFraction) {
  let wordIndex = 0;
  const fragment = document.createDocumentFragment();

  content.replace(/\S+|\s+/g, (part) => {
    if (/\s+/.test(part)) {
      fragment.appendChild(document.createTextNode(part));
      return part;
    }

    const score = deterministicWordScore(part, wordIndex);
    wordIndex += 1;
    const word = document.createElement('span');
    word.textContent = part;

    if (score >= visibleWordFraction) {
      word.className = 'waiting-on-rain-trace__redacted-word';
    }

    fragment.appendChild(word);
    return part;
  });

  traceContent.replaceChildren(fragment);
}

function renderTrace() {
  if (!publishedTrace || !traceContainer || !traceContent || !traceTimestamp) {
    return;
  }

  const timestamp = new Date(publishedTrace.timestamp);
  const timestampMilliseconds = timestamp.getTime();

  if (!Number.isFinite(timestampMilliseconds)) {
    return;
  }

  const ageMilliseconds = Math.max(0, Date.now() - timestampMilliseconds);
  traceTimestamp.dateTime = timestamp.toISOString();
  traceTimestamp.textContent = timestamp.toISOString();
  traceContainer.hidden = false;

  if (ageMilliseconds >= TRACE_RESIDUE_AFTER_MS) {
    traceContent.hidden = true;
    return;
  }

  traceContent.hidden = false;

  if (ageMilliseconds <= TRACE_VISIBLE_DURATION_MS) {
    traceContent.textContent = publishedTrace.content;
    return;
  }

  const fadingAgeMilliseconds = ageMilliseconds - TRACE_VISIBLE_DURATION_MS;
  const visibleWordFraction = 1 - (fadingAgeMilliseconds / TRACE_FADING_DURATION_MS);
  renderStaleTraceContent(
    publishedTrace.content,
    Math.max(0, Math.min(1, visibleWordFraction)),
  );
}

function hideTrace() {
  if (traceContainer) {
    traceContainer.hidden = true;
  }
}

function renderWaitingState() {
  if (waitingField) {
    waitingField.hidden = publishedTrace !== null;
  }
}

function ensureTemporalRenderTimer() {
  if (!temporalRenderTimerStarted) {
    window.setInterval(renderTrace, TRACE_RECALCULATION_INTERVAL_MS);
    temporalRenderTimerStarted = true;
  }
}

function refreshState() {
  return fetch(`waiting-on-rain-state.json?refresh=${Date.now()}`, {
    cache: 'no-store',
  })
    .then((response) => {
      if (!response.ok) {
        throw new Error(`Unable to load Waiting on Rain state: ${response.status}`);
      }
      return response.json();
    })
    .then((state) => {
      publishedTrace = state.publishedTrace;
      renderWaitingState();

      if (publishedTrace) {
        renderTrace();
        ensureTemporalRenderTimer();
      } else {
        hideTrace();
      }
    })
    .catch(() => {
      // A failed refresh leaves the last successfully loaded state untouched.
    });
}

refreshState();
window.setInterval(refreshState, STATE_REFRESH_INTERVAL_MS);
