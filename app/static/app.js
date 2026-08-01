const tg = window.Telegram?.WebApp;
tg?.ready();
tg?.expand();

const form = document.querySelector('#filters');
const sourcesNode = document.querySelector('#sources');
const resultsNode = document.querySelector('#results');
const sourceLinksNode = document.querySelector('#source-links');
const statusNode = document.querySelector('#status');
const money = new Intl.NumberFormat('ru-RU');
const currencies = {
  RUB: new Intl.NumberFormat('ru-RU', {style: 'currency', currency: 'RUB', maximumFractionDigits: 0}),
  JPY: new Intl.NumberFormat('ru-RU', {style: 'currency', currency: 'JPY', maximumFractionDigits: 0}),
  USD: new Intl.NumberFormat('ru-RU', {style: 'currency', currency: 'USD', minimumFractionDigits: 2})
};

function value(id) { return document.querySelector(id).value.trim(); }
function optionalNumber(id) { const raw = value(id); return raw === '' ? null : Number(raw); }
function escapeHtml(text) {
  const div = document.createElement('div'); div.textContent = text ?? ''; return div.innerHTML;
}

async function loadSources() {
  const response = await fetch('/api/sources');
  const sources = await response.json();
  sourcesNode.innerHTML = sources.map(source => `
    <label class="source"><input type="checkbox" value="${escapeHtml(source.id)}" checked>
    ${escapeHtml(source.name)}</label>`).join('');
}

function render(products) {
  resultsNode.innerHTML = products.map(product => `
    <a class="card" href="${escapeHtml(product.url)}" target="_blank" rel="noopener">
      <img src="${escapeHtml(product.image_url || '')}" alt="" loading="lazy">
      <div class="card-body"><span class="store">${escapeHtml(product.source)}</span>
        <div class="title">${escapeHtml(product.title)}</div>
        <div class="price">${(currencies[product.currency] || money).format(product.price)}</div>
        ${product.original_price ? `<div class="original-price">${currencies[product.original_currency].format(product.original_price)}</div>` : ''}
        <div class="sizes">${escapeHtml(product.sizes.join(' · '))}</div>
      </div>
    </a>`).join('');
}

function renderSourceLinks(links) {
  sourceLinksNode.innerHTML = links.map(link => `
    <a class="source-link" href="${escapeHtml(link.url)}" target="_blank" rel="noopener">
      Смотреть результаты на ${escapeHtml(link.source)} →
      <small>${escapeHtml(link.note)}</small>
    </a>`).join('');
}

form.addEventListener('submit', async event => {
  event.preventDefault();
  const button = form.querySelector('button');
  const sources = [...sourcesNode.querySelectorAll('input:checked')].map(node => node.value);
  if (!sources.length) { tg?.showAlert('Выбери хотя бы один сайт'); return; }
  button.disabled = true; statusNode.hidden = false; statusNode.textContent = 'Ищем лучшие варианты…';
  resultsNode.innerHTML = ''; sourceLinksNode.innerHTML = '';
  try {
    const response = await fetch('/api/search', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ brand: value('#brand') || null, size: value('#size') || null,
        price_from: optionalNumber('#price-from'), price_to: optionalNumber('#price-to'),
        clothing_type: value('#clothing-type') || null, sources })
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail?.[0]?.msg || 'Ошибка поиска');
    render(data.products);
    renderSourceLinks(data.source_links || []);
    const total = data.products.length + (data.source_links?.length || 0);
    statusNode.textContent = total ? 'Результаты готовы' : 'Ничего не найдено. Попробуй изменить фильтры.';
  } catch (error) { statusNode.textContent = error.message; }
  finally { button.disabled = false; }
});

loadSources().catch(() => { statusNode.hidden = false; statusNode.textContent = 'Не удалось загрузить магазины.'; });
