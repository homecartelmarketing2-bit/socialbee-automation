// ── State ──
const state = {
  images: [],
  currentIndex: 0,
  viewMode: 'single',
  pairedMode: false,
  pairedFieldName: null,
  tripleMode: false,
  tripleFieldName: null,
  zohoMode: false,
  zohoFieldName: null,
  zohoFolderId: null,
  gridSelected: new Set(),
  posting: false,
  currentSourceId: null,
  currentField: null,
  fetchId: 0,
  streaming: false,
};

// ── DOM refs ──
const $ = (id) => document.getElementById(id);

// ── Init ──
async function initApp() {
  const sources = await eel.get_sources()();
  const sel = $('source-select');
  for (const [id, name] of Object.entries(sources)) {
    const opt = document.createElement('option');
    opt.value = id;
    opt.textContent = name;
    sel.appendChild(opt);
  }

  const today = new Date().toISOString().split('T')[0];
  $('schedule-date').value = today;
  $('schedule-date').min = today;

  // Bind events
  sel.addEventListener('change', onSourceChange);
  $('field-select').addEventListener('change', onFieldChange);
  $('refresh-btn').addEventListener('click', onRefresh);
  $('grid-toggle-btn').addEventListener('click', toggleView);
  $('prev-btn').addEventListener('click', () => navigate(-1));
  $('next-btn').addEventListener('click', () => navigate(1));
  $('gen-caption-btn').addEventListener('click', onGenerateCaption);
  $('post-btn').addEventListener('click', onPost);
  $('post-story-btn').addEventListener('click', onPostStory);
  $('setup-chrome-post-btn').addEventListener('click', () => onSetup('post'));
  $('setup-chrome-story-btn').addEventListener('click', () => onSetup('story'));
  $('post-now-check').addEventListener('change', toggleSchedule);

  // Keyboard nav
  document.addEventListener('keydown', (e) => {
    if (e.target.tagName === 'TEXTAREA' || e.target.tagName === 'INPUT') return;
    if (e.key === 'ArrowLeft') navigate(-1);
    if (e.key === 'ArrowRight') navigate(1);
    if (e.key === 'Escape') closePreview();
  });

  // Context menu
  document.addEventListener('contextmenu', onContextMenu);
  document.addEventListener('click', hideContextMenu);
  $('ctx-disregard').addEventListener('click', () => doDisregard(true));
  $('ctx-undo-disregard').addEventListener('click', () => doDisregard(false));
  $('ctx-ig-story').addEventListener('click', onConvertIgStory);
  $('ctx-wm-upper').addEventListener('click', () => addWatermark('upper'));
  $('ctx-wm-lower').addEventListener('click', () => addWatermark('lower'));

  // Preview modal
  $('preview-close').addEventListener('click', closePreview);
  $('preview-backdrop').addEventListener('click', closePreview);
}

// ── Source & Field Selection ──
async function onSourceChange() {
  const baseId = $('source-select').value;
  if (!baseId) return;
  state.currentSourceId = baseId;
  const opts = await eel.get_field_options(baseId)();
  if (opts && opts.length > 0) {
    const fsel = $('field-select');
    fsel.innerHTML = '';

    const placeholder = document.createElement('option');
    placeholder.value = '';
    placeholder.textContent = '── Select a field ──';
    placeholder.disabled = true;
    placeholder.selected = true;
    fsel.appendChild(placeholder);

    for (const o of opts) {
      const opt = document.createElement('option');
      opt.value = o;
      opt.textContent = o;
      const isSeparator = o.startsWith('─');
      if (isSeparator) { opt.disabled = true; }
      fsel.appendChild(opt);
    }

    $('field-bar').classList.remove('hidden');
    
    state.images = [];
    state.currentIndex = 0;
    clearDisplay();
    $('status-label').textContent = 'Select a field to load images.';
    $('counter-label').textContent = '';
  } else {
    $('field-bar').classList.add('hidden');
    startFetch(baseId, null, null);
  }
}

