const CATEGORY_GROUPS = [
  {
    title: "Image Archive",
    items: [
      {
        id: "blended-image",
        label: "Blended Image",
        description: "Image Archive",
        fetchField: "Blended Image",
        fetchLabel: "Blended Image",
        fetchKind: "single",
        postCategory: "Blended Image",
      },
      {
        id: "moodboard-image",
        label: "Moodboard Image",
        description: "Image Archive",
        fetchField: "Moodboard Image",
        fetchLabel: "Moodboard Image",
        fetchKind: "single",
        postCategory: "Moodboard",
      },
      {
        id: "before-and-after",
        label: "Before and After",
        description: "Image Archive",
        fetchField: "Blended Image + Styled Photo",
        fetchLabel: "Before and After",
        fetchKind: "pair",
        pairLabels: ["Before", "After"],
        postCategory: "Before and After",
      },
      {
        id: "closeup-photos",
        label: "Closeup Photos",
        description: "Image Archive",
        fetchField: "Blended Image + Closeup Photo One + Closeup Photo Two",
        fetchLabel: "Closeup Photos",
        fetchKind: "triple",
        tripleLabels: ["Blended Image", "Closeup Photo One", "Closeup Photo Two"],
        postCategory: "Product Features",
      },
    ],
  },
  {
    title: "Reel Archive",
    items: [
      {
        id: "styled-reels",
        label: "Styled Reels",
        description: "Reel Archive",
        fetchField: "After Reels",
        fetchLabel: "Styled Reels",
        fetchKind: "single",
        postCategory: "Styled Photo",
      },
      {
        id: "tips-reels",
        label: "Tips Reels",
        description: "Reel Archive",
        fetchField: "After Reels",
        fetchLabel: "Tips Reels",
        fetchKind: "single",
        postCategory: "Style Feature",
      },
      {
        id: "before-and-after-reels",
        label: "Before and After Reels",
        description: "Reel Archive",
        fetchField: "Combine Video Before and After",
        fetchLabel: "Before and After Reels",
        fetchKind: "zoho",
        postCategory: "Before and After",
      },
      {
        id: "closeup-reels",
        label: "Closeup Reels",
        description: "Reel Archive",
        fetchField: "Closeup Videos",
        fetchLabel: "Closeup Reels",
        fetchKind: "zoho",
        postCategory: "Product Features",
      },
    ],
  },
  {
    title: "Library Meta",
    items: [
      {
        id: "collection-category",
        label: "Collection Category",
        description: "Library Meta",
        fetchField: null,
        fetchKind: "local",
        localSourceField: "Collection Categ System",
        postCategory: "Collection Category",
      },
      {
        id: "tips-and-education",
        label: "Tips and Education",
        description: "Library Meta",
        fetchField: null,
        fetchKind: "local",
        localSourceField: "Tips Educational Photos",
        postCategory: "Style Feature",
      },
      {
        id: "quotes-photos",
        label: "Quotes Photos",
        description: "Library Meta",
        fetchField: null,
        fetchKind: "local",
        localSourceField: "Quotes Photos",
        postCategory: "Style Feature",
      },
    ],
  },
];

const CATEGORY_DESCRIPTIONS = {
  "blended-image": "Composite stills and merged visual treatments.",
  "moodboard-image": "Reference boards, styling direction, and atmosphere studies.",
  "before-and-after": "Side-by-side transformations staged as a paired image review set.",
  "closeup-photos": "Three-photo product feature sets combining the hero frame with two close detail shots.",
  "styled-reels": "Styled product reels staged with a branded placeholder before playback.",
  "tips-reels": "Styled reels converted into 9:16 AI tip videos with animated overlay text.",
  "before-and-after-reels": "Transformation reels presented with a placeholder poster and inline playback preview.",
  "closeup-reels": "Close detail video cuts with branded placeholder cards and modal playback.",
  "collection-category": "Persistent local library for collection-ready photos queued without re-uploading old picks.",
  "tips-and-education": "Persistent local library for tips and education photos, staged for quick reuse and posting.",
  "quotes-photos": "Persistent local library for quote photos, staged for quick reuse and posting.",
};

const FRONTEND_BUILD = "2026-04-29-tips-reels-03";
const VIDEO_EXTENSIONS = new Set([".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"]);

const CATEGORY_MAP = new Map(
  CATEGORY_GROUPS.flatMap((group) => group.items.map((item) => [item.id, item])),
);

const FILTERS = [
  { id: "all", label: "All" },
  { id: "posted", label: "Posted" },
  { id: "pending", label: "Not Posted" },
  { id: "disregard", label: "Disregard" },
];

const state = {
  sourceId: null,
  sourceName: "",
  activeCategory: "blended-image",
  activeFilter: "all",
  categories: {},
  nextSessionSeq: 0,
  previewOpen: false,
  posting: false,
  settingUpLogin: false,
  postContext: null,
  generatingCaption: false,
  runtimeInfo: {
    checked: false,
    build: "",
    runtime: "",
    frozen: null,
    hasToggleDisregard: false,
  },
  contextMenu: {
    open: false,
    categoryId: null,
    index: null,
    x: 0,
    y: 0,
  },
};

const $ = (id) => document.getElementById(id);

function eelFunctionAvailable(name) {
  return !!(window.eel && typeof eel[name] === "function");
}

function hasDisregardCapability() {
  return !!state.runtimeInfo.hasToggleDisregard;
}

function getDisregardUnavailableMessage() {
  const backendBuild = state.runtimeInfo.build ? ` (backend ${state.runtimeInfo.build})` : "";
  return `This app runtime${backendBuild} does not support Disregard yet. Restart the app or rebuild the exe.`;
}

function renderBuildInfo() {
  const node = $("build-info");
  if (!node) {
    return;
  }

  if (!state.runtimeInfo.checked) {
    node.textContent = `Runtime: checking build...`;
    return;
  }

  const runtimeLabel = state.runtimeInfo.runtime
    ? `${state.runtimeInfo.runtime.toUpperCase()} runtime`
    : "Runtime";
  const buildLabel = state.runtimeInfo.build || "legacy backend";
  const capabilityLabel = hasDisregardCapability() ? "Disregard ready" : "Restart for Disregard";
  node.textContent = `${runtimeLabel} | frontend ${FRONTEND_BUILD} | backend ${buildLabel} | ${capabilityLabel}`;
}

async function loadRuntimeInfo() {
  state.runtimeInfo.hasToggleDisregard = eelFunctionAvailable("toggle_disregard");

  if (eelFunctionAvailable("get_app_build_info")) {
    try {
      const info = await eel.get_app_build_info()();
      if (info && typeof info === "object") {
        state.runtimeInfo.build = String(info.build || "").trim();
        state.runtimeInfo.runtime = String(info.runtime || "").trim();
        state.runtimeInfo.frozen = Object.prototype.hasOwnProperty.call(info, "frozen")
          ? !!info.frozen
          : null;
      }
    } catch (error) {
      console.warn("Could not load app build info:", error);
    }
  }

  state.runtimeInfo.checked = true;
  renderBuildInfo();
}

function createCategoryState() {
  return {
    images: [],
    currentIndex: null,
    previewIndex: null,
    sessionId: null,
    loadedSessionId: null,
    hasLoadedOnce: false,
    streaming: false,
    fetchDone: 0,
    fetchTotal: 0,
    fetchError: "",
    preserveVisible: false,
    uploadingCount: 0,
    pendingDisregard: null,
    comboSelected: new Set(),
  };
}

function getCategoryConfig(categoryId = state.activeCategory) {
  return CATEGORY_MAP.get(categoryId);
}

function activeCategoryConfig() {
  return getCategoryConfig(state.activeCategory);
}

function getCategoryState(categoryId = state.activeCategory) {
  if (!state.categories[categoryId]) {
    state.categories[categoryId] = createCategoryState();
  }
  return state.categories[categoryId];
}

function currentCategoryState() {
  return getCategoryState(state.activeCategory);
}

function createSessionId(categoryId) {
  state.nextSessionSeq += 1;
  return `${categoryId}::${state.nextSessionSeq}`;
}

function categoryIdForSession(sessionId) {
  if (!sessionId) {
    return null;
  }
  return Object.keys(state.categories).find((categoryId) => {
    const lane = state.categories[categoryId];
    return lane && lane.sessionId === sessionId;
  }) || null;
}

function getPendingDisregard(categoryId = state.activeCategory) {
  const lane = getCategoryState(categoryId);
  return lane.pendingDisregard || null;
}

function isDisregardPending(categoryId = state.activeCategory) {
  return !!getPendingDisregard(categoryId);
}

function isLaneMutationBusy(categoryId = state.activeCategory) {
  return isDisregardPending(categoryId);
}

function getDisregardBusyMessage() {
  return "Wait for the Zoho archive to finish before changing this item.";
}

function isFetchBackedCategory(categoryId = state.activeCategory) {
  const config = getCategoryConfig(categoryId);
  return !!(config && config.fetchField);
}

function isLocalUploadCategory(categoryId = state.activeCategory) {
  const config = getCategoryConfig(categoryId);
  return !!(config && config.localSourceField);
}

function isMediaBackedCategory(categoryId = state.activeCategory) {
  const config = getCategoryConfig(categoryId);
  return !!(config && (config.fetchField || config.localSourceField));
}

function isLaneReady(categoryId = state.activeCategory) {
  if (!isMediaBackedCategory(categoryId)) {
    return false;
  }
  const lane = getCategoryState(categoryId);
  return !!(
    lane.sessionId
    && lane.loadedSessionId === lane.sessionId
    && lane.hasLoadedOnce
    && !lane.streaming
    && lane.uploadingCount === 0
    && !lane.pendingDisregard
  );
}

function getSourceLabel(categoryId = state.activeCategory) {
  const config = getCategoryConfig(categoryId);
  return config ? (config.fetchLabel || config.label || config.fetchField || "selected field") : "selected field";
}

function itemMatchesFilter(img, filterId = state.activeFilter) {
  const posted = !!(img && img.fields && img.fields["SB Posted"]);
  const disregarded = !!(img && img.fields && img.fields["Disregard"]);
  switch (filterId) {
    case "posted":
      return posted;
    case "disregard":
      return disregarded;
    case "pending":
      return !posted && !disregarded;
    default:
      return true;
  }
}

function readyCombinedSourceIndexSet(categoryId = state.activeCategory) {
  const hidden = new Set();
  if (categoryId !== "tips-reels") {
    return hidden;
  }
  const lane = getCategoryState(categoryId);
  lane.images.forEach((img) => {
    const status = getTipsReelStatus(img);
    if (!img || img.type !== "tips_combo" || status === "error" || !Array.isArray(img.source_indices)) {
      return;
    }
    img.source_indices.forEach((sourceIndex) => {
      const index = Number(sourceIndex);
      if (Number.isInteger(index) && lane.images[index] && lane.images[index].type !== "tips_combo") {
        hidden.add(index);
      }
    });
  });
  return hidden;
}

function visibleItems(categoryId = state.activeCategory, filterId = state.activeFilter) {
  const lane = getCategoryState(categoryId);
  const hiddenComboSources = readyCombinedSourceIndexSet(categoryId);
  const out = [];
  lane.images.forEach((img, index) => {
    if (hiddenComboSources.has(index)) {
      return;
    }
    if (itemMatchesFilter(img, filterId)) {
      out.push({ img, index });
    }
  });
  return out;
}

function categoryCounts(categoryId) {
  if (!isMediaBackedCategory(categoryId)) {
    return 0;
  }
  const lane = getCategoryState(categoryId);
  if (categoryId === "tips-reels" && lane.images.length === 0) {
    return getCategoryState("styled-reels").images.length;
  }
  return visibleItems(categoryId, "all").length;
}

function postedCount(categoryId = state.activeCategory) {
  if (!isMediaBackedCategory(categoryId)) {
    return 0;
  }
  return visibleItems(categoryId, "all").filter(({ img }) => img.fields && img.fields["SB Posted"]).length;
}

function disregardCount(categoryId = state.activeCategory) {
  if (!isMediaBackedCategory(categoryId)) {
    return 0;
  }
  return visibleItems(categoryId, "all").filter(({ img }) => img.fields && img.fields["Disregard"]).length;
}

function pendingCount(categoryId = state.activeCategory) {
  if (!isMediaBackedCategory(categoryId)) {
    return 0;
  }
  return visibleItems(categoryId, "all").filter(({ img }) => {
    const fields = img.fields || {};
    return !fields["SB Posted"] && !fields["Disregard"];
  }).length;
}

function selectedImage(categoryId = state.activeCategory) {
  const lane = getCategoryState(categoryId);
  if (lane.currentIndex === null) {
    return null;
  }
  return lane.images[lane.currentIndex] || null;
}

function previewedImage(categoryId = state.activeCategory) {
  const lane = getCategoryState(categoryId);
  if (lane.previewIndex === null) {
    return null;
  }
  return lane.images[lane.previewIndex] || null;
}

function formatDateForSummary(raw) {
  if (!raw) {
    return "--/--/----";
  }
  const [year, month, day] = raw.split("-");
  if (!year || !month || !day) {
    return raw;
  }
  return `${month}/${day}/${year}`;
}

