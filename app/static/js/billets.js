/**
 * Billets — candidate blog-post detector
 */
const Billets = (() => {

  const CONFIDENCE_BADGE = {
    high:   'bg-green-100 text-green-700',
    medium: 'bg-yellow-100 text-yellow-700',
    low:    'bg-gray-100 text-gray-600',
    none:   'bg-gray-100 text-gray-500',
  };

  const CONFIDENCE_TEXT = {
    high: 'Confiance élevée', medium: 'Confiance moyenne', low: 'Confiance faible', none: '',
  };

  // ---- Public API ----

  function init() {
    // Nothing to preload yet.
  }

  async function browse() {
    const res = await fetch('/api/browse', { method: 'POST', headers: {'Content-Type':'application/json'}, body: '{}' });
    const data = await res.json();
    if (data.path) document.getElementById('folder').value = data.path;
  }

  async function scan() {
    const folder = document.getElementById('folder').value.trim();
    if (!folder) { alert('Veuillez renseigner le dossier à analyser.'); return; }

    const btn = document.getElementById('btn_scan');
    btn.disabled = true; btn.textContent = 'Analyse en cours…';

    const body = {
      folder,
      subdirs: document.getElementById('subdirs').checked,
      min_cluster_size: parseInt(document.getElementById('min_cluster_size').value, 10) || undefined,
      max_gap_days: parseInt(document.getElementById('max_gap_days').value, 10) || undefined,
      gps_max_km: parseFloat(document.getElementById('gps_max_km').value) || undefined,
    };

    let data;
    try {
      const res = await fetch('/api/billets/scan', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify(body),
      });
      data = await res.json();
    } catch (e) {
      btn.disabled = false; btn.textContent = 'Analyser';
      alert('Erreur réseau : ' + e);
      return;
    }

    btn.disabled = false; btn.textContent = 'Analyser';

    if (data.error) { alert('Erreur : ' + data.error); return; }
    render(data.clusters || []);
  }

  // ---- Rendering ----

  function render(clusters) {
    const list = document.getElementById('clusters_list');
    const empty = document.getElementById('empty_state');

    if (!clusters.length) {
      empty.classList.remove('hidden');
      list.innerHTML = '';
      return;
    }
    empty.classList.add('hidden');
    list.innerHTML = clusters.map(clusterCard).join('');
  }

  function clusterCard(c) {
    const dateRange = c.start_date === c.end_date
      ? formatDate(c.start_date)
      : `${formatDate(c.start_date)} → ${formatDate(c.end_date)}`;

    const labelText = c.label ? esc(c.label.fr) : 'Activité non identifiée';
    const badgeClass = CONFIDENCE_BADGE[c.confidence_level] || CONFIDENCE_BADGE.none;
    const confidenceText = CONFIDENCE_TEXT[c.confidence_level] || '';

    const thumbs = (c.thumbnails || []).map(url => `
      <img src="${esc(url)}" class="w-20 h-20 object-cover rounded-lg border border-gray-200 flex-shrink-0">
    `).join('');

    const videoBadge = c.video_count > 0
      ? `<span class="badge bg-purple-100 text-purple-700">🎬 ${c.video_count} vidéo${c.video_count > 1 ? 's' : ''}</span>`
      : '';

    const peopleLine = c.people && c.people.length
      ? `<div class="text-sm text-gray-500 mt-2">👤 ${c.people.map(esc).join(', ')}</div>`
      : '';

    const keywordChips = (c.matched_keywords || []).map(k => `
      <span class="badge bg-blue-50 text-blue-600">${esc(k)}</span>
    `).join('');

    return `
      <div class="card">
        <div class="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <div class="font-semibold text-gray-800">${dateRange}</div>
            <div class="text-sm text-gray-500 mt-0.5">
              ${c.day_count} jour${c.day_count > 1 ? 's' : ''} · ${c.file_count} média${c.file_count > 1 ? 's' : ''}
            </div>
          </div>
          <div class="flex items-center gap-2 flex-wrap justify-end">
            <span class="badge bg-blue-100 text-blue-700">${labelText}</span>
            ${confidenceText ? `<span class="badge ${badgeClass}">${confidenceText}</span>` : ''}
            ${videoBadge}
          </div>
        </div>

        ${thumbs ? `<div class="flex gap-2 overflow-x-auto mt-3 pb-1">${thumbs}</div>` : ''}
        ${peopleLine}
        ${keywordChips ? `<div class="mt-2">${keywordChips}</div>` : ''}
      </div>
    `;
  }

  function formatDate(iso) {
    const d = new Date(iso + 'T00:00:00');
    return d.toLocaleDateString('fr-FR', { day: 'numeric', month: 'long', year: 'numeric' });
  }

  function esc(str) {
    return String(str).replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }

  return { init, browse, scan };
})();