async function onFieldChange() {
  const fieldName = $('field-select').value;
  if (!fieldName || fieldName.startsWith('\u2500')) return;
  state.currentField = fieldName;

  // Check triple first, then paired
  const triple = await eel.get_triple_field_info(fieldName)();
  if (triple) {
    state.tripleMode = true;
    state.tripleFieldName = fieldName;
    state.pairedMode = true;
    state.pairedFieldName = fieldName;
    startFetch(state.currentSourceId, null, null, triple);
    return;
  }

  state.tripleMode = false;
  state.tripleFieldName = null;

  state.zohoMode = false;
  state.zohoFieldName = null;
  state.zohoFolderId = null;

  const zoho = await eel.get_zoho_folder_info(fieldName)();
  if (zoho) {
    state.zohoMode = true;
    state.zohoFieldName = fieldName;
    state.zohoFolderId = zoho;
    startFetch(state.currentSourceId, fieldName, null, null, zoho);
    return;
  }

  const paired = await eel.get_paired_field_info(fieldName)();
  if (paired) {
    state.pairedMode = true;
    state.pairedFieldName = fieldName;
    startFetch(state.currentSourceId, null, paired, null, null);
  } else {
    state.pairedMode = false;
    state.pairedFieldName = null;
    startFetch(state.currentSourceId, fieldName, null, null, null);
  }
}

function startFetch(baseId, fieldName, pairedFields, tripleFields, zohoFolderId) {
  state.images = [];
  state.currentIndex = 0;
  state.gridSelected.clear();
  state.fetchId += 1;
  state.streaming = true;
  $('progress-container').classList.remove('hidden');
  $('progress-bar').style.width = '0%';
  $('progress-text').textContent = 'Loading...';
  $('counter-label').textContent = '';
  $('status-label').textContent = 'Fetching from Airtable...';
  clearDisplay();
  eel.fetch_images(baseId, fieldName, pairedFields, tripleFields, zohoFolderId);
}

async function onRefresh() {
  await eel.refresh_cache()();
  if (state.currentSourceId) {
    if (state.currentField) {
      onFieldChange();
    } else {
      startFetch(state.currentSourceId, null, null);
    }
  }
}

// ── JS callbacks from Python ──
eel.expose(on_fetch_progress);
function on_fetch_progress(done, total, imageCount) {
  const pct = total > 0 ? Math.round((done / total) * 100) : 0;
  $('progress-bar').style.width = pct + '%';
  $('progress-text').textContent = `${done}/${total} tables \u2022 ${imageCount} images`;
}

eel.expose(on_images_appended);
function on_images_appended(batch, fetchId) {
  // Drop stale batches from a superseded fetch
  if (fetchId !== state.fetchId) return;
  if (!batch || batch.length === 0) return;

  const wasEmpty = state.images.length === 0;
  const firstNewIndex = state.images.length;
  for (const img of batch) state.images.push(img);

  if (wasEmpty) {
    // First batch arrived — hide the blocking text and show first result
    updatePostButton();
    if (state.viewMode === 'grid') {
      buildGrid();
      $('counter-label').textContent = `${state.images.length} items (loading…)`;
    } else {
      displayImage(0);
      // displayImage overwrites counter-label; append the loading hint
      $('counter-label').textContent = `1 / ${state.images.length} (loading…)`;
    }
    $('status-label').textContent = `Loaded ${state.images.length} so far…`;
  } else {
    if (state.viewMode === 'grid') {
      for (let i = 0; i < batch.length; i++) {
        appendGridCell(batch[i], firstNewIndex + i);
      }
      $('counter-label').textContent = `${state.images.length} items (loading…)`;
    } else {
      $('counter-label').textContent = `${state.currentIndex + 1} / ${state.images.length} (loading…)`;
    }
    $('status-label').textContent = `Loaded ${state.images.length} so far…`;
  }
}

eel.expose(on_images_loaded);
function on_images_loaded(images, fetchId) {
  // Drop completion callbacks from a superseded fetch
  if (fetchId !== undefined && fetchId !== state.fetchId) return;
  $('progress-container').classList.add('hidden');
  state.streaming = false;

  // If streaming already populated state.images, keep it as-is
  // (same data, already rendered). Only adopt `images` when streaming
  // produced nothing — i.e. the cache-hit path.
  if (state.images.length === 0) {
    state.images = images;
    state.currentIndex = 0;
    if (images.length === 0) {
      $('status-label').textContent = 'No images found.';
      $('counter-label').textContent = '0 / 0';
      return;
    }
    updatePostButton();
    if (state.viewMode === 'grid') {
      buildGrid();
      $('counter-label').textContent = `${images.length} items`;
    } else {
      displayImage(0);
    }
  } else {
    // Streaming already rendered; just finalize the counter labels.
    if (state.viewMode === 'grid') {
      $('counter-label').textContent = `${state.images.length} items`;
    } else {
      $('counter-label').textContent = `${state.currentIndex + 1} / ${state.images.length}`;
    }
  }
  $('status-label').textContent = `Loaded ${state.images.length} items.`;
}

