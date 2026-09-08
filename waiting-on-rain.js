const TRACE_VISIBLE_DURATION_MS = 6 * 60 * 60 * 1000;
const TRACE_FADING_DURATION_MS = 18 * 60 * 60 * 1000;
const TRACE_RESIDUE_AFTER_MS = TRACE_VISIBLE_DURATION_MS + TRACE_FADING_DURATION_MS;
const TRACE_RECALCULATION_INTERVAL_MS = 60 * 1000;

const traceContainer = document.querySelector('.waiting-on-rain-trace');
const traceContent = document.querySelector('.waiting-on-rain-trace__content');
const traceTimestamp = document.querySelector('.waiting-on-rain-trace__timestamp');

let publishedTrace = null;

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

fetch('waiting-on-rain-state.json')
  .then((response) => {
    if (!response.ok) {
      throw new Error(`Unable to load Waiting on Rain state: ${response.status}`);
    }
    return response.json();
  })
  .then((state) => {
    publishedTrace = state.publishedTrace;
    renderTrace();

    if (publishedTrace) {
      window.setInterval(renderTrace, TRACE_RECALCULATION_INTERVAL_MS);
    }
  })
  .catch(() => {
    // An unavailable state leaves the empty trace container untouched.
  });
