/**
 * ProfileEditor — drag & drop token-based profile builder
 */
const ProfileEditor = (() => {

  const TOKENS = [
    { key: 'ANNEE',        label: 'Année',        color: 'blue',   example: '2024' },
    { key: 'MOIS',         label: 'Mois',         color: 'blue',   example: '06' },
    { key: 'JOUR',         label: 'Jour',         color: 'blue',   example: '15' },
    { key: 'HEURE',        label: 'Heure',        color: 'blue',   example: '14' },
    { key: 'MIN',          label: 'Minute',       color: 'blue',   example: '30' },
    { key: 'SEC',          label: 'Seconde',      color: 'blue',   example: '00' },
    { key: 'NOM_ORIGINAL', label: 'Nom original', color: 'purple', example: 'IMG_20240615_143000' },
    { key: 'LIEU',         label: 'Lieu',         color: 'green',  example: 'Tampere' },
    { key: 'PAYS',         label: 'Pays',         color: 'green',  example: 'Finland' },
    { key: 'APPAREIL',     label: 'Appareil',     color: 'yellow', example: 'Samsung' },
    { key: 'COMPTEUR',     label: 'Compteur',     color: 'gray',   example: '001' },
  ];

  const COLOR_MAP = {
    blue:   'bg-blue-100 text-blue-800 border-blue-200',
    purple: 'bg-purple-100 text-purple-800 border-purple-200',
    green:  'bg-green-100 text-green-800 border-green-200',
    yellow: 'bg-yellow-100 text-yellow-800 border-yellow-200',
    gray:   'bg-gray-100 text-gray-700 border-gray-300',
  };

  let folderSortable = null;
  let filenameSortable = null;
  let currentProfileName = null;

  // ---- Public API ----

  function init(preloadName) {
    loadProfileList().then(() => {
      if (preloadName) editProfile(preloadName);
    });
  }

  // ---- Profile list ----

  async function loadProfileList() {
    const res = await fetch('/api/profiles');
    const profiles = await res.json();
    const el = document.getElementById('profile_list');
    if (!profiles.length) {
      el.innerHTML = '<p class="px-4 py-3 text-sm text-gray-400">Aucun profil enregistré.</p>';
      return;
    }
    el.innerHTML = profiles.map(p => `
      <div class="profile-item px-4 py-3 flex items-center justify-between hover:bg-gray-50 cursor-pointer"
           data-name="${esc(p.name)}" onclick="ProfileEditor.editProfile('${esc(p.name)}')">
        <span class="text-sm font-medium text-gray-800">${esc(p.name)}</span>
        <button onclick="event.stopPropagation(); ProfileEditor.deleteProfile('${esc(p.name)}')"
                class="text-gray-300 hover:text-red-500 transition" title="Supprimer">✕</button>
      </div>
    `).join('');
  }

  // ---- Open editor ----

  function newProfile() {
    currentProfileName = null;
    openEditor({
      name: '',
      folder_tokens: [
        { type:'field', value:'ANNEE' },
        { type:'text',  value:'/' },
        { type:'field', value:'MOIS' },
        { type:'text',  value:'/' },
        { type:'field', value:'JOUR' },
      ],
      filename_tokens: [
        { type:'field', value:'ANNEE' },
        { type:'text',  value:'_' },
        { type:'field', value:'MOIS' },
        { type:'text',  value:'_' },
        { type:'field', value:'JOUR' },
        { type:'text',  value:'-' },
        { type:'field', value:'HEURE' },
        { type:'text',  value:'_' },
        { type:'field', value:'MIN' },
        { type:'text',  value:'_' },
        { type:'field', value:'SEC' },
      ],
      action: 'copy',
      delete_json: true,
    });
  }

  async function editProfile(name) {
    currentProfileName = name;
    // Highlight active
    document.querySelectorAll('.profile-item').forEach(el => {
      el.classList.toggle('bg-blue-50', el.dataset.name === name);
    });
    const res = await fetch('/api/profiles/' + encodeURIComponent(name));
    const profile = await res.json();
    openEditor(profile);
  }

  async function deleteProfile(name) {
    if (!confirm(`Supprimer le profil "${name}" ?`)) return;
    await fetch('/api/profiles/' + encodeURIComponent(name), { method: 'DELETE' });
    loadProfileList();
    if (currentProfileName === name) cancelEdit();
  }

  function cancelEdit() {
    currentProfileName = null;
    const ed = document.getElementById('editor');
    ed.innerHTML = '<p class="text-gray-400 text-sm text-center py-8">Sélectionnez un profil ou créez-en un nouveau.</p>';
    folderSortable = filenameSortable = null;
  }

  // ---- Render editor ----

  async function openEditor(profile) {
    const tpl = document.getElementById('editor_tpl');
    const ed  = document.getElementById('editor');
    ed.innerHTML = '';
    ed.appendChild(tpl.content.cloneNode(true));

    document.getElementById('ed_title').textContent =
      profile.name ? `Modifier : ${profile.name}` : 'Nouveau profil';
    document.getElementById('ed_name').value       = profile.name || '';
    document.getElementById('ed_action').value     = profile.action || 'copy';
    document.getElementById('ed_delete_json').checked    = profile.delete_json !== false;
    document.getElementById('ed_face_recognition').checked = !!profile.face_recognition;
    document.getElementById('ed_auto_caption').checked     = !!profile.auto_caption;

    // Check if face_recognition is installed
    const facesRes = await fetch('/api/faces');
    const facesData = await facesRes.json();
    if (!facesData.available) {
      document.getElementById('face_unavailable').classList.remove('hidden');
      document.getElementById('ed_face_recognition').disabled = true;
    }

    // Check if captioning is installed + populate language select
    const capRes = await fetch('/api/captioning');
    const capData = await capRes.json();
    const langSel = document.getElementById('ed_caption_language');
    langSel.innerHTML = Object.entries(capData.languages).map(([code, label]) =>
      `<option value="${code}">${label}</option>`
    ).join('');
    langSel.value = profile.caption_language || 'fi';
    if (!capData.available) {
      document.getElementById('caption_unavailable').classList.remove('hidden');
      document.getElementById('ed_auto_caption').disabled = true;
    }

    buildPalette();
    buildZone('zone_folder',   profile.folder_tokens   || []);
    buildZone('zone_filename', profile.filename_tokens || []);
    updatePreviews();
  }

  // ---- Token palette ----

  function buildPalette() {
    const palette = document.getElementById('token_palette');
    palette.innerHTML = TOKENS.map(t =>
      `<div class="token draggable border rounded px-2 py-1 text-xs font-medium cursor-grab select-none ${COLOR_MAP[t.color]}"
            data-type="field" data-value="${t.key}" draggable="true"
            title="${t.key}">${t.label}</div>`
    ).join('') +
    `<div class="token draggable border rounded px-2 py-1 text-xs font-medium cursor-grab select-none bg-white text-gray-600 border-gray-300"
          data-type="text" data-value="" draggable="true"
          title="Texte libre">✎ Texte libre</div>`;

    // Native DnD from palette → zones
    palette.querySelectorAll('.draggable').forEach(el => {
      el.addEventListener('dragstart', e => {
        e.dataTransfer.setData('token', JSON.stringify({
          type: el.dataset.type, value: el.dataset.value
        }));
      });
    });
  }

  // ---- Drop zones ----

  function buildZone(zoneId, tokens) {
    const zone = document.getElementById(zoneId);
    zone.innerHTML = '';
    if (!tokens.length) {
      zone.innerHTML = '<span class="placeholder-text">Glissez des tokens ici…</span>';
    } else {
      tokens.forEach(t => zone.appendChild(makeChip(t)));
    }

    // Accept drops from palette
    zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('drag-over'); });
    zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'));
    zone.addEventListener('drop', e => {
      e.preventDefault();
      zone.classList.remove('drag-over');
      const raw = e.dataTransfer.getData('token');
      if (!raw) return;
      const tok = JSON.parse(raw);
      const chip = makeChip(tok);
      // Remove placeholder
      zone.querySelector('.placeholder-text')?.remove();
      zone.appendChild(chip);
      updatePreviews();
    });

    // Sortable within zone
    const sortable = Sortable.create(zone, {
      animation: 150,
      ghostClass: 'sortable-ghost',
      onEnd: updatePreviews,
    });

    if (zoneId === 'zone_folder')   folderSortable   = sortable;
    if (zoneId === 'zone_filename') filenameSortable = sortable;
  }

  function makeChip(tok) {
    const div = document.createElement('div');
    div.dataset.type  = tok.type;
    div.dataset.value = tok.value || '';

    if (tok.type === 'field') {
      const def = TOKENS.find(t => t.key === tok.value);
      const color = def ? COLOR_MAP[def.color] : COLOR_MAP.gray;
      const label = def ? def.label : tok.value;
      div.className = `token border rounded px-2 py-1 text-xs font-medium flex items-center gap-1 cursor-grab select-none ${color}`;
      div.innerHTML = `<span>${label}</span><button class="remove-btn ml-1 opacity-60 hover:opacity-100" tabindex="-1">✕</button>`;
    } else {
      div.className = 'token border rounded flex items-center gap-1 cursor-grab select-none bg-white border-gray-300';
      div.innerHTML = `
        <input type="text" value="${esc(tok.value)}" placeholder="texte"
               class="text-xs px-2 py-1 w-20 bg-transparent outline-none font-mono text-gray-700"
               oninput="ProfileEditor.updatePreviews()">
        <button class="remove-btn pr-1 opacity-40 hover:opacity-100 text-xs" tabindex="-1">✕</button>`;
    }

    div.querySelector('.remove-btn').addEventListener('click', e => {
      e.stopPropagation();
      div.remove();
      // Re-add placeholder if zone empty
      const zone = div.closest('.drop-zone');
      if (zone && !zone.querySelector('.token')) {
        zone.innerHTML = '<span class="placeholder-text">Glissez des tokens ici…</span>';
        // Re-attach drop listeners
        buildZone(zone.id, []);
      }
      updatePreviews();
    });

    return div;
  }

  // ---- Preview ----

  function updatePreviews() {
    document.getElementById('preview_folder').textContent   = previewZone('zone_folder');
    document.getElementById('preview_filename').textContent = previewZone('zone_filename');
  }

  function previewZone(zoneId) {
    const zone = document.getElementById(zoneId);
    if (!zone) return '';
    return Array.from(zone.querySelectorAll('.token')).map(el => {
      if (el.dataset.type === 'field') {
        const def = TOKENS.find(t => t.key === el.dataset.value);
        return def ? def.example : el.dataset.value;
      }
      const inp = el.querySelector('input');
      return inp ? inp.value : el.dataset.value;
    }).join('');
  }

  // ---- Read tokens from DOM ----

  function readTokens(zoneId) {
    const zone = document.getElementById(zoneId);
    return Array.from(zone.querySelectorAll('.token')).map(el => {
      if (el.dataset.type === 'field') {
        return { type: 'field', value: el.dataset.value };
      }
      const inp = el.querySelector('input');
      return { type: 'text', value: inp ? inp.value : el.dataset.value };
    });
  }

  // ---- Save ----

  async function saveProfile() {
    const name = document.getElementById('ed_name').value.trim();
    if (!name) { alert('Veuillez donner un nom au profil.'); return; }

    const profile = {
      name,
      folder_tokens:    readTokens('zone_folder'),
      filename_tokens:  readTokens('zone_filename'),
      action:           document.getElementById('ed_action').value,
      delete_json:      document.getElementById('ed_delete_json').checked,
      face_recognition: document.getElementById('ed_face_recognition').checked,
      auto_caption:     document.getElementById('ed_auto_caption').checked,
      caption_language: document.getElementById('ed_caption_language').value,
    };

    const res = await fetch('/api/profiles', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(profile),
    });
    const data = await res.json();
    if (data.error) { alert('Erreur : ' + data.error); return; }

    currentProfileName = name;
    loadProfileList();
    alert('Profil enregistré !');
  }

  // ---- Helpers ----

  function esc(str) {
    return String(str).replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }

  return { init, newProfile, editProfile, deleteProfile, cancelEdit, saveProfile, updatePreviews };
})();