// ── Image Display ──
function displayImage(index) {
  if (state.images.length === 0) return;
  state.currentIndex = index;
  const img = state.images[index];
  const total = state.images.length;
  const isPair = img.type === 'pair';
  const isTriple = img.type === 'triple';

  let marks = '';
  if (img.fields && img.fields['SB Posted']) marks += ' [POSTED]';
  if (img.fields && img.fields['Disregard']) marks += ' [DISREGARD]';
  $('counter-label').textContent = `${index + 1} / ${total}${marks}`;

  if (isTriple) {
    $('filename-label').textContent = `${img.left.filename}  |  ${img.center.filename}  |  ${img.right.filename}`;
  } else if (isPair) {
    $('filename-label').textContent = `${img.left.filename}  |  ${img.right.filename}`;
  } else {
    $('filename-label').textContent = img.filename || '';
  }

  // Reset all media
  const videoExts = ['.mp4', '.mov', '.avi', '.mkv', '.webm', '.m4v'];
  $('main-image').classList.add('hidden');
  $('main-video').classList.add('hidden');
  $('main-video').pause();
  $('main-video').removeAttribute('src');
  $('paired-container').classList.add('hidden');
  $('triple-container').classList.add('hidden');

  if (isTriple) {
    $('triple-container').classList.remove('hidden');
    $('triple-left-image').src = img.left.url;
    $('triple-center-image').src = img.center.url;
    $('triple-right-image').src = img.right.url;
    $('triple-left-label').textContent = img.left.label || 'Blended Image';
    $('triple-center-label').textContent = img.center.label || 'Closeup Photo One';
    $('triple-right-label').textContent = img.right.label || 'Closeup Photo Two';
  } else if (isPair) {
    $('paired-container').classList.remove('hidden');
    const leftIsVideo = videoExts.includes(getExt(img.left.filename));
    const rightIsVideo = videoExts.includes(getExt(img.right.filename));

    if (leftIsVideo) {
      $('left-image').classList.add('hidden');
      $('left-video').classList.remove('hidden');
      $('left-video').src = img.left.url;
    } else {
      $('left-video').classList.add('hidden');
      $('left-video').pause();
      $('left-video').removeAttribute('src');
      $('left-image').classList.remove('hidden');
      $('left-image').src = img.left.url;
    }

    if (rightIsVideo) {
      $('right-image').classList.add('hidden');
      $('right-video').classList.remove('hidden');
      $('right-video').src = img.right.url;
    } else {
      $('right-video').classList.add('hidden');
      $('right-video').pause();
      $('right-video').removeAttribute('src');
      $('right-image').classList.remove('hidden');
      $('right-image').src = img.right.url;
    }

    $('left-label').textContent = img.left.label || 'Before';
    $('right-label').textContent = img.right.label || 'After';
  } else {
    const isVideo = videoExts.includes(getExt(img.filename || ''));
    if (isVideo) {
      $('main-video').classList.remove('hidden');
      $('main-video').src = img.url;
    } else {
      $('main-image').classList.remove('hidden');
      $('main-image').src = img.url;
    }
  }

  // Badges
  const posted = img.fields && img.fields['SB Posted'];
  const disregard = img.fields && img.fields['Disregard'];
  $('badge-posted').classList.toggle('hidden', !posted);
  $('badge-disregard').classList.toggle('hidden', !disregard);

  updateItemNames(index);
  $('status-label').textContent = 'Ready';
}

function clearDisplay() {
  $('main-image').src = '';
  $('main-image').classList.add('hidden');
  $('main-video').pause();
  $('main-video').removeAttribute('src');
  $('main-video').classList.add('hidden');
  $('paired-container').classList.add('hidden');
  $('triple-container').classList.add('hidden');
  $('left-image').src = '';
  $('right-image').src = '';
  $('left-video').pause();
  $('left-video').removeAttribute('src');
  $('left-video').classList.add('hidden');
  $('right-video').pause();
  $('right-video').removeAttribute('src');
  $('right-video').classList.add('hidden');
  $('triple-left-image').src = '';
  $('triple-center-image').src = '';
  $('triple-right-image').src = '';
  $('badge-posted').classList.add('hidden');
  $('badge-disregard').classList.add('hidden');
  $('item-names').textContent = '(navigate to a photo)';
  $('filename-label').textContent = '';
}

