(() => {
  'use strict';
  const token = document.querySelector('meta[name="inventario-token"]').content;
  const $ = id => document.getElementById(id);
  const itemFields = ['titulo', 'marca', 'categoria', 'referencia', 'referencia_tienda', 'descripcion', 'observaciones'];
  let articles = [], inventories = [], selected = null, editing = null, photoData = '', photoRemoved = false, dirty = false;
  let activeInventoryId = null, selectedInventoryId = null;
  const form = $('itemForm');

  async function api(route, data) {
    const response = await fetch(route, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Inventario-Token': token },
      body: JSON.stringify(data)
    });
    let json = {};
    try { json = await response.json(); } catch (_) { /* respuesta inesperada */ }
    if (!response.ok) throw new Error(json.error || `Error ${response.status}`);
    return json;
  }

  function textNode(tag, value, cls = '') {
    const el = document.createElement(tag);
    el.textContent = value ?? '';
    if (cls) el.className = cls;
    return el;
  }

  function setMessage(id, message, kind = '') {
    $(id).textContent = message;
    $(id).className = 'msg ' + kind;
  }

  function getActiveInventory() {
    return inventories.find(x => x.id === activeInventoryId) || null;
  }

  function refreshInventoryLabels() {
    const current = getActiveInventory();
    const name = current?.nombre || 'Sin inventario';
    $('currentInventoryLabel').textContent = name.toUpperCase();
    $('dialogInventoryLabel').textContent = name.toUpperCase();
    document.title = `Recambios · ${name}`;
  }

  async function loadInventories(keepSelection = true) {
    const response = await fetch('/api/inventarios', { cache: 'no-store' });
    if (!response.ok) throw new Error('No se pudieron cargar los inventarios.');
    const data = await response.json();
    inventories = data.inventarios || [];
    activeInventoryId = data.activo_id || inventories[0]?.id || null;
    if (!keepSelection || !inventories.some(x => x.id === selectedInventoryId)) {
      selectedInventoryId = activeInventoryId;
    }
    refreshInventoryLabels();
    renderInventoryManager();
  }

  async function reload(preferred = selected) {
    try {
      if (!inventories.length) await loadInventories(false);
      const response = await fetch('/api/articulos' + (activeInventoryId ? '?inventario_id=' + encodeURIComponent(activeInventoryId) : ''), { cache: 'no-store' });
      if (!response.ok) throw new Error('No se pudo consultar el inventario.');
      const data = await response.json();
      articles = data.articulos || [];
      const inventory = data.inventario;
      if (inventory) {
        const idx = inventories.findIndex(x => x.id === inventory.id);
        if (idx >= 0) inventories[idx] = inventory;
      }
      const cats = [...new Set(articles.map(a => a.categoria).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'es'));
      const before = $('categoryFilter').value;
      $('categoryFilter').replaceChildren(new Option('Todas las categorías', ''));
      for (const c of cats) $('categoryFilter').add(new Option(c, c));
      if (cats.includes(before)) $('categoryFilter').value = before;
      if (!articles.some(a => a.id === preferred)) preferred = articles.length ? articles[0].id : null;
      selected = preferred;
      refreshInventoryLabels();
      render();
    } catch (err) {
      $('resultsInfo').textContent = err.message;
    }
  }

  function render() {
    const term = $('search').value.trim().toLocaleLowerCase('es');
    const category = $('categoryFilter').value;
    const list = articles.filter(a => (!category || a.categoria === category) && (
      !term || [a.titulo, a.referencia, a.referencia_tienda, a.marca, a.categoria, a.descripcion, a.observaciones]
        .some(v => (v || '').toLocaleLowerCase('es').includes(term))
    ));
    $('itemCount').textContent = `${articles.length} ${articles.length === 1 ? 'pieza' : 'piezas'}`;
    $('addBtn').disabled = !activeInventoryId;
    $('search').disabled = !activeInventoryId;
    $('categoryFilter').disabled = !activeInventoryId;
    $('emptyAdd').textContent = activeInventoryId ? '＋ Añadir recambio' : '＋ Crear primer inventario';
    $('emptyTitle').textContent = activeInventoryId ? 'Selecciona un recambio' : 'Todavía no hay inventarios';
    $('emptyText').textContent = activeInventoryId ? 'Haz clic en una pieza de la lista para ver su fotografía, referencias y enlaces de compra.' : 'Crea tu primer inventario y ponle el nombre que quieras. Después podrás añadir recambios.';
    $('resultsInfo').textContent = `${list.length} ${list.length === 1 ? 'resultado' : 'resultados'}`;
    const container = $('items');
    container.replaceChildren();
    if (!list.length) container.append(textNode('div', !activeInventoryId ? 'No hay inventarios. Pulsa «Inventarios» para crear uno.' : (articles.length ? 'No hay piezas que coincidan con tu búsqueda.' : 'Todavía no hay recambios. Pulsa «Nuevo recambio».'), 'empty-list'));
    for (const a of list) {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'item' + (a.id === selected ? ' active' : '');
      button.setAttribute('role', 'listitem');
      const thumb = document.createElement('div'); thumb.className = 'thumb';
      if (a.foto_url) {
        const img = document.createElement('img'); img.src = a.foto_url; img.alt = ''; thumb.append(img);
      } else thumb.textContent = '▧';
      const copy = document.createElement('div'); copy.className = 'item-copy'; copy.append(textNode('strong', a.titulo));
      copy.append(textNode('small', [a.marca, a.referencia ? 'Ref. ' + a.referencia : '', a.categoria].filter(Boolean).join(' · ')));
      button.append(thumb, copy); button.addEventListener('click', () => { selected = a.id; render(); }); container.append(button);
    }
    const a = articles.find(x => x.id === selected);
    $('emptyDetail').classList.toggle('hidden', !!a); $('itemDetail').classList.toggle('hidden', !a);
    if (!a) return;
    $('detailPhoto').classList.toggle('hidden', !a.foto_url); $('detailNoPhoto').classList.toggle('hidden', !!a.foto_url);
    if (a.foto_url) $('detailPhoto').src = a.foto_url; else $('detailPhoto').removeAttribute('src');
    $('detailTitle').textContent = a.titulo;
    $('detailDescription').textContent = a.descripcion || 'Sin descripción adicional.';
    $('detailBrand').textContent = a.marca || '—';
    $('detailRef').textContent = a.referencia || '—';
    $('detailStoreRef').textContent = a.referencia_tienda || '—';
    $('detailCategory').textContent = a.categoria || 'Sin categoría';
    $('detailNotes').textContent = a.observaciones;
    $('notesSection').classList.toggle('hidden', !a.observaciones);
    const shops = $('shopLinks'); shops.replaceChildren();
    if (!a.enlaces.length) shops.append(textNode('div', 'Todavía no hay enlaces para esta pieza.', 'no-links'));
    for (const link of a.enlaces) {
      const anchor = document.createElement('a'); anchor.className = 'shop'; anchor.target = '_blank'; anchor.rel = 'noopener noreferrer'; anchor.href = link.url;
      anchor.append(textNode('span', '▣', 'shop-icon'));
      const info = document.createElement('div'); info.className = 'shop-copy'; info.append(textNode('strong', link.tienda || 'Abrir tienda'));
      info.append(textNode('small', link.url)); anchor.append(info, textNode('span', '↗', 'shop-arrow')); shops.append(anchor);
    }
  }

  function addShopRow(shop = '', url = '') {
    const line = document.createElement('div'); line.className = 'shop-field';
    const name = document.createElement('label'); name.textContent = 'Tienda';
    const n = document.createElement('input'); n.type = 'text'; n.maxLength = 100; n.placeholder = 'Nombre de tienda'; n.value = shop; name.append(n);
    const link = document.createElement('label'); link.textContent = 'Enlace del producto';
    const u = document.createElement('input'); u.type = 'url'; u.maxLength = 2000; u.placeholder = 'https://…'; u.value = url; link.append(u);
    const remove = document.createElement('button'); remove.type = 'button'; remove.className = 'btn subtle'; remove.textContent = '×'; remove.title = 'Quitar esta tienda';
    remove.addEventListener('click', () => { line.remove(); dirty = true; });
    n.addEventListener('input', () => dirty = true); u.addEventListener('input', () => dirty = true);
    line.append(name, link, remove); $('shopFields').append(line);
  }

  function setPhoto(url = '') {
    $('formPhoto').classList.toggle('hidden', !url); $('formNoPhoto').classList.toggle('hidden', !!url);
    if (url) $('formPhoto').src = url; else $('formPhoto').removeAttribute('src');
  }

  function showForm(a = null) {
    if (!activeInventoryId) { openInventoryManager(); return; }
    editing = a?.id ?? null; photoData = ''; photoRemoved = false; dirty = false;
    form.reset(); $('shopFields').replaceChildren(); setMessage('importMessage', ''); setMessage('formMessage', '');
    $('dialogTitle').textContent = a ? 'Editar recambio' : 'Nuevo recambio';
    for (const f of itemFields) form.elements.namedItem(f).value = a?.[f] || '';
    if (a?.enlaces?.length) { for (const x of a.enlaces) addShopRow(x.tienda, x.url); } else addShopRow();
    setPhoto(a?.foto_url || ''); $('overlay').classList.remove('hidden'); refreshInventoryLabels();
    form.elements.namedItem('titulo').focus();
  }

  function closeForm() {
    if (dirty && !confirm('Tienes cambios sin guardar. ¿Cerrar sin guardarlos?')) return;
    $('overlay').classList.add('hidden'); dirty = false;
  }

  async function importUrl() {
    const url = $('importUrl').value.trim();
    if (!url) { setMessage('importMessage', 'Primero pega un enlace de producto.', 'error'); return; }
    $('importBtn').disabled = true; setMessage('importMessage', 'Consultando la ficha de la tienda…');
    try {
      const data = await api('/api/importar', { url });
      for (const f of itemFields) { if (data[f]) form.elements.namedItem(f).value = data[f]; }
      const filled = [...$('shopFields').querySelectorAll('.shop-field')].some(row => row.querySelectorAll('input')[1].value.trim());
      if (!filled) $('shopFields').replaceChildren();
      addShopRow(data.tienda, data.url);
      if (data.foto_data) { photoData = data.foto_data; photoRemoved = false; setPhoto(photoData); }
      dirty = true;
      setMessage('importMessage', 'Datos importados. Compruébalos y pulsa «Guardar recambio». ' + (data.aviso || ''), 'success');
    } catch (err) {
      setMessage('importMessage', `${err.message} Puedes introducir los datos manualmente.`, 'error');
    } finally { $('importBtn').disabled = false; }
  }

  async function saveForm(ev) {
    ev.preventDefault();
    const data = { id: editing, inventario_id: activeInventoryId };
    for (const f of itemFields) data[f] = form.elements.namedItem(f).value;
    data.enlaces = [...$('shopFields').querySelectorAll('.shop-field')].map(line => {
      const [shop, url] = line.querySelectorAll('input'); return { tienda: shop.value, url: url.value };
    });
    if (photoData) data.foto_data = photoData;
    if (photoRemoved) data.quitar_foto = true;
    $('saveBtn').disabled = true; setMessage('formMessage', 'Guardando…');
    try {
      const result = await api('/api/guardar', data);
      dirty = false; $('overlay').classList.add('hidden');
      $('search').value = ''; $('categoryFilter').value = ''; await reload(result.articulo.id);
    } catch (err) { setMessage('formMessage', err.message, 'error'); }
    finally { $('saveBtn').disabled = false; }
  }

  async function deleteCurrent() {
    const a = articles.find(x => x.id === selected); if (!a) return;
    const invName = getActiveInventory()?.nombre || 'este inventario';
    if (!confirm(`¿Eliminar definitivamente «${a.titulo}» de ${invName}?\n\nSe borrará también su fotografía guardada.`)) return;
    try { await api('/api/eliminar', { inventario_id: activeInventoryId, id: a.id }); selected = null; await reload(); } catch (err) { alert(err.message); }
  }

  function searchReference() {
    const a = articles.find(x => x.id === selected); if (!a) return;
    const query = [a.marca, a.referencia || a.referencia_tienda || a.titulo].filter(Boolean).join(' ');
    window.open('https://www.google.com/search?q=' + encodeURIComponent(query), '_blank', 'noopener,noreferrer');
  }

  async function saveBackup() {
    try {
      $('backupBtn').disabled = true;
      // En la aplicación Windows/WebView2 utilizamos un diálogo de guardado nativo.
      if (window.pywebview?.api?.guardar_copia) {
        const outcome = await window.pywebview.api.guardar_copia();
        if (outcome?.guardado) alert('Copia de seguridad guardada: ' + outcome.nombre);
        return;
      }
      // Mantener la compatibilidad con el programa portátil en navegador.
      const res = await fetch('/api/copia', { cache: 'no-store' });
      if (!res.ok) throw new Error('No se pudo crear la copia de seguridad.');
      const blob = await res.blob();
      const stamp = new Date().toISOString().slice(0, 10).replaceAll('-', '');
      const filename = `Recambios_${stamp}.zip`;
      if (typeof window.showSaveFilePicker === 'function') {
        try {
          const handle = await window.showSaveFilePicker({
            suggestedName: filename,
            types: [{ description: 'Copia de seguridad ZIP', accept: { 'application/zip': ['.zip'] } }]
          });
          const writer = await handle.createWritable(); await writer.write(blob); await writer.close();
          alert('Copia de seguridad guardada.'); return;
        } catch (err) { if (err.name === 'AbortError') return; throw err; }
      }
      const url = URL.createObjectURL(blob); const anchor = document.createElement('a'); anchor.href = url; anchor.download = filename;
      document.body.append(anchor); anchor.click(); anchor.remove(); setTimeout(() => URL.revokeObjectURL(url), 30000);
    } catch (err) { alert(err.message + ' Si tu navegador no permite elegir carpeta, revisa su configuración de descargas.'); }
    finally { $('backupBtn').disabled = false; }
  }

  function renderInventoryManager() {
    const list = $('inventoryList'); list.replaceChildren();
    const active = getActiveInventory();
    $('inventoryCurrentText').textContent = `Inventario actual: ${active?.nombre || '—'}`;
    for (const inv of inventories) {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'inventory-item' + (inv.id === selectedInventoryId ? ' selected' : '') + (inv.id === activeInventoryId ? ' active' : '');
      const title = document.createElement('strong'); title.textContent = inv.nombre;
      const meta = document.createElement('small'); meta.textContent = inv.id === activeInventoryId ? 'Abierto ahora' : 'Pulsa para seleccionarlo';
      button.append(title, meta);
      button.addEventListener('click', () => {
        selectedInventoryId = inv.id;
        $('inventoryName').value = inv.nombre;
        setMessage('inventoryMessage', '');
        renderInventoryManager();
      });
      list.append(button);
    }
    if (!inventories.length) list.append(textNode('div', 'Todavía no hay inventarios.', 'empty-list'));
    if (!$('inventoryName').matches(':focus')) {
      const selectedInv = inventories.find(x => x.id === selectedInventoryId);
      $('inventoryName').value = selectedInv?.nombre || '';
    }
  }

  function openInventoryManager() {
    selectedInventoryId = activeInventoryId;
    renderInventoryManager();
    setMessage('inventoryMessage', '');
    $('inventoryOverlay').classList.remove('hidden');
    $('inventoryName').focus();
    $('inventoryName').select();
  }

  function closeInventoryManager() {
    $('inventoryOverlay').classList.add('hidden');
  }

  async function openSelectedInventory() {
    const inv = inventories.find(x => x.id === selectedInventoryId);
    if (!inv) { setMessage('inventoryMessage', 'Selecciona un inventario.', 'error'); return; }
    try {
      await api('/api/inventarios/activar', { id: inv.id });
      activeInventoryId = inv.id;
      selected = null;
      $('search').value = ''; $('categoryFilter').value = '';
      await loadInventories(false);
      await reload();
      closeInventoryManager();
    } catch (err) { setMessage('inventoryMessage', err.message, 'error'); }
  }

  async function createInventoryAction() {
    const name = $('inventoryName').value.trim();
    if (!name) { setMessage('inventoryMessage', 'Escribe el nombre del nuevo inventario.', 'error'); return; }
    try {
      const data = await api('/api/inventarios/nuevo', { nombre: name });
      inventories = data.inventarios || [];
      activeInventoryId = data.activo_id;
      selectedInventoryId = activeInventoryId;
      selected = null;
      $('search').value = ''; $('categoryFilter').value = '';
      renderInventoryManager(); refreshInventoryLabels(); await reload();
      setMessage('inventoryMessage', 'Inventario creado y abierto.', 'success');
      closeInventoryManager();
    } catch (err) { setMessage('inventoryMessage', err.message, 'error'); }
  }

  async function renameInventoryAction() {
    const inv = inventories.find(x => x.id === selectedInventoryId);
    if (!inv) { setMessage('inventoryMessage', 'Selecciona un inventario.', 'error'); return; }
    const name = $('inventoryName').value.trim();
    if (!name) { setMessage('inventoryMessage', 'Escribe el nuevo nombre.', 'error'); return; }
    try {
      const data = await api('/api/inventarios/renombrar', { id: inv.id, nombre: name });
      inventories = data.inventarios || [];
      if (inv.id === activeInventoryId) refreshInventoryLabels();
      renderInventoryManager(); refreshInventoryLabels();
      if (inv.id === activeInventoryId) $('currentInventoryLabel').textContent = name.toUpperCase();
      setMessage('inventoryMessage', 'Inventario renombrado.', 'success');
    } catch (err) { setMessage('inventoryMessage', err.message, 'error'); }
  }

  async function deleteInventoryAction() {
    const inv = inventories.find(x => x.id === selectedInventoryId);
    if (!inv) { setMessage('inventoryMessage', 'Selecciona un inventario.', 'error'); return; }
    if (!confirm(`¿Eliminar el inventario «${inv.nombre}»?\n\nSe borrarán todos sus recambios y fotografías guardadas.`)) return;
    try {
      const data = await api('/api/inventarios/eliminar', { id: inv.id });
      inventories = data.inventarios || [];
      activeInventoryId = data.activo_id;
      selectedInventoryId = activeInventoryId;
      selected = null;
      $('search').value = ''; $('categoryFilter').value = '';
      renderInventoryManager(); refreshInventoryLabels(); await reload();
      setMessage('inventoryMessage', 'Inventario eliminado.', 'success');
    } catch (err) { setMessage('inventoryMessage', err.message, 'error'); }
  }

  let restoreFile = null;
  let restorePreview = null;

  function cancelRestore() {
    if ($('restoreConfirm').disabled) return;
    $('restoreOverlay').classList.add('hidden');
    restoreFile = null;
    restorePreview = null;
    $('restoreChoices').replaceChildren();
    setMessage('restoreMessage', '');
  }

  async function restoreBackup() {
    const file = $('restoreBackupFile').files?.[0];
    if (!file) return;
    $('restoreBackupFile').value = '';
    if (!file.name.toLowerCase().endsWith('.zip')) {
      setMessage('inventoryMessage', 'Selecciona una copia de seguridad ZIP.', 'error'); return;
    }
    if (file.size > 60 * 1024 * 1024) {
      setMessage('inventoryMessage', 'La copia es demasiado grande (máximo 60 MB).', 'error'); return;
    }
    $('restoreBackupBtn').disabled = true;
    setMessage('inventoryMessage', 'Comprobando la copia sin modificar tus datos…');
    try {
      const response = await fetch('/api/previsualizar-copia', {
        method: 'POST',
        headers: { 'X-Inventario-Token': token, 'Content-Type': 'application/zip' },
        body: file
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'No se pudo comprobar el ZIP.');
      restoreFile = file;
      restorePreview = data;
      renderRestoreChoices();
      setMessage('inventoryMessage', 'Copia comprobada. Confirma cómo quieres recuperarla.');
      $('restoreOverlay').classList.remove('hidden');
    } catch (err) {
      setMessage('inventoryMessage', err.message, 'error');
    } finally {
      $('restoreBackupBtn').disabled = false;
    }
  }

  function renderRestoreChoices() {
    const container = $('restoreChoices'); container.replaceChildren();
    $('restoreFilename').textContent = `Archivo: ${restoreFile.name}. Los nombres se conservarán tal como aparecen en la copia.`;
    setMessage('restoreMessage', '');
    for (const item of restorePreview.inventarios) {
      const card = document.createElement('div'); card.className = 'restore-choice';
      card.dataset.sourceId = item.id_origen;
      card.append(textNode('strong', item.nombre));
      card.append(textNode('small', `${item.recambios} ${item.recambios === 1 ? 'recambio' : 'recambios'} en la copia`));
      if (item.coincidencia) {
        card.append(textNode('div', `Ya existe «${item.coincidencia.nombre}» con ${item.coincidencia.recambios} recambios. ¿Qué quieres hacer?`, 'restore-warning'));
        const controls = document.createElement('div'); controls.className = 'restore-controls';
        const select = document.createElement('select'); select.className = 'restore-action';
        select.add(new Option('Elegir una opción…', ''));
        select.add(new Option('Sobrescribir inventario existente', 'sobrescribir'));
        select.add(new Option('Cambiar nombre al recuperado', 'renombrar'));
        select.value = '';
        const input = document.createElement('input'); input.type = 'text'; input.maxLength = 60;
        input.className = 'restore-new-name'; input.placeholder = 'Nuevo nombre'; input.hidden = true;
        select.addEventListener('change', () => { input.hidden = select.value !== 'renombrar'; if (!input.hidden) input.focus(); });
        controls.append(select, input); card.append(controls);
        card.dataset.targetId = item.coincidencia.id;
      } else {
        card.append(textNode('div', 'Se creará con este mismo nombre, sin añadir «(recuperado)».', 'restore-info'));
      }
      container.append(card);
    }

    if (restorePreview.listas?.length) {
      container.append(textNode('h3', 'Mis Listas — recuperar también', 'restore-subtitle'));
      for (const item of restorePreview.listas) {
        const card = document.createElement('div'); card.className = 'restore-choice';
        card.dataset.sourceId = 'lista:' + item.id_origen;
        card.append(textNode('strong', item.nombre + ' (lista)'));
        card.append(textNode('small', `${item.articulos} artículos en la lista`));
        if (item.coincidencia) {
          card.append(textNode('div', 'Ya hay una lista con este nombre. Selecciona qué hacer:', 'restore-warning'));
          const controls = document.createElement('div'); controls.className = 'restore-controls';
          const select = document.createElement('select'); select.className = 'restore-action';
          select.add(new Option('Elegir una opción…', ''));
          select.add(new Option('Sobrescribir lista existente', 'sobrescribir'));
          select.add(new Option('Cambiar nombre a la lista recuperada', 'renombrar'));
          const input = document.createElement('input'); input.className = 'restore-new-name'; input.maxLength = 60; input.hidden = true; input.placeholder = 'Nombre nuevo';
          select.addEventListener('change', () => { input.hidden = select.value !== 'renombrar'; if (!input.hidden) input.focus(); });
          card.dataset.targetId = item.coincidencia.id;
          controls.append(select, input); card.append(controls);
        } else card.append(textNode('div', 'Se recuperará con su nombre original.', 'restore-info'));
        container.append(card);
      }
    }

    if (restorePreview.inventarios.some(i => i.coincidencia) || restorePreview.listas?.some(i => i.coincidencia)) {
      container.append(textNode('div', 'Sobrescribir sustituye todos los recambios y fotografías de ese inventario. Antes se guardará una copia de seguridad automática de los datos actuales.', 'restore-warning'));
    }
  }

  async function confirmRestore() {
    if (!restoreFile || !restorePreview) return;
    const options = {};
    for (const card of $('restoreChoices').querySelectorAll('.restore-choice')) {
      const sourceId = card.dataset.sourceId;
      const select = card.querySelector('.restore-action');
      if (!select) { options[sourceId] = { accion: 'crear' }; continue; }
      if (select.value === 'sobrescribir') {
        options[sourceId] = { accion: 'sobrescribir', destino_id: Number(card.dataset.targetId) };
      } else if (select.value === 'renombrar') {
        const name = card.querySelector('.restore-new-name').value.trim();
        if (!name) { setMessage('restoreMessage', 'Escribe un nombre nuevo para cada inventario que quieras renombrar.', 'error'); return; }
        options[sourceId] = { accion: 'renombrar', nombre: name };
      } else {
        setMessage('restoreMessage', 'Elige sobrescribir o cambiar nombre para cada inventario o lista repetida.', 'error'); return;
      }
    }
    const replacements = Object.values(options).filter(x => x.accion === 'sobrescribir').length;
    if (replacements && !confirm(`Vas a SOBRESCRIBIR ${replacements} inventario(s) o lista(s). Su contenido actual será sustituido por el del ZIP.

Antes se creará una copia de seguridad. ¿Confirmas?`)) return;
    $('restoreConfirm').disabled = true;
    $('restoreCancel').disabled = true;
    setMessage('restoreMessage', 'Recuperando los datos y fotografías…');
    try {
      const params = new URLSearchParams({ opciones: JSON.stringify(options), huella: restorePreview.huella });
      const response = await fetch('/api/cargar-copia?' + params, {
        method: 'POST',
        headers: { 'X-Inventario-Token': token, 'Content-Type': 'application/zip' },
        body: restoreFile
      });
      let data = {};
      try { data = await response.json(); } catch (_) { /* respuesta inesperada */ }
      if (!response.ok) throw new Error(data.error || 'No se pudo recuperar la copia.');
      $('restoreOverlay').classList.add('hidden');
      restoreFile = null; restorePreview = null;
      selected = null;
      $('search').value = ''; $('categoryFilter').value = '';
      await loadInventories(false);
      await reload();
      await loadShoppingLists();
      const text = `Copia cargada: ${data.inventarios_importados} inventario(s), ${data.articulos_importados} recambio(s).` +
        ` Listas: ${data.listas_importadas || 0}; piezas de listas: ${data.piezas_lista_importadas || 0}.` +
        (data.inventarios_sobrescritos ? ` Sustituidos: ${data.inventarios_sobrescritos}. Copia preventiva guardada en Datos.` : '');
      setMessage('inventoryMessage', text, 'success');
    } catch (err) {
      setMessage('restoreMessage', err.message, 'error');
    } finally {
      $('restoreConfirm').disabled = false;
      $('restoreCancel').disabled = false;
    }
  }


  // Las listas almacenan instantáneas. Nunca se altera el catálogo de origen.
  let shoppingLists = [], currentListId = null;
  let listNameMode = 'crear';
  let listAddSourceLock = null;
  let listAddTargetLock = null;
  let listAddArticles = [];
  let listAddFetchSerial = 0;

  function switchTab(tab) {
    const listMode = tab === 'listas';
    $('catalogPage').classList.toggle('hidden', listMode);
    $('listsPage').classList.toggle('hidden', !listMode);
    $('tabRecambios').classList.toggle('active', !listMode);
    $('tabMisListas').classList.toggle('active', listMode);
    $('manageInventories').classList.toggle('hidden', listMode);
    $('addBtn').classList.toggle('hidden', listMode);
    $('itemCount').classList.toggle('hidden', listMode);
    $('currentInventoryLabel').classList.toggle('hidden', listMode);
    $('currentInventoryLabel').previousElementSibling?.classList.toggle('hidden', listMode);
    if (listMode) loadShoppingLists().catch(e => alert(e.message));
  }

  async function loadShoppingLists(prefer = currentListId) {
    const response = await fetch('/api/listas', { cache: 'no-store' });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'No se pudieron consultar las listas.');
    shoppingLists = data.listas;
    if (!shoppingLists.some(l => l.id === prefer)) prefer = shoppingLists[0]?.id || null;
    currentListId = prefer;
    renderShoppingNavigation();
    await loadShoppingDetail();
  }

  function renderShoppingNavigation() {
    const container = $('shoppingLists'); container.replaceChildren();
    for (const lst of shoppingLists) {
      const button = document.createElement('button');
      button.type = 'button'; button.className = 'shopping-list-btn' + (lst.id === currentListId ? ' active' : '');
      const body = document.createElement('div');
      body.append(textNode('strong', lst.nombre), textNode('small', `${lst.articulos} ${lst.articulos === 1 ? 'artículo' : 'artículos'} · ${lst.unidades} unidades`));
      button.append(body, textNode('span', lst.id === currentListId ? 'Abierta' : 'Abrir', 'shopping-pill'));
      button.addEventListener('click', async () => { currentListId = lst.id; renderShoppingNavigation(); await loadShoppingDetail(); });
      container.append(button);
    }
    if (!shoppingLists.length) container.append(textNode('p', 'Todavía no tienes listas. Crea la primera con el nombre que quieras.', 'empty-list'));
    $('shoppingEmpty').classList.toggle('hidden', !!currentListId);
    $('shoppingDetails').classList.toggle('hidden', !currentListId);
  }

  async function loadShoppingDetail() {
    if (!currentListId) return;
    const response = await fetch('/api/listas/detalle?id=' + encodeURIComponent(currentListId), { cache: 'no-store' });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'No se pudo abrir la lista.');
    $('shoppingTitle').textContent = data.lista.nombre;
    const lines = data.lineas;
    $('shoppingCount').textContent = `${lines.length} artículos · ${lines.reduce((sum, line) => sum + line.cantidad, 0)} unidades a comprar`;
    const container = $('shoppingLines'); container.replaceChildren();
    if (!lines.length) {
      container.append(textNode('p', 'Esta lista está vacía. Pulsa «Añadir desde catálogos» para seleccionar los recambios que quieras comprar.', 'empty-list'));
      return;
    }
    for (const line of lines) {
      const card = document.createElement('article'); card.className = 'shopping-line';
      const photo = document.createElement('div'); photo.className = 'shopping-line-photo';
      if (line.foto_url) {
        const img = document.createElement('img'); img.src = line.foto_url; img.alt = ''; photo.append(img);
      } else photo.textContent = '▧';
      const main = document.createElement('div'); main.className = 'shopping-line-main';
      main.append(textNode('strong', line.titulo));
      main.append(textNode('small', [line.origen_inventario, line.marca, line.referencia ? 'Ref. ' + line.referencia : line.referencia_tienda].filter(Boolean).join(' · ')));
      if (line.descripcion) main.append(textNode('small', line.descripcion));
      const allShops = line.enlaces || [];
      const chosenShop = allShops.find(link => link.seleccionada) || allShops[0] || null;
      if (chosenShop) {
        const chosen = document.createElement('div'); chosen.className = 'shopping-line-chosen';
        chosen.append(textNode('span', 'WEB ELEGIDA PARA COMPRAR', 'shopping-line-chosen-label'));
        const a = document.createElement('a'); a.href = chosenShop.url; a.target = '_blank'; a.rel = 'noopener noreferrer';
        a.append(textNode('strong', chosenShop.tienda || new URL(chosenShop.url).hostname), textNode('span', ' ↗'));
        chosen.append(a, textNode('small', chosenShop.url, 'shopping-shop-url'));
        main.append(chosen);
      } else {
        main.append(textNode('small', 'Sin web de compra guardada.', 'shopping-muted'));
      }
      if (allShops.length > 1) {
        const other = document.createElement('div'); other.className = 'shopping-line-links';
        for (const link of allShops.filter(link => link.url !== chosenShop?.url)) {
          const a = document.createElement('a'); a.href = link.url; a.target = '_blank'; a.rel = 'noopener noreferrer';
          a.textContent = 'Otra tienda: ' + (link.tienda || 'Abrir web') + ' ↗'; other.append(a);
        }
        main.append(other);
      }
      const controls = document.createElement('div'); controls.className = 'shopping-line-controls';
      const label = document.createElement('label'); label.textContent = 'Cantidad a comprar';
      const input = document.createElement('input'); input.type = 'number'; input.min = '1'; input.max = '100000'; input.step = '1'; input.value = line.cantidad; label.append(input);
      const message = textNode('span', '', 'shopping-muted');
      input.addEventListener('change', async () => {
        const count = Number(input.value);
        if (!Number.isInteger(count) || count < 1 || count > 100000) {
          input.value = line.cantidad; message.textContent = 'Cantidad no válida'; return;
        }
        input.disabled = true; message.textContent = 'Guardando…';
        try {
          await api('/api/listas/cantidad', { lista_id: currentListId, linea_id: line.id, cantidad: count });
          await loadShoppingLists(currentListId);
        } catch (err) {
          input.value = line.cantidad; message.textContent = err.message;
        } finally { input.disabled = false; }
      });
      const remove = document.createElement('button'); remove.className = 'btn danger small'; remove.type = 'button'; remove.textContent = 'Quitar';
      remove.title = 'Solo quita el artículo de esta lista, nunca del catálogo';
      remove.addEventListener('click', async () => {
        if (!confirm(`¿Quitar «${line.titulo}» de esta lista? El recambio original no se modificará.`)) return;
        try {
          await api('/api/listas/quitar', { lista_id: currentListId, linea_id: line.id });
          await loadShoppingLists(currentListId);
        } catch (err) { alert(err.message); }
      });
      controls.append(label, message, remove); card.append(photo, main, controls); container.append(card);
    }
  }

  function openListName(mode) {
    listNameMode = mode;
    const current = shoppingLists.find(l => l.id === currentListId);
    $('listNameTitle').textContent = mode === 'crear' ? 'Nueva lista' : 'Renombrar lista';
    $('listNameInput').value = mode === 'renombrar' ? current?.nombre || '' : '';
    setMessage('listNameMessage', ''); $('listNameOverlay').classList.remove('hidden');
    $('listNameInput').focus(); $('listNameInput').select();
  }

  function closeListName() { $('listNameOverlay').classList.add('hidden'); }

  async function submitListName(ev) {
    ev.preventDefault();
    const nombre = $('listNameInput').value.trim();
    if (!nombre) { setMessage('listNameMessage', 'Escribe un nombre.', 'error'); return; }
    $('listNameSubmit').disabled = true;
    try {
      if (listNameMode === 'crear') {
        const data = await api('/api/listas/nueva', { nombre });
        await loadShoppingLists(data.id);
      } else {
        await api('/api/listas/renombrar', { id: currentListId, nombre });
        await loadShoppingLists(currentListId);
      }
      closeListName();
    } catch (err) { setMessage('listNameMessage', err.message, 'error'); }
    finally { $('listNameSubmit').disabled = false; }
  }

  async function deleteSelectedList() {
    const lst = shoppingLists.find(l => l.id === currentListId); if (!lst) return;
    if (!confirm(`¿Eliminar la lista «${lst.nombre}» y sus ${lst.articulos} artículos?\n\nNo se eliminará ningún recambio de tus catálogos.`)) return;
    try {
      await api('/api/listas/eliminar', { id: lst.id });
      currentListId = null; await loadShoppingLists();
    } catch (err) { alert(err.message); }
  }

  // Fotografía y webs guardadas en el catálogo: siempre visibles antes de elegir.
  function renderAddArticlePreview() {
    const pieceId = Number($('listAddArticle').value);
    const a = listAddArticles.find(item => item.id === pieceId);
    $('listAddPreview').classList.toggle('hidden', !a);
    $('listAddShops').replaceChildren();
    $('listAddSubmit').disabled = !a;
    if (!a) return;
    $('listAddPieceTitle').textContent = a.titulo;
    $('listAddPieceRef').textContent = a.referencia ? 'Ref. fabricante: ' + a.referencia : 'Sin referencia de fabricante';
    $('listAddPieceBrand').textContent = [a.marca, a.referencia_tienda ? 'Ref. tienda: ' + a.referencia_tienda : ''].filter(Boolean).join(' · ');
    $('listAddPhoto').classList.toggle('hidden', !a.foto_url);
    $('listAddNoPhoto').classList.toggle('hidden', !!a.foto_url);
    if (a.foto_url) $('listAddPhoto').src = a.foto_url;
    else $('listAddPhoto').removeAttribute('src');
    const links = a.enlaces || [];
    if (!links.length) {
      $('listAddShops').append(textNode('p', 'Este recambio no tiene ninguna web de compra guardada. Puedes añadirlo a la lista sin tienda.', 'list-add-no-shops'));
      return;
    }
    for (let i = 0; i < links.length; i++) {
      const shop = links[i];
      const row = document.createElement('div'); row.className = 'list-add-shop-row';
      const label = document.createElement('label'); label.className = 'list-add-shop-choice';
      const radio = document.createElement('input'); radio.type = 'radio'; radio.name = 'listAddShop';
      radio.value = shop.url; radio.required = true; radio.checked = i === 0;
      const info = document.createElement('span'); info.className = 'list-add-shop-info';
      info.append(textNode('strong', shop.tienda || new URL(shop.url).hostname));
      info.append(textNode('span', shop.url, 'list-add-shop-url'));
      label.append(radio, info);
      const open = document.createElement('a'); open.href = shop.url; open.target = '_blank'; open.rel = 'noopener noreferrer';
      open.className = 'list-add-shop-open'; open.textContent = 'Abrir web ↗';
      open.title = 'Consultar esta página de la tienda';
      row.append(label, open); $('listAddShops').append(row);
    }
  }

  async function updateAddArticleSelect(selectedId = null) {
    const serial = ++listAddFetchSerial;
    const invId = Number($('listAddInventory').value);
    const select = $('listAddArticle'); select.replaceChildren(); listAddArticles = [];
    renderAddArticlePreview();
    if (!invId) return;
    const response = await fetch('/api/articulos?inventario_id=' + encodeURIComponent(invId), { cache: 'no-store' });
    const data = await response.json();
    if (serial !== listAddFetchSerial) return; // Evitar resultados tardíos del inventario anterior.
    if (!response.ok) { setMessage('listAddMessage', data.error || 'Error al cargar catálogo.', 'error'); return; }
    listAddArticles = data.articulos || [];
    for (const article of listAddArticles) select.add(new Option(`${article.titulo}${article.referencia ? ' · '+article.referencia : ''}`, article.id));
    if (selectedId && [...select.options].some(opt => Number(opt.value) === selectedId)) select.value = String(selectedId);
    if (!select.options.length) setMessage('listAddMessage', 'No hay recambios en ese catálogo. Elige otro.', 'error');
    renderAddArticlePreview();
  }

  async function openListAdd(fromCatalog = false) {
    if (!shoppingLists.length) await loadShoppingLists();
    if (!shoppingLists.length) {
      switchTab('listas');
      openListName('crear');
      return;
    }
    setMessage('listAddMessage', '');
    $('listAddTarget').replaceChildren();
    for (const lst of shoppingLists) $('listAddTarget').add(new Option(lst.nombre, lst.id));
    $('listAddTarget').value = String(fromCatalog ? shoppingLists[0].id : currentListId);
    $('listAddInventory').replaceChildren();
    for (const inv of inventories) $('listAddInventory').add(new Option(inv.nombre, inv.id));
    if (!inventories.length) { alert('Primero debes crear un catálogo y guardar recambios.'); return; }
    $('listAddInventory').value = String(activeInventoryId || inventories[0].id);
    $('listAddQuantity').value = '1';
    $('listAddOverlay').classList.remove('hidden');
    await updateAddArticleSelect(fromCatalog ? selected : null);
  }

  async function submitListAdd(ev) {
    ev.preventDefault();
    const lista_id = Number($('listAddTarget').value);
    const inventario_id = Number($('listAddInventory').value);
    const articulo_id = Number($('listAddArticle').value);
    const cantidad = Number($('listAddQuantity').value);
    if (![lista_id, inventario_id, articulo_id, cantidad].every(Number.isInteger) || cantidad < 1 || cantidad > 100000 || !articulo_id) {
      setMessage('listAddMessage', 'Selecciona una lista, un recambio y una cantidad válida.', 'error'); return;
    }
    $('listAddSubmit').disabled = true;
    try {
      const selectedShop = $('listAddShops').querySelector('input[name="listAddShop"]:checked');
      const url_compra = selectedShop?.value || '';
      if (listAddArticles.find(item => item.id === articulo_id)?.enlaces?.length && !url_compra) {
        setMessage('listAddMessage', 'Elige la web donde comprarás este recambio.', 'error'); return;
      }
      await api('/api/listas/anadir', { lista_id, inventario_id, articulo_id, cantidad, url_compra });
      $('listAddOverlay').classList.add('hidden');
      currentListId = lista_id;
      await loadShoppingLists(lista_id);
      switchTab('listas');
    } catch (err) { setMessage('listAddMessage', err.message, 'error'); }
    finally { $('listAddSubmit').disabled = false; }
  }

  $('tabRecambios').addEventListener('click', () => switchTab('catalogo'));
  $('tabMisListas').addEventListener('click', () => switchTab('listas'));
  $('addToListFromCatalog').addEventListener('click', async () => {
    try { await loadShoppingLists(); await openListAdd(true); } catch (err) { alert(err.message); }
  });
  $('newListBtn').addEventListener('click', () => openListName('crear'));
  $('shoppingEmptyCreate').addEventListener('click', () => openListName('crear'));
  $('renameListBtn').addEventListener('click', () => openListName('renombrar'));
  $('deleteListBtn').addEventListener('click', deleteSelectedList);
  $('addFromCatalogBtn').addEventListener('click', () => openListAdd(false).catch(err => alert(err.message)));
  $('listNameClose').addEventListener('click', closeListName);
  $('listNameCancel').addEventListener('click', closeListName);
  $('listNameForm').addEventListener('submit', submitListName);
  $('listAddInventory').addEventListener('change', () => updateAddArticleSelect().catch(err => setMessage('listAddMessage', err.message, 'error')));
  $('listAddArticle').addEventListener('change', renderAddArticlePreview);
  $('listAddClose').addEventListener('click', () => $('listAddOverlay').classList.add('hidden'));
  $('listAddCancel').addEventListener('click', () => $('listAddOverlay').classList.add('hidden'));
  $('listAddForm').addEventListener('submit', submitListAdd);

  $('search').addEventListener('input', render); $('categoryFilter').addEventListener('change', render);
  $('addBtn').addEventListener('click', () => showForm());
  $('emptyAdd').addEventListener('click', () => activeInventoryId ? showForm() : openInventoryManager());
  $('editBtn').addEventListener('click', () => showForm(articles.find(x => x.id === selected)));
  $('deleteBtn').addEventListener('click', deleteCurrent);
  $('searchWeb').addEventListener('click', searchReference);
  $('backupBtn').addEventListener('click', saveBackup);
  $('manageInventories').addEventListener('click', openInventoryManager);
  $('closeDialog').addEventListener('click', closeForm); $('cancelBtn').addEventListener('click', closeForm);
  $('closeInventoryDialog').addEventListener('click', closeInventoryManager);
  $('closeInventoryFooter').addEventListener('click', closeInventoryManager);
  $('openInventoryBtn').addEventListener('click', openSelectedInventory);
  $('newInventoryBtn').addEventListener('click', createInventoryAction);
  $('renameInventoryBtn').addEventListener('click', renameInventoryAction);
  $('deleteInventoryBtn').addEventListener('click', deleteInventoryAction);
  $('restoreBackupBtn').addEventListener('click', () => $('restoreBackupFile').click());
  $('restoreBackupFile').addEventListener('change', restoreBackup);
  $('restoreConfirm').addEventListener('click', confirmRestore);
  $('restoreCancel').addEventListener('click', cancelRestore);
  $('restoreClose').addEventListener('click', cancelRestore);
  $('restoreOverlay').addEventListener('click', ev => { if (ev.target === $('restoreOverlay')) cancelRestore(); });
  $('addShop').addEventListener('click', () => { if ($('shopFields').children.length >= 8) { alert('Máximo ocho tiendas por recambio.'); return; } addShopRow(); dirty = true; });
  $('importBtn').addEventListener('click', importUrl);
  $('choosePhoto').addEventListener('click', () => $('photoFile').click());
  $('photoFile').addEventListener('change', async ev => {
    const f = ev.target.files?.[0]; if (!f) return;
    if (f.size > 4 * 1024 * 1024 || !['image/jpeg', 'image/png', 'image/webp'].includes(f.type)) {
      setMessage('formMessage', 'La fotografía debe ser JPG, PNG o WebP y ocupar menos de 4 MB.', 'error'); ev.target.value = ''; return;
    }
    const reader = new FileReader(); reader.onload = () => { photoData = reader.result; photoRemoved = false; setPhoto(photoData); dirty = true; }; reader.readAsDataURL(f);
    ev.target.value = '';
  });
  $('removePhoto').addEventListener('click', () => { photoData = ''; photoRemoved = true; dirty = true; setPhoto(); });
  form.addEventListener('input', () => { dirty = true; }); form.addEventListener('submit', saveForm);
  $('overlay').addEventListener('click', ev => { if (ev.target === $('overlay')) closeForm(); });
  $('inventoryOverlay').addEventListener('click', ev => { if (ev.target === $('inventoryOverlay')) closeInventoryManager(); });
  document.addEventListener('keydown', ev => {
    if (ev.key === 'Escape' && !$('restoreOverlay').classList.contains('hidden')) cancelRestore();
    else if (ev.key === 'Escape' && !$('overlay').classList.contains('hidden')) closeForm();
    else if (ev.key === 'Escape' && !$('inventoryOverlay').classList.contains('hidden')) closeInventoryManager();
  });
  $('goBack').addEventListener('click', async () => {
    if (!$('overlay').classList.contains('hidden') && dirty && !confirm('Tienes cambios sin guardar. ¿Cerrar el programa?')) return;
    if (!confirm('¿Quieres cerrar Recambios? Los inventarios guardados se conservarán.')) return;
    $('goBack').disabled = true;
    try {
      // En Windows cerrar la ventana también finaliza el servidor local.
      if (window.pywebview?.api?.cerrar) {
        await window.pywebview.api.cerrar();
        return;
      }
      await api('/api/salir', {});
      document.body.replaceChildren();
      const notice = document.createElement('main'); notice.className = 'close-screen';
      const title = document.createElement('h1'); title.textContent = 'Recambios cerrado';
      const info = document.createElement('p'); info.textContent = 'Tus inventarios, artículos y fotografías están guardados. Puedes cerrar esta pestaña.';
      notice.append(title, info); document.body.append(notice);
      window.close();
    } catch (err) {
      $('goBack').disabled = false; alert('No se pudo cerrar el servidor: ' + err.message);
    }
  });

  (async () => {
    try {
      await loadInventories(false);
      await reload();
      // Sin datos previos se muestra el gestor, pero no se crea nada por sí solo.
      if (!inventories.length) openInventoryManager();
    } catch (err) {
      $('resultsInfo').textContent = err.message;
    }
  })();
})();