function normalizeTimeInput(target, max) {
  const digits = String(target.value || "").replace(/\D/g, "").slice(0, 2);
  if (!digits) {
    target.value = "";
    return;
  }
  target.value = String(Math.min(Number(digits), max)).padStart(2, "0");
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function normalizeFieldText(value) {
  if (Array.isArray(value)) {
    return value.map((item) => String(item).trim()).filter(Boolean).join(", ");
  }
  return value ? String(value).trim() : "";
}

function getItemNameLinesFromFields(fields) {
  const lineOne = normalizeFieldText(fields && fields["Item Name from File"]);
  const lineTwo = normalizeFieldText(fields && fields["Item Name from File2"]);
  return [lineOne, lineTwo].filter(Boolean);
}

function getCardTitle(filename) {
  if (!filename) {
    return "Untitled";
  }
  const noExt = filename.replace(/\.[^.]+$/, "");
  return noExt
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (match) => match.toUpperCase());
}

function getFileExtension(filename) {
  const match = String(filename || "").toLowerCase().match(/(\.[^.]+)$/);
  return match ? match[1] : "";
}

function isVideoItem(img) {
  if (!img) {
    return false;
  }
  if (img.type === "tips_combo") {
    return true;
  }
  if (img.type === "zoho") {
    return true;
  }
  return VIDEO_EXTENSIONS.has(getFileExtension(img.filename));
}

function isTipsReelCategory(categoryId = state.activeCategory) {
  return categoryId === "tips-reels";
}

function isVideoUploadCategory(categoryId = state.activeCategory) {
  return categoryId === "styled-reels" || categoryId === "tips-reels";
}

function isTipsReelActionCategory(categoryId = state.activeCategory) {
  return categoryId === "tips-reels";
}

function canConvertToTipsReel(img, categoryId = state.activeCategory) {
  return !!(img && isVideoItem(img) && isTipsReelActionCategory(categoryId) && img.type !== "pair" && img.type !== "triple" && img.type !== "tips_combo");
}

function canUseInCombinedTipsReel(img, categoryId = state.activeCategory) {
  return !!(img && categoryId === "tips-reels" && isVideoItem(img) && img.type !== "pair" && img.type !== "triple" && img.type !== "tips_combo");
}

function getComboSelection(categoryId = state.activeCategory) {
  const lane = getCategoryState(categoryId);
  return [...(lane.comboSelected || new Set())]
    .filter((index) => lane.images[index] && canUseInCombinedTipsReel(lane.images[index], categoryId))
    .sort((a, b) => a - b);
}

function isCombinedTipsSelectionReady(categoryId = state.activeCategory) {
  return getComboSelection(categoryId).length === 3;
}

function clearComboSelection(categoryId = state.activeCategory) {
  getCategoryState(categoryId).comboSelected.clear();
}

function toggleComboSelection(index, categoryId = state.activeCategory) {
  const lane = getCategoryState(categoryId);
  const img = lane.images[index];
  if (!canUseInCombinedTipsReel(img, categoryId)) {
    return;
  }
  if (lane.comboSelected.has(index)) {
    lane.comboSelected.delete(index);
  } else {
    if (lane.comboSelected.size >= 3) {
      $("post-status").textContent = "Only 3 reels can be selected for one combined Tips Reel.";
      return;
    }
    lane.comboSelected.add(index);
  }
  renderAll();
  const count = getComboSelection(categoryId).length;
  $("post-status").textContent = count === 3
    ? "3 reels selected. Right-click one selected reel to convert them together."
    : `${count}/3 reels selected for combined Tips Reel.`;
}

function getTipsReelStatus(img) {
  const status = img && img.tips_reel && img.tips_reel.status ? img.tips_reel.status : "not_converted";
  return status || "not_converted";
}

function isTipsReelBusy(img) {
  return ["queued", "downloading_source", "analyzing_frames", "writing_tip", "generating_voiceover", "rendering"].includes(getTipsReelStatus(img));
}

function isTipsReelReady(img) {
  return getTipsReelStatus(img) === "ready" && !!(img && img.tips_reel && img.tips_reel.url);
}

function getTipsReelLabel(img) {
  if (img && img.tips_reel && img.tips_reel.label) {
    return img.tips_reel.label;
  }
  if (img && img.tips_reel && img.tips_reel.status === "analyzing_frames" && img.tips_reel.visual_source) {
    return `Analyzing ${img.tips_reel.visual_source}`;
  }
  const labels = {
    not_converted: "Not Converted",
    queued: "Queued",
    downloading_source: "Downloading source video",
    analyzing_frames: "Analyzing Row Image",
    writing_tip: "Writing AI tip",
    generating_voiceover: "Generating voiceover",
    rendering: "Rendering 9:16 video",
    ready: "Ready",
    error: "Error",
  };
  return labels[getTipsReelStatus(img)] || "Not Converted";
}

function getTipsReelDetail(img) {
  const status = img && img.tips_reel ? img.tips_reel : {};
  const statusName = getTipsReelStatus(img);
  const tip = status.tip ? `Tip: ${status.tip}` : "";
  if (statusName === "error") {
    return status.error ? `Error: ${status.error}` : "Conversion failed.";
  }
  if (status.voiceover_error) {
    return status.voiceover_error;
  }
  if (tip && ["generating_voiceover", "rendering", "ready"].includes(statusName)) {
    return tip;
  }
  if (statusName === "downloading_source") {
    return "Fetching the selected reel video.";
  }
  if (statusName === "analyzing_frames") {
    return "Reading the row image or a frame from the video.";
  }
  if (statusName === "writing_tip") {
    return "Asking LM Studio to write the short overlay tip.";
  }
  if (statusName === "queued") {
    return "Waiting for the conversion worker to start.";
  }
  return "";
}

function formatTipsReelStatusMessage(statusPayload, fallback = "Converting Tips Reel") {
  const label = statusPayload && statusPayload.label ? statusPayload.label : fallback;
  if (statusPayload && statusPayload.status === "ready") {
    return statusPayload.tip ? `Tips Reel ready. Tip: ${statusPayload.tip}` : "Tips Reel ready.";
  }
  if (statusPayload && statusPayload.status === "error") {
    return `${label}: ${statusPayload.error || "Conversion failed."}`;
  }
  if (statusPayload && statusPayload.voiceover_error) {
    return `${label}... ${statusPayload.voiceover_error}`;
  }
  if (statusPayload && statusPayload.tip && ["generating_voiceover", "rendering"].includes(statusPayload.status)) {
    return `${label}... Tip: ${statusPayload.tip}`;
  }
  return `${label}...`;
}

function withCacheBuster(url, value) {
  if (!url || !value) {
    return url || "";
  }
  const separator = url.includes("?") ? "&" : "?";
  return `${url}${separator}cb=${encodeURIComponent(String(value))}`;
}

function getTipsReelVideoUrl(img, categoryId = state.activeCategory) {
  if (isTipsReelCategory(categoryId) && isTipsReelReady(img)) {
    const version = img.tips_reel.render_version || img.tips_reel.updated_at || "";
    return withCacheBuster(img.tips_reel.url, version);
  }
  return img && img.url ? img.url : "";
}

function itemHasAirtableRecord(img) {
  return !!(img && img.base_id && img.table_id && img.record_id);
}

function isBlendedImageZohoSyncCandidate(img, categoryId = state.activeCategory) {
  return (
    categoryId === "blended-image"
    && !!img
    && !img.local_upload
    && img.type === "single"
    && itemHasAirtableRecord(img)
  );
}

function isDisregarded(img) {
  return !!(img && img.fields && img.fields["Disregard"]);
}

function getPostSyncProgressMessage(img, categoryId, isStory = false) {
  if (img && img.type === "tips_combo") {
    return "Posted successfully. Marking 3 source rows in Airtable...";
  }
  if (!itemHasAirtableRecord(img)) {
    return isStory ? "Story posted." : "Posted successfully.";
  }
  if (isBlendedImageZohoSyncCandidate(img, categoryId)) {
    return isStory
      ? "Story posted. Syncing Zoho and Airtable..."
      : "Posted successfully. Syncing Zoho and Airtable...";
  }
  return isStory
    ? "Story posted. Marking in Airtable..."
    : "Posted successfully. Marking in Airtable...";
}

function getPostCompletionMessage(img, categoryId, result, isStory = false) {
  const ok = !result || result.ok !== false;
  const warning = result && result.warning ? String(result.warning) : "";
  if (!ok) {
    return warning || (isStory
      ? "Story posted, but Airtable marking failed."
      : "Posted on SocialBee, but Airtable marking failed.");
  }
  if (warning) {
    return warning;
  }
  if (img && img.type === "tips_combo") {
    return "Posted and marked all 3 source rows in Airtable.";
  }
  if (result && result.zohoSynced && isBlendedImageZohoSyncCandidate(img, categoryId)) {
    return isStory
      ? "Story posted, marked in Airtable, and archived to Zoho."
      : "Posted, marked in Airtable, and archived to Zoho.";
  }
  return itemHasAirtableRecord(img)
    ? "Posted and marked in Airtable."
    : (isStory ? "Story posted." : "Posted successfully.");
}

function getMediaOriginLabel(img) {
  if (itemHasAirtableRecord(img)) {
    return "Airtable";
  }
  if (img && img.type === "zoho") {
    return "Zoho";
  }
  if (img && img.tips_reel_upload) {
    return "Uploaded";
  }
  return "Local";
}

function localUploadPanelMarkup(config, lane) {
  const isBusy = lane.streaming || lane.uploadingCount > 0;
  const helper = isBusy
    ? `Working on ${lane.uploadingCount > 0 ? `${lane.uploadingCount} upload${lane.uploadingCount === 1 ? "" : "s"}` : "your library"}...`
    : "Drag and drop photos here, or browse from your computer.";
  return `
    <section class="local-upload-panel">
      <div class="local-upload-copy">
        <p class="eyebrow">Local Queue</p>
        <h4>${escapeHtml(config.label)}</h4>
        <p>${escapeHtml(helper)}</p>
      </div>
      <div class="local-upload-actions">
        <div class="local-upload-dropzone${isBusy ? " busy" : ""}" data-local-dropzone="true" tabindex="0" role="button" aria-label="Upload photos to ${escapeHtml(config.label)}">
          <input class="local-upload-input" data-local-input="true" type="file" accept="image/*" multiple>
          <span class="local-upload-title">${isBusy ? "Uploading..." : "Drop Photos"}</span>
          <span class="local-upload-subtitle">Files append to this queue and stay available after restart.</span>
        </div>
      </div>
    </section>
  `;
}

function videoUploadPanelMarkup(lane, categoryId = state.activeCategory) {
  const isBusy = lane.streaming || lane.uploadingCount > 0;
  const helper = isBusy
    ? `Uploading ${lane.uploadingCount} video${lane.uploadingCount === 1 ? "" : "s"}...`
    : "Drag and drop video files here, or browse from your computer.";
  const config = getCategoryConfig(categoryId);
  return `
    <section class="local-upload-panel tips-reel-upload-panel">
      <div class="local-upload-copy">
        <p class="eyebrow">Video Upload</p>
        <h4>Upload ${escapeHtml(config.label || "Videos")}</h4>
        <p>${escapeHtml(helper)}</p>
      </div>
      <div class="local-upload-actions">
        <div class="local-upload-dropzone${isBusy ? " busy" : ""}" data-tips-reel-dropzone="true" tabindex="0" role="button" aria-label="Upload videos">
          <input class="local-upload-input" data-tips-reel-input="true" type="file" accept="video/*" multiple>
          <span class="local-upload-title">${isBusy ? "Uploading..." : "Drop Videos"}</span>
          <span class="local-upload-subtitle">Video files only. Uploaded reels stay saved for later use.</span>
        </div>
      </div>
    </section>
  `;
}