function navigate(dir) {
  if (state.images.length === 0) return;
  let idx = state.currentIndex + dir;
  if (idx < 0) idx = state.images.length - 1;
  if (idx >= state.images.length) idx = 0;
  if (state.viewMode === 'single') {
    displayImage(idx);
  } else {
    state.currentIndex = idx;
    updateGridHighlights();
    scrollGridTo(idx);
    $('counter-label').textContent = `${idx + 1} / ${state.images.length}`;
  }
}

async function updateItemNames(index) {
  const names = await eel.get_item_names_for_index(index)();
  $('item-names').textContent = names || '(no item names)';
}

function getExt(filename) {
  const dot = filename.lastIndexOf('.');
  return dot >= 0 ? filename.substring(dot).toLowerCase() : '';
}

// ── Grid View ──
function toggleView() {
  if (state.viewMode === 'single') {
    state.viewMode = 'grid';
    $('single-view').classList.add('hidden');
    $('grid-view').classList.remove('hidden');
    $('grid-toggle-btn').textContent = 'Single View';
    $('prev-btn').disabled = true;
    $('next-btn').disabled = true;
    buildGrid();
    $('counter-label').textContent = `${state.images.length} items`;
  } else {
    state.viewMode = 'single';
    $('grid-view').classList.add('hidden');
    $('single-view').classList.remove('hidden');
    $('grid-toggle-btn').textContent = 'Grid View';
    $('prev-btn').disabled = false;
    $('next-btn').disabled = false;
    state.gridSelected.clear();
    displayImage(state.currentIndex);
  }
}

function appendGridCell(img, i) {
  const container = $('grid-container');
  const cell = document.createElement('div');
  cell.className = 'grid-cell';
  cell.dataset.index = i;
  if (i === state.currentIndex) cell.classList.add('current');

  const wrap = document.createElement('div');
  wrap.className = 'grid-thumb-wrap';
  const thumb = document.createElement('img');
  const isPair = img.type === 'pair';
  const isTriple = img.type === 'triple';
  thumb.src = (isPair || isTriple) ? (img.left.thumb_url || img.left.url) : (img.thumb_url || img.url);
  thumb.loading = 'lazy';
  thumb.alt = '';
  wrap.appendChild(thumb);

  // Play icon overlay for video files
  const videoExts = ['.mp4', '.mov', '.avi', '.mkv', '.webm', '.m4v'];
  const hasVideo = isPair
    ? (videoExts.includes(getExt(img.left.filename)) || videoExts.includes(getExt(img.right.filename)))
    : isTriple ? false
    : videoExts.includes(getExt(img.filename || ''));
  if (hasVideo) {
    const playIcon = document.createElement('div');
    playIcon.className = 'grid-play-icon';
    playIcon.innerHTML = '&#9654;';
    wrap.appendChild(playIcon);
  }

  cell.appendChild(wrap);

  const fname = document.createElement('div');
  fname.className = 'grid-fname';
  fname.textContent = isTriple ? `[3x] ${img.left.filename}` : isPair ? `[2x] ${img.left.filename}` : (img.filename || '');
  cell.appendChild(fname);

  // Badges
  if (img.fields && img.fields['SB Posted']) {
    const b = document.createElement('div');
    b.className = 'grid-badge grid-badge-posted';
    b.textContent = 'POSTED';
    cell.appendChild(b);
  }
  if (img.fields && img.fields['Disregard']) {
    const b = document.createElement('div');
    b.className = 'grid-badge grid-badge-disregard';
    b.textContent = 'DISREGARD';
    cell.appendChild(b);
  }
  if (isTriple) {
    const b = document.createElement('div');
    b.className = 'grid-badge grid-badge-pair';
    b.textContent = '3x';
    cell.appendChild(b);
  } else if (isPair) {
    const b = document.createElement('div');
    b.className = 'grid-badge grid-badge-pair';
    b.textContent = '2x';
    cell.appendChild(b);
  }

  cell.addEventListener('click', (e) => onGridClick(i, e));
  container.appendChild(cell);
}

function buildGrid() {
  const container = $('grid-container');
  container.innerHTML = '';
  state.gridSelected.clear();
  state.images.forEach((img, i) => appendGridCell(img, i));
  scrollGridTo(state.currentIndex);
}