function galleryCardsMarkup(visible, lane, { allowDelete = false } = {}) {
  return visible.map(({ img, index }) => {
    const pendingDisregard = isCardPendingDisregard(img, index, lane);
    const comboSelected = !!(lane.comboSelected && lane.comboSelected.has(index));
    const tipsEligible = canConvertToTipsReel(img, state.activeCategory);
    const tipsStatusCapable = tipsEligible || (isTipsReelCategory() && img && img.type === "tips_combo");
    const tipsBusy = tipsStatusCapable && isTipsReelBusy(img);
    const tipsReady = tipsStatusCapable && isTipsReelReady(img);
    const tipsError = tipsStatusCapable && getTipsReelStatus(img) === "error";
    const tipsDetail = tipsStatusCapable ? getTipsReelDetail(img) : "";
    const badges = [
      index === lane.currentIndex ? '<span class="badge badge-target">Post Target</span>' : "",
      comboSelected ? '<span class="badge badge-combo">Combo Pick</span>' : "",
      isVideoItem(img)
        ? '<span class="badge badge-primary">Video</span>'
        : img.type === "triple"
        ? '<span class="badge badge-pair">Triple</span>'
        : (img.type === "pair" ? '<span class="badge badge-pair">Pair</span>' : '<span class="badge badge-primary">Image</span>'),
      tipsReady ? '<span class="badge badge-tips">Tips Ready</span>' : "",
      tipsBusy ? '<span class="badge badge-tips-working">Converting</span>' : "",
      tipsError ? '<span class="badge badge-tips-error">Tips Error</span>' : "",
      img.fields && img.fields["SB Posted"] ? '<span class="badge badge-surface">Posted</span>' : "",
      img.fields && img.fields["Disregard"] ? '<span class="badge badge-disregard">Disregard</span>' : "",
    ].join("");

    const statusText = pendingDisregard
      ? "Archiving..."
      : isTipsReelCategory()
      ? getTipsReelLabel(img)
      : tipsBusy
      ? getTipsReelLabel(img)
      : tipsReady
      ? "Tips Ready"
      : index === lane.currentIndex
      ? "Selected"
      : (isDisregarded(img) ? "Disregard" : (img.fields && img.fields["SB Posted"] ? "Posted" : "Ready"));
    const deleteAction = allowDelete && img.local_upload
      ? `<button class="gallery-delete-button" data-delete-upload="${escapeHtml(img.upload_id || "")}" data-index="${index}" type="button" aria-label="Remove ${escapeHtml(img.filename || "photo")}">Remove</button>`
      : "";
    const tipsDetailMarkup = tipsDetail && (tipsBusy || tipsError || (tipsReady && isTipsReelCategory()))
      ? `<p class="gallery-tips-detail">${escapeHtml(tipsDetail)}</p>`
      : "";
    const loadingMarkup = pendingDisregard
      ? `
          <div class="gallery-card-loading" aria-hidden="true">
            <div class="gallery-card-loading-inner">
              <span class="gallery-card-spinner"></span>
              <p class="gallery-card-loading-title">Sending to Zoho...</p>
              <p class="gallery-card-loading-subtitle">Archiving this photo to WorkDrive.</p>
            </div>
          </div>
        `
      : tipsBusy
      ? `
          <div class="gallery-card-loading tips-loading" aria-hidden="true">
            <div class="gallery-card-loading-inner">
              <span class="gallery-card-spinner"></span>
              <p class="gallery-card-loading-title">${escapeHtml(getTipsReelLabel(img))}</p>
              <p class="gallery-card-loading-subtitle">${escapeHtml(tipsDetail || "Converting this reel into a 9:16 tips video.")}</p>
            </div>
          </div>
        `
      : "";

    return `
      <article class="gallery-card-shell${index === lane.currentIndex ? " selected" : ""}${comboSelected ? " combo-selected" : ""}${pendingDisregard ? " pending-disregard" : ""}">
        <button class="gallery-card${index === lane.currentIndex ? " selected" : ""}${comboSelected ? " combo-selected" : ""}${pendingDisregard ? " pending-disregard" : ""}" data-index="${index}" type="button" aria-busy="${pendingDisregard || tipsBusy ? "true" : "false"}" aria-pressed="${comboSelected ? "true" : "false"}">
          <div class="gallery-thumb${img.type === "pair" ? " gallery-thumb-pair" : ""}${pendingDisregard ? " pending-disregard" : ""}">
            <div class="gallery-topline"></div>
            ${getGalleryMediaMarkup(img, state.activeCategory)}
            ${loadingMarkup}
            <div class="gallery-badges">${badges}</div>
            <div class="gallery-info">
              <p class="gallery-title">${escapeHtml(getGalleryTitle(img, state.activeCategory))}</p>
              <p class="gallery-filename">${escapeHtml(getGallerySubtitle(img, state.activeCategory))}</p>
              <div class="gallery-meta-row">
                <span>${getMediaOriginLabel(img)}</span>
                <span>${statusText}</span>
              </div>
              ${tipsDetailMarkup}
            </div>
          </div>
        </button>
        ${deleteAction}
      </article>
    `;
  }).join("");
}

function getImageKey(img) {
  if (!img) {
    return "";
  }
  if (img.type === "pair") {
    return [
      img.record_id || "-",
      "pair",
      img.left && img.left.filename ? img.left.filename : "",
      img.right && img.right.filename ? img.right.filename : "",
    ].join("|");
  }
  if (img.type === "triple") {
    return [
      img.record_id || "-",
      "triple",
      img.left && img.left.filename ? img.left.filename : "",
      img.center && img.center.filename ? img.center.filename : "",
      img.right && img.right.filename ? img.right.filename : "",
    ].join("|");
  }
  if (img.type === "tips_combo") {
    return `tips_combo|${img.combo_key || img.filename || ""}`;
  }
  if (img.type === "zoho") {
    return `zoho|${img.file_id || img.filename || img.url || ""}`;
  }
  if (img.record_id) {
    return `${img.record_id}:${img.type || "single"}:${img.filename || img.url || ""}`;
  }
  return img.url || img.filename || "";
}

function isCardPendingDisregard(img, index, lane = currentCategoryState()) {
  if (!lane || !lane.pendingDisregard || lane.pendingDisregard.nextDisregard !== true) {
    return false;
  }
  return lane.pendingDisregard.index === index && lane.pendingDisregard.imageKey === getImageKey(img);
}

function getPairSideLabels(img, categoryId = state.activeCategory) {
  const config = getCategoryConfig(categoryId);
  if (config && Array.isArray(config.pairLabels) && config.pairLabels.length === 2) {
    return config.pairLabels;
  }
  return [
    img && img.left && img.left.label ? img.left.label : "Before",
    img && img.right && img.right.label ? img.right.label : "After",
  ];
}

function getTripleSideLabels(img, categoryId = state.activeCategory) {
  const config = getCategoryConfig(categoryId);
  if (config && Array.isArray(config.tripleLabels) && config.tripleLabels.length === 3) {
    return config.tripleLabels;
  }
  return [
    img && img.left && img.left.label ? img.left.label : "Image One",
    img && img.center && img.center.label ? img.center.label : "Image Two",
    img && img.right && img.right.label ? img.right.label : "Image Three",
  ];
}

function getGalleryTitle(img, categoryId = state.activeCategory) {
  const lines = getItemNameLinesFromFields(img.fields || {});
  if (img.type === "tips_combo") {
    return lines[0] || "Combined Tips Reel";
  }
  if (img.type === "pair") {
    return lines[0] || "Before and After";
  }
  if (img.type === "triple") {
    const config = getCategoryConfig(categoryId);
    return lines[0] || (config ? config.label : "Closeup Photos");
  }
  return lines[0] || getCardTitle(img.filename);
}

function getGallerySubtitle(img, categoryId = state.activeCategory) {
  const lines = getItemNameLinesFromFields(img.fields || {});
  if (img.type === "tips_combo") {
    return lines[1] || "3 combined Tips Reel clips";
  }
  if (img.type === "pair") {
    if (lines[1]) {
      return lines[1];
    }
    const labels = getPairSideLabels(img, categoryId);
    return `${labels[0]} | ${labels[1]}`;
  }
  if (img.type === "triple") {
    if (lines[1]) {
      return lines[1];
    }
    return getTripleSideLabels(img, categoryId).join(" | ");
  }
  return img.filename || "";
}

function getPreviewTitle(img, categoryId = state.activeCategory) {
  const config = getCategoryConfig(categoryId);
  if (img.type === "pair" || img.type === "triple") {
    return config ? `${config.label} Preview` : "Multi-image Preview";
  }
  return getGalleryTitle(img, categoryId);
}

function getPreviewFooterText(img, categoryId = state.activeCategory) {
  if (img.type === "tips_combo") {
    return img.filename || "Combined Tips Reel";
  }
  if (img.type === "pair") {
    const labels = getPairSideLabels(img, categoryId);
    return `${labels[0]}: ${img.left.filename || ""} | ${labels[1]}: ${img.right.filename || ""}`;
  }
  if (img.type === "triple") {
    const labels = getTripleSideLabels(img, categoryId);
    return `${labels[0]}: ${img.left.filename || ""} | ${labels[1]}: ${img.center.filename || ""} | ${labels[2]}: ${img.right.filename || ""}`;
  }
  return img.filename || getSourceLabel(categoryId);
}

function getGalleryMediaMarkup(img, categoryId = state.activeCategory) {
  if (isVideoItem(img)) {
    const title = getGalleryTitle(img, categoryId);
    return `
      <div class="gallery-video-thumb">
        <div class="gallery-video-poster" role="img" aria-label="${escapeHtml(title)} video placeholder"></div>
        <span class="gallery-play-icon" aria-hidden="true">
          <svg viewBox="0 0 24 24" focusable="false">
            <path d="M8 6.5v11l9-5.5z"></path>
          </svg>
        </span>
      </div>
    `;
  }

  if (img.type === "pair") {
    const labels = getPairSideLabels(img, categoryId);
    return `
      <div class="gallery-pair-thumb">
        <div class="gallery-pair-pane">
          <img src="${escapeHtml(img.left.thumb_url || img.left.url)}" alt="${escapeHtml(labels[0])}" loading="lazy">
          <span class="gallery-pair-caption">${escapeHtml(labels[0])}</span>
        </div>
        <div class="gallery-pair-pane">
          <img src="${escapeHtml(img.right.thumb_url || img.right.url)}" alt="${escapeHtml(labels[1])}" loading="lazy">
          <span class="gallery-pair-caption">${escapeHtml(labels[1])}</span>
        </div>
      </div>
    `;
  }

  if (img.type === "triple") {
    const labels = getTripleSideLabels(img, categoryId);
    return `
      <div class="gallery-triple-thumb">
        <div class="gallery-pair-pane">
          <img src="${escapeHtml(img.left.thumb_url || img.left.url)}" alt="${escapeHtml(labels[0])}" loading="lazy">
          <span class="gallery-pair-caption">${escapeHtml(labels[0])}</span>
        </div>
        <div class="gallery-pair-pane">
          <img src="${escapeHtml(img.center.thumb_url || img.center.url)}" alt="${escapeHtml(labels[1])}" loading="lazy">
          <span class="gallery-pair-caption">${escapeHtml(labels[1])}</span>
        </div>
        <div class="gallery-pair-pane">
          <img src="${escapeHtml(img.right.thumb_url || img.right.url)}" alt="${escapeHtml(labels[2])}" loading="lazy">
          <span class="gallery-pair-caption">${escapeHtml(labels[2])}</span>
        </div>
      </div>
    `;
  }

  return `<img src="${escapeHtml(img.thumb_url || img.url)}" alt="${escapeHtml(img.filename || "photo")}" loading="lazy">`;
}

function reconcileLaneImages(lane, nextImages) {
  const previousSelectedKey = getImageKey(lane.currentIndex !== null ? lane.images[lane.currentIndex] : null);
  const previousPreviewKey = getImageKey(lane.previewIndex !== null ? lane.images[lane.previewIndex] : null);

  lane.images = nextImages || [];
  lane.comboSelected.clear();

  if (lane.images.length === 0) {
    lane.currentIndex = null;
    lane.previewIndex = null;
    return;
  }

  lane.currentIndex = previousSelectedKey
    ? lane.images.findIndex((img) => getImageKey(img) === previousSelectedKey)
    : -1;
  lane.previewIndex = previousPreviewKey
    ? lane.images.findIndex((img) => getImageKey(img) === previousPreviewKey)
    : -1;

  if (lane.currentIndex < 0) {
    lane.currentIndex = null;
  }
  if (lane.previewIndex < 0) {
    lane.previewIndex = null;
  }
}

function renderSidebar() {
  const container = $("sidebar-sections");
  container.innerHTML = CATEGORY_GROUPS.map((group) => `
    <section class="sidebar-group">
      <p class="sidebar-group-title">${group.title}</p>
      ${group.items.map((item) => `
        <button class="sidebar-item${state.activeCategory === item.id ? " active" : ""}" data-category="${item.id}" type="button">
          <div class="sidebar-item-row">
            <div>
              <strong>${item.label}</strong>
              <small>${item.description}</small>
            </div>
            <span class="sidebar-count">${categoryCounts(item.id)}</span>
          </div>
        </button>
      `).join("")}
    </section>
  `).join("");

  container.querySelectorAll("[data-category]").forEach((button) => {
    button.addEventListener("click", () => onCategorySelect(button.dataset.category));
  });

}

function renderFilters() {
  const total = isMediaBackedCategory() ? visibleItems(state.activeCategory, "all").length : 0;
  const counts = {
    all: total,
    posted: postedCount(),
    pending: pendingCount(),
    disregard: disregardCount(),
  };

  $("filter-bar").innerHTML = FILTERS.map((filter) => `
    <button class="filter-button${state.activeFilter === filter.id ? " active" : ""}" data-filter="${filter.id}" type="button">
      ${filter.label}<span>${counts[filter.id]}</span>
    </button>
  `).join("");

  $("filter-bar").querySelectorAll("[data-filter]").forEach((button) => {
    button.addEventListener("click", () => {
      closeCardContextMenu();
      state.activeFilter = button.dataset.filter;
      ensureSelection();
      syncPreviewAfterVisibilityChange();
      renderAll();
    });
  });
}

function renderHeader() {
  const config = activeCategoryConfig();
  $("collection-title").textContent = config ? config.label : "Collection";

  if (config && isMediaBackedCategory(config.id)) {
    $("collection-description").textContent =
      CATEGORY_DESCRIPTIONS[config.id] || "Media staged inside the archive layout.";
    return;
  }

  $("collection-description").textContent =
    "This archive lane is staged in the new design, but the currently wired still and reel collections will load directly into the archive layout.";
}

function renderGalleryMeta() {
  const meta = $("gallery-meta");
  const config = activeCategoryConfig();
  const lane = currentCategoryState();
  const sourceLabel = getSourceLabel();

  if (!config || !isMediaBackedCategory()) {
    meta.textContent = "Select a wired still, reel, or local library collection to load media into this archive layout.";
    return;
  }

  if (isLocalUploadCategory()) {
    if (lane.fetchError && lane.images.length === 0) {
      meta.textContent = `Local library error: ${lane.fetchError}`;
      return;
    }
    if (lane.streaming) {
      meta.textContent = "Loading local library...";
      return;
    }
    if (lane.uploadingCount > 0) {
      meta.textContent = `Uploading ${lane.uploadingCount} photo${lane.uploadingCount === 1 ? "" : "s"} into ${config.label}...`;
      return;
    }
    if (lane.images.length > 0) {
      meta.textContent = `${lane.images.length} item${lane.images.length === 1 ? "" : "s"} stored in the ${config.label} queue.`;
      return;
    }
    meta.textContent = `No local uploads yet for ${config.label}.`;
    return;
  }

  if (lane.pendingDisregard) {
    meta.textContent = "Archiving 1 photo to Zoho WorkDrive...";
    return;
  }

  if (isTipsReelCategory() && lane.images.length > 0 && !lane.streaming) {
    const comboCount = getComboSelection().length;
    const visible = visibleItems(state.activeCategory, "all");
    const hiddenCount = readyCombinedSourceIndexSet(state.activeCategory).size;
    const ready = visible.filter(({ img }) => isTipsReelReady(img)).length;
    const working = visible.filter(({ img }) => isTipsReelBusy(img)).length;
    if (comboCount > 0) {
      meta.textContent = `${comboCount}/3 reels selected for one combined Tips Reel. Ctrl-click reels to adjust selection.`;
      return;
    }
    if (working > 0) {
      meta.textContent = `${working} reel${working === 1 ? "" : "s"} converting. ${ready}/${visible.length} Tips Reels ready.`;
      return;
    }
    meta.textContent = hiddenCount > 0
      ? `${ready}/${visible.length} Tips Reels ready. ${hiddenCount} source clip${hiddenCount === 1 ? "" : "s"} hidden because they are already combined.`
      : `${ready}/${visible.length} Tips Reels ready. Ctrl-click 3 reels, then right-click to combine.`;
    return;
  }

  if (lane.fetchError && lane.images.length > 0) {
    meta.textContent = `${lane.images.length} item${lane.images.length === 1 ? "" : "s"} shown. Last sync failed: ${lane.fetchError}`;
    return;
  }

  if (lane.fetchError) {
    meta.textContent = `Fetch error: ${lane.fetchError}`;
    return;
  }

  if (lane.streaming) {
    if (lane.preserveVisible && lane.images.length > 0) {
      meta.textContent = `Refreshing ${lane.images.length} item${lane.images.length === 1 ? "" : "s"} from ${sourceLabel}...`;
      return;
    }
    const done = lane.fetchTotal ? `${lane.fetchDone}/${lane.fetchTotal} tables` : "Loading tables";
    meta.textContent = `${done} - ${lane.images.length} item${lane.images.length === 1 ? "" : "s"} so far`;
    return;
  }

  if (lane.images.length > 0) {
    const config = activeCategoryConfig();
    const sourceName = config && config.fetchKind === "zoho"
      ? "Zoho WorkDrive"
      : (state.sourceName || "Airtable");
    meta.textContent = `${lane.images.length} item${lane.images.length === 1 ? "" : "s"} loaded from ${sourceName} (${sourceLabel}).`;
    return;
  }

  meta.textContent = `No items loaded yet for ${sourceLabel}.`;
}

function skeletonMarkup(count) {
  return Array.from({ length: count }, () => `
    <div class="gallery-skeleton" aria-hidden="true">
      <div class="gallery-skeleton-block top"></div>
      <div class="gallery-skeleton-block title"></div>
      <div class="gallery-skeleton-block sub"></div>
      <div class="gallery-skeleton-block meta"></div>
    </div>
  `).join("");
}

function renderGallery() {
  const container = $("gallery-area");
  const config = activeCategoryConfig();
  const lane = currentCategoryState();
  const visible = visibleItems();
  const sourceLabel = getSourceLabel();
  const isLocal = isLocalUploadCategory();

  if (!config || !isMediaBackedCategory()) {
    container.innerHTML = `
      <div class="gallery-empty">
        <div>
          <h4>No photos wired for this category yet.</h4>
          <p>Wired archive lanes will load here once the selected collection returns media.</p>
        </div>
      </div>
    `;
    return;
  }

  if (isLocal) {
    let bodyMarkup = "";
    if (lane.fetchError && lane.images.length === 0) {
      bodyMarkup = `
        <div class="gallery-error">
          <div>
            <h4>Could not load ${config.label}.</h4>
            <p>${escapeHtml(lane.fetchError)}</p>
          </div>
        </div>
      `;
    } else if (lane.streaming && lane.images.length === 0) {
      bodyMarkup = `<div class="gallery-grid">${skeletonMarkup(4)}</div>`;
    } else if (visible.length === 0 && lane.images.length === 0) {
      bodyMarkup = `
        <div class="gallery-empty">
          <div>
            <h4>No queued photos yet.</h4>
            <p>Upload your first image here. New photos will stack in this queue and stay saved for later use.</p>
          </div>
        </div>
      `;
    } else if (visible.length === 0) {
      bodyMarkup = `
        <div class="gallery-empty">
          <div>
            <h4>No frames match this view.</h4>
            <p>Adjust the collection filter to reopen the queued photo set.</p>
          </div>
        </div>
      `;
    } else {
      bodyMarkup = `<div class="gallery-grid">${galleryCardsMarkup(visible, lane, { allowDelete: true })}</div>`;
    }

    container.innerHTML = `
      ${localUploadPanelMarkup(config, lane)}
      ${bodyMarkup}
    `;

    wireGalleryInteractions(container, { allowDelete: true });
    wireLocalUploadControls(container);
    return;
  }

  if (lane.fetchError && lane.images.length === 0) {
    const uploadPanel = isVideoUploadCategory() ? videoUploadPanelMarkup(lane) : "";
    container.innerHTML = `
      ${uploadPanel}
      <div class="gallery-error">
        <div>
          <h4>Could not load ${config.label}.</h4>
          <p>${escapeHtml(lane.fetchError)}</p>
        </div>
      </div>
    `;
    if (isVideoUploadCategory()) {
      wireTipsReelUploadControls(container);
    }
    return;
  }

  if (lane.streaming && lane.images.length === 0) {
    container.innerHTML = `<div class="gallery-grid">${skeletonMarkup(4)}</div>`;
    return;
  }

  if (visible.length === 0 && lane.images.length === 0) {
    const uploadPanel = isVideoUploadCategory() ? videoUploadPanelMarkup(lane) : "";
    container.innerHTML = `
      ${uploadPanel}
      <div class="gallery-empty">
        <div>
          <h4>No items found.</h4>
          <p>This source did not return any attachments for <strong>${escapeHtml(sourceLabel)}</strong>.${isVideoUploadCategory() ? " Upload your own videos above." : ""}</p>
        </div>
      </div>
    `;
    if (isVideoUploadCategory()) {
      wireTipsReelUploadControls(container);
    }
    return;
  }

  if (visible.length === 0) {
    container.innerHTML = `
      <div class="gallery-empty">
        <div>
          <h4>No frames match this view.</h4>
          <p>Adjust the collection filter to reopen the fetched photo set.</p>
        </div>
      </div>
    `;
    return;
  }

  const remainder = visible.length % 4;
  const trailingCount = remainder === 0 ? 1 : Math.max(1, 4 - remainder);
  const loadingTail = lane.streaming ? skeletonMarkup(Math.min(3, trailingCount)) : "";
  const uploadPanel = isVideoUploadCategory() ? videoUploadPanelMarkup(lane) : "";
  const deleteAllowed = isVideoUploadCategory();
  container.innerHTML = `${uploadPanel}<div class="gallery-grid">${galleryCardsMarkup(visible, lane, { allowDelete: deleteAllowed })}${loadingTail}</div>`;

  wireGalleryInteractions(container, { allowDelete: deleteAllowed });
  if (isVideoUploadCategory()) {
    wireTipsReelUploadControls(container);
  }
}

function wireGalleryInteractions(container, { allowDelete = false } = {}) {
  container.querySelectorAll(".gallery-card[data-index]").forEach((button) => {
    const index = Number(button.dataset.index);
    button.addEventListener("click", (event) => {
      if (isTipsReelCategory() && (event.ctrlKey || event.metaKey || event.shiftKey)) {
        event.preventDefault();
        toggleComboSelection(index);
        return;
      }
      openPreview(index);
    });
    button.addEventListener("contextmenu", (event) => {
      if ((allowDelete && !isTipsReelCategory()) || isLocalUploadCategory()) {
        selectPostTarget(index, event);
        return;
      }
      openCardContextMenu(index, event);
    });
  });

  if (!allowDelete) {
    return;
  }

  container.querySelectorAll("[data-delete-upload]").forEach((button) => {
    button.addEventListener("click", (event) => {
      const index = Number(button.dataset.index);
      const img = currentCategoryState().images[index];
      if (isVideoUploadCategory() && img && img.tips_reel_upload) {
        onDeleteTipsReelUpload(button.dataset.deleteUpload, index, event);
      } else {
        onDeleteLocalUpload(button.dataset.deleteUpload, index, event);
      }
    });
  });
}

function wireLocalUploadControls(container) {
  const dropzone = container.querySelector("[data-local-dropzone]");
  const input = container.querySelector("[data-local-input]");
  if (!dropzone || !input) {
    return;
  }

  const openPicker = () => {
    if (state.posting) {
      $("post-status").textContent = "Wait for the current post to finish before uploading more photos.";
      return;
    }
    input.click();
  };

  dropzone.addEventListener("click", () => openPicker());
  dropzone.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      openPicker();
    }
  });
  dropzone.addEventListener("dragover", (event) => {
    event.preventDefault();
    dropzone.classList.add("dragging");
  });
  dropzone.addEventListener("dragleave", () => {
    dropzone.classList.remove("dragging");
  });
  dropzone.addEventListener("drop", (event) => {
    event.preventDefault();
    dropzone.classList.remove("dragging");
    uploadLocalFiles(Array.from(event.dataTransfer ? event.dataTransfer.files || [] : []));
  });
  input.addEventListener("change", () => {
    uploadLocalFiles(Array.from(input.files || []));
    input.value = "";
  });
}

function wireTipsReelUploadControls(container) {
  const dropzone = container.querySelector("[data-tips-reel-dropzone]");
  const input = container.querySelector("[data-tips-reel-input]");
  if (!dropzone || !input) {
    return;
  }

  const handleFiles = (files) => {
    uploadTipsReelVideos(files, state.activeCategory);
  };

  const openPicker = () => {
    if (state.posting) {
      $("post-status").textContent = "Wait for the current post to finish before uploading more videos.";
      return;
    }
    input.click();
  };

  dropzone.addEventListener("click", () => openPicker());
  dropzone.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      openPicker();
    }
  });
  dropzone.addEventListener("dragover", (event) => {
    event.preventDefault();
    dropzone.classList.add("dragging");
  });
  dropzone.addEventListener("dragleave", () => {
    dropzone.classList.remove("dragging");
  });
  dropzone.addEventListener("drop", (event) => {
    event.preventDefault();
    dropzone.classList.remove("dragging");
    uploadTipsReelVideos(Array.from(event.dataTransfer ? event.dataTransfer.files || [] : []));
  });
  input.addEventListener("change", () => {
    uploadTipsReelVideos(Array.from(input.files || []));
    input.value = "";
  });
}

function renderSelectedMetadata() {
  const display = $("item-name-display");
  const meta = $("selection-meta");
  const categoryId = state.activeCategory;
  const lane = currentCategoryState();
  const selected = selectedImage(categoryId);

  if (!display || !meta) {
    return;
  }

  if (!selected || !isMediaBackedCategory(categoryId)) {
    display.classList.add("empty");
    display.innerHTML = '<p class="item-name-placeholder">Right-click a photo to select it for posting.</p>';
    meta.textContent = isMediaBackedCategory(categoryId)
      ? "No photo selected for posting."
      : "This collection is not wired for posting yet.";
    return;
  }

  const lines = getItemNameLinesFromFields(selected.fields || {});
  if (lines.length === 0 && selected.local_upload) {
    display.classList.remove("empty");
    display.innerHTML = `
      <p class="item-name-line">${escapeHtml(getGalleryTitle(selected, categoryId))}</p>
      <p class="item-name-line subtle">${escapeHtml(selected.filename || "Local upload")}</p>
    `;
  } else if (lines.length === 0) {
    display.classList.add("empty");
    display.innerHTML = '<p class="item-name-placeholder">Item names unavailable for the selected post target.</p>';
  } else {
    display.classList.remove("empty");
    display.innerHTML = lines
      .map((line) => `<p class="item-name-line">${escapeHtml(line)}</p>`)
      .join("");
  }

  const selectedPendingDisregard = selected && lane.currentIndex !== null
    ? isCardPendingDisregard(selected, lane.currentIndex, lane)
    : false;
  const syncText = selectedPendingDisregard || isDisregardPending(categoryId)
    ? ""
    : (isLaneReady(categoryId) ? "" : " Syncing media state...");
  const selectionKind = isVideoItem(selected)
    ? (selected.type === "tips_combo" ? "Combined Tips Reel" : "Video")
    : (selected.type === "triple"
      ? "Triple"
      : (selected.type === "pair" ? "Paired" : "Single"));
  const hasTipsStatus = canConvertToTipsReel(selected, categoryId) || (categoryId === "tips-reels" && selected.type === "tips_combo");
  const tipsText = hasTipsStatus
    ? ` Tips Reel: ${getTipsReelLabel(selected)}.`
    : "";
  const tipsDetail = hasTipsStatus ? getTipsReelDetail(selected) : "";
  const tipsDetailText = tipsDetail ? ` ${tipsDetail}` : "";
  const disregardText = isDisregarded(selected) ? " Marked as disregard." : "";
  const pendingText = selectedPendingDisregard
    ? " Archiving to Zoho..."
    : (isDisregardPending(categoryId) ? " Another photo is archiving to Zoho..." : "");
  meta.textContent = `${selectionKind} post target selected.${tipsText}${tipsDetailText}${disregardText}${pendingText}${syncText}`.trim();
}