function onGridClick(index, event) {
  if (event && event.ctrlKey) {
    if (state.gridSelected.has(index)) {
      state.gridSelected.delete(index);
    } else {
      state.gridSelected.add(index);
    }
    updateGridHighlights();
    const count = state.gridSelected.size;
    $('counter-label').textContent = count > 0 ? `${count} selected` : `${state.images.length} items`;
    return;
  }

  state.gridSelected.clear();
  state.currentIndex = index;
  const clickedImg = state.images[index];

  // Paired/Triple items → show preview modal
  if (clickedImg.type === 'pair' || clickedImg.type === 'triple') {
    showPreview(index);
    updateItemNames(index);
    return;
  }

  // Single items → switch to single view
  state.viewMode = 'single';
  $('grid-view').classList.add('hidden');
  $('single-view').classList.remove('hidden');
  $('grid-toggle-btn').textContent = 'Grid View';
  $('prev-btn').disabled = false;
  $('next-btn').disabled = false;
  displayImage(index);
}

function updateGridHighlights() {
  const cells = $('grid-container').querySelectorAll('.grid-cell');
  cells.forEach((cell) => {
    const idx = parseInt(cell.dataset.index);
    cell.classList.toggle('selected', state.gridSelected.has(idx));
    cell.classList.toggle('current', idx === state.currentIndex && !state.gridSelected.has(idx));
  });
}