function renderPreview() {
  const modal = $("preview-modal");
  const singleMedia = $("preview-single-media");
  const singleImage = $("preview-image");
  const singleVideo = $("preview-video");
  const pairGrid = $("preview-pair-grid");
  const leftLabel = $("preview-left-label");
  const leftImage = $("preview-left-image");
  const leftFilename = $("preview-left-filename");
  const centerCard = $("preview-center-card");
  const centerLabel = $("preview-center-label");
  const centerImage = $("preview-center-image");
  const centerFilename = $("preview-center-filename");
  const rightLabel = $("preview-right-label");
  const rightImage = $("preview-right-image");
  const rightFilename = $("preview-right-filename");
  const title = $("preview-title");
  const meta = $("preview-meta");
  const filename = $("preview-filename");
  const prevButton = $("preview-prev");
  const nextButton = $("preview-next");
  const downloadBtn = $("preview-download-btn");

  if (
    !modal || !singleMedia || !singleImage || !singleVideo || !pairGrid || !leftLabel || !leftImage || !leftFilename
    || !centerCard || !centerLabel || !centerImage || !centerFilename
    || !rightLabel || !rightImage || !rightFilename || !title || !meta || !filename || !prevButton || !nextButton
    || !downloadBtn
  ) {
    return;
  }

  if (!state.previewOpen || !isMediaBackedCategory()) {
    modal.classList.add("hidden");
    modal.setAttribute("aria-hidden", "true");
    document.body.classList.remove("modal-open");
    singleMedia.classList.remove("hidden");
    pairGrid.classList.add("hidden");
    pairGrid.classList.remove("triple-layout");
    centerCard.classList.add("hidden");
    downloadBtn.classList.add("hidden");
    singleVideo.pause();
    singleVideo.classList.add("hidden");
    singleVideo.removeAttribute("src");
    singleVideo.load();
    singleImage.classList.remove("hidden");
    singleImage.removeAttribute("src");
    leftImage.removeAttribute("src");
    centerImage.removeAttribute("src");
    rightImage.removeAttribute("src");
    return;
  }

  const lane = currentCategoryState();
  const visible = visibleItems();
  const previewed = previewedImage();
  const position = lane.previewIndex === null
    ? -1
    : visible.findIndex((item) => item.index === lane.previewIndex);

  if (!previewed || visible.length === 0 || position === -1) {
    closePreview({ restoreFocus: false });
    return;
  }

  modal.classList.remove("hidden");
  modal.setAttribute("aria-hidden", "false");
  document.body.classList.add("modal-open");

  title.textContent = getPreviewTitle(previewed, state.activeCategory);
  meta.textContent = `${position + 1} / ${visible.length}`;
  filename.textContent = getPreviewFooterText(previewed, state.activeCategory);

  if (isVideoItem(previewed)) {
    const videoUrl = getTipsReelVideoUrl(previewed, state.activeCategory);
    pairGrid.classList.add("hidden");
    pairGrid.classList.remove("triple-layout");
    centerCard.classList.add("hidden");
    singleMedia.classList.remove("hidden");
    singleImage.classList.add("hidden");
    singleImage.removeAttribute("src");
    singleVideo.classList.remove("hidden");
    
    if (state.activeCategory === "styled-reels") {
      downloadBtn.classList.remove("hidden");
    } else {
      downloadBtn.classList.add("hidden");
    }

    if (singleVideo.getAttribute("src") !== (videoUrl || "")) {
      singleVideo.pause();
      singleVideo.src = videoUrl || "";
      singleVideo.load();
    }
    singleVideo.play().catch(() => {});
    leftImage.removeAttribute("src");
    centerImage.removeAttribute("src");
    rightImage.removeAttribute("src");
    leftFilename.textContent = "";
    centerFilename.textContent = "";
    rightFilename.textContent = "";
  } else if (previewed.type === "pair" || previewed.type === "triple") {
    downloadBtn.classList.add("hidden");
    singleMedia.classList.add("hidden");
    singleVideo.pause();
    singleVideo.classList.add("hidden");
    singleVideo.removeAttribute("src");
    singleVideo.load();
    singleImage.classList.remove("hidden");
    pairGrid.classList.remove("hidden");
    if (previewed.type === "triple") {
      const tripleLabels = getTripleSideLabels(previewed, state.activeCategory);
      pairGrid.classList.add("triple-layout");
      leftLabel.textContent = tripleLabels[0];
      centerLabel.textContent = tripleLabels[1];
      rightLabel.textContent = tripleLabels[2];
      leftImage.src = previewed.left.url || previewed.left.thumb_url || "";
      centerImage.src = previewed.center.url || previewed.center.thumb_url || "";
      rightImage.src = previewed.right.url || previewed.right.thumb_url || "";
      leftImage.alt = tripleLabels[0];
      centerImage.alt = tripleLabels[1];
      rightImage.alt = tripleLabels[2];
      leftFilename.textContent = previewed.left.filename || tripleLabels[0];
      centerFilename.textContent = previewed.center.filename || tripleLabels[1];
      rightFilename.textContent = previewed.right.filename || tripleLabels[2];
      centerCard.classList.remove("hidden");
    } else {
      const labels = getPairSideLabels(previewed, state.activeCategory);
      pairGrid.classList.remove("triple-layout");
      leftLabel.textContent = labels[0];
      rightLabel.textContent = labels[1];
      leftImage.src = previewed.left.url || previewed.left.thumb_url || "";
      rightImage.src = previewed.right.url || previewed.right.thumb_url || "";
      leftImage.alt = labels[0];
      rightImage.alt = labels[1];
      leftFilename.textContent = previewed.left.filename || labels[0];
      rightFilename.textContent = previewed.right.filename || labels[1];
      centerCard.classList.add("hidden");
      centerImage.removeAttribute("src");
      centerFilename.textContent = "";
    }
  } else {
    downloadBtn.classList.add("hidden");
    pairGrid.classList.add("hidden");
    pairGrid.classList.remove("triple-layout");
    singleMedia.classList.remove("hidden");
    centerCard.classList.add("hidden");
    singleVideo.pause();
    singleVideo.classList.add("hidden");
    singleVideo.removeAttribute("src");
    singleVideo.load();
    singleImage.classList.remove("hidden");
    singleImage.src = previewed.url || previewed.thumb_url || "";
    singleImage.alt = previewed.filename || getSourceLabel();
    leftImage.removeAttribute("src");
    centerImage.removeAttribute("src");
    rightImage.removeAttribute("src");
    leftFilename.textContent = "";
    centerFilename.textContent = "";
    rightFilename.textContent = "";
  }

  prevButton.disabled = position <= 0;
  nextButton.disabled = position >= visible.length - 1;
  prevButton.classList.toggle("hidden", visible.length <= 1);
  nextButton.classList.toggle("hidden", visible.length <= 1);
}

async function downloadStyledReelMedia() {
  const previewed = previewedImage();
  if (!previewed || state.activeCategory !== "styled-reels" || !isVideoItem(previewed)) {
    return;
  }

  const btn = $("preview-download-btn");
  const originalText = btn.textContent;
  const url = getTipsReelVideoUrl(previewed, state.activeCategory);
  let baseName = previewed.filename || "styled_reel.mp4";
  
  // Enforce .mp4 extension
  if (!baseName.toLowerCase().endsWith(".mp4")) {
    const lastDot = baseName.lastIndexOf(".");
    if (lastDot !== -1) {
      baseName = baseName.substring(0, lastDot) + ".mp4";
    } else {
      baseName += ".mp4";
    }
  }

  try {
    btn.disabled = true;
    btn.textContent = "Downloading...";
    
    const response = await fetch(url);
    if (!response.ok) throw new Error("Network response was not ok");
    
    const blob = await response.blob();
    const blobUrl = window.URL.createObjectURL(blob);
    
    const a = document.createElement("a");
    a.style.display = "none";
    a.href = blobUrl;
    a.download = baseName;
    document.body.appendChild(a);
    a.click();
    
    window.URL.revokeObjectURL(blobUrl);
    document.body.removeChild(a);
  } catch (error) {
    console.error("Download failed:", error);
    alert("Download failed. Please try again.");
  } finally {
    btn.disabled = false;
    btn.textContent = originalText;
  }
}

function renderAll() {
  renderBuildInfo();
  renderSidebar();
  renderHeader();
  renderFilters();
  renderGalleryMeta();
  renderGallery();
  renderSelectedMetadata();
  renderPreview();
  updateComposerAvailability();
  renderContextMenu();
}

function setPostTargetIndex(nextIndex, options = {}) {
  const lane = currentCategoryState();
  lane.currentIndex = nextIndex;
  renderAll();

  if (!options.silent) {
    if (nextIndex === null) {
      $("post-status").textContent = "Post target cleared.";
    } else if (isLaneReady()) {
      $("post-status").textContent = "Photo selected for posting.";
    } else {
      $("post-status").textContent = "Photo selected for posting. Syncing media...";
    }
  }
}

function ensureSelection() {
  const lane = currentCategoryState();
  const visible = visibleItems();

  if (visible.length === 0) {
    if (lane.currentIndex !== null) {
      lane.currentIndex = null;
    }
    return;
  }

  if (lane.currentIndex !== null && !visible.some((item) => item.index === lane.currentIndex)) {
    lane.currentIndex = null;
  }
}

function openPreview(index) {
  const lane = currentCategoryState();
  lane.previewIndex = index;
  state.previewOpen = true;
  renderPreview();
}

function closePreview({ restoreFocus = true } = {}) {
  if (!state.previewOpen) {
    return;
  }

  const lane = currentCategoryState();
  const restoreIndex = lane.previewIndex;
  lane.previewIndex = null;
  state.previewOpen = false;
  renderPreview();

  if (!restoreFocus || restoreIndex === null) {
    return;
  }

  requestAnimationFrame(() => {
    const target = document.querySelector(`#gallery-area [data-index="${restoreIndex}"]`);
    if (target) {
      target.focus();
    }
  });
}

function navigatePreview(direction) {
  if (!state.previewOpen) {
    return;
  }

  const lane = currentCategoryState();
  const visible = visibleItems();
  const position = lane.previewIndex === null
    ? -1
    : visible.findIndex((item) => item.index === lane.previewIndex);

  if (position === -1) {
    return;
  }

  const next = visible[position + direction];
  if (!next) {
    return;
  }

  lane.previewIndex = next.index;
  renderPreview();
}

function syncPreviewAfterVisibilityChange() {
  if (!state.previewOpen) {
    return;
  }

  if (!isMediaBackedCategory()) {
    closePreview({ restoreFocus: false });
    return;
  }

  const lane = currentCategoryState();
  const visible = visibleItems();
  if (visible.length === 0 || lane.previewIndex === null) {
    closePreview({ restoreFocus: false });
    return;
  }

  if (!visible.some((item) => item.index === lane.previewIndex)) {
    closePreview({ restoreFocus: false });
    return;
  }

  renderPreview();
}

function closeCardContextMenu() {
  state.contextMenu.open = false;
  state.contextMenu.categoryId = null;
  state.contextMenu.index = null;
  renderContextMenu();
}

function renderContextMenu() {
  const menu = $("card-context-menu");
  const postButton = $("card-context-post");
  const convertButton = $("card-context-convert");
  const disregardButton = $("card-context-disregard");
  if (!menu || !postButton || !convertButton || !disregardButton) {
    return;
  }

  const { open, categoryId, index, x, y } = state.contextMenu;
  const lane = categoryId ? getCategoryState(categoryId) : null;
  const img = lane && index !== null ? lane.images[index] : null;
  const isActiveCategory = categoryId && categoryId === state.activeCategory;
  const eligible = !!(open && isActiveCategory && img && !img.local_upload && !isLaneMutationBusy(categoryId));

  if (!eligible) {
    menu.classList.add("hidden");
    menu.setAttribute("aria-hidden", "true");
    menu.style.left = "";
    menu.style.top = "";
    return;
  }

  const disregardActive = isDisregarded(img);
  const disregardUnavailable = !hasDisregardCapability();
  const disregardDisabled = disregardUnavailable || !!(img.fields && img.fields["SB Posted"] && !disregardActive);
  const comboSelection = getComboSelection(categoryId);
  const combinedEligible = categoryId === "tips-reels" && comboSelection.includes(index) && comboSelection.length === 3;
  const convertEligible = canConvertToTipsReel(img, categoryId);
  const tipsStatus = getTipsReelStatus(img);
  const tipsBusy = isTipsReelBusy(img);
  const tipsReady = isTipsReelReady(img);
  convertButton.classList.toggle("hidden", !(convertEligible || combinedEligible));
  convertButton.disabled = (!convertEligible && !combinedEligible)
    || tipsBusy
    || (combinedEligible ? !eelFunctionAvailable("prepare_combined_tips_reel") : !eelFunctionAvailable("prepare_tips_reel"));
  convertButton.textContent = combinedEligible
    ? "Convert 3 to Tips Reel"
    : tipsBusy
    ? getTipsReelLabel(img)
    : tipsReady
    ? "Re-render Tips Reel"
    : tipsStatus === "error"
    ? "Retry Tips Reel"
    : "Convert to Tips Reel";
  convertButton.title = combinedEligible && !eelFunctionAvailable("prepare_combined_tips_reel")
    ? "Restart the app or rebuild the exe to enable combined Tips Reel conversion."
    : !eelFunctionAvailable("prepare_tips_reel")
    ? "Restart the app or rebuild the exe to enable Tips Reel conversion."
    : "";
  disregardButton.textContent = disregardUnavailable
    ? "Restart for Disregard"
    : (disregardActive ? "Remove Disregard" : "Disregard");
  disregardButton.disabled = disregardDisabled;
  disregardButton.title = disregardUnavailable ? getDisregardUnavailableMessage() : "";

  menu.classList.remove("hidden");
  menu.setAttribute("aria-hidden", "false");
  menu.style.left = `${x}px`;
  menu.style.top = `${y}px`;

  requestAnimationFrame(() => {
    const rect = menu.getBoundingClientRect();
    const edge = 14;
    const left = Math.max(edge, Math.min(x, window.innerWidth - rect.width - edge));
    const top = Math.max(edge, Math.min(y, window.innerHeight - rect.height - edge));
    menu.style.left = `${left}px`;
    menu.style.top = `${top}px`;
  });
}

function openCardContextMenu(index, event) {
  if (event) {
    event.preventDefault();
    event.stopPropagation();
  }

  if (state.posting) {
    $("post-status").textContent = "Wait for the current post to finish before changing this item.";
    return;
  }

  if (isLaneMutationBusy()) {
    $("post-status").textContent = getDisregardBusyMessage();
    return;
  }

  const lane = currentCategoryState();
  const img = lane.images[index];
  if (!img || img.local_upload) {
    selectPostTarget(index, event);
    return;
  }

  state.contextMenu.open = true;
  state.contextMenu.categoryId = state.activeCategory;
  state.contextMenu.index = index;
  state.contextMenu.x = event ? event.clientX : 0;
  state.contextMenu.y = event ? event.clientY : 0;
  if (!hasDisregardCapability()) {
    $("post-status").textContent = getDisregardUnavailableMessage();
  }
  renderContextMenu();
}

function onContextMenuPostIt() {
  const { open, categoryId, index } = state.contextMenu;
  if (!open || categoryId !== state.activeCategory || index === null) {
    closeCardContextMenu();
    return;
  }
  if (isLaneMutationBusy(categoryId)) {
    closeCardContextMenu();
    $("post-status").textContent = getDisregardBusyMessage();
    return;
  }
  const lane = currentCategoryState();
  const img = lane.images[index];
  closeCardContextMenu();
  setPostTargetIndex(index);
  if (isDisregarded(img)) {
    $("post-status").textContent = "Remove disregard before posting this item.";
  }
}

async function onContextMenuConvertTipsReel() {
  const { open, categoryId, index } = state.contextMenu;
  if (!open || categoryId !== state.activeCategory || index === null) {
    closeCardContextMenu();
    return;
  }

  const lane = currentCategoryState();
  const img = lane.images[index];
  const comboSelection = getComboSelection(categoryId);
  closeCardContextMenu();
  if (categoryId === "tips-reels" && comboSelection.includes(index) && comboSelection.length === 3) {
    await startCombinedTipsReelConversion(comboSelection, lane.sessionId);
    return;
  }
  if (!canConvertToTipsReel(img, categoryId)) {
    $("post-status").textContent = "Tips Reel conversion is available for single Styled Reels videos only.";
    return;
  }
  await startTipsReelConversion(index, lane.sessionId, { force: isTipsReelReady(img) });
}

function applyTipsReelStatusByKey(mediaKey, statusPayload) {
  if (!mediaKey || !statusPayload) {
    return;
  }
  Object.values(state.categories).forEach((lane) => {
    if (!lane || !Array.isArray(lane.images)) {
      return;
    }
    lane.images.forEach((img) => {
      if (getTipsReelStatus(img) && img.tips_reel && img.tips_reel.key === mediaKey) {
        img.tips_reel = statusPayload;
        return;
      }
      if (statusPayload.key && img.tips_reel && img.tips_reel.key === statusPayload.key) {
        img.tips_reel = statusPayload;
      }
    });
  });
}

async function startTipsReelConversion(index, sessionId, options = {}) {
  const lane = currentCategoryState();
  const img = lane.images[index];
  if (!img) {
    return;
  }
  if (!eelFunctionAvailable("prepare_tips_reel")) {
    $("post-status").textContent = "Restart the app or rebuild the exe to enable Tips Reel conversion.";
    return;
  }

  img.tips_reel = {
    ...(img.tips_reel || {}),
    status: "queued",
    label: "Queued",
    tip: "",
    voiceover_error: "",
    key: img.tips_reel && img.tips_reel.key ? img.tips_reel.key : "",
  };
  renderAll();
  $("post-status").textContent = "Queued Tips Reel conversion...";

  try {
    const result = await eel.prepare_tips_reel(index, sessionId, !!options.force)();
    if (!result || !result.ok) {
      throw new Error((result && result.error) || "Tips Reel conversion failed.");
    }
    if (result.status && result.status.key) {
      lane.images[index].tips_reel = result.status;
      applyTipsReelStatusByKey(result.status.key, result.status);
      renderAll();
    }
  } catch (error) {
    lane.images[index].tips_reel = {
      ...(lane.images[index].tips_reel || {}),
      status: "error",
      label: "Error",
      error: error.message || String(error),
    };
    renderAll();
    $("post-status").textContent = `Tips Reel error: ${error.message || error}`;
    alert(`Tips Reel error: ${error.message || error}`);
  }
}

function upsertCombinedTipsReelItem(lane, itemPayload) {
  if (!lane || !itemPayload || itemPayload.type !== "tips_combo") {
    return;
  }
  const key = itemPayload.combo_key || (itemPayload.tips_reel && itemPayload.tips_reel.key);
  const existingIndex = lane.images.findIndex((img) => img.type === "tips_combo" && (
    (key && (img.combo_key === key || (img.tips_reel && img.tips_reel.key === key)))
    || img.filename === itemPayload.filename
  ));
  if (existingIndex >= 0) {
    lane.images[existingIndex] = itemPayload;
    return;
  }
  lane.images.push(itemPayload);
}

async function startCombinedTipsReelConversion(indices, sessionId, options = {}) {
  const lane = currentCategoryState();
  if (!eelFunctionAvailable("prepare_combined_tips_reel")) {
    $("post-status").textContent = "Restart the app or rebuild the exe to enable combined Tips Reel conversion.";
    return;
  }
  const selection = (indices || getComboSelection()).slice().sort((a, b) => a - b);
  if (selection.length !== 3) {
    $("post-status").textContent = "Select exactly 3 reels before combining.";
    return;
  }

  $("post-status").textContent = "Queued combined Tips Reel conversion...";
  try {
    const result = await eel.prepare_combined_tips_reel(selection, sessionId, !!options.force)();
    if (!result || !result.ok) {
      throw new Error((result && result.error) || "Combined Tips Reel conversion failed.");
    }
    if (result.item) {
      upsertCombinedTipsReelItem(lane, result.item);
      lane.currentIndex = lane.images.findIndex((img) => img.type === "tips_combo" && img.combo_key === result.item.combo_key);
      clearComboSelection();
      renderAll();
    }
  } catch (error) {
    $("post-status").textContent = `Combined Tips Reel error: ${error.message || error}`;
    alert(`Combined Tips Reel error: ${error.message || error}`);
  }
}

async function onContextMenuDisregard() {
  const { open, categoryId, index } = state.contextMenu;
  if (!open || categoryId !== state.activeCategory || index === null) {
    closeCardContextMenu();
    return;
  }

  const lane = currentCategoryState();
  const img = lane.images[index];
  if (!img) {
    closeCardContextMenu();
    return;
  }

  if (!hasDisregardCapability() || !eelFunctionAvailable("toggle_disregard")) {
    closeCardContextMenu();
    $("post-status").textContent = getDisregardUnavailableMessage();
    return;
  }

  const nextDisregard = !isDisregarded(img);
  if (isLaneMutationBusy(categoryId)) {
    closeCardContextMenu();
    $("post-status").textContent = getDisregardBusyMessage();
    return;
  }

  closeCardContextMenu();
  if (nextDisregard) {
    lane.pendingDisregard = {
      index,
      imageKey: getImageKey(img),
      nextDisregard,
      startedAt: Date.now(),
    };
    renderAll();
    $("post-status").textContent = "Archiving photo to Zoho WorkDrive...";
  }

  try {
    const result = await eel.toggle_disregard(index, nextDisregard, lane.sessionId)();
    if (!result || !result.ok) {
      throw new Error((result && result.error) || "Disregard update failed.");
    }

    lane.images[index].fields = lane.images[index].fields || {};
    lane.images[index].fields["Disregard"] = !!result.disregard;
    lane.pendingDisregard = null;
    ensureSelection();
    syncPreviewAfterVisibilityChange();
    renderAll();
    $("post-status").textContent = result.message || (result.disregard
      ? "Item moved to this category's Disregard tab."
      : "Item returned to this category's active queue.");
  } catch (error) {
    lane.pendingDisregard = null;
    renderAll();
    $("post-status").textContent = `Disregard error: ${error.message || error}`;
    alert(`Disregard error: ${error.message || error}`);
  }
}

function selectPostTarget(index, event) {
  if (event) {
    event.preventDefault();
    event.stopPropagation();
  }
  closeCardContextMenu();

  if (state.posting) {
    $("post-status").textContent = "Wait for the current post to finish before changing the post target.";
    return;
  }

  setPostTargetIndex(index);
}

function getPostParams() {
  const caption = $("caption-text").value.trim();
  const category = $("category-input").value.trim() || null;
  let scheduleDate = null;
  let scheduleTime = null;
  if (!$("post-now-check").checked) {
    scheduleDate = $("schedule-date").value;
    const hour = String($("schedule-hour").value || "").padStart(2, "0");
    const minute = String($("schedule-minute").value || "").padStart(2, "0");
    scheduleTime = `${hour}:${minute}`;
  }
  return { caption, category, scheduleDate, scheduleTime };
}

function toggleSchedule() {
  $("schedule-controls").classList.toggle("hidden", $("post-now-check").checked);
  updateScheduleSummary();
}

function updateScheduleSummary() {
  if ($("post-now-check").checked) {
    $("schedule-summary").textContent = "Will post immediately once you send it to SocialBee.";
    return;
  }

  const dateText = formatDateForSummary($("schedule-date").value);
  const hour = String($("schedule-hour").value || "").padStart(2, "0");
  const minute = String($("schedule-minute").value || "").padStart(2, "0");
  $("schedule-summary").textContent = `Scheduled for ${dateText} at ${hour}:${minute}.`;
}

function applyCategoryDefaults() {
  const config = activeCategoryConfig();
  if (config && config.postCategory) {
    $("category-input").value = config.postCategory;
  }
}

async function resolveFetchRequest(config) {
  if (!config || !config.fetchField) {
    return { fieldName: null, pairedFields: null, tripleFields: null, zohoFolderId: null };
  }

  const zohoFolderId = await eel.get_zoho_folder_info(config.fetchField)();
  if (zohoFolderId) {
    return { fieldName: config.fetchField, pairedFields: null, tripleFields: null, zohoFolderId };
  }

  const tripleFields = await eel.get_triple_field_info(config.fetchField)();
  if (tripleFields && tripleFields.length === 3) {
    return { fieldName: config.fetchField, pairedFields: null, tripleFields, zohoFolderId: null };
  }

  const pairedFields = await eel.get_paired_field_info(config.fetchField)();
  if (pairedFields && pairedFields.length === 2) {
    return { fieldName: config.fetchField, pairedFields, tripleFields: null, zohoFolderId: null };
  }

  if (config.fetchKind === "zoho") {
    throw new Error(`Zoho folder config not found for ${config.fetchField}`);
  }

  if (config.fetchKind === "triple") {
    throw new Error(`Triple field config not found for ${config.fetchField}`);
  }

  if (config.fetchKind === "pair") {
    throw new Error(`Paired field config not found for ${config.fetchField}`);
  }

  return { fieldName: config.fetchField, pairedFields: null, tripleFields: null, zohoFolderId: null };
}

async function startCategoryFetch(categoryId = state.activeCategory, { preserveImages = false } = {}) {
  const config = getCategoryConfig(categoryId);
  if (!config || !config.fetchField) {
    return;
  }

  const lane = getCategoryState(categoryId);
  lane.fetchDone = 0;
  lane.fetchTotal = 0;
  lane.fetchError = "";
  lane.streaming = true;
  lane.preserveVisible = preserveImages && lane.images.length > 0;
  lane.sessionId = createSessionId(categoryId);

  if (!lane.preserveVisible) {
    lane.images = [];
    lane.currentIndex = null;
    lane.previewIndex = null;
    lane.loadedSessionId = null;
    lane.hasLoadedOnce = false;
  }

  if (state.activeCategory === categoryId) {
    $("post-status").textContent = lane.preserveVisible ? "Refreshing media..." : "";
    renderAll();
  } else {
    renderSidebar();
  }

  try {
    const request = await resolveFetchRequest(config);
    if (!state.sourceId && !request.zohoFolderId) {
      lane.fetchError = "No Airtable source is configured.";
      lane.streaming = false;
      lane.preserveVisible = false;
      if (state.activeCategory === categoryId) {
        renderAll();
      } else {
        renderSidebar();
      }
      return;
    }
    const sessionId = lane.sessionId;

    eel.fetch_images(
      state.sourceId || null,
      request.fieldName,
      request.pairedFields || null,
      request.tripleFields || null,
      request.zohoFolderId || null,
      sessionId,
    );
  } catch (error) {
    lane.streaming = false;
    lane.preserveVisible = false;
    lane.fetchError = error.message || String(error);
    if (state.activeCategory === categoryId) {
      renderAll();
    } else {
      renderSidebar();
    }
  }
}