function scrollGridTo(index) {
  const cell = $('grid-container').querySelector(`[data-index="${index}"]`);
  if (cell) cell.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

// ── Preview Modal ──
function showPreview(index) {
  const img = state.images[index];
  if (img.type !== 'pair' && img.type !== 'triple') return;

  state.currentIndex = index;
  const isTriple = img.type === 'triple';
  const videoExts = ['.mp4', '.mov', '.avi', '.mkv', '.webm', '.m4v'];

  // Center panel visibility
  const centerSide = $('preview-center-side');
  if (isTriple) {
    centerSide.classList.add('visible');
  } else {
    centerSide.classList.remove('visible');
  }

  if (isTriple) {
    $('preview-title').textContent = 'Product Closeup Preview (3 Photos)';

    $('preview-left-label').textContent = img.left.label || 'Blended Image';
    $('preview-center-label').textContent = img.center.label || 'Closeup Photo One';
    $('preview-right-label').textContent = img.right.label || 'Closeup Photo Two';

    // Left media
    const leftContainer = $('preview-left-media');
    leftContainer.innerHTML = '';
    const il = document.createElement('img');
    il.src = img.left.url;
    leftContainer.appendChild(il);

    // Center media
    const centerContainer = $('preview-center-media');
    centerContainer.innerHTML = '';
    const ic = document.createElement('img');
    ic.src = img.center.url;
    centerContainer.appendChild(ic);

    // Right media
    const rightContainer = $('preview-right-media');
    rightContainer.innerHTML = '';
    const ir = document.createElement('img');
    ir.src = img.right.url;
    rightContainer.appendChild(ir);

    $('preview-info').innerHTML =
      `<strong>${img.left.label || 'Blended Image'}:</strong> ${img.left.filename}<br>` +
      `<strong>${img.center.label || 'Closeup Photo One'}:</strong> ${img.center.filename}<br>` +
      `<strong>${img.right.label || 'Closeup Photo Two'}:</strong> ${img.right.filename}`;

    $('counter-label').textContent = `${index + 1} / ${state.images.length}`;
    $('filename-label').textContent = `${img.left.filename}  |  ${img.center.filename}  |  ${img.right.filename}`;
  } else {
    // Paired (2 images)
    const leftIsVideo = videoExts.includes(getExt(img.left.filename));
    const rightIsVideo = videoExts.includes(getExt(img.right.filename));

    const type = (leftIsVideo || rightIsVideo) ? 'Video' : 'Image';
    $('preview-title').textContent = `Before + After ${type} Preview`;

    $('preview-left-label').textContent = img.left.filename;
    $('preview-right-label').textContent = img.right.filename;

    // Left media
    const leftContainer = $('preview-left-media');
    leftContainer.innerHTML = '';
    if (leftIsVideo) {
      const v = document.createElement('video');
      v.controls = true;
      v.src = img.left.url;
      leftContainer.appendChild(v);
    } else {
      const i = document.createElement('img');
      i.src = img.left.url;
      leftContainer.appendChild(i);
    }

    // Right media
    const rightContainer = $('preview-right-media');
    rightContainer.innerHTML = '';
    if (rightIsVideo) {
      const v = document.createElement('video');
      v.controls = true;
      v.src = img.right.url;
      rightContainer.appendChild(v);
    } else {
      const i = document.createElement('img');
      i.src = img.right.url;
      rightContainer.appendChild(i);
    }

    $('preview-info').innerHTML =
      `<strong>${img.left.label || 'Before'}:</strong> ${img.left.filename}<br>` +
      `<strong>${img.right.label || 'After'}:</strong> ${img.right.filename}`;

    let marks = '';
    if (img.fields && img.fields['SB Posted']) marks += ' [POSTED]';
    if (img.fields && img.fields['Disregard']) marks += ' [DISREGARD]';
    $('counter-label').textContent = `${index + 1} / ${state.images.length}${marks}`;
    $('filename-label').textContent = `${img.left.filename}  |  ${img.right.filename}`;
  }

  $('preview-modal').classList.remove('hidden');
}

function closePreview() {
  const modal = $('preview-modal');
  if (modal.classList.contains('hidden')) return;
  modal.querySelectorAll('video').forEach(v => { v.pause(); v.removeAttribute('src'); });
  modal.classList.add('hidden');
}

// ── Context Menu ──
function onContextMenu(e) {
  const cell = e.target.closest('.grid-cell');
  const inSingle = $('single-view').contains(e.target) && !$('single-view').classList.contains('hidden');

  if (!cell && !inSingle) {
    hideContextMenu();
    return;
  }
  e.preventDefault();

  let targetIndex;
  if (cell) {
    targetIndex = parseInt(cell.dataset.index);
    if (state.gridSelected.size > 0 && !state.gridSelected.has(targetIndex)) {
      state.gridSelected.clear();
      updateGridHighlights();
    }
    if (state.gridSelected.size === 0) {
      state.gridSelected.add(targetIndex);
      updateGridHighlights();
      $('counter-label').textContent = '1 selected';
    }
  } else {
    targetIndex = state.currentIndex;
    state.gridSelected.clear();
    state.gridSelected.add(targetIndex);
  }

  const indices = cell ? [...state.gridSelected] : [targetIndex];
  const anyDisregarded = indices.some(i => state.images[i].fields && state.images[i].fields['Disregard']);
  const anyNot = indices.some(i => !(state.images[i].fields && state.images[i].fields['Disregard']));
  const count = indices.length;
  const suffix = count > 1 ? ` (${count})` : '';

  const menu = $('context-menu');
  $('ctx-disregard').textContent = `Disregard${suffix}`;
  $('ctx-undo-disregard').textContent = `Undo Disregard${suffix}`;
  $('ctx-disregard').classList.toggle('hidden', !anyNot);
  $('ctx-undo-disregard').classList.toggle('hidden', !anyDisregarded);

  // Show "Convert to IG Story" only for single images (not videos, not multi-select)
  const videoExts = ['.mp4', '.mov', '.avi', '.mkv', '.webm', '.m4v'];
  const singleTarget = indices.length === 1 ? state.images[indices[0]] : null;
  let showIgStory = false;
  if (singleTarget) {
    if (singleTarget.type === 'pair') {
      // For pairs, check if left side is an image (not video)
      showIgStory = !videoExts.includes(getExt(singleTarget.left.filename));
    } else {
      showIgStory = !videoExts.includes(getExt(singleTarget.filename || ''));
    }
  }
  $('ctx-ig-story').classList.toggle('hidden', !showIgStory);
  $('ctx-wm-upper').classList.toggle('hidden', !showIgStory);
  $('ctx-wm-lower').classList.toggle('hidden', !showIgStory);
  // Hide divider if image options are hidden
  const divider = document.querySelector('.ctx-divider');
  if (divider) divider.classList.toggle('hidden', !showIgStory);

  menu.style.left = e.clientX + 'px';
  menu.style.top = e.clientY + 'px';
  menu.classList.remove('hidden');
}

function hideContextMenu() {
  $('context-menu').classList.add('hidden');
}

function doDisregard(disregard) {
  hideContextMenu();
  const indices = state.gridSelected.size > 0 ? [...state.gridSelected] : [state.currentIndex];
  $('status-label').textContent = disregard ? `Disregarding ${indices.length} record(s)...` : `Un-disregarding...`;
  eel.disregard_records(indices, disregard);
}

eel.expose(on_disregard_done);
function on_disregard_done(updatedIndices, disregard) {
  updatedIndices.forEach(i => {
    if (!state.images[i].fields) state.images[i].fields = {};
    state.images[i].fields['Disregard'] = disregard;
  });
  state.gridSelected.clear();
  $('status-label').textContent = 'Done!';
  if (state.viewMode === 'grid') {
    buildGrid();
  } else {
    displayImage(state.currentIndex);
  }
}

// ── Caption ──
async function onGenerateCaption() {
  if (state.images.length === 0) return;
  $('gen-caption-btn').disabled = true;
  $('gen-caption-btn').textContent = 'Generating...';
  eel.generate_caption(state.currentIndex);
}

eel.expose(on_caption_ready);
function on_caption_ready(caption) {
  $('caption-text').value = caption;
  $('gen-caption-btn').disabled = false;
  $('gen-caption-btn').textContent = 'Generate Caption';
}

eel.expose(on_caption_error);
function on_caption_error(error) {
  $('caption-text').value = `Error: ${error}`;
  $('gen-caption-btn').disabled = false;
  $('gen-caption-btn').textContent = 'Generate Caption';
}

// ── Posting ──
function updatePostButton() {
  const btn = $('post-btn');
  if (state.zohoMode) {
    btn.textContent = 'Ready to Post Closeup Videos';
    btn.className = 'action-btn purple-btn';
  } else if (state.tripleMode) {
    btn.textContent = 'Ready to Post Product Closeup';
    btn.className = 'action-btn purple-btn';
  } else if (state.pairedMode && state.pairedFieldName === 'Before Reels + After Reels') {
    btn.textContent = 'Ready to Post Before and After Reels';
    btn.className = 'action-btn purple-btn';
  } else if (state.pairedMode) {
    btn.textContent = 'Ready to Post Before and After';
    btn.className = 'action-btn purple-btn';
  } else {
    btn.textContent = 'Post to SocialBee';
    btn.className = 'action-btn yellow-btn';
  }
}

function getPostParams() {
  const caption = $('caption-text').value.trim();
  const category = $('category-input').value.trim() || null;
  let scheduleDate = null;
  let scheduleTime = null;
  if (!$('post-now-check').checked) {
    scheduleDate = $('schedule-date').value;
    const h = $('schedule-hour').value.padStart(2, '0');
    const m = $('schedule-minute').value.padStart(2, '0');
    scheduleTime = `${h}:${m}`;
  }
  return { caption, category, scheduleDate, scheduleTime };
}

function onPost() {
  if (state.posting || state.images.length === 0) return;
  const { caption, category, scheduleDate, scheduleTime } = getPostParams();
  if (!caption) { alert('Generate or type a caption first.'); return; }
  state.posting = true;
  $('post-btn').disabled = true;
  $('post-btn').textContent = 'Posting...';
  $('post-status').textContent = 'Downloading & posting...';
  eel.post_to_sb(state.currentIndex, caption, category, scheduleDate, scheduleTime);
}

function onPostStory() {
  if (state.posting || state.images.length === 0) return;
  const { caption, category, scheduleDate, scheduleTime } = getPostParams();
  state.posting = true;
  $('post-story-btn').disabled = true;
  $('post-story-btn').textContent = 'Posting Story...';
  $('post-status').textContent = 'Downloading & posting story...';
  eel.post_story_to_sb(state.currentIndex, caption, category, scheduleDate, scheduleTime);
}

eel.expose(on_post_result);
function on_post_result(status, message) {
  state.posting = false;
  $('post-btn').disabled = false;
  updatePostButton();
  if (status === 'success') {
    $('post-status').textContent = 'Posted successfully! Marking in Airtable...';
    alert(message);
    eel.mark_posted(state.currentIndex);
  } else {
    $('post-status').textContent = `Error: ${message}`;
    alert(`Error: ${message}`);
  }
}

eel.expose(on_post_story_result);
function on_post_story_result(status, message) {
  state.posting = false;
  $('post-story-btn').disabled = false;
  $('post-story-btn').textContent = 'Post to SocialBee Story';
  if (status === 'success') {
    $('post-status').textContent = 'Story posted! Marking in Airtable...';
    alert(message);
    eel.mark_posted(state.currentIndex);
  } else {
    $('post-status').textContent = `Error: ${message}`;
    alert(`Error: ${message}`);
  }
}

eel.expose(on_posted_marked);
function on_posted_marked(index) {
  if (state.images[index]) {
    if (!state.images[index].fields) state.images[index].fields = {};
    state.images[index].fields['SB Posted'] = true;
  }
  $('post-status').textContent = 'Posted & marked in Airtable!';
  if (state.viewMode === 'grid') {
    buildGrid();
  } else {
    displayImage(state.currentIndex);
  }
}

// ── Setup Login ──
function onSetup(type) {
  const btn = type === 'post' ? $('setup-chrome-post-btn') : $('setup-chrome-story-btn');
  btn.disabled = true;
  btn.textContent = 'Browser open...';
  $('post-status').textContent = 'Log in to SocialBee in the browser, then close it.';
  if (type === 'post') eel.setup_chrome_post();
  else eel.setup_chrome_story();
}

eel.expose(on_setup_done);
function on_setup_done(message) {
  $('setup-chrome-post-btn').disabled = false;
  $('setup-chrome-post-btn').textContent = 'Setup Login (Chrome - Post)';
  $('setup-chrome-story-btn').disabled = false;
  $('setup-chrome-story-btn').textContent = 'Setup Login (Chrome - Story)';
  $('post-status').textContent = message;
}

// ── Schedule Toggle ──
function toggleSchedule() {
  $('schedule-controls').classList.toggle('hidden', $('post-now-check').checked);
}

// ── Video Download (fallback for non-playable) ──
eel.expose(on_video_progress);
function on_video_progress(pct, downloadedMb, totalMb) {
  if (pct >= 100) {
    $('status-label').textContent = 'Video opened in player.';
  } else {
    $('status-label').textContent = `Downloading video... ${pct}%`;
  }
}

// ── Watermark ──
function addWatermark(position) {
  hideContextMenu();
  const indices = state.gridSelected.size > 0 ? [...state.gridSelected] : [state.currentIndex];
  if (indices.length !== 1) return;
  const index = indices[0];

  // Show loading overlay
  const overlay = document.createElement('div');
  overlay.id = 'convert-overlay';
  overlay.innerHTML = '<div class="convert-spinner"></div><div class="convert-text">Adding watermark...</div>';
  $('image-container').appendChild(overlay);

  // Send current displayed image src (could be base64 from IG Story conversion)
  const currentSrc = $('main-image').src || '';
  eel.add_watermark(index, position, currentSrc);
}

eel.expose(on_watermark_done);
function on_watermark_done(success, dataUriOrError) {
  const overlay = document.getElementById('convert-overlay');
  if (overlay) overlay.remove();

  if (success) {
    $('main-image').classList.remove('hidden');
    $('main-image').src = dataUriOrError;
    showToast('Watermark added!');
  } else {
    showToast('Error: ' + dataUriOrError, true);
  }
}

// ── Convert to IG Story ──
function onConvertIgStory() {
  hideContextMenu();
  const indices = state.gridSelected.size > 0 ? [...state.gridSelected] : [state.currentIndex];
  if (indices.length !== 1) return;
  const index = indices[0];

  // Show loading overlay on the image
  const overlay = document.createElement('div');
  overlay.id = 'convert-overlay';
  overlay.innerHTML = '<div class="convert-spinner"></div><div class="convert-text">Converting to Story...</div>';
  $('image-container').appendChild(overlay);

  eel.convert_to_ig_story(index);
}

eel.expose(on_story_converted);
function on_story_converted(success, dataUriOrError) {
  // Remove loading overlay
  const overlay = document.getElementById('convert-overlay');
  if (overlay) overlay.remove();

  if (success) {
    // Replace the displayed image with the converted version
    $('main-image').classList.remove('hidden');
    $('main-image').src = dataUriOrError;
    showToast('Converted to Instagram Story (1080x1920)');
  } else {
    showToast('Error: ' + dataUriOrError, true);
  }
}

function showToast(message, isError) {
  const toast = $('toast');
  $('toast-icon').innerHTML = isError ? '&#10007;' : '&#10003;';
  $('toast-text').textContent = message;
  toast.className = isError ? 'error' : '';
  toast.classList.remove('hidden');
  setTimeout(() => toast.classList.add('hidden'), 4000);
}

// ── Start ──
document.addEventListener('DOMContentLoaded', initApp);