async function startLocalCategoryLoad(categoryId = state.activeCategory, { preserveSelection = true } = {}) {
  const config = getCategoryConfig(categoryId);
  if (!config || !config.localSourceField) {
    return;
  }

  const lane = getCategoryState(categoryId);
  const sessionId = lane.sessionId || createSessionId(categoryId);
  lane.sessionId = sessionId;
  lane.streaming = true;
  lane.fetchError = "";
  lane.fetchDone = 0;
  lane.fetchTotal = 0;
  if (!preserveSelection) {
    lane.currentIndex = null;
    lane.previewIndex = null;
  }

  if (state.activeCategory === categoryId) {
    renderAll();
  } else {
    renderSidebar();
  }

  try {
    const images = await eel.get_local_uploads(config.localSourceField, sessionId)();
    if (lane.sessionId !== sessionId) {
      return;
    }
    lane.streaming = false;
    lane.fetchError = "";
    lane.hasLoadedOnce = true;
    lane.loadedSessionId = sessionId;
    reconcileLaneImages(lane, images || []);
    if (state.activeCategory === categoryId) {
      ensureSelection();
      syncPreviewAfterVisibilityChange();
      renderAll();
    } else {
      renderSidebar();
    }
  } catch (error) {
    lane.streaming = false;
    lane.fetchError = error.message || String(error);
    if (state.activeCategory === categoryId) {
      renderAll();
    } else {
      renderSidebar();
    }
  }
}

async function preloadLocalCategories() {
  const localIds = CATEGORY_GROUPS
    .flatMap((group) => group.items)
    .filter((item) => item.localSourceField)
    .map((item) => item.id);
  await Promise.all(localIds.map((categoryId) => startLocalCategoryLoad(categoryId)));
}

function onCategorySelect(categoryId) {
  if (!CATEGORY_MAP.has(categoryId)) {
    return;
  }

  if (state.posting) {
    $("post-status").textContent = "Wait for the current post to finish before switching collections.";
    return;
  }

  if (state.previewOpen) {
    closePreview({ restoreFocus: false });
  }
  closeCardContextMenu();

  state.activeCategory = categoryId;
  state.activeFilter = "all";
  applyCategoryDefaults();
  $("caption-text").value = "";
  $("post-status").textContent = "";
  renderAll();

  if (!isMediaBackedCategory(categoryId)) {
    return;
  }

  const lane = getCategoryState(categoryId);
  if (lane.streaming) {
    return;
  }

  if (isLocalUploadCategory(categoryId)) {
    const shouldLoadLocal = lane.fetchError || (!lane.hasLoadedOnce && !lane.streaming);
    if (shouldLoadLocal) {
      startLocalCategoryLoad(categoryId);
      return;
    }
    ensureSelection();
    renderAll();
    return;
  }

  const shouldStartFetch = lane.fetchError || (!lane.hasLoadedOnce && !lane.streaming);
  if (shouldStartFetch) {
    startCategoryFetch(categoryId, { preserveImages: lane.images.length > 0 });
    return;
  }

  ensureSelection();
  renderAll();
}

function onDocumentKeydown(event) {
  if (state.contextMenu.open && event.key === "Escape") {
    event.preventDefault();
    closeCardContextMenu();
    return;
  }

  if (state.contextMenu.open) {
    return;
  }

  if (!state.previewOpen) {
    return;
  }

  if (event.key === "Escape") {
    event.preventDefault();
    closePreview();
    return;
  }

  if (event.key === "ArrowLeft") {
    event.preventDefault();
    navigatePreview(-1);
    return;
  }

  if (event.key === "ArrowRight") {
    event.preventDefault();
    navigatePreview(1);
  }
}

async function initApp() {
  await loadRuntimeInfo();
  const sources = await eel.get_sources()();
  const entries = Object.entries(sources || {});
  if (entries.length > 0) {
    state.sourceId = entries[0][0];
    state.sourceName = entries[0][1];
  }

  const today = new Date().toISOString().split("T")[0];
  $("schedule-date").value = today;
  $("schedule-date").min = today;
  $("schedule-hour").value = "10";
  $("schedule-minute").value = "00";
  toggleSchedule();
  applyCategoryDefaults();

  $("refresh-btn").addEventListener("click", async () => {
    if (state.posting) {
      $("post-status").textContent = "Wait for the current post to finish before refreshing.";
      return;
    }
    if (isDisregardPending()) {
      $("post-status").textContent = "Wait for the Zoho archive to finish before refreshing.";
      return;
    }
    closeCardContextMenu();
    if (!isMediaBackedCategory()) {
      return;
    }
    if (isLocalUploadCategory()) {
      $("post-status").textContent = "Refreshing local library...";
      startLocalCategoryLoad(state.activeCategory);
      return;
    }
    await eel.refresh_cache()();
    startCategoryFetch(state.activeCategory, { preserveImages: currentCategoryState().images.length > 0 });
  });

  $("gen-caption-btn").addEventListener("click", onGenerateCaption);
  $("setup-login-btn").addEventListener("click", onSetupLogin);
  $("post-btn").addEventListener("click", onPost);
  $("post-story-btn").addEventListener("click", onPostStory);
  $("post-now-check").addEventListener("change", toggleSchedule);
  $("schedule-date").addEventListener("input", updateScheduleSummary);
  $("schedule-hour").addEventListener("input", () => {
    normalizeTimeInput($("schedule-hour"), 23);
    updateScheduleSummary();
  });
  $("schedule-minute").addEventListener("input", () => {
    normalizeTimeInput($("schedule-minute"), 59);
    updateScheduleSummary();
  });
  $("schedule-date-trigger").addEventListener("click", () => {
    const input = $("schedule-date");
    if (typeof input.showPicker === "function") {
      input.showPicker();
      return;
    }
    input.focus();
  });

  $("preview-close").addEventListener("click", () => closePreview());
  $("preview-prev").addEventListener("click", () => navigatePreview(-1));
  $("preview-next").addEventListener("click", () => navigatePreview(1));
  $("preview-download-btn").addEventListener("click", downloadStyledReelMedia);
  $("preview-backdrop").addEventListener("click", () => closePreview());
  $("card-context-post").addEventListener("click", onContextMenuPostIt);
  $("card-context-convert").addEventListener("click", onContextMenuConvertTipsReel);
  $("card-context-disregard").addEventListener("click", onContextMenuDisregard);
  document.addEventListener("keydown", onDocumentKeydown);
  document.addEventListener("pointerdown", (event) => {
    const menu = $("card-context-menu");
    if (!state.contextMenu.open || (menu && menu.contains(event.target))) {
      return;
    }
    closeCardContextMenu();
  });
  window.addEventListener("resize", () => closeCardContextMenu());
  document.addEventListener("scroll", () => closeCardContextMenu(), true);

  renderAll();
  preloadLocalCategories().catch((error) => {
    console.error("Local category preload failed:", error);
  });
  startCategoryFetch(state.activeCategory);
}

async function onGenerateCaption() {
  const lane = currentCategoryState();
  if (lane.currentIndex === null || !isLaneReady()) {
    return;
  }

  state.generatingCaption = true;
  updateComposerAvailability();
  $("gen-caption-btn").textContent = "Generating...";
  $("post-status").textContent = "Generating caption...";
  try {
    await eel.generate_caption(lane.currentIndex, lane.sessionId);
  } catch (error) {
    state.generatingCaption = false;
    $("gen-caption-btn").textContent = "Generate Caption";
    updateComposerAvailability();
    $("post-status").textContent = `Caption error: ${error.message || error}`;
  }
}

function onSetupLogin() {
  if (state.settingUpLogin || state.posting) {
    return;
  }
  state.settingUpLogin = true;
  $("setup-login-btn").disabled = true;
  $("setup-login-btn").textContent = "Browser open - log in...";
  $("setup-status").textContent =
    "A browser window opened. Log in to SocialBee, then close that window. Your session will be saved.";
  if (eelFunctionAvailable("setup_chrome_post")) {
    eel.setup_chrome_post();
  } else {
    $("setup-status").textContent = "Setup is unavailable in this build.";
    resetSetupLoginButton();
  }
}

function resetSetupLoginButton() {
  state.settingUpLogin = false;
  $("setup-login-btn").disabled = false;
  $("setup-login-btn").textContent = "Setup SocialBee Login";
  updateComposerAvailability();
}

function onPost() {
  const lane = currentCategoryState();
  if (state.posting || lane.currentIndex === null || !isLaneReady()) {
    return;
  }

  const { caption, category, scheduleDate, scheduleTime } = getPostParams();
  if (!caption) {
    alert("Generate or type a caption first.");
    return;
  }
  const selected = lane.images[lane.currentIndex];
  if (isTipsReelCategory() && !isTipsReelReady(selected)) {
    $("post-status").textContent = "Convert this video to a Tips Reel before posting.";
    return;
  }
  if (!$("post-now-check").checked && !scheduleDate) {
    alert("Pick a schedule date first.");
    return;
  }

  state.posting = true;
  state.postContext = { categoryId: state.activeCategory, sessionId: lane.sessionId, index: lane.currentIndex, kind: "post" };
  updateComposerAvailability();
  $("post-btn").textContent = "Posting...";
  $("post-status").textContent = "Downloading and posting...";
  eel.post_to_sb(lane.currentIndex, caption, category, scheduleDate, scheduleTime, lane.sessionId);
}

function onPostStory() {
  const lane = currentCategoryState();
  if (state.posting || lane.currentIndex === null || !isLaneReady()) {
    return;
  }

  const selected = lane.images[lane.currentIndex];
  if (!selected || selected.type === "pair" || selected.type === "triple") {
    $("post-status").textContent = "Story posting currently supports single images only.";
    return;
  }
  if (isTipsReelCategory() && !isTipsReelReady(selected)) {
    $("post-status").textContent = "Convert this video to a Tips Reel before posting.";
    return;
  }

  const { caption, category, scheduleDate, scheduleTime } = getPostParams();
  state.posting = true;
  state.postContext = { categoryId: state.activeCategory, sessionId: lane.sessionId, index: lane.currentIndex, kind: "story" };
  updateComposerAvailability();
  $("post-story-btn").textContent = "Posting Story...";
  $("post-status").textContent = "Downloading and posting story...";
  eel.post_story_to_sb(lane.currentIndex, caption, category, scheduleDate, scheduleTime, lane.sessionId);
}

function updateComposerAvailability() {
  const lane = currentCategoryState();
  const hasSelection = isMediaBackedCategory()
    && lane.currentIndex !== null
    && lane.images[lane.currentIndex]
    && !isDisregarded(lane.images[lane.currentIndex])
    && isLaneReady();
  const selected = hasSelection ? lane.images[lane.currentIndex] : null;
  const storySupported = !!(selected && selected.type !== "pair" && selected.type !== "triple");
  const tipsPostReady = !selected || !isTipsReelCategory() || isTipsReelReady(selected);
  $("gen-caption-btn").disabled = !hasSelection || state.generatingCaption;
  $("post-btn").disabled = !hasSelection || state.posting || !tipsPostReady;
  $("post-btn").title = tipsPostReady
    ? ""
    : "Convert this video to a Tips Reel before posting.";
  $("post-story-btn").disabled = !storySupported || state.posting;
  $("post-story-btn").title = storySupported || !selected
    ? ""
    : "Story posting currently supports single images only.";
}

eel.expose(on_fetch_progress);
function on_fetch_progress(done, total, count, sessionId) {
  const categoryId = categoryIdForSession(sessionId);
  if (!categoryId) {
    return;
  }

  const lane = getCategoryState(categoryId);
  if (!lane.streaming || lane.sessionId !== sessionId) {
    return;
  }

  lane.fetchDone = done;
  lane.fetchTotal = total;
  if (state.activeCategory === categoryId) {
    renderGalleryMeta();
  } else {
    renderSidebar();
  }
}

eel.expose(on_images_appended);
function on_images_appended(batch, sessionId) {
  const categoryId = categoryIdForSession(sessionId);
  if (!categoryId || !batch || batch.length === 0) {
    return;
  }

  const lane = getCategoryState(categoryId);
  if (!lane.streaming || lane.sessionId !== sessionId) {
    return;
  }

  if (!lane.preserveVisible) {
    lane.images = lane.images.concat(batch || []);
  }

  if (state.activeCategory === categoryId) {
    ensureSelection();
    try {
      renderAll();
    } catch (e) {
      console.error("Render failed after batch update:", e);
    }
  } else {
    renderSidebar();
  }
}

eel.expose(on_images_loaded);
function on_images_loaded(images, sessionId) {
  const categoryId = categoryIdForSession(sessionId);
  if (!categoryId) {
    return;
  }

  const lane = getCategoryState(categoryId);
  if (lane.sessionId !== sessionId) {
    return;
  }
  lane.streaming = false;
  lane.preserveVisible = false;
  lane.fetchError = "";
  lane.hasLoadedOnce = true;
  lane.loadedSessionId = sessionId;
  
  if (images && images.length > 0) {
    reconcileLaneImages(lane, images);
  }

  if (isVideoUploadCategory(categoryId)) {
    mergeTipsReelUploadsIntoLane(categoryId).then(() => {
      if (state.activeCategory === categoryId) {
        ensureSelection();
        syncPreviewAfterVisibilityChange();
        renderAll();
      } else {
        renderSidebar();
      }
    });
    return;
  }

  if (state.activeCategory === categoryId) {
    ensureSelection();
    syncPreviewAfterVisibilityChange();
    renderAll();
  } else {
    renderSidebar();
  }
}

eel.expose(on_fetch_error);
function on_fetch_error(message, sessionId) {
  const categoryId = categoryIdForSession(sessionId);
  if (!categoryId) {
    return;
  }

  const lane = getCategoryState(categoryId);
  if (lane.sessionId !== sessionId) {
    return;
  }
  lane.streaming = false;
  lane.preserveVisible = false;
  lane.fetchError = message;
  lane.fetchDone = 0;
  lane.fetchTotal = 0;

  if (state.activeCategory === categoryId) {
    syncPreviewAfterVisibilityChange();
    renderAll();
  } else {
    renderSidebar();
  }
}

eel.expose(on_caption_ready);
function on_caption_ready(caption) {
  state.generatingCaption = false;
  $("caption-text").value = caption;
  $("gen-caption-btn").textContent = "Generate Caption";
  $("post-status").textContent = "Caption ready.";
  updateComposerAvailability();
}

eel.expose(on_caption_error);
function on_caption_error(error) {
  state.generatingCaption = false;
  $("caption-text").value = `Error: ${error}`;
  $("gen-caption-btn").textContent = "Generate Caption";
  $("post-status").textContent = `Caption error: ${error}`;
  updateComposerAvailability();
}

eel.expose(on_tips_reel_status);
function on_tips_reel_status(index, sessionId, statusPayload) {
  const categoryId = categoryIdForSession(sessionId);
  if (!categoryId || !statusPayload) {
    return;
  }

  const lane = getCategoryState(categoryId);
  if (lane.sessionId !== sessionId || !lane.images[index]) {
    return;
  }

  lane.images[index].tips_reel = statusPayload;
  if (statusPayload.key) {
    applyTipsReelStatusByKey(statusPayload.key, statusPayload);
  }

  if (state.activeCategory === categoryId) {
    renderAll();
  } else {
    renderSidebar();
  }

  if (state.activeCategory === categoryId) {
    $("post-status").textContent = formatTipsReelStatusMessage(statusPayload, "Converting Tips Reel");
  }
}

eel.expose(on_combined_tips_reel_status);
function on_combined_tips_reel_status(sessionId, itemPayload) {
  const categoryId = categoryIdForSession(sessionId);
  if (!categoryId || !itemPayload) {
    return;
  }
  const lane = getCategoryState(categoryId);
  if (lane.sessionId !== sessionId) {
    return;
  }

  upsertCombinedTipsReelItem(lane, itemPayload);
  const itemIndex = lane.images.findIndex((img) => img.type === "tips_combo" && img.combo_key === itemPayload.combo_key);
  if (itemPayload.tips_reel && itemPayload.tips_reel.status === "ready") {
    lane.currentIndex = itemIndex >= 0 ? itemIndex : lane.currentIndex;
    clearComboSelection(categoryId);
  }

  if (state.activeCategory === categoryId) {
    renderAll();
    const status = itemPayload.tips_reel || {};
    if (status.status === "ready") {
      $("post-status").textContent = status.tip ? `Combined Tips Reel ready. Tips: ${status.tip}` : "Combined Tips Reel ready.";
    } else if (status.status === "error") {
      $("post-status").textContent = `${status.label || "Combined Tips Reel error"}: ${status.error || "Conversion failed."}`;
    } else {
      $("post-status").textContent = formatTipsReelStatusMessage(status, "Converting combined Tips Reel");
    }
  } else {
    renderSidebar();
  }
}

eel.expose(on_post_result);
function on_post_result(status, message) {
  state.posting = false;
  $("post-btn").textContent = "Post To SocialBee";
  updateComposerAvailability();
  if (status === "success") {
    const categoryId = state.postContext ? state.postContext.categoryId : state.activeCategory;
    const selected = state.postContext ? getCategoryState(state.postContext.categoryId).images[state.postContext.index] : null;
    $("post-status").textContent = getPostSyncProgressMessage(selected, categoryId, false);
    if (state.postContext && state.postContext.index !== null) {
      eel.mark_posted(state.postContext.index, state.postContext.sessionId);
    }
    return;
  }
  state.postContext = null;
  $("post-status").textContent = `Error: ${message}`;
  alert(`Error: ${message}`);
}

eel.expose(on_post_story_result);
function on_post_story_result(status, message) {
  state.posting = false;
  $("post-story-btn").textContent = "Post To SocialBee Story";
  updateComposerAvailability();
  if (status === "success") {
    const categoryId = state.postContext ? state.postContext.categoryId : state.activeCategory;
    const selected = state.postContext ? getCategoryState(state.postContext.categoryId).images[state.postContext.index] : null;
    $("post-status").textContent = getPostSyncProgressMessage(selected, categoryId, true);
    if (state.postContext && state.postContext.index !== null) {
      eel.mark_posted(state.postContext.index, state.postContext.sessionId);
    }
    return;
  }
  state.postContext = null;
  $("post-status").textContent = `Error: ${message}`;
  alert(`Error: ${message}`);
}

eel.expose(on_setup_done);
function on_setup_done(message) {
  $("setup-status").textContent = message || "Login saved.";
  resetSetupLoginButton();
}

eel.expose(on_posted_marked);
function on_posted_marked(index, sessionId, result) {
  const categoryId = categoryIdForSession(sessionId)
    || (state.postContext && state.postContext.sessionId === sessionId ? state.postContext.categoryId : null);
  if (!categoryId) {
    return;
  }

  const lane = getCategoryState(categoryId);
  const ok = !result || result.ok !== false;
  if (ok && lane.images[index]) {
    lane.images[index].fields = lane.images[index].fields || {};
    lane.images[index].fields["SB Posted"] = true;
  }
  if (ok && result && Array.isArray(result.posted_indices)) {
    result.posted_indices.forEach((sourceIndex) => {
      const source = lane.images[Number(sourceIndex)];
      if (source) {
        source.fields = source.fields || {};
        source.fields["SB Posted"] = true;
      }
    });
  }

  if (ok && lane.currentIndex === index && itemMatchesFilter(lane.images[index]) === false) {
    lane.currentIndex = null;
  }

  const isStory = !!(state.postContext && state.postContext.kind === "story");
  $("post-status").textContent = getPostCompletionMessage(lane.images[index], categoryId, result, isStory);
  if (state.activeCategory === categoryId) {
    ensureSelection();
    renderAll();
  } else {
    renderSidebar();
  }
  state.postContext = null;
}

async function uploadLocalFiles(files, categoryId = state.activeCategory) {
  const config = getCategoryConfig(categoryId);
  if (!config || !config.localSourceField) {
    return;
  }

  const imageFiles = (files || []).filter((file) => file && String(file.type || "").startsWith("image/"));
  if (imageFiles.length === 0) {
    $("post-status").textContent = "Only image files can be queued here.";
    return;
  }

  const lane = getCategoryState(categoryId);
  if (!lane.sessionId) {
    lane.sessionId = createSessionId(categoryId);
  }

  lane.uploadingCount += imageFiles.length;
  lane.hasLoadedOnce = true;
  lane.loadedSessionId = lane.sessionId;
  if (state.activeCategory === categoryId) {
    renderAll();
  } else {
    renderSidebar();
  }

  for (const file of imageFiles) {
    const formData = new FormData();
    formData.append("photo", file);
    formData.append("source_field", config.localSourceField);
    formData.append("session_id", lane.sessionId);

    try {
      const response = await fetch("/local_upload_photo", {
        method: "POST",
        body: formData,
      });
      const payload = await response.json();
      if (!response.ok || !payload.ok) {
        throw new Error(payload.error || "Upload failed.");
      }

      reconcileLaneImages(lane, payload.images || []);
      lane.fetchError = "";
      lane.currentIndex = lane.images.length > 0 ? lane.images.length - 1 : null;
      lane.previewIndex = null;
      $("post-status").textContent = `${file.name} added to ${config.label}.`;
    } catch (error) {
      lane.fetchError = error.message || String(error);
      $("post-status").textContent = `Upload error: ${lane.fetchError}`;
      alert(`Upload error: ${lane.fetchError}`);
    } finally {
      lane.uploadingCount = Math.max(0, lane.uploadingCount - 1);
      if (state.activeCategory === categoryId) {
        ensureSelection();
        syncPreviewAfterVisibilityChange();
        renderAll();
      } else {
        renderSidebar();
      }
    }
  }
}

async function onDeleteLocalUpload(uploadId, index, event) {
  if (event) {
    event.preventDefault();
    event.stopPropagation();
  }

  if (state.posting) {
    $("post-status").textContent = "Wait for the current post to finish before removing queued photos.";
    return;
  }

  const config = activeCategoryConfig();
  const lane = currentCategoryState();
  try {
    const result = await eel.delete_local_upload(uploadId, config.localSourceField, lane.sessionId)();
    if (!result || !result.ok) {
      throw new Error((result && result.error) || "Delete failed.");
    }
    reconcileLaneImages(lane, result.images || []);
    if (lane.currentIndex === index && itemMatchesFilter(lane.images[index]) === false) {
      lane.currentIndex = null;
    }
    ensureSelection();
    syncPreviewAfterVisibilityChange();
    renderAll();
    $("post-status").textContent = "Photo removed from the local queue.";
  } catch (error) {
    $("post-status").textContent = `Delete error: ${error.message || error}`;
    alert(`Delete error: ${error.message || error}`);
  }
}

async function uploadTipsReelVideos(files, categoryId = state.activeCategory) {
  const videoFiles = (files || []).filter((file) => {
    const name = String(file.name || "").toLowerCase();
    return VIDEO_EXTENSIONS.has(getFileExtension(name));
  });
  if (videoFiles.length === 0) {
    $("post-status").textContent = "Only video files can be uploaded here (.mp4, .mov, .avi, .mkv, .webm, .m4v).";
    return;
  }

  const lane = getCategoryState(categoryId);
  if (!lane.sessionId) {
    lane.sessionId = createSessionId(categoryId);
  }

  lane.uploadingCount += videoFiles.length;
  lane.hasLoadedOnce = true;
  lane.loadedSessionId = lane.sessionId;
  if (state.activeCategory === categoryId) {
    renderAll();
  } else {
    renderSidebar();
  }

  for (const file of videoFiles) {
    const formData = new FormData();
    formData.append("video", file);
    formData.append("session_id", lane.sessionId);
    formData.append("category_id", categoryId);

    try {
      const response = await fetch("/tips_reel_upload_video", {
        method: "POST",
        body: formData,
      });
      const payload = await response.json();
      if (!response.ok || !payload.ok) {
        throw new Error(payload.error || "Upload failed.");
      }

      if (payload.item) {
        lane.images.push(payload.item);
      }
      lane.fetchError = "";
      lane.currentIndex = lane.images.length > 0 ? lane.images.length - 1 : null;
      lane.previewIndex = null;
      $("post-status").textContent = `${file.name} added to Tips Reels.`;
    } catch (error) {
      lane.fetchError = error.message || String(error);
      $("post-status").textContent = `Upload error: ${lane.fetchError}`;
      alert(`Upload error: ${lane.fetchError}`);
    } finally {
      lane.uploadingCount = Math.max(0, lane.uploadingCount - 1);
      if (state.activeCategory === categoryId) {
        ensureSelection();
        syncPreviewAfterVisibilityChange();
        renderAll();
      } else {
        renderSidebar();
      }
    }
  }
}

async function mergeTipsReelUploadsIntoLane(categoryId = state.activeCategory) {
  try {
    const lane = getCategoryState(categoryId);
    const uploads = await eel.get_tips_reel_uploads(lane.sessionId)();
    if (uploads && uploads.length > 0) {
      const existingKeys = new Set(lane.images.map((img) => getImageKey(img)));
      const newItems = uploads.filter((img) => !existingKeys.has(getImageKey(img)));
      if (newItems.length > 0) {
        lane.images.push(...newItems);
      }
    }
  } catch (error) {
    console.warn("Could not load tips reel uploads:", error);
  }
}

async function onDeleteTipsReelUpload(uploadId, index, event) {
  if (event) {
    event.preventDefault();
    event.stopPropagation();
  }

  if (state.posting) {
    $("post-status").textContent = "Wait for the current post to finish before removing queued videos.";
    return;
  }

  const lane = currentCategoryState();
  try {
    const result = await eel.delete_tips_reel_upload(uploadId, lane.sessionId)();
    if (!result || !result.ok) {
      throw new Error((result && result.error) || "Delete failed.");
    }
    lane.images = lane.images.filter((img) => !(img.tips_reel_upload && img.upload_id === uploadId));
    if (lane.currentIndex === index && itemMatchesFilter(lane.images[index]) === false) {
      lane.currentIndex = null;
    }
    ensureSelection();
    syncPreviewAfterVisibilityChange();
    renderAll();
    $("post-status").textContent = "Video removed from Tips Reels.";
  } catch (error) {
    $("post-status").textContent = `Delete error: ${error.message || error}`;
    alert(`Delete error: ${error.message || error}`);
  }
}

document.addEventListener("DOMContentLoaded", initApp);
