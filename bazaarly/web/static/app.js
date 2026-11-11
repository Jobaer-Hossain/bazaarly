/**
 * Bazaarly — Enterprise Multi-Vendor eCommerce Platform
 * Client Application Logic
 */

// Global State
const state = {
  token: localStorage.getItem('bazaarly_token') || '',
  currentUser: null,
  activeView: 'storefront',
  categories: [],
  brands: [],
  products: [],
  currentProduct: null,
  selectedVariant: null,
  selectedQuantity: 1,
  cart: {
    items: [],
    subtotal: 0,
    discount_amount: 0,
    shipping_fee: 0,
    tax_amount: 0,
    grand_total: 0,
    coupon_code: null
  },
  wishlist: JSON.parse(localStorage.getItem('bazaarly_wishlist') || '[]'),
  sellerChart: null,
  lastCompletedOrder: null,
  saActiveTab: 'overview',
  saUsers: [],
  saRoles: [],
  saActiveRoleKey: 'super_admin',
  saTrendChart: null,
  saGatewaysChart: null,
  catalogOffset: 0,
  catalogLimit: 20,
  catalogHasMore: true,
  catalogLoading: false,
  catalogFilters: {}
};

// API Helper
async function api(endpoint, options = {}) {
  const headers = {
    'Content-Type': 'application/json',
    ...(state.token ? { 'Authorization': `Bearer ${state.token}` } : {}),
    ...(options.headers || {})
  };

  try {
    const res = await fetch(endpoint, { ...options, headers });
    if (res.status === 401) {
      // If unauthorized, prompt or reset to customer demo
      console.warn('Unauthorized request, re-authenticating as customer demo');
      await switchRole('customer', false);
      return null;
    }
    const contentType = res.headers.get('content-type');
    if (contentType && contentType.includes('application/json')) {
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'API request failed');
      }
      return data;
    } else {
      if (!res.ok) throw new Error(`HTTP Error ${res.status}`);
      return await res.text();
    }
  } catch (err) {
    console.error(`API Error on ${endpoint}:`, err);
    throw err;
  }
}

// ==========================================
// INITIALIZATION
// ==========================================
document.addEventListener('DOMContentLoaded', async () => {
  setupEventListeners();
  await initSession();
  await loadCategories();
  await loadProducts();
  await refreshCart();
  updateWishlistUI();
  lucide.createIcons();
});

async function initSession() {
  try {
    if (!state.token) {
      // Auto-login as default customer demo
      await switchRole('customer', false);
    } else {
      const user = await api('/api/auth/me');
      state.currentUser = user;
      updateHeaderUserUI();
    }
  } catch (e) {
    console.warn('Session init failed, switching to customer demo:', e);
    await switchRole('customer', false);
  }
}

function updateHeaderUserUI() {
  if (!state.currentUser) return;
  const roleLabel = document.getElementById('active-role-label');
  if (roleLabel) {
    const formatted = state.currentUser.role.replace('_', ' ').toUpperCase();
    roleLabel.textContent = `${state.currentUser.first_name} (${formatted})`;
  }
  const greeting = document.getElementById('customer-greeting');
  if (greeting) {
    greeting.textContent = `Welcome, ${state.currentUser.first_name} ${state.currentUser.last_name}`;
  }
}

// ==========================================
// ROLE SWITCHING & AUTH
// ==========================================
async function switchRole(role, notify = true) {
  try {
    const res = await api(`/api/auth/switch-demo?role=${role}`, { 
      method: 'POST',
      body: JSON.stringify({ role })
    });
    if (res && res.access_token) {
      state.token = res.access_token;
      state.currentUser = res.user;
      localStorage.setItem('bazaarly_token', res.access_token);
      updateHeaderUserUI();
      
      const dropdown = document.getElementById('role-switcher-dropdown');
      if (dropdown) dropdown.classList.add('hidden');

      if (notify) {
        showToast(`Switched to ${role.replace('_', ' ').toUpperCase()} portal (${res.user.first_name})`, 'success');
      }

      // Navigate to matching portal
      if (role === 'customer') {
        navigateTo('storefront');
      } else if (role === 'seller') {
        navigateTo('seller-dashboard');
      } else if (role === 'admin') {
        navigateTo('admin-dashboard');
      } else if (role === 'super_admin') {
        navigateTo('super-admin-dashboard');
      }

      await refreshCart();
    }
  } catch (err) {
    showToast('Failed to switch role: ' + err.message, 'error');
  }
}

// ==========================================
// NAVIGATION & VIEW SWITCHING
// ==========================================
function navigateTo(viewName) {
  const views = [
    'storefront',
    'product-detail',
    'customer-dashboard',
    'seller-dashboard',
    'admin-dashboard',
    'super-admin-dashboard'
  ];

  views.forEach(v => {
    const el = document.getElementById(`view-${v}`);
    if (el) {
      if (v === viewName) {
        el.classList.remove('hidden');
      } else {
        el.classList.add('hidden');
      }
    }
  });

  state.activeView = viewName;
  window.scrollTo({ top: 0, behavior: 'smooth' });

  // Update navbar active states
  document.querySelectorAll('.nav-tab').forEach(tab => {
    if (tab.dataset.tab === viewName) {
      tab.classList.add('text-brand-600', 'font-bold');
      tab.classList.remove('text-slate-600');
    } else {
      tab.classList.remove('text-brand-600', 'font-bold');
      tab.classList.add('text-slate-600');
    }
  });

  // Specific view loaders
  if (viewName === 'customer-dashboard') {
    loadCustomerOrders();
  } else if (viewName === 'seller-dashboard') {
    loadSellerDashboard();
  } else if (viewName === 'admin-dashboard') {
    loadAdminDashboard();
  } else if (viewName === 'super-admin-dashboard') {
    loadSuperAdminDashboard();
  } else if (viewName === 'wishlist') {
    navigateTo('storefront');
    filterByWishlist();
  }

  setTimeout(() => lucide.createIcons(), 50);
}

function scrollToProducts() {
  const el = document.getElementById('products-catalog-section');
  if (el) el.scrollIntoView({ behavior: 'smooth' });
}

// ==========================================
// CATALOG & PRODUCT STOREFRONT
// ==========================================
async function loadCategories() {
  try {
    const categories = await api('/api/catalog/categories');
    state.categories = categories || [];

    // Render Pills
    const bar = document.getElementById('categories-bar');
    if (bar) {
      bar.innerHTML = state.categories.map(cat => `
        <button onclick="filterByCategory('${cat.slug}')" class="p-3 rounded-xl bg-white border border-slate-200 hover:border-brand-500 hover:shadow-xs transition text-left flex items-center space-x-3">
          <div class="w-9 h-9 rounded-lg bg-brand-50 text-brand-600 flex items-center justify-center font-bold text-sm">
            <i data-lucide="${getCategoryIcon(cat.slug)}" class="w-4 h-4"></i>
          </div>
          <div>
            <div class="font-bold text-xs text-slate-800">${cat.name}</div>
            <div class="text-[10px] text-slate-400 truncate max-w-[120px]">${cat.description || 'Explore products'}</div>
          </div>
        </button>
      `).join('');
    }

    // Render Sidebar filters
    const filterContainer = document.getElementById('filter-categories-container');
    if (filterContainer) {
      filterContainer.innerHTML = `
        <label class="flex items-center space-x-2 cursor-pointer">
          <input type="radio" name="dept_filter" value="" checked onchange="applyFilters()" class="text-brand-600 focus:ring-brand-500">
          <span>All Departments</span>
        </label>
        ${state.categories.map(c => `
          <label class="flex items-center space-x-2 cursor-pointer">
            <input type="radio" name="dept_filter" value="${c.slug}" onchange="applyFilters()" class="text-brand-600 focus:ring-brand-500">
            <span>${c.name}</span>
          </label>
        `).join('')}
      `;
    }

    lucide.createIcons();
  } catch (err) {
    console.error('Failed to load categories:', err);
  }
}

function getCategoryIcon(slug) {
  if (slug.includes('elect')) return 'cpu';
  if (slug.includes('fash')) return 'shirt';
  if (slug.includes('home')) return 'home';
  if (slug.includes('sport')) return 'activity';
  return 'tag';
}

async function loadProducts(params = {}, append = false) {
  try {
    if (!append) {
      state.catalogOffset = 0;
      state.catalogFilters = params;
      state.catalogHasMore = true;
      const grid = document.getElementById('products-grid');
      if (grid) grid.innerHTML = `<div class="col-span-full py-12 text-center text-slate-400 text-xs"><i data-lucide="loader" class="w-6 h-6 animate-spin mx-auto mb-2 text-brand-600"></i><span>Loading catalog collection...</span></div>`;
      lucide.createIcons();
    }

    const q = new URLSearchParams();
    if (state.catalogFilters.search) q.append('search', state.catalogFilters.search);
    if (state.catalogFilters.category_slug) q.append('category_slug', state.catalogFilters.category_slug);
    if (state.catalogFilters.min_price) q.append('min_price', state.catalogFilters.min_price);
    if (state.catalogFilters.max_price) q.append('max_price', state.catalogFilters.max_price);
    if (state.catalogFilters.in_stock) q.append('in_stock', 'true');
    if (state.catalogFilters.sort) q.append('sort', state.catalogFilters.sort);

    q.append('limit', state.catalogLimit || 20);
    q.append('offset', state.catalogOffset || 0);

    const items = await api(`/api/catalog/products?${q.toString()}`) || [];

    if (append) {
      state.products = state.products.concat(items);
      appendProductsToGrid(items);
    } else {
      state.products = items;
      renderProductsGrid(state.products);
    }

    // Determine if more products exist
    const seeMoreBtn = document.getElementById('btn-see-more');
    const allLoadedMsg = document.getElementById('all-products-loaded-msg');

    if (items.length < (state.catalogLimit || 20)) {
      state.catalogHasMore = false;
      if (seeMoreBtn) seeMoreBtn.classList.add('hidden');
      if (allLoadedMsg && state.products.length > 0) allLoadedMsg.classList.remove('hidden');
    } else {
      state.catalogHasMore = true;
      if (seeMoreBtn) seeMoreBtn.classList.remove('hidden');
      if (allLoadedMsg) allLoadedMsg.classList.add('hidden');
    }

    // Update count badges
    const countBadge = document.getElementById('products-count-badge');
    const seeMoreCurrent = document.getElementById('see-more-current');
    if (countBadge) countBadge.textContent = state.products.length;
    if (seeMoreCurrent) seeMoreCurrent.textContent = state.products.length;

    lucide.createIcons();
  } catch (err) {
    console.error('Failed to load products:', err);
  }
}

async function loadMoreProducts() {
  if (state.catalogLoading || !state.catalogHasMore) return;
  state.catalogLoading = true;

  const btn = document.getElementById('btn-see-more');
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = `<i data-lucide="loader" class="w-4 h-4 animate-spin text-brand-600"></i><span>Loading next 20 items...</span>`;
    lucide.createIcons();
  }

  state.catalogOffset += (state.catalogLimit || 20);
  await loadProducts(state.catalogFilters, true);

  if (btn) {
    btn.disabled = false;
    btn.innerHTML = `<i data-lucide="chevron-down" class="w-4 h-4 text-brand-600 group-hover:translate-y-0.5 transition"></i><span>See More Products (+20)</span>`;
    lucide.createIcons();
  }
  state.catalogLoading = false;
}

function renderProductCardHtml(p) {
  const isWishlisted = state.wishlist.includes(p.id);
  const hasDiscount = p.sale_price && p.sale_price < p.regular_price;
  const discountPct = hasDiscount ? Math.round(((p.regular_price - p.sale_price) / p.regular_price) * 100) : 0;
  const priceDisplay = hasDiscount 
    ? `<span class="text-base font-extrabold text-slate-900">$${p.sale_price.toFixed(2)}</span>
       <span class="text-xs text-slate-400 line-through">$${p.regular_price.toFixed(2)}</span>`
    : `<span class="text-base font-extrabold text-slate-900">$${p.regular_price.toFixed(2)}</span>`;

  const imgUrl = p.primary_image || 'https://images.unsplash.com/photo-1523275335684-37898b6baf30?auto=format&fit=crop&w=600&q=80';

  return `
    <div class="product-card bg-white rounded-2xl border border-slate-200 overflow-hidden shadow-xs hover:shadow-md transition flex flex-col justify-between group">
      
      <!-- Image & Badges -->
      <div class="relative bg-slate-100 aspect-square overflow-hidden cursor-pointer" onclick="viewProductDetails('${p.id}')">
        <img src="${imgUrl}" alt="${p.title}" class="w-full h-full object-cover group-hover:scale-105 transition duration-300">
        
        <div class="absolute top-2.5 left-2.5 flex flex-col gap-1">
          ${hasDiscount ? `<span class="px-2 py-0.5 rounded bg-rose-600 text-white text-[10px] font-bold shadow-xs">-${discountPct}% OFF</span>` : ''}
          ${p.in_stock ? `<span class="px-2 py-0.5 rounded bg-emerald-600 text-white text-[9px] font-bold shadow-xs">IN STOCK</span>` : `<span class="px-2 py-0.5 rounded bg-slate-800 text-white text-[9px] font-bold shadow-xs">OUT OF STOCK</span>`}
        </div>

        <button onclick="event.stopPropagation(); toggleWishlist('${p.id}')" class="absolute top-2.5 right-2.5 p-1.5 rounded-full bg-white/90 backdrop-blur-xs text-slate-600 hover:text-rose-600 transition shadow-xs">
          <i data-lucide="heart" class="w-4 h-4 ${isWishlisted ? 'fill-rose-500 text-rose-500' : ''}"></i>
        </button>
      </div>

      <!-- Product Details Content -->
      <div class="p-4 flex-1 flex flex-col justify-between space-y-3">
        <div class="space-y-1">
          <div class="flex items-center justify-between text-[10px] text-slate-400 uppercase tracking-wider font-semibold">
            <span>${p.brand_name || 'Verified Merchant'}</span>
            <span class="text-slate-500">${p.category_name || ''}</span>
          </div>
          
          <h4 class="font-bold text-xs text-slate-800 line-clamp-2 hover:text-brand-600 cursor-pointer" onclick="viewProductDetails('${p.id}')">
            ${p.title}
          </h4>

          <!-- Rating Stars -->
          <div class="flex items-center space-x-1 text-amber-500 text-[11px] pt-1">
            <div class="flex">${renderStarIcons(p.rating_average || 5)}</div>
            <span class="text-slate-400 text-[10px]">(${p.review_count || 1})</span>
          </div>
        </div>

        <!-- Price & Action -->
        <div class="pt-2 border-t border-slate-100 flex items-center justify-between">
          <div class="flex flex-col">
            <div class="flex items-baseline space-x-1.5">
              ${priceDisplay}
            </div>
            <span class="text-[10px] text-slate-400">by ${p.seller_store_name || 'Direct Merchant'}</span>
          </div>

          <button onclick="quickAddToCart('${p.id}')" class="px-3 py-1.5 rounded-lg bg-brand-600 hover:bg-brand-700 text-white text-xs font-semibold shadow-xs transition flex items-center space-x-1">
            <i data-lucide="shopping-cart" class="w-3.5 h-3.5"></i>
            <span>Add</span>
          </button>
        </div>

      </div>

    </div>
  `;
}

function appendProductsToGrid(newItems) {
  const grid = document.getElementById('products-grid');
  if (!grid) return;
  const html = newItems.map(p => renderProductCardHtml(p)).join('');
  grid.insertAdjacentHTML('beforeend', html);
  lucide.createIcons();
}

function renderProductsGrid(products) {
  const grid = document.getElementById('products-grid');
  if (!grid) return;

  if (products.length === 0) {
    grid.innerHTML = `
      <div class="col-span-full py-16 text-center bg-white rounded-2xl border border-slate-200">
        <i data-lucide="package-search" class="w-12 h-12 text-slate-300 mx-auto mb-3"></i>
        <h3 class="text-sm font-bold text-slate-700">No matching products found</h3>
        <p class="text-xs text-slate-400 mt-1">Try relaxing your filter criteria or search keyword.</p>
        <button onclick="resetFilters()" class="mt-4 px-4 py-2 rounded-lg bg-brand-600 text-white font-medium text-xs">Reset All Filters</button>
      </div>
    `;
    lucide.createIcons();
    return;
  }

  grid.innerHTML = products.map(p => renderProductCardHtml(p)).join('');
  lucide.createIcons();
}

  lucide.createIcons();
}

function renderStarIcons(rating) {
  const full = Math.floor(rating);
  let stars = '';
  for (let i = 0; i < 5; i++) {
    if (i < full) {
      stars += '<i data-lucide="star" class="w-3 h-3 fill-amber-400 text-amber-400"></i>';
    } else {
      stars += '<i data-lucide="star" class="w-3 h-3 text-slate-300"></i>';
    }
  }
  return stars;
}

function filterByCategory(slug) {
  navigateTo('storefront');
  const radios = document.getElementsByName('dept_filter');
  radios.forEach(r => {
    r.checked = (r.value === slug);
  });
  applyFilters();
}

function filterByWishlist() {
  const wishlisted = state.products.filter(p => state.wishlist.includes(p.id));
  renderProductsGrid(wishlisted);
  showToast(`Showing ${wishlisted.length} items from your wishlist`, 'info');
}

function applyFilters() {
  const search = document.getElementById('global-search-input')?.value.trim() || '';
  const radios = document.getElementsByName('dept_filter');
  let category_slug = '';
  radios.forEach(r => { if (r.checked) category_slug = r.value; });

  const min_price = document.getElementById('filter-min-price')?.value || '';
  const max_price = document.getElementById('filter-max-price')?.value || '';
  const in_stock = document.getElementById('filter-in-stock')?.checked || false;
  const sort = document.getElementById('sort-select')?.value || 'featured';

  loadProducts({ search, category_slug, min_price, max_price, in_stock, sort });
}

function resetFilters() {
  if (document.getElementById('global-search-input')) document.getElementById('global-search-input').value = '';
  if (document.getElementById('filter-min-price')) document.getElementById('filter-min-price').value = '';
  if (document.getElementById('filter-max-price')) document.getElementById('filter-max-price').value = '';
  if (document.getElementById('filter-in-stock')) document.getElementById('filter-in-stock').checked = false;
  if (document.getElementById('sort-select')) document.getElementById('sort-select').value = 'featured';

  const radios = document.getElementsByName('dept_filter');
  radios.forEach(r => { r.checked = (r.value === ''); });

  loadProducts();
}

// ==========================================
// PRODUCT DETAIL PAGE
// ==========================================
async function viewProductDetails(productId) {
  try {
    const product = await api(`/api/catalog/products/${productId}`);
    state.currentProduct = product;
    state.selectedVariant = product.variants && product.variants.length > 0 ? product.variants[0] : null;
    state.selectedQuantity = 1;

    const container = document.getElementById('product-detail-container');
    if (!container) return;

    const hasDiscount = product.sale_price && product.sale_price < product.regular_price;
    const discountPct = hasDiscount ? Math.round(((product.regular_price - product.sale_price) / product.regular_price) * 100) : 0;
    const currentPrice = state.selectedVariant ? state.selectedVariant.price : (product.sale_price || product.regular_price);
    const stockAvailable = state.selectedVariant ? state.selectedVariant.stock_quantity : product.stock_quantity;

    const images = (product.images && product.images.length > 0) 
      ? product.images 
      : [{ image_url: product.primary_image || 'https://images.unsplash.com/photo-1523275335684-37898b6baf30?auto=format&fit=crop&w=600&q=80' }];

    container.innerHTML = `
      <!-- Gallery Column -->
      <div class="space-y-4">
        <div class="aspect-square bg-slate-50 rounded-2xl border border-slate-200 overflow-hidden shadow-xs flex items-center justify-center relative">
          <img id="detail-main-image" src="${images[0].image_url}" class="w-full h-full object-cover">
          ${hasDiscount ? `<span class="absolute top-4 left-4 px-2.5 py-1 rounded bg-rose-600 text-white text-xs font-bold shadow-md">SAVE ${discountPct}%</span>` : ''}
        </div>
        
        <!-- Thumbnail strip -->
        ${images.length > 1 ? `
          <div class="flex items-center space-x-2 overflow-x-auto pb-2">
            ${images.map((img, idx) => `
              <button onclick="document.getElementById('detail-main-image').src='${img.image_url}'" class="w-16 h-16 rounded-xl border-2 border-slate-200 overflow-hidden focus:border-brand-600 shrink-0">
                <img src="${img.image_url}" class="w-full h-full object-cover">
              </button>
            `).join('')}
          </div>
        ` : ''}
      </div>

      <!-- Specs & Action Column -->
      <div class="space-y-6">
        <div>
          <div class="flex items-center space-x-2 text-xs text-slate-400 uppercase tracking-wider font-semibold">
            <span>${product.brand?.name || 'Exclusive'}</span>
            <span>•</span>
            <span class="text-brand-600 font-bold">${product.category?.name || 'Marketplace'}</span>
          </div>
          <h1 class="text-2xl font-extrabold text-slate-900 mt-1">${product.title}</h1>
          <div class="text-xs text-slate-400 font-mono mt-0.5">SKU: ${product.sku}</div>
        </div>

        <!-- Rating & Seller Bar -->
        <div class="flex flex-wrap items-center gap-4 py-2 border-y border-slate-100 text-xs">
          <div class="flex items-center space-x-1.5 text-amber-500">
            <div class="flex">${renderStarIcons(product.rating_average || 5)}</div>
            <span class="font-bold text-slate-700">${(product.rating_average || 5).toFixed(1)}</span>
            <span class="text-slate-400">(${product.reviews?.length || 0} customer reviews)</span>
          </div>
          <span class="text-slate-300">•</span>
          <div class="flex items-center space-x-1 text-slate-600">
            <i data-lucide="store" class="w-3.5 h-3.5 text-brand-600"></i>
            <span>Sold by <strong class="text-slate-800">${product.seller?.store_name || 'Independent Merchant'}</strong></span>
          </div>
        </div>

        <!-- Pricing Bar -->
        <div class="space-y-1">
          <div class="flex items-baseline space-x-3">
            <span class="text-3xl font-extrabold text-slate-900" id="detail-current-price">$${currentPrice.toFixed(2)}</span>
            ${hasDiscount ? `<span class="text-base text-slate-400 line-through">$${product.regular_price.toFixed(2)}</span>` : ''}
          </div>
          <div class="text-xs ${stockAvailable > 5 ? 'text-emerald-600' : 'text-rose-600'} font-semibold flex items-center space-x-1" id="detail-stock-badge">
            <i data-lucide="${stockAvailable > 0 ? 'check-circle' : 'alert-circle'}" class="w-3.5 h-3.5"></i>
            <span>${stockAvailable > 0 ? `In Stock (${stockAvailable} units ready to dispatch)` : 'Currently Out of Stock'}</span>
          </div>
        </div>

        <!-- Variants Selection -->
        ${product.variants && product.variants.length > 0 ? `
          <div class="space-y-2">
            <span class="text-xs font-bold text-slate-800 uppercase tracking-wider block">Select Configuration:</span>
            <div class="flex flex-wrap gap-2" id="detail-variants-container">
              ${product.variants.map((v, i) => `
                <button onclick="selectProductVariant('${v.id}')" id="variant-btn-${v.id}" class="variant-pill px-3 py-2 rounded-xl border text-xs font-semibold transition ${i === 0 ? 'border-brand-600 bg-brand-50 text-brand-700 shadow-xs' : 'border-slate-200 text-slate-700 hover:border-slate-300'}">
                  ${v.variant_name} — $${v.price.toFixed(2)}
                </button>
              `).join('')}
            </div>
          </div>
        ` : ''}

        <!-- Quantity & Order Buttons -->
        <div class="space-y-3 pt-2">
          <div class="flex items-center space-x-4">
            <span class="text-xs font-bold text-slate-800 uppercase tracking-wider">Quantity:</span>
            <div class="flex items-center border border-slate-200 rounded-xl overflow-hidden bg-slate-50">
              <button onclick="updateDetailQty(-1)" class="px-3 py-1.5 text-slate-600 hover:bg-slate-200 font-bold text-sm">-</button>
              <span id="detail-qty-val" class="px-4 py-1.5 text-xs font-bold text-slate-900 bg-white">1</span>
              <button onclick="updateDetailQty(1)" class="px-3 py-1.5 text-slate-600 hover:bg-slate-200 font-bold text-sm">+</button>
            </div>
          </div>

          <div class="grid grid-cols-2 gap-3 pt-2">
            <button onclick="addDetailToCart(false)" class="w-full py-3 rounded-xl bg-brand-600 hover:bg-brand-700 text-white font-bold text-xs shadow-md transition flex items-center justify-center space-x-2">
              <i data-lucide="shopping-cart" class="w-4 h-4"></i>
              <span>Add to Cart</span>
            </button>
            <button onclick="addDetailToCart(true)" class="w-full py-3 rounded-xl bg-slate-900 hover:bg-slate-800 text-white font-bold text-xs shadow-md transition flex items-center justify-center space-x-2">
              <i data-lucide="zap" class="w-4 h-4 text-amber-400"></i>
              <span>Buy Now</span>
            </button>
          </div>
        </div>

        <!-- Description Box -->
        <div class="space-y-2 pt-4 border-t border-slate-100">
          <span class="text-xs font-bold text-slate-800 uppercase tracking-wider block">Overview & Technical Specifications</span>
          <p class="text-xs text-slate-600 leading-relaxed whitespace-pre-line">${product.description || 'Full manufacturer warranty and certified high performance guarantee.'}</p>
        </div>

        <!-- Assurance Features -->
        <div class="grid grid-cols-2 gap-2 text-[11px] text-slate-500 pt-2">
          <div class="flex items-center space-x-1.5">
            <i data-lucide="truck" class="w-3.5 h-3.5 text-brand-600"></i>
            <span>Tracked Direct Delivery</span>
          </div>
          <div class="flex items-center space-x-1.5">
            <i data-lucide="refresh-cw" class="w-3.5 h-3.5 text-brand-600"></i>
            <span>30-Day Hassle-Free Returns</span>
          </div>
        </div>

      </div>
    `;

    // Render Reviews
    renderProductReviews(product.reviews || []);

    navigateTo('product-detail');
    lucide.createIcons();
  } catch (err) {
    showToast('Failed to load product details: ' + err.message, 'error');
  }
}

function selectProductVariant(variantId) {
  if (!state.currentProduct || !state.currentProduct.variants) return;
  const variant = state.currentProduct.variants.find(v => v.id === variantId);
  if (!variant) return;

  state.selectedVariant = variant;

  // Update UI Pills
  document.querySelectorAll('.variant-pill').forEach(btn => {
    btn.classList.remove('border-brand-600', 'bg-brand-50', 'text-brand-700', 'shadow-xs');
    btn.classList.add('border-slate-200', 'text-slate-700');
  });
  const activeBtn = document.getElementById(`variant-btn-${variant.id}`);
  if (activeBtn) {
    activeBtn.classList.add('border-brand-600', 'bg-brand-50', 'text-brand-700', 'shadow-xs');
  }

  // Update Price & Stock
  const priceEl = document.getElementById('detail-current-price');
  if (priceEl) priceEl.textContent = `$${variant.price.toFixed(2)}`;

  const stockBadge = document.getElementById('detail-stock-badge');
  if (stockBadge) {
    stockBadge.className = `text-xs ${variant.stock_quantity > 5 ? 'text-emerald-600' : 'text-rose-600'} font-semibold flex items-center space-x-1`;
    stockBadge.innerHTML = `
      <i data-lucide="${variant.stock_quantity > 0 ? 'check-circle' : 'alert-circle'}" class="w-3.5 h-3.5"></i>
      <span>${variant.stock_quantity > 0 ? `In Stock (${variant.stock_quantity} units ready to dispatch)` : 'Currently Out of Stock'}</span>
    `;
    lucide.createIcons();
  }
}

function updateDetailQty(delta) {
  let next = state.selectedQuantity + delta;
  const maxStock = state.selectedVariant ? state.selectedVariant.stock_quantity : (state.currentProduct ? state.currentProduct.stock_quantity : 99);
  if (next < 1) next = 1;
  if (next > maxStock) {
    next = maxStock;
    showToast(`Maximum available stock is ${maxStock} units`, 'warning');
  }
  state.selectedQuantity = next;
  const qtyEl = document.getElementById('detail-qty-val');
  if (qtyEl) qtyEl.textContent = state.selectedQuantity;
}

async function addDetailToCart(instantCheckout = false) {
  if (!state.currentProduct) return;
  const variantId = state.selectedVariant ? state.selectedVariant.id : null;
  const qty = state.selectedQuantity;

  try {
    await api('/api/cart/items', {
      method: 'POST',
      body: JSON.stringify({
        product_id: state.currentProduct.id,
        variant_id: variantId,
        quantity: qty
      })
    });

    await refreshCart();
    showToast(`Added ${qty} item(s) to cart`, 'success');

    if (instantCheckout) {
      openCheckoutModal();
    } else {
      openCartDrawer();
    }
  } catch (err) {
    showToast('Failed to add to cart: ' + err.message, 'error');
  }
}

async function quickAddToCart(productId) {
  try {
    await api('/api/cart/items', {
      method: 'POST',
      body: JSON.stringify({
        product_id: productId,
        quantity: 1
      })
    });
    await refreshCart();
    showToast('Product added to shopping cart', 'success');
  } catch (err) {
    showToast('Failed to add to cart: ' + err.message, 'error');
  }
}

function renderProductReviews(reviews) {
  const container = document.getElementById('product-reviews-list');
  if (!container) return;

  if (reviews.length === 0) {
    container.innerHTML = `
      <div class="py-6 text-center text-slate-400 text-xs">
        No customer reviews written yet for this item. Be the first to leave one!
      </div>
    `;
    return;
  }

  container.innerHTML = reviews.map(r => `
    <div class="p-4 rounded-xl border border-slate-100 bg-slate-50 space-y-2">
      <div class="flex items-center justify-between text-xs">
        <div class="flex items-center space-x-2">
          <div class="w-6 h-6 rounded-full bg-brand-100 text-brand-700 flex items-center justify-center font-bold text-[10px]">
            ${r.user_name ? r.user_name.charAt(0) : 'U'}
          </div>
          <span class="font-bold text-slate-800">${r.user_name || 'Verified Buyer'}</span>
          <span class="text-[10px] text-emerald-600 bg-emerald-50 px-1.5 py-0.5 rounded font-semibold border border-emerald-200">Verified Purchase</span>
        </div>
        <span class="text-[10px] text-slate-400 font-mono">${new Date(r.created_at).toLocaleDateString()}</span>
      </div>

      <div class="flex items-center space-x-1 text-amber-500">
        <div class="flex">${renderStarIcons(r.rating)}</div>
        <span class="font-bold text-slate-900 text-xs">${r.title}</span>
      </div>

      <p class="text-xs text-slate-600 leading-relaxed">${r.comment || ''}</p>
    </div>
  `).join('');

  lucide.createIcons();
}

// ==========================================
// WISHLIST FUNCTIONALITY
// ==========================================
async function toggleWishlist(productId) {
  const idx = state.wishlist.indexOf(productId);
  if (idx >= 0) {
    state.wishlist.splice(idx, 1);
    showToast('Removed from wishlist', 'info');
  } else {
    state.wishlist.push(productId);
    showToast('Saved to your wishlist', 'success');
  }
  localStorage.setItem('bazaarly_wishlist', JSON.stringify(state.wishlist));
  updateWishlistUI();
  
  if (state.activeView === 'storefront') {
    renderProductsGrid(state.products);
  }
}

function updateWishlistUI() {
  const badge = document.getElementById('wishlist-badge');
  const kpi = document.getElementById('cust-kpi-wishlist');
  const count = state.wishlist.length;

  if (badge) {
    if (count > 0) {
      badge.textContent = count;
      badge.classList.remove('hidden');
    } else {
      badge.classList.add('hidden');
    }
  }
  if (kpi) kpi.textContent = count;
}

// ==========================================
// SHOPPING CART DRAWER
// ==========================================
async function refreshCart() {
  try {
    const cart = await api('/api/cart');
    state.cart = cart || {
      items: [],
      subtotal: 0,
      discount_amount: 0,
      shipping_fee: 0,
      grand_total: 0
    };

    // Update Header Count
    const countEl = document.getElementById('header-cart-count');
    const totalQty = state.cart.items.reduce((acc, item) => acc + item.quantity, 0);
    if (countEl) countEl.textContent = totalQty;

    // Render Drawer items
    renderCartDrawer();
  } catch (err) {
    console.error('Failed to refresh cart:', err);
  }
}

function renderCartDrawer() {
  const itemsContainer = document.getElementById('cart-drawer-items');
  const subtotalEl = document.getElementById('cart-subtotal');
  const discountEl = document.getElementById('cart-discount');
  const discountRow = document.getElementById('cart-discount-row');
  const shippingEl = document.getElementById('cart-shipping');
  const grandTotalEl = document.getElementById('cart-grand-total');

  if (!itemsContainer) return;

  if (state.cart.items.length === 0) {
    itemsContainer.innerHTML = `
      <div class="py-16 text-center text-slate-400 space-y-3">
        <i data-lucide="shopping-cart" class="w-12 h-12 mx-auto text-slate-300"></i>
        <p class="text-xs">Your shopping cart is currently empty.</p>
        <button onclick="closeCartDrawer(); navigateTo('storefront')" class="px-4 py-2 rounded-lg bg-brand-600 text-white font-semibold text-xs">
          Discover Products
        </button>
      </div>
    `;
  } else {
    itemsContainer.innerHTML = state.cart.items.map(item => {
      const img = item.product?.primary_image || 'https://images.unsplash.com/photo-1523275335684-37898b6baf30?auto=format&fit=crop&w=120&q=80';
      const variantText = item.variant ? `<span class="text-[10px] text-brand-600 font-semibold block">${item.variant.variant_name}</span>` : '';

      return `
        <div class="flex items-center space-x-3 p-3 rounded-xl border border-slate-100 bg-slate-50/60">
          <img src="${img}" class="w-14 h-14 rounded-lg object-cover border border-slate-200">
          <div class="flex-1 min-w-0">
            <h5 class="text-xs font-bold text-slate-800 truncate">${item.product?.title || 'Product'}</h5>
            ${variantText}
            <div class="text-xs font-extrabold text-slate-900 mt-1">$${item.unit_price.toFixed(2)}</div>
          </div>
          <div class="flex flex-col items-end space-y-2">
            <button onclick="removeCartItem('${item.id}')" class="text-slate-400 hover:text-rose-600 transition" title="Remove item">
              <i data-lucide="trash-2" class="w-3.5 h-3.5"></i>
            </button>
            <div class="flex items-center border border-slate-200 rounded-lg bg-white overflow-hidden text-xs">
              <button onclick="updateCartItemQty('${item.id}', ${item.quantity - 1})" class="px-2 py-0.5 text-slate-600 hover:bg-slate-100">-</button>
              <span class="px-2 font-bold">${item.quantity}</span>
              <button onclick="updateCartItemQty('${item.id}', ${item.quantity + 1})" class="px-2 py-0.5 text-slate-600 hover:bg-slate-100">+</button>
            </div>
          </div>
        </div>
      `;
    }).join('');
  }

  if (subtotalEl) subtotalEl.textContent = `$${state.cart.subtotal.toFixed(2)}`;
  if (shippingEl) shippingEl.textContent = state.cart.shipping_fee === 0 ? 'FREE' : `$${state.cart.shipping_fee.toFixed(2)}`;
  if (discountEl) discountEl.textContent = `-$${state.cart.discount_amount.toFixed(2)}`;
  if (grandTotalEl) grandTotalEl.textContent = `$${state.cart.grand_total.toFixed(2)}`;

  if (discountRow) {
    if (state.cart.discount_amount > 0) {
      discountRow.classList.remove('hidden');
    } else {
      discountRow.classList.add('hidden');
    }
  }

  lucide.createIcons();
}

async function updateCartItemQty(itemId, newQty) {
  try {
    if (newQty <= 0) {
      await removeCartItem(itemId);
      return;
    }
    await api(`/api/cart/items/${itemId}`, {
      method: 'PUT',
      body: JSON.stringify({ quantity: newQty })
    });
    await refreshCart();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

async function removeCartItem(itemId) {
  try {
    await api(`/api/cart/items/${itemId}`, { method: 'DELETE' });
    await refreshCart();
    showToast('Item removed from cart', 'info');
  } catch (err) {
    showToast(err.message, 'error');
  }
}

async function applyCartCoupon() {
  const input = document.getElementById('cart-coupon-input');
  const code = input?.value.trim().toUpperCase();
  if (!code) return;

  try {
    await api('/api/cart/coupon', {
      method: 'POST',
      body: JSON.stringify({ coupon_code: code })
    });
    await refreshCart();
    showToast(`Coupon ${code} applied successfully!`, 'success');
  } catch (err) {
    showToast('Invalid or expired coupon: ' + err.message, 'error');
  }
}

function openCartDrawer() {
  const drawer = document.getElementById('cart-drawer-backdrop');
  if (drawer) drawer.classList.remove('hidden');
}

function closeCartDrawer() {
  const drawer = document.getElementById('cart-drawer-backdrop');
  if (drawer) drawer.classList.add('hidden');
}

// ==========================================
// MULTI-STEP CHECKOUT
// ==========================================
function openCheckoutModal() {
  if (state.cart.items.length === 0) {
    showToast('Your shopping cart is empty', 'warning');
    return;
  }
  closeCartDrawer();

  // Populate default address if user is logged in
  if (state.currentUser) {
    const nameEl = document.getElementById('chk-name');
    const phoneEl = document.getElementById('chk-phone');
    if (nameEl && !nameEl.value) nameEl.value = `${state.currentUser.first_name} ${state.currentUser.last_name}`;
    if (phoneEl && !phoneEl.value) phoneEl.value = '+1 (555) 321-7890';
  }

  const finalAmount = document.getElementById('checkout-final-amount');
  if (finalAmount) finalAmount.textContent = `$${state.cart.grand_total.toFixed(2)}`;

  const modal = document.getElementById('modal-checkout');
  if (modal) modal.classList.remove('hidden');
  lucide.createIcons();
}

function closeCheckoutModal() {
  const modal = document.getElementById('modal-checkout');
  if (modal) modal.classList.add('hidden');
}

async function submitCheckoutOrder(e) {
  e.preventDefault();

  const fullName = document.getElementById('chk-name')?.value.trim();
  const phone = document.getElementById('chk-phone')?.value.trim();
  const addressLine1 = document.getElementById('chk-addr1')?.value.trim();
  const city = document.getElementById('chk-city')?.value.trim();
  const stateVal = document.getElementById('chk-state')?.value.trim();
  const zip = document.getElementById('chk-zip')?.value.trim();

  if (!fullName || !addressLine1 || !city) {
    showToast('Please provide your full shipping address and recipient details', 'warning');
    return;
  }

  const paymentMethod = document.querySelector('input[name="payment_method"]:checked')?.value || 'stripe';

  const payload = {
    shipping_address: {
      full_name: fullName,
      phone: phone || '+1-555-0199',
      address_line1: addressLine1,
      city: city,
      state: stateVal || 'CA',
      postal_code: zip || '90210',
      country: 'United States'
    },
    payment_method: paymentMethod,
    coupon_code: state.cart.coupon_code
  };

  const submitBtn = document.getElementById('btn-submit-order');
  if (submitBtn) {
    submitBtn.disabled = true;
    submitBtn.innerHTML = `<i data-lucide="loader" class="w-4 h-4 animate-spin inline-block mr-1"></i> Processing Order...`;
  }

  try {
    const orderResult = await api('/api/checkout', {
      method: 'POST',
      body: JSON.stringify(payload)
    });

    state.lastCompletedOrder = orderResult;
    closeCheckoutModal();

    // Populate order success modal
    document.getElementById('success-order-number').textContent = orderResult.order_number;
    document.getElementById('success-tracking-number').textContent = orderResult.tracking_number;
    document.getElementById('success-total-charged').textContent = `$${orderResult.total_amount.toFixed(2)} (${orderResult.payment_method.toUpperCase()})`;

    const successModal = document.getElementById('modal-order-success');
    if (successModal) successModal.classList.remove('hidden');

    await refreshCart();
    lucide.createIcons();
  } catch (err) {
    showToast('Checkout transaction failed: ' + err.message, 'error');
  } finally {
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.innerHTML = `Confirm & Place Multi-Vendor Order`;
    }
  }
}

function viewCustomerOrders() {
  const successModal = document.getElementById('modal-order-success');
  if (successModal) successModal.classList.add('hidden');
  navigateTo('customer-dashboard');
}

// ==========================================
// CUSTOMER DASHBOARD & ORDERS
// ==========================================
async function loadCustomerOrders() {
  try {
    const orders = await api('/api/orders');
    const container = document.getElementById('customer-orders-container');
    const kpiTotal = document.getElementById('cust-kpi-total-orders');
    const kpiActive = document.getElementById('cust-kpi-active-orders');

    if (kpiTotal) kpiTotal.textContent = orders.length;
    if (kpiActive) {
      const activeCount = orders.filter(o => ['pending', 'processing', 'packed', 'shipped'].includes(o.status)).length;
      kpiActive.textContent = activeCount;
    }

    if (!container) return;

    if (orders.length === 0) {
      container.innerHTML = `
        <div class="py-12 text-center text-slate-400 space-y-2">
          <i data-lucide="package-open" class="w-12 h-12 mx-auto text-slate-300"></i>
          <h4 class="text-sm font-bold text-slate-700">No orders placed yet</h4>
          <p class="text-xs">Browse the catalog to place your first direct merchant order.</p>
        </div>
      `;
      lucide.createIcons();
      return;
    }

    container.innerHTML = orders.map(ord => {
      const statusBadge = getStatusBadge(ord.status);
      const isCancellable = ['pending', 'processing'].includes(ord.status);

      return `
        <div class="rounded-2xl border border-slate-200 bg-white p-5 space-y-4 shadow-xs">
          
          <div class="flex flex-col sm:flex-row sm:items-center justify-between pb-3 border-b border-slate-100 gap-2">
            <div>
              <div class="flex items-center space-x-2">
                <span class="font-mono font-bold text-slate-900 text-sm">#${ord.order_number}</span>
                ${statusBadge}
              </div>
              <span class="text-[11px] text-slate-400 font-mono">Placed on ${new Date(ord.created_at).toLocaleString()}</span>
            </div>
            <div class="flex items-center space-x-2">
              <button onclick="renderPrintableInvoice('${ord.id}')" class="px-3 py-1.5 rounded-lg border border-slate-200 bg-slate-50 hover:bg-slate-100 text-slate-700 text-xs font-semibold flex items-center space-x-1">
                <i data-lucide="printer" class="w-3.5 h-3.5 text-slate-500"></i>
                <span>Invoice</span>
              </button>
              ${isCancellable ? `
                <button onclick="cancelCustomerOrder('${ord.id}')" class="px-3 py-1.5 rounded-lg border border-rose-200 bg-rose-50 hover:bg-rose-100 text-rose-700 text-xs font-semibold">
                  Cancel Order
                </button>
              ` : ''}
            </div>
          </div>

          <!-- Merchant Suborders Breakdown -->
          <div class="space-y-3">
            <span class="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">Merchant Shipments Breakdown</span>
            ${(ord.seller_orders || []).map(so => `
              <div class="p-3 rounded-xl bg-slate-50 border border-slate-100 flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-xs">
                <div class="flex items-center space-x-2">
                  <i data-lucide="store" class="w-4 h-4 text-brand-600"></i>
                  <div>
                    <span class="font-bold text-slate-800">${so.store_name}</span>
                    <span class="text-[10px] text-slate-400 block font-mono">Suborder: ${so.seller_order_number}</span>
                  </div>
                </div>
                <div class="flex items-center space-x-3">
                  <span class="font-mono text-slate-500">Track: <strong class="text-slate-800">${so.tracking_number || ord.tracking_number}</strong></span>
                  ${getStatusBadge(so.status)}
                </div>
              </div>
            `).join('')}
          </div>

          <!-- Items Row -->
          <div class="space-y-2 pt-1">
            ${(ord.items || []).map(item => `
              <div class="flex items-center justify-between text-xs py-1">
                <div class="flex items-center space-x-2">
                  <span class="font-bold text-slate-800">${item.title}</span>
                  ${item.variant_name ? `<span class="text-[10px] text-brand-600 bg-brand-50 px-1.5 py-0.5 rounded font-mono">${item.variant_name}</span>` : ''}
                  <span class="text-slate-400 font-mono">× ${item.quantity}</span>
                </div>
                <span class="font-extrabold text-slate-900">$${item.total_price.toFixed(2)}</span>
              </div>
            `).join('')}
          </div>

          <!-- Total Footer -->
          <div class="pt-3 border-t border-slate-100 flex items-center justify-between text-xs">
            <span class="text-slate-500">Payment Method: <strong class="text-slate-800 uppercase font-mono">${ord.payment_method}</strong></span>
            <div class="text-sm font-extrabold text-slate-900">
              Total: <span class="text-brand-600">$${ord.total_amount.toFixed(2)}</span>
            </div>
          </div>

        </div>
      `;
    }).join('');

    lucide.createIcons();
  } catch (err) {
    console.error('Failed to load customer orders:', err);
  }
}

async function cancelCustomerOrder(orderId) {
  if (!confirm('Are you sure you want to cancel this order? Stock will be automatically restocked.')) return;
  try {
    await api(`/api/orders/${orderId}/cancel`, { method: 'POST' });
    showToast('Order successfully cancelled', 'info');
    await loadCustomerOrders();
  } catch (err) {
    showToast('Failed to cancel order: ' + err.message, 'error');
  }
}

// ==========================================
// SELLER DASHBOARD
// ==========================================
async function loadSellerDashboard() {
  try {
    const data = await api('/api/seller/dashboard');
    if (!data) return;

    // Header info
    const storeName = data.seller_profile?.store_name || data.store_name || 'Merchant Dashboard';
    if (document.getElementById('seller-store-name')) document.getElementById('seller-store-name').textContent = storeName;
    
    const rev = data.metrics?.total_revenue || data.metrics?.gross_revenue || 0;
    const bal = data.metrics?.available_balance || 0;
    const pending = data.metrics?.pending_fulfillment || data.metrics?.pending_orders || 0;
    const lowStock = data.metrics?.low_stock_count || 0;

    if (document.getElementById('seller-kpi-revenue')) document.getElementById('seller-kpi-revenue').textContent = `$${rev.toFixed(2)}`;
    if (document.getElementById('seller-kpi-balance')) document.getElementById('seller-kpi-balance').textContent = `$${bal.toFixed(2)}`;
    if (document.getElementById('seller-kpi-pending-orders')) document.getElementById('seller-kpi-pending-orders').textContent = pending;
    if (document.getElementById('seller-kpi-low-stock')) document.getElementById('seller-kpi-low-stock').textContent = lowStock;

    // Chart.js Revenue Chart
    initSellerChart(data.monthly_chart || data.monthly_revenue || []);

    // Load Seller Orders
    await loadSellerOrders();

    // Load Seller Products
    await loadSellerProducts();

    lucide.createIcons();
  } catch (err) {
    console.error('Failed to load seller dashboard:', err);
  }
}

function initSellerChart(monthlyData) {
  const canvas = document.getElementById('seller-revenue-chart');
  if (!canvas) return;

  if (state.sellerChart) {
    state.sellerChart.destroy();
  }

  const labels = monthlyData.map(d => d.month);
  const revenues = monthlyData.map(d => d.revenue);

  state.sellerChart = new Chart(canvas, {
    type: 'line',
    data: {
      labels: labels.length ? labels : ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun'],
      datasets: [{
        label: 'Merchant Monthly Net Earnings ($)',
        data: revenues.length ? revenues : [1200, 1900, 3000, 5200, 4800, 7500],
        borderColor: '#2563eb',
        backgroundColor: 'rgba(37, 99, 235, 0.08)',
        fill: true,
        tension: 0.35,
        borderWidth: 2.5,
        pointBackgroundColor: '#2563eb',
        pointRadius: 4
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false }
      },
      scales: {
        y: {
          beginAtZero: true,
          grid: { color: '#f1f5f9' },
          ticks: { font: { family: 'Inter', size: 10 } }
        },
        x: {
          grid: { display: false },
          ticks: { font: { family: 'Inter', size: 10 } }
        }
      }
    }
  });
}

async function loadSellerOrders() {
  try {
    const orders = await api('/api/seller/orders');
    const tbody = document.getElementById('seller-orders-table-body');
    if (!tbody) return;

    if (orders.length === 0) {
      tbody.innerHTML = `<tr><td colspan="7" class="text-center py-6 text-slate-400">No vendor suborders dispatched yet.</td></tr>`;
      return;
    }

    tbody.innerHTML = orders.map(so => {
      const orderNum = so.suborder_number || so.seller_order_number || so.id;
      const earnings = so.seller_earnings !== undefined ? so.seller_earnings : (so.net_payout || 0);

      return `
      <tr class="hover:bg-slate-50 transition">
        <td class="py-3 px-4 font-mono font-bold text-slate-900">${orderNum}</td>
        <td class="py-3 px-3 text-slate-500 font-mono">${new Date(so.created_at).toLocaleDateString()}</td>
        <td class="py-3 px-3 font-medium text-slate-800">${so.customer_name || 'Verified Customer'}</td>
        <td class="py-3 px-3">${so.items?.length || 1} items</td>
        <td class="py-3 px-3 text-right font-extrabold text-slate-900">$${earnings.toFixed(2)}</td>
        <td class="py-3 px-3">${getStatusBadge(so.status)}</td>
        <td class="py-3 px-3 text-center">
          <select onchange="updateSellerOrderStatus('${so.id}', this.value)" class="bg-slate-50 border border-slate-200 rounded-lg px-2 py-1 text-slate-700 text-xs focus:outline-none focus:border-brand-500">
            <option value="confirmed" ${so.status === 'confirmed' ? 'selected' : ''}>Confirmed</option>
            <option value="processing" ${so.status === 'processing' ? 'selected' : ''}>Processing</option>
            <option value="packed" ${so.status === 'packed' ? 'selected' : ''}>Packed</option>
            <option value="shipped" ${so.status === 'shipped' ? 'selected' : ''}>Shipped</option>
            <option value="delivered" ${so.status === 'delivered' ? 'selected' : ''}>Delivered</option>
          </select>
        </td>
      </tr>
      `;
    }).join('');
  } catch (err) {
    console.error('Failed to load seller orders:', err);
  }
}

async function updateSellerOrderStatus(suborderId, status) {
  try {
    await api(`/api/seller/orders/${suborderId}/status`, {
      method: 'PUT',
      body: JSON.stringify({ status })
    });
    showToast(`Suborder status updated to ${status.toUpperCase()}`, 'success');
    await loadSellerOrders();
  } catch (err) {
    showToast('Failed to update status: ' + err.message, 'error');
  }
}

async function loadSellerProducts() {
  try {
    const products = await api('/api/seller/products');
    const tbody = document.getElementById('seller-products-table-body');
    if (!tbody) return;

    if (products.length === 0) {
      tbody.innerHTML = `<tr><td colspan="7" class="text-center py-6 text-slate-400">No products published in catalog. Click "Add New Product" to list inventory.</td></tr>`;
      return;
    }

    tbody.innerHTML = products.map(p => `
      <tr class="hover:bg-slate-50 transition">
        <td class="py-3 px-4 font-bold text-slate-800 flex items-center space-x-2">
          <img src="${p.primary_image || 'https://images.unsplash.com/photo-1523275335684-37898b6baf30?auto=format&fit=crop&w=60&q=80'}" class="w-8 h-8 rounded object-cover border border-slate-200">
          <span class="truncate max-w-xs">${p.title}</span>
        </td>
        <td class="py-3 px-3 font-mono text-slate-500">${p.sku}</td>
        <td class="py-3 px-3 text-right text-slate-400 line-through">$${p.regular_price.toFixed(2)}</td>
        <td class="py-3 px-3 text-right font-extrabold text-slate-900">$${(p.sale_price || p.regular_price).toFixed(2)}</td>
        <td class="py-3 px-3 text-center font-bold ${p.stock_quantity < 5 ? 'text-rose-600' : 'text-slate-700'}">${p.stock_quantity}</td>
        <td class="py-3 px-3 text-center">
          <span class="px-2 py-0.5 rounded text-[10px] font-bold ${p.status === 'published' ? 'bg-emerald-50 text-emerald-700 border border-emerald-200' : 'bg-slate-100 text-slate-700'}">
            ${p.status.toUpperCase()}
          </span>
        </td>
        <td class="py-3 px-3 text-center">
          <button onclick="deleteSellerProduct('${p.id}')" class="p-1 rounded text-slate-400 hover:text-rose-600 transition" title="Archive product">
            <i data-lucide="trash-2" class="w-4 h-4"></i>
          </button>
        </td>
      </tr>
    `).join('');

    lucide.createIcons();
  } catch (err) {
    console.error('Failed to load seller products:', err);
  }
}

async function deleteSellerProduct(productId) {
  if (!confirm('Are you sure you want to remove this product from your inventory?')) return;
  try {
    await api(`/api/seller/products/${productId}`, { method: 'DELETE' });
    showToast('Product archived successfully', 'info');
    await loadSellerProducts();
    await loadProducts();
  } catch (err) {
    showToast('Failed to delete product: ' + err.message, 'error');
  }
}

function openAddProductModal() {
  document.getElementById('modal-add-product')?.classList.remove('hidden');
}
function closeAddProductModal() {
  document.getElementById('modal-add-product')?.classList.add('hidden');
}

async function submitNewProduct(e) {
  e.preventDefault();
  const title = document.getElementById('new-prod-title')?.value.trim();
  const category_id = document.getElementById('new-prod-cat')?.value;
  const sku = document.getElementById('new-prod-sku')?.value.trim();
  const regular_price = parseFloat(document.getElementById('new-prod-regular-price')?.value);
  const sale_price = parseFloat(document.getElementById('new-prod-sale-price')?.value);
  const stock_quantity = parseInt(document.getElementById('new-prod-stock')?.value);
  const primary_image = document.getElementById('new-prod-image')?.value.trim();
  const description = document.getElementById('new-prod-desc')?.value.trim();

  const payload = {
    title,
    category_id,
    sku,
    regular_price,
    sale_price: sale_price || regular_price,
    stock_quantity,
    primary_image: primary_image || 'https://images.unsplash.com/photo-1546868871-7041f2a55e12?auto=format&fit=crop&w=600&q=80',
    description
  };

  try {
    await api('/api/seller/products', {
      method: 'POST',
      body: JSON.stringify(payload)
    });

    showToast('Product published to marketplace!', 'success');
    closeAddProductModal();
    document.getElementById('add-product-form')?.reset();
    await loadSellerProducts();
    await loadProducts();
  } catch (err) {
    showToast('Failed to add product: ' + err.message, 'error');
  }
}

function openAddressModal() {
  openCheckoutModal();
  document.getElementById('checkout-new-address-section')?.scrollIntoView({ behavior: 'smooth' });
}

function openNewAdminModal() {
  const email = prompt('Enter the email address for the new Operations Administrator:');
  if (!email) return;
  const firstName = prompt('Enter Admin First Name:') || 'Staff';
  const lastName = prompt('Enter Admin Last Name:') || 'Admin';

  api('/api/super-admin/admins', {
    method: 'POST',
    body: JSON.stringify({
      email,
      password: 'password123',
      first_name: firstName,
      last_name: lastName,
      role: 'admin'
    })
  }).then(() => {
    showToast(`Administrator account created for ${email}`, 'success');
    loadSuperAdminDashboard();
  }).catch(err => {
    showToast('Failed to create admin: ' + err.message, 'error');
  });
}

function openPayoutModal() {
  document.getElementById('modal-payout')?.classList.remove('hidden');
}

function closePayoutModal() {
  document.getElementById('modal-payout')?.classList.add('hidden');
}

async function submitPayout(e) {
  e.preventDefault();
  const amount = parseFloat(document.getElementById('payout-amount')?.value);
  const bank = document.getElementById('payout-bank')?.value.trim();
  const notes = document.getElementById('payout-notes')?.value.trim();

  try {
    await api('/api/seller/payouts', {
      method: 'POST',
      body: JSON.stringify({ amount, bank_info: bank, notes })
    });
    showToast('Payout withdrawal request submitted successfully', 'success');
    closePayoutModal();
    await loadSellerDashboard();
  } catch (err) {
    showToast('Payout failed: ' + err.message, 'error');
  }
}

// ==========================================
// ADMIN OPERATIONS CONSOLE
// ==========================================
async function loadAdminDashboard() {
  try {
    const metrics = await api('/api/admin/metrics');
    if (!metrics) return;

    document.getElementById('adm-kpi-gmv').textContent = `$${metrics.gross_merchandise_value.toFixed(2)}`;
    document.getElementById('adm-kpi-commission').textContent = `$${metrics.platform_commission.toFixed(2)}`;
    document.getElementById('adm-kpi-sellers').textContent = metrics.active_sellers_count;
    document.getElementById('adm-kpi-pending-approvals').textContent = metrics.pending_seller_count;

    // Load Pending Sellers
    const sellers = await api('/api/admin/sellers');
    const pendingList = document.getElementById('admin-pending-sellers-list');
    if (pendingList) {
      const pendingSellers = sellers.filter(s => s.approval_status === 'pending');
      if (pendingSellers.length === 0) {
        pendingList.innerHTML = `<div class="p-4 rounded-xl bg-slate-50 text-slate-400 text-xs text-center">No pending merchant applications at this time. All stores verified!</div>`;
      } else {
        pendingList.innerHTML = pendingSellers.map(s => `
          <div class="p-4 rounded-xl border border-amber-200 bg-amber-50/40 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs">
            <div class="space-y-0.5">
              <div class="flex items-center space-x-2">
                <span class="font-bold text-slate-900">${s.store_name}</span>
                <span class="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-100 text-amber-800">PENDING REVIEW</span>
              </div>
              <p class="text-slate-600">${s.business_description || 'Independent retail distributor'}</p>
              <span class="text-[10px] text-slate-400 font-mono">Contact: ${s.user_email || 'vendor@bazaarly.com'}</span>
            </div>
            <div class="flex items-center space-x-2">
              <button onclick="approveSeller('${s.id}')" class="px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white font-semibold shadow-xs">Approve Merchant</button>
              <button onclick="rejectSeller('${s.id}')" class="px-3 py-1.5 rounded-lg bg-rose-600 hover:bg-rose-700 text-white font-semibold shadow-xs">Reject</button>
            </div>
          </div>
        `).join('');
      }
    }

    // Load Admin Products Table
    const products = await api('/api/admin/products');
    const prodTable = document.getElementById('admin-products-table-body');
    if (prodTable) {
      prodTable.innerHTML = products.map(p => `
        <tr class="hover:bg-slate-50 transition">
          <td class="py-3 px-4 font-bold text-slate-800">${p.title}</td>
          <td class="py-3 px-3 text-slate-600">${p.seller_store_name || 'Merchant'}</td>
          <td class="py-3 px-3 text-slate-500">${p.category_name || 'Category'}</td>
          <td class="py-3 px-3 text-right font-extrabold text-slate-900">$${p.regular_price.toFixed(2)}</td>
          <td class="py-3 px-3 text-center">
            <span class="px-2 py-0.5 rounded text-[10px] font-bold ${p.status === 'published' ? 'bg-emerald-50 text-emerald-700 border border-emerald-200' : 'bg-amber-50 text-amber-700'}">
              ${p.status.toUpperCase()}
            </span>
          </td>
          <td class="py-3 px-3 text-center">
            <button onclick="toggleProductApproval('${p.id}', '${p.status === 'published' ? 'archived' : 'published'}')" class="px-2.5 py-1 rounded bg-slate-100 hover:bg-slate-200 text-slate-700 font-semibold text-[11px]">
              ${p.status === 'published' ? 'Delist' : 'Approve'}
            </button>
          </td>
        </tr>
      `).join('');
    }

    // Load Admin Orders Table
    const orders = await api('/api/admin/orders');
    const orderTable = document.getElementById('admin-orders-table-body');
    if (orderTable) {
      orderTable.innerHTML = orders.map(o => `
        <tr class="hover:bg-slate-50 transition">
          <td class="py-3 px-4 font-mono font-bold text-slate-900">#${o.order_number}</td>
          <td class="py-3 px-3 text-slate-700">${o.customer_name || 'Customer'}</td>
          <td class="py-3 px-3 text-slate-500 font-mono">${new Date(o.created_at).toLocaleDateString()}</td>
          <td class="py-3 px-3 text-right font-extrabold text-slate-900">$${o.total_amount.toFixed(2)}</td>
          <td class="py-3 px-3 uppercase font-mono text-[11px] text-slate-600">${o.payment_method}</td>
          <td class="py-3 px-3">${getStatusBadge(o.status)}</td>
          <td class="py-3 px-3 text-center">
            ${o.status !== 'refunded' ? `
              <button onclick="adminRefundOrder('${o.id}')" class="px-2.5 py-1 rounded bg-rose-50 hover:bg-rose-100 text-rose-700 border border-rose-200 font-semibold text-[11px]">
                Dispute Refund
              </button>
            ` : `<span class="text-[10px] text-slate-400">Refunded</span>`}
          </td>
        </tr>
      `).join('');
    }

    lucide.createIcons();
  } catch (err) {
    console.error('Failed to load admin dashboard:', err);
  }
}

async function approveSeller(sellerId) {
  try {
    await api(`/api/admin/sellers/${sellerId}/approve`, { method: 'POST' });
    showToast('Merchant approved for marketplace fulfillment', 'success');
    await loadAdminDashboard();
  } catch (err) {
    showToast('Approval failed: ' + err.message, 'error');
  }
}

async function rejectSeller(sellerId) {
  if (!confirm('Reject this seller onboarding request?')) return;
  try {
    await api(`/api/admin/sellers/${sellerId}/reject`, { method: 'POST' });
    showToast('Merchant application rejected', 'info');
    await loadAdminDashboard();
  } catch (err) {
    showToast('Rejection failed: ' + err.message, 'error');
  }
}

async function toggleProductApproval(productId, newStatus) {
  try {
    await api(`/api/admin/products/${productId}/approve`, {
      method: 'PUT',
      body: JSON.stringify({ status: newStatus })
    });
    showToast(`Product listing updated to ${newStatus.toUpperCase()}`, 'success');
    await loadAdminDashboard();
  } catch (err) {
    showToast('Update failed: ' + err.message, 'error');
  }
}

async function adminRefundOrder(orderId) {
  if (!confirm('Execute transaction refund for this order? Inventory will be replenished and customer credited.')) return;
  try {
    await api(`/api/admin/orders/${orderId}/refund`, { method: 'POST' });
    showToast('Order refunded and inventory replenished', 'success');
    await loadAdminDashboard();
  } catch (err) {
    showToast('Refund failed: ' + err.message, 'error');
  }
}

function downloadSalesCSV() {
  window.open('/api/admin/export/sales-csv', '_blank');
}

// ==========================================
// SUPER ADMIN GOVERNANCE CONSOLE
// ==========================================
function switchSuperAdminTab(tabName) {
  state.saActiveTab = tabName;

  // Toggle button active styling
  document.querySelectorAll('.sa-subtab').forEach(btn => {
    if (btn.dataset.satab === tabName) {
      btn.className = 'sa-subtab px-4 py-2 rounded-xl font-bold transition flex items-center space-x-2 text-brand-600 bg-brand-50';
    } else {
      btn.className = 'sa-subtab px-4 py-2 rounded-xl font-semibold transition flex items-center space-x-2 text-slate-600 hover:text-slate-900';
    }
  });

  // Toggle panels
  const panels = ['overview', 'users', 'rbac', 'settlements', 'config', 'security'];
  panels.forEach(p => {
    const el = document.getElementById(`sa-panel-${p}`);
    if (el) {
      if (p === tabName) el.classList.remove('hidden');
      else el.classList.add('hidden');
    }
  });

  if (tabName === 'users') loadSuperAdminUsers();
  else if (tabName === 'rbac') loadSuperAdminRoles();
  else if (tabName === 'settlements') loadSuperAdminPayouts();
  else if (tabName === 'config') loadSuperAdminConfig();
  else if (tabName === 'security') loadSuperAdminSecurity();

  lucide.createIcons();
}

async function loadSuperAdminDashboard() {
  try {
    const overview = await api('/api/super-admin/overview');
    if (!overview) return;

    // 1. Fill Hero Financial KPIs
    const f = overview.finances || {};
    const gmv = parseFloat(f.total_gross_merchandise_value || 0);
    const comm = parseFloat(f.platform_net_commissions || 0);
    const completedPayouts = parseFloat(f.completed_payouts_volume || 0);
    const pendingPayouts = parseFloat(f.pending_payouts_volume || 0);
    const totalUsers = parseInt(f.total_registered_users || 0);
    const verifiedMerchants = parseInt(f.verified_merchants || 0);

    document.getElementById('sa-kpi-gmv').textContent = `$${gmv.toFixed(2)}`;
    document.getElementById('sa-kpi-commission').textContent = `$${comm.toFixed(2)}`;
    document.getElementById('sa-kpi-payouts').textContent = `$${completedPayouts.toFixed(2)}`;
    document.getElementById('sa-kpi-pending-payouts').textContent = `$${pendingPayouts.toFixed(2)}`;
    document.getElementById('sa-kpi-total-users').textContent = `${totalUsers}`;
    document.getElementById('sa-kpi-users-desc').textContent = `${f.total_customers || 0} Customers • ${verifiedMerchants} Stores • ${f.total_administrators || 0} Admins`;

    // 2. Initialize Charts
    initSuperAdminCharts(overview.monthly_trend || [], overview.gateways_volume || []);

    // 3. Maintenance mode status label
    const isMaintenance = overview.settings?.maintenance_mode === 'true';
    const statusLbl = document.getElementById('lbl-maintenance-status');
    if (statusLbl) {
      statusLbl.textContent = isMaintenance ? 'ON' : 'OFF';
      statusLbl.className = isMaintenance ? 'text-rose-600' : 'text-emerald-600';
    }

    switchSuperAdminTab(state.saActiveTab || 'overview');

    lucide.createIcons();
  } catch (err) {
    console.error('Failed to load super admin overview:', err);
  }
}

function initSuperAdminCharts(monthlyTrend, gatewaysVolume) {
  // Chart 1: Revenue & Commission Trend
  const canvasTrend = document.getElementById('sa-revenue-trend-chart');
  if (canvasTrend) {
    if (state.saTrendChart) state.saTrendChart.destroy();

    const labels = monthlyTrend.map(m => m.month);
    const gmvData = monthlyTrend.map(m => m.gmv);
    const commData = monthlyTrend.map(m => m.net_commission);
    const payoutData = monthlyTrend.map(m => m.payouts);

    state.saTrendChart = new Chart(canvasTrend, {
      type: 'line',
      data: {
        labels: labels.length ? labels : ['Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov'],
        datasets: [
          {
            label: 'Platform GMV ($)',
            data: gmvData.length ? gmvData : [12400, 15800, 19200, 24500, 28900, 34200],
            borderColor: '#2563eb',
            backgroundColor: 'rgba(37, 99, 235, 0.08)',
            fill: true,
            tension: 0.35,
            borderWidth: 2.5,
            pointRadius: 4
          },
          {
            label: 'Net Platform Commission ($)',
            data: commData.length ? commData : [1240, 1580, 1920, 2450, 2890, 3420],
            borderColor: '#10b981',
            backgroundColor: 'transparent',
            borderWidth: 2,
            borderDash: [5, 5],
            pointRadius: 3
          },
          {
            label: 'Merchant Wire Disbursements ($)',
            data: payoutData.length ? payoutData : [10500, 13200, 16400, 21000, 24800, 29000],
            borderColor: '#f59e0b',
            backgroundColor: 'transparent',
            borderWidth: 1.5,
            pointRadius: 2
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { position: 'top', labels: { boxWidth: 12, font: { family: 'Inter', size: 10 } } }
        },
        scales: {
          y: { beginAtZero: true, grid: { color: '#f1f5f9' }, ticks: { font: { family: 'Inter', size: 10 } } },
          x: { grid: { display: false }, ticks: { font: { family: 'Inter', size: 10 } } }
        }
      }
    });
  }

  // Chart 2: Gateways Volume Distribution (Doughnut)
  const canvasGateways = document.getElementById('sa-gateways-chart');
  if (canvasGateways) {
    if (state.saGatewaysChart) state.saGatewaysChart.destroy();

    const providerMap = {
      'stripe': { label: 'Stripe (Cards)', color: '#2563eb' },
      'cod': { label: 'Cash on Delivery', color: '#10b981' },
      'sslcommerz': { label: 'SSLCommerz', color: '#f59e0b' },
      'bank_transfer': { label: 'Bank Wire', color: '#8b5cf6' }
    };

    const providers = gatewaysVolume.length ? gatewaysVolume.map(g => g.provider) : ['stripe', 'cod', 'sslcommerz', 'bank_transfer'];
    const volumes = gatewaysVolume.length ? gatewaysVolume.map(g => g.total_volume) : [473.09, 350.00, 200.00, 600.00];

    state.saGatewaysChart = new Chart(canvasGateways, {
      type: 'doughnut',
      data: {
        labels: providers.map(p => (providerMap[p]?.label || p.toUpperCase())),
        datasets: [{
          data: volumes,
          backgroundColor: providers.map(p => (providerMap[p]?.color || '#94a3b8')),
          borderWidth: 2,
          borderColor: '#ffffff'
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '70%',
        plugins: { legend: { display: false } }
      }
    });

    const legendContainer = document.getElementById('sa-gateways-legend');
    if (legendContainer) {
      legendContainer.innerHTML = providers.map((p, i) => `
        <div class="flex items-center justify-between">
          <div class="flex items-center space-x-1.5">
            <span class="w-2.5 h-2.5 rounded-full" style="background-color: ${providerMap[p]?.color || '#94a3b8'}"></span>
            <span>${providerMap[p]?.label || p.toUpperCase()}</span>
          </div>
          <span class="font-bold text-slate-800">$${(volumes[i] || 0).toFixed(2)}</span>
        </div>
      `).join('');
    }
  }
}

// ------------------------------------------
// Super Admin Users Management
// ------------------------------------------
async function loadSuperAdminUsers() {
  try {
    const role = document.getElementById('sa-user-role-filter')?.value || 'all';
    const status = document.getElementById('sa-user-status-filter')?.value || 'all';
    const search = document.getElementById('sa-user-search-input')?.value || '';

    const q = new URLSearchParams({ role, status, search });
    const users = await api(`/api/super-admin/users?${q.toString()}`);
    state.saUsers = users || [];
    renderSuperAdminUsersTable(state.saUsers);
  } catch (err) {
    console.error('Failed to load super admin users:', err);
  }
}

function filterSuperAdminUsers() {
  loadSuperAdminUsers();
}

function renderSuperAdminUsersTable(users) {
  const tbody = document.getElementById('sa-users-table-body');
  if (!tbody) return;

  if (users.length === 0) {
    tbody.innerHTML = `<tr><td colspan="6" class="text-center py-8 text-slate-400">No matching user accounts found.</td></tr>`;
    return;
  }

  tbody.innerHTML = users.map(u => {
    const isSelf = state.currentUser && state.currentUser.id === u.id;
    const roleColors = {
      'super_admin': 'bg-purple-50 text-purple-700 border-purple-200',
      'admin': 'bg-brand-50 text-brand-700 border-brand-200',
      'finance_admin': 'bg-emerald-50 text-emerald-700 border-emerald-200',
      'support_admin': 'bg-amber-50 text-amber-700 border-amber-200',
      'seller': 'bg-sky-50 text-sky-700 border-sky-200',
      'customer': 'bg-slate-100 text-slate-700 border-slate-200'
    };

    const statusBadge = u.status === 'active'
      ? `<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">ACTIVE</span>`
      : u.status === 'suspended'
      ? `<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-rose-50 text-rose-700 border border-rose-200">SUSPENDED</span>`
      : `<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-50 text-amber-700 border border-amber-200">PENDING</span>`;

    const storeOrOrders = u.role === 'seller'
      ? `<div class="font-bold text-slate-800">${u.store_name || 'Merchant'}</div><div class="text-[10px] text-slate-400 font-mono">Sales: $${(u.total_sales || 0).toFixed(2)}</div>`
      : `<div class="text-slate-600">${u.customer_orders_count || 0} purchases placed</div>`;

    return `
      <tr class="hover:bg-slate-50 transition">
        <td class="py-3 px-4">
          <div class="flex items-center space-x-2.5">
            <div class="w-8 h-8 rounded-xl bg-slate-100 border border-slate-200 text-slate-700 flex items-center justify-center font-bold text-xs uppercase shrink-0">
              ${(u.full_name || u.email || 'U').charAt(0)}
            </div>
            <div>
              <div class="font-bold text-slate-900">${u.full_name || 'User'} ${isSelf ? '<span class="text-[9px] bg-brand-100 text-brand-800 px-1 py-0.2 rounded font-bold">YOU</span>' : ''}</div>
              <div class="text-[11px] text-slate-400 font-mono">${u.email}</div>
            </div>
          </div>
        </td>
        <td class="py-3 px-3">
          <select onchange="changeSuperAdminUserRole('${u.id}', this.value)" ${isSelf ? 'disabled' : ''} class="bg-white border border-slate-200 rounded-lg px-2 py-1 text-xs font-semibold focus:outline-none focus:border-brand-500">
            <option value="customer" ${u.role === 'customer' ? 'selected' : ''}>Customer</option>
            <option value="seller" ${u.role === 'seller' ? 'selected' : ''}>Seller</option>
            <option value="admin" ${u.role === 'admin' ? 'selected' : ''}>Operations Admin</option>
            <option value="finance_admin" ${u.role === 'finance_admin' ? 'selected' : ''}>Finance Admin</option>
            <option value="support_admin" ${u.role === 'support_admin' ? 'selected' : ''}>Support Staff</option>
            <option value="super_admin" ${u.role === 'super_admin' ? 'selected' : ''}>Super Admin</option>
          </select>
        </td>
        <td class="py-3 px-3">${storeOrOrders}</td>
        <td class="py-3 px-3 text-center">${statusBadge}</td>
        <td class="py-3 px-3 text-slate-400 font-mono text-[11px]">${new Date(u.created_at).toLocaleDateString()}</td>
        <td class="py-3 px-3 text-center">
          ${!isSelf ? `
            <div class="flex items-center justify-center space-x-1.5">
              <button onclick="toggleSuperAdminUserStatus('${u.id}', '${u.status === 'active' ? 'suspended' : 'active'}')" class="px-2 py-1 rounded text-[11px] font-semibold border ${u.status === 'active' ? 'border-amber-200 bg-amber-50 hover:bg-amber-100 text-amber-700' : 'border-emerald-200 bg-emerald-50 hover:bg-emerald-100 text-emerald-700'}">
                ${u.status === 'active' ? 'Suspend' : 'Reactivate'}
              </button>
              <button onclick="deleteSuperAdminUser('${u.id}')" class="p-1 rounded text-slate-400 hover:text-rose-600 transition" title="Delete account">
                <i data-lucide="trash-2" class="w-3.5 h-3.5"></i>
              </button>
            </div>
          ` : `<span class="text-[10px] text-slate-400 italic">Self (Protected)</span>`}
        </td>
      </tr>
    `;
  }).join('');

  lucide.createIcons();
}

async function toggleSuperAdminUserStatus(userId, newStatus) {
  try {
    await api(`/api/super-admin/users/${userId}/status`, {
      method: 'PUT',
      body: JSON.stringify({ status: newStatus })
    });
    showToast(`Account status set to ${newStatus.toUpperCase()}`, 'success');
    await loadSuperAdminUsers();
  } catch (err) {
    showToast('Failed to update user status: ' + err.message, 'error');
  }
}

async function changeSuperAdminUserRole(userId, newRole) {
  try {
    await api(`/api/super-admin/users/${userId}/role`, {
      method: 'PUT',
      body: JSON.stringify({ role: newRole })
    });
    showToast(`Role reassigned to ${newRole.toUpperCase()}`, 'success');
    await loadSuperAdminUsers();
  } catch (err) {
    showToast('Role update failed: ' + err.message, 'error');
  }
}

async function deleteSuperAdminUser(userId) {
  if (!confirm('Are you sure you want to permanently delete this user account?')) return;
  try {
    await api(`/api/super-admin/users/${userId}`, { method: 'DELETE' });
    showToast('User account removed from platform', 'info');
    await loadSuperAdminUsers();
  } catch (err) {
    showToast('Delete failed: ' + err.message, 'error');
  }
}

// ------------------------------------------
// Super Admin RBAC & Roles Matrix
// ------------------------------------------
async function loadSuperAdminRoles() {
  try {
    const roles = await api('/api/super-admin/roles');
    state.saRoles = roles || [];

    const pillsList = document.getElementById('sa-roles-pills-list');
    if (pillsList) {
      pillsList.innerHTML = state.saRoles.map(r => {
        const isSelected = r.role_key === state.saActiveRoleKey;
        return `
          <button onclick="selectRoleToEdit('${r.role_key}')" class="w-full text-left p-3 rounded-xl border transition flex items-center justify-between ${isSelected ? 'border-brand-600 bg-brand-50/60 shadow-xs' : 'border-slate-200 bg-white hover:border-slate-300'}">
            <div>
              <div class="font-bold text-xs text-slate-900">${r.role_name}</div>
              <div class="text-[10px] text-slate-400 font-mono">${r.role_key} • ${r.users_count || 0} assigned</div>
            </div>
            ${r.is_system ? `<span class="px-1.5 py-0.5 rounded text-[9px] font-bold bg-slate-100 text-slate-600">SYSTEM</span>` : ''}
          </button>
        `;
      }).join('');
    }

    // Default select active role
    selectRoleToEdit(state.saActiveRoleKey);
  } catch (err) {
    console.error('Failed to load super admin roles:', err);
  }
}

function selectRoleToEdit(roleKey) {
  state.saActiveRoleKey = roleKey;
  const role = state.saRoles.find(r => r.role_key === roleKey) || state.saRoles[0];
  if (!role) return;

  // Header
  document.getElementById('sa-active-role-name').textContent = role.role_name;
  document.getElementById('sa-active-role-desc').textContent = role.description || 'Custom administrative role';
  
  const sysBadge = document.getElementById('sa-active-role-system-badge');
  const deleteBtn = document.getElementById('btn-sa-delete-role');
  if (role.is_system) {
    if (sysBadge) sysBadge.classList.remove('hidden');
    if (deleteBtn) deleteBtn.classList.add('hidden');
  } else {
    if (sysBadge) sysBadge.classList.add('hidden');
    if (deleteBtn) deleteBtn.classList.remove('hidden');
  }

  // Render Matrix Checkboxes
  const modules = [
    { key: 'catalog', name: 'Product Catalog & Brands' },
    { key: 'orders', name: 'Platform Orders & Shipments' },
    { key: 'merchants', name: 'Merchant Onboarding & Stores' },
    { key: 'settlements', name: 'Financial Settlements & Payouts' },
    { key: 'settings', name: 'System Policies & Gateways' },
    { key: 'security', name: 'Audit Trail & Login Monitoring' }
  ];
  const actions = ['view', 'create', 'edit', 'delete', 'approve', 'export'];

  const tbody = document.getElementById('sa-matrix-tbody');
  if (tbody) {
    tbody.innerHTML = modules.map(m => {
      const perms = role.permissions[m.key] || [];
      return `
        <tr class="hover:bg-slate-50 transition">
          <td class="py-3 px-4 font-bold text-slate-800">${m.name}</td>
          ${actions.map(act => {
            const hasAction = perms.includes(act);
            return `
              <td class="py-3 px-3 text-center">
                <input type="checkbox" id="matrix-${m.key}-${act}" ${hasAction ? 'checked' : ''} class="rounded border-slate-300 text-brand-600 focus:ring-brand-500 cursor-pointer">
              </td>
            `;
          }).join('')}
        </tr>
      `;
    }).join('');
  }

  // Update pills highlight
  document.querySelectorAll('#sa-roles-pills-list button').forEach(btn => {
    if (btn.innerText.includes(role.role_key)) {
      btn.className = 'w-full text-left p-3 rounded-xl border transition flex items-center justify-between border-brand-600 bg-brand-50/60 shadow-xs';
    } else {
      btn.className = 'w-full text-left p-3 rounded-xl border transition flex items-center justify-between border-slate-200 bg-white hover:border-slate-300';
    }
  });

  lucide.createIcons();
}

async function saveRolePermissions() {
  const role = state.saRoles.find(r => r.role_key === state.saActiveRoleKey);
  if (!role) return;

  const modules = ['catalog', 'orders', 'merchants', 'settlements', 'settings', 'security'];
  const actions = ['view', 'create', 'edit', 'delete', 'approve', 'export'];

  const newPermissions = {};
  modules.forEach(m => {
    newPermissions[m] = [];
    actions.forEach(act => {
      const checkbox = document.getElementById(`matrix-${m}-${act}`);
      if (checkbox && checkbox.checked) {
        newPermissions[m].push(act);
      }
    });
  });

  try {
    await api(`/api/super-admin/roles/${role.role_key}`, {
      method: 'PUT',
      body: JSON.stringify({
        role_key: role.role_key,
        role_name: role.role_name,
        description: role.description,
        permissions: newPermissions
      })
    });
    showToast(`Permissions updated for '${role.role_name}'`, 'success');
    await loadSuperAdminRoles();
  } catch (err) {
    showToast('Failed to save permissions: ' + err.message, 'error');
  }
}

async function deleteActiveRole() {
  if (!confirm(`Are you sure you want to delete role '${state.saActiveRoleKey}'?`)) return;
  try {
    await api(`/api/super-admin/roles/${state.saActiveRoleKey}`, { method: 'DELETE' });
    showToast('Role deleted', 'info');
    state.saActiveRoleKey = 'super_admin';
    await loadSuperAdminRoles();
  } catch (err) {
    showToast('Delete failed: ' + err.message, 'error');
  }
}

function openCreateRoleModal() {
  document.getElementById('modal-sa-create-role')?.classList.remove('hidden');
}
function closeCreateRoleModal() {
  document.getElementById('modal-sa-create-role')?.classList.add('hidden');
}

async function submitCreateRole(e) {
  e.preventDefault();
  const name = document.getElementById('sa-new-role-name')?.value.trim();
  const key = document.getElementById('sa-new-role-key')?.value.trim().toLowerCase().replace(/\s+/g, '_');
  const desc = document.getElementById('sa-new-role-desc')?.value.trim();

  try {
    await api('/api/super-admin/roles', {
      method: 'POST',
      body: JSON.stringify({
        role_key: key,
        role_name: name,
        description: desc,
        permissions: {
          catalog: ['view'],
          orders: ['view'],
          merchants: ['view'],
          settlements: [],
          settings: [],
          security: []
        }
      })
    });
    showToast(`Role '${name}' created successfully!`, 'success');
    closeCreateRoleModal();
    document.getElementById('sa-create-role-form')?.reset();
    state.saActiveRoleKey = key;
    await loadSuperAdminRoles();
  } catch (err) {
    showToast('Failed to create role: ' + err.message, 'error');
  }
}

// ------------------------------------------
// Super Admin Merchant Settlements
// ------------------------------------------
async function loadSuperAdminPayouts() {
  try {
    const filter = document.getElementById('sa-payout-filter')?.value || 'all';
    const payouts = await api(`/api/super-admin/payouts?status=${filter}`);
    const container = document.getElementById('sa-payouts-container');
    if (!container) return;

    if (payouts.length === 0) {
      container.innerHTML = `<div class="p-8 rounded-2xl bg-white border border-slate-200 text-center text-slate-400 text-xs">No merchant settlement requests matching this filter.</div>`;
      return;
    }

    container.innerHTML = payouts.map(p => {
      const isPending = p.status === 'requested';
      return `
        <div class="p-5 rounded-2xl bg-white border border-slate-200 shadow-xs flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div class="space-y-1 text-xs">
            <div class="flex items-center space-x-2">
              <span class="font-extrabold text-slate-900 text-sm">${p.store_name}</span>
              ${p.status === 'completed' ? `<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">SETTLED</span>` : p.status === 'rejected' ? `<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-rose-50 text-rose-700 border border-rose-200">REJECTED</span>` : `<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-50 text-amber-700 border border-amber-200">PENDING APPROVAL</span>`}
              <span class="text-[10px] text-slate-400 font-mono">ID: #${p.id}</span>
            </div>
            <div class="text-slate-600 font-mono">${p.bank_details || 'Bank of America • AC-1234567890'}</div>
            <div class="text-slate-400 text-[11px]">Requested: ${new Date(p.requested_at).toLocaleString()} ${p.notes ? `• "${p.notes}"` : ''}</div>
          </div>

          <div class="flex items-center space-x-4">
            <div class="text-right">
              <span class="text-[10px] text-slate-400 uppercase tracking-wider block">Disbursement Amount</span>
              <span class="text-xl font-extrabold text-slate-900 font-mono">$${p.amount.toFixed(2)}</span>
            </div>

            ${isPending ? `
              <div class="flex items-center space-x-2">
                <button onclick="openSettlePayoutModal('${p.id}', ${p.amount}, '${p.store_name}')" class="px-3.5 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white font-bold text-xs shadow-xs transition">
                  Authorize Wire
                </button>
                <button onclick="rejectPayoutRequest('${p.id}')" class="px-3.5 py-2 rounded-xl border border-rose-200 bg-rose-50 hover:bg-rose-100 text-rose-700 font-semibold text-xs transition">
                  Reject
                </button>
              </div>
            ` : `<span class="text-xs text-slate-400 font-mono">${p.processed_at ? new Date(p.processed_at).toLocaleDateString() : 'Closed'}</span>`}
          </div>
        </div>
      `;
    }).join('');

    lucide.createIcons();
  } catch (err) {
    console.error('Failed to load super admin payouts:', err);
  }
}

function openSettlePayoutModal(payoutId, amount, storeName) {
  document.getElementById('sa-settle-payout-id').value = payoutId;
  document.getElementById('sa-settle-store-name').textContent = storeName;
  document.getElementById('sa-settle-amount').textContent = `$${amount.toFixed(2)}`;
  document.getElementById('sa-settle-ref').value = `FED-WIRE-${Date.now().toString().slice(-8)}`;
  document.getElementById('modal-sa-settle-payout')?.classList.remove('hidden');
}
function closeSettlePayoutModal() {
  document.getElementById('modal-sa-settle-payout')?.classList.add('hidden');
}

async function submitSettlePayout(e) {
  e.preventDefault();
  const payoutId = document.getElementById('sa-settle-payout-id')?.value;
  const ref = document.getElementById('sa-settle-ref')?.value.trim();
  const notes = document.getElementById('sa-settle-notes')?.value.trim();

  try {
    await api(`/api/super-admin/payouts/${payoutId}/settle`, {
      method: 'POST',
      body: JSON.stringify({ transaction_ref: ref, notes })
    });
    showToast(`Settlement authorized with reference ${ref}`, 'success');
    closeSettlePayoutModal();
    await loadSuperAdminPayouts();
    await loadSuperAdminDashboard();
  } catch (err) {
    showToast('Settlement authorization failed: ' + err.message, 'error');
  }
}

async function rejectPayoutRequest(payoutId) {
  const reason = prompt('Please specify the reason for rejecting this payout request:');
  if (!reason) return;
  try {
    await api(`/api/super-admin/payouts/${payoutId}/reject`, {
      method: 'POST',
      body: JSON.stringify({ reason })
    });
    showToast('Payout request rejected', 'info');
    await loadSuperAdminPayouts();
    await loadSuperAdminDashboard();
  } catch (err) {
    showToast('Rejection failed: ' + err.message, 'error');
  }
}

// ------------------------------------------
// Super Admin Gateway & Platform Config
// ------------------------------------------
async function loadSuperAdminConfig() {
  try {
    const s = await api('/api/super-admin/settings');
    if (!s) return;

    // Rates & Info
    if (document.getElementById('cfg-commission')) document.getElementById('cfg-commission').value = s.platform_commission_percent || s.platform_commission_pct || 10.0;
    if (document.getElementById('cfg-tax')) document.getElementById('cfg-tax').value = s.tax_percent || s.sales_tax_pct || 5.0;
    if (document.getElementById('cfg-shipping')) document.getElementById('cfg-shipping').value = s.flat_shipping_rate || s.flat_shipping_fee || 5.0;
    if (document.getElementById('cfg-free-ship-threshold')) document.getElementById('cfg-free-ship-threshold').value = s.free_shipping_threshold || 100.0;
    if (document.getElementById('cfg-currency')) document.getElementById('cfg-currency').value = s.currency_code || 'USD';
    if (document.getElementById('cfg-site-name')) document.getElementById('cfg-site-name').value = s.site_name || 'Bazaarly';
    if (document.getElementById('cfg-support-email')) document.getElementById('cfg-support-email').value = s.support_email || 'support@bazaarly.com';
    if (document.getElementById('cfg-smtp-host')) document.getElementById('cfg-smtp-host').value = s.smtp_host || 'smtp.sendgrid.net';
    if (document.getElementById('cfg-smtp-port')) document.getElementById('cfg-smtp-port').value = s.smtp_port || 587;
    if (document.getElementById('cfg-seo-title')) document.getElementById('cfg-seo-title').value = s.seo_meta_title || 'Bazaarly — Curated Multi-Vendor Marketplace';

    // Gateways
    if (document.getElementById('gw-stripe-enabled')) document.getElementById('gw-stripe-enabled').checked = s.stripe_enabled !== 'false';
    if (document.getElementById('gw-stripe-mode')) document.getElementById('gw-stripe-mode').value = s.stripe_mode || 'test';
    if (document.getElementById('gw-stripe-pub')) document.getElementById('gw-stripe-pub').value = s.stripe_publishable_key || 'pk_test_...';
    if (document.getElementById('gw-stripe-sec')) document.getElementById('gw-stripe-sec').value = s.stripe_secret_key || '••••••••';

    if (document.getElementById('gw-ssl-enabled')) document.getElementById('gw-ssl-enabled').checked = s.sslcommerz_enabled !== 'false';
    if (document.getElementById('gw-ssl-sandbox')) document.getElementById('gw-ssl-sandbox').value = s.sslcommerz_sandbox || 'true';
    if (document.getElementById('gw-ssl-store-id')) document.getElementById('gw-ssl-store-id').value = s.sslcommerz_store_id || 'bazaarly_live01';
    if (document.getElementById('gw-ssl-store-pw')) document.getElementById('gw-ssl-store-pw').value = s.sslcommerz_store_passwd || '••••••••';

    if (document.getElementById('gw-cod-enabled')) document.getElementById('gw-cod-enabled').checked = s.cod_enabled !== 'false';
    if (document.getElementById('gw-wire-enabled')) document.getElementById('gw-wire-enabled').checked = s.bank_wire_enabled !== 'false';
    if (document.getElementById('gw-wire-instructions')) document.getElementById('gw-wire-instructions').value = s.bank_wire_instructions || 'Wire to: Chase Commercial Banking, AC# 9876543210';
  } catch (err) {
    console.error('Failed to load super admin config:', err);
  }
}

async function saveAllSuperAdminSettings(e) {
  e.preventDefault();

  const payload = {
    platform_commission_percent: document.getElementById('cfg-commission')?.value || '10.0',
    tax_percent: document.getElementById('cfg-tax')?.value || '5.0',
    flat_shipping_rate: document.getElementById('cfg-shipping')?.value || '5.00',
    free_shipping_threshold: document.getElementById('cfg-free-ship-threshold')?.value || '100.00',
    currency_code: document.getElementById('cfg-currency')?.value || 'USD',
    site_name: document.getElementById('cfg-site-name')?.value || 'Bazaarly',
    support_email: document.getElementById('cfg-support-email')?.value || 'support@bazaarly.com',
    smtp_host: document.getElementById('cfg-smtp-host')?.value || 'smtp.sendgrid.net',
    smtp_port: document.getElementById('cfg-smtp-port')?.value || '587',
    seo_meta_title: document.getElementById('cfg-seo-title')?.value || '',

    stripe_enabled: document.getElementById('gw-stripe-enabled')?.checked ? 'true' : 'false',
    stripe_mode: document.getElementById('gw-stripe-mode')?.value || 'test',
    stripe_publishable_key: document.getElementById('gw-stripe-pub')?.value || '',
    stripe_secret_key: document.getElementById('gw-stripe-sec')?.value || '',

    sslcommerz_enabled: document.getElementById('gw-ssl-enabled')?.checked ? 'true' : 'false',
    sslcommerz_sandbox: document.getElementById('gw-ssl-sandbox')?.value || 'true',
    sslcommerz_store_id: document.getElementById('gw-ssl-store-id')?.value || '',
    sslcommerz_store_passwd: document.getElementById('gw-ssl-store-pw')?.value || '',

    cod_enabled: document.getElementById('gw-cod-enabled')?.checked ? 'true' : 'false',
    bank_wire_enabled: document.getElementById('gw-wire-enabled')?.checked ? 'true' : 'false',
    bank_wire_instructions: document.getElementById('gw-wire-instructions')?.value || ''
  };

  try {
    await api('/api/super-admin/settings', {
      method: 'PUT',
      body: JSON.stringify(payload)
    });
    showToast('All platform policies and gateway parameters saved successfully!', 'success');
  } catch (err) {
    showToast('Failed to save settings: ' + err.message, 'error');
  }
}

async function toggleMaintenanceMode() {
  try {
    const s = await api('/api/super-admin/settings');
    const current = s?.maintenance_mode === 'true';
    const next = !current;

    await api('/api/super-admin/settings', {
      method: 'PUT',
      body: JSON.stringify({ maintenance_mode: next ? 'true' : 'false' })
    });

    const statusLbl = document.getElementById('lbl-maintenance-status');
    if (statusLbl) {
      statusLbl.textContent = next ? 'ON' : 'OFF';
      statusLbl.className = next ? 'text-rose-600' : 'text-emerald-600';
    }

    showToast(`Platform Maintenance Mode set to ${next ? 'ACTIVATED (ON)' : 'DEACTIVATED (OFF)'}`, next ? 'warning' : 'success');
  } catch (err) {
    showToast('Failed to toggle maintenance mode: ' + err.message, 'error');
  }
}

// ------------------------------------------
// Super Admin Security & Audit Monitoring
// ------------------------------------------
async function loadSuperAdminSecurity() {
  try {
    const stats = await api('/api/super-admin/security-stats');
    if (stats) {
      document.getElementById('sec-kpi-failed-attempts').textContent = stats.failed_attempts_count || 0;
      document.getElementById('sec-kpi-audits-count').textContent = stats.total_audit_events || 0;

      const loginsTbody = document.getElementById('sa-login-history-tbody');
      if (loginsTbody) {
        loginsTbody.innerHTML = (stats.login_history || []).map(l => {
          const statusBadge = l.status === 'success'
            ? `<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">SUCCESS</span>`
            : l.status === 'blocked'
            ? `<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-purple-50 text-purple-700 border border-purple-200">BLOCKED</span>`
            : `<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-rose-50 text-rose-700 border border-rose-200">FAILED</span>`;

          return `
            <tr class="hover:bg-slate-50 transition">
              <td class="py-2.5 px-4 text-slate-400 font-mono">${new Date(l.created_at).toLocaleString()}</td>
              <td class="py-2.5 px-3 font-bold text-slate-800">${l.email}</td>
              <td class="py-2.5 px-3 font-mono text-slate-600">${l.ip_address}</td>
              <td class="py-2.5 px-3 text-slate-500 truncate max-w-xs">${l.user_agent || '--'}</td>
              <td class="py-2.5 px-3 text-center">${statusBadge}</td>
              <td class="py-2.5 px-3 text-slate-400">${l.failure_reason || 'Legitimate sign-in'}</td>
            </tr>
          `;
        }).join('');
      }
    }

    // Platform Audit Trail Table
    const audits = await api('/api/super-admin/audit-logs');
    const auditTbody = document.getElementById('superadmin-audit-table-body');
    if (auditTbody && audits) {
      auditTbody.innerHTML = audits.map(a => `
        <tr class="hover:bg-slate-50 transition">
          <td class="py-2.5 px-4 text-slate-400">${new Date(a.created_at).toLocaleString()}</td>
          <td class="py-2.5 px-3 font-semibold text-slate-700">${a.user_id || 'SUPER_ADMIN'}</td>
          <td class="py-2.5 px-3 font-bold text-brand-600 uppercase">${a.action}</td>
          <td class="py-2.5 px-3 text-slate-600">${a.resource_type} (${a.resource_id || '--'})</td>
          <td class="py-2.5 px-3 text-slate-500 truncate max-w-xs">${a.metadata_json || '--'}</td>
        </tr>
      `).join('');
    }

    lucide.createIcons();
  } catch (err) {
    console.error('Failed to load super admin security stats:', err);
  }
}

// ------------------------------------------
// Super Admin Provision Staff Modal
// ------------------------------------------
function openProvisionAdminModal() {
  document.getElementById('modal-sa-provision-admin')?.classList.remove('hidden');
}
function closeProvisionAdminModal() {
  document.getElementById('modal-sa-provision-admin')?.classList.add('hidden');
}

async function submitProvisionAdmin(e) {
  e.preventDefault();
  const name = document.getElementById('sa-new-admin-name')?.value.trim();
  const email = document.getElementById('sa-new-admin-email')?.value.trim();
  const password = document.getElementById('sa-new-admin-password')?.value;
  const phone = document.getElementById('sa-new-admin-phone')?.value.trim();
  const role = document.getElementById('sa-new-admin-role')?.value || 'admin';

  try {
    await api('/api/super-admin/admins', {
      method: 'POST',
      body: JSON.stringify({
        email,
        full_name: name,
        password,
        phone,
        role
      })
    });
    showToast(`Administrator account provisioned for ${email}!`, 'success');
    closeProvisionAdminModal();
    document.getElementById('sa-provision-admin-form')?.reset();
    await loadSuperAdminUsers();
    await loadSuperAdminDashboard();
  } catch (err) {
    showToast('Failed to provision staff: ' + err.message, 'error');
  }
}


// ==========================================
// INVOICE RENDERING & PRINTING
// ==========================================
async function renderPrintableInvoice(orderId) {
  try {
    const order = await api(`/api/orders/${orderId}`);
    if (!order) return;

    const modal = document.getElementById('printable-invoice-modal');
    const sheet = document.getElementById('invoice-sheet');
    if (!modal || !sheet) return;

    sheet.innerHTML = `
      <div class="flex items-center justify-between border-b border-slate-200 pb-4">
        <div class="flex items-center space-x-2">
          <div class="w-8 h-8 rounded-lg bg-brand-600 text-white flex items-center justify-center font-bold">
            <i data-lucide="shopping-bag" class="w-4 h-4"></i>
          </div>
          <div>
            <h2 class="text-base font-extrabold text-slate-900">Bazaarly Marketplace</h2>
            <p class="text-[10px] text-slate-400">Direct Multi-Vendor Order Invoice</p>
          </div>
        </div>
        <div class="text-right">
          <h3 class="text-sm font-mono font-bold text-slate-900">INVOICE #${order.order_number}</h3>
          <span class="text-[10px] text-slate-400 font-mono">Date: ${new Date(order.created_at).toLocaleDateString()}</span>
        </div>
      </div>

      <div class="grid grid-cols-2 gap-4 text-xs">
        <div>
          <span class="text-[10px] font-bold text-slate-400 uppercase tracking-wider block mb-1">Delivered To</span>
          <div class="font-bold text-slate-900">${order.shipping_address?.full_name || 'Customer'}</div>
          <div class="text-slate-600">${order.shipping_address?.address_line1 || ''}</div>
          <div class="text-slate-600">${order.shipping_address?.city || ''}, ${order.shipping_address?.state || ''} ${order.shipping_address?.postal_code || ''}</div>
          <div class="text-slate-500 font-mono mt-1">${order.shipping_address?.phone || ''}</div>
        </div>
        <div class="text-right">
          <span class="text-[10px] font-bold text-slate-400 uppercase tracking-wider block mb-1">Shipment & Payment</span>
          <div class="font-semibold text-slate-800">Tracking: <span class="font-mono text-brand-600 font-bold">${order.tracking_number}</span></div>
          <div class="text-slate-600 uppercase font-mono mt-0.5">Method: ${order.payment_method}</div>
          <div class="mt-1">${getStatusBadge(order.status)}</div>
        </div>
      </div>

      <!-- Items Table -->
      <table class="w-full text-left text-xs border border-slate-200 rounded-xl overflow-hidden">
        <thead class="bg-slate-50 text-slate-700 font-semibold border-b border-slate-200">
          <tr>
            <th class="py-2.5 px-3">Item Description</th>
            <th class="py-2.5 px-3 text-center">Qty</th>
            <th class="py-2.5 px-3 text-right">Unit Price</th>
            <th class="py-2.5 px-3 text-right">Total</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          ${(order.items || []).map(item => `
            <tr>
              <td class="py-2 px-3 font-medium text-slate-800">
                ${item.title}
                ${item.variant_name ? `<span class="text-[10px] text-brand-600 block font-mono">${item.variant_name}</span>` : ''}
              </td>
              <td class="py-2 px-3 text-center font-mono">${item.quantity}</td>
              <td class="py-2 px-3 text-right font-mono">$${item.unit_price.toFixed(2)}</td>
              <td class="py-2 px-3 text-right font-mono font-bold">$${item.total_price.toFixed(2)}</td>
            </tr>
          `).join('')}
        </tbody>
      </table>

      <!-- Totals -->
      <div class="border-t border-slate-200 pt-3 flex flex-col items-end space-y-1 text-xs">
        <div class="flex justify-between w-48 text-slate-600">
          <span>Subtotal:</span>
          <span class="font-mono font-semibold">$${order.subtotal.toFixed(2)}</span>
        </div>
        ${order.discount_amount > 0 ? `
          <div class="flex justify-between w-48 text-emerald-600">
            <span>Coupon Discount:</span>
            <span class="font-mono font-semibold">-$${order.discount_amount.toFixed(2)}</span>
          </div>
        ` : ''}
        <div class="flex justify-between w-48 text-slate-600">
          <span>Shipping:</span>
          <span class="font-mono font-semibold">$${order.shipping_fee.toFixed(2)}</span>
        </div>
        <div class="flex justify-between w-48 text-slate-600">
          <span>Sales Tax:</span>
          <span class="font-mono font-semibold">$${order.tax_amount.toFixed(2)}</span>
        </div>
        <div class="flex justify-between w-48 text-sm font-extrabold text-slate-900 border-t border-slate-200 pt-1">
          <span>Amount Paid:</span>
          <span class="text-brand-600 font-mono">$${order.total_amount.toFixed(2)}</span>
        </div>
      </div>

      <!-- Action Buttons -->
      <div class="flex items-center justify-end space-x-2 pt-2 border-t border-slate-100 print:hidden">
        <button onclick="closeInvoiceModal()" class="px-4 py-2 rounded-lg border border-slate-200 bg-slate-50 text-slate-700 text-xs font-semibold">Close</button>
        <button onclick="window.print()" class="px-4 py-2 rounded-lg bg-brand-600 hover:bg-brand-700 text-white text-xs font-bold shadow-xs flex items-center space-x-1">
          <i data-lucide="printer" class="w-3.5 h-3.5"></i>
          <span>Print Official Receipt</span>
        </button>
      </div>
    `;

    modal.classList.remove('hidden');
    lucide.createIcons();
  } catch (err) {
    showToast('Failed to render invoice: ' + err.message, 'error');
  }
}

function printOrderInvoice() {
  if (state.lastCompletedOrder) {
    renderPrintableInvoice(state.lastCompletedOrder.id);
  }
}

function closeInvoiceModal() {
  document.getElementById('printable-invoice-modal')?.classList.add('hidden');
}

// ==========================================
// REVIEWS
// ==========================================
function openReviewModal() {
  document.getElementById('modal-review')?.classList.remove('hidden');
}
function closeReviewModal() {
  document.getElementById('modal-review')?.classList.add('hidden');
}

async function submitReview(e) {
  e.preventDefault();
  if (!state.currentProduct) return;

  const rating = parseInt(document.getElementById('rev-rating')?.value || '5');
  const title = document.getElementById('rev-title')?.value.trim();
  const comment = document.getElementById('rev-comment')?.value.trim();

  try {
    await api(`/api/catalog/products/${state.currentProduct.id}/reviews`, {
      method: 'POST',
      body: JSON.stringify({ rating, title, comment })
    });
    showToast('Review submitted successfully!', 'success');
    closeReviewModal();
    document.getElementById('review-form')?.reset();
    await viewProductDetails(state.currentProduct.id);
  } catch (err) {
    showToast('Failed to post review: ' + err.message, 'error');
  }
}

// ==========================================
// UTILITY HELPERS & EVENT LISTENERS
// ==========================================
function getStatusBadge(status) {
  const map = {
    'pending': 'bg-amber-50 text-amber-700 border-amber-200',
    'processing': 'bg-blue-50 text-blue-700 border-blue-200',
    'packed': 'bg-indigo-50 text-indigo-700 border-indigo-200',
    'shipped': 'bg-purple-50 text-purple-700 border-purple-200',
    'delivered': 'bg-emerald-50 text-emerald-700 border-emerald-200',
    'cancelled': 'bg-slate-100 text-slate-700 border-slate-200',
    'refunded': 'bg-rose-50 text-rose-700 border-rose-200'
  };
  const cls = map[status] || 'bg-slate-100 text-slate-700 border-slate-200';
  return `<span class="px-2 py-0.5 rounded text-[10px] font-bold uppercase border ${cls}">${status}</span>`;
}

function showToast(message, type = 'info') {
  const toast = document.createElement('div');
  const colors = {
    success: 'bg-emerald-600 text-white',
    error: 'bg-rose-600 text-white',
    warning: 'bg-amber-600 text-white',
    info: 'bg-slate-900 text-white'
  };
  toast.className = `fixed bottom-5 right-5 z-50 px-4 py-2.5 rounded-xl shadow-xl font-medium text-xs flex items-center space-x-2 transition-all duration-300 transform translate-y-2 opacity-0 ${colors[type] || colors.info}`;
  toast.innerHTML = `<span>${message}</span>`;
  document.body.appendChild(toast);

  setTimeout(() => {
    toast.classList.remove('translate-y-2', 'opacity-0');
  }, 10);

  setTimeout(() => {
    toast.classList.add('opacity-0', 'translate-y-2');
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}

function setupEventListeners() {
  // Global search with debounce
  let searchTimeout = null;
  const searchInput = document.getElementById('global-search-input');
  if (searchInput) {
    searchInput.addEventListener('input', () => {
      clearTimeout(searchTimeout);
      searchTimeout = setTimeout(() => {
        applyFilters();
      }, 350);
    });
  }

  // Cart button
  document.getElementById('btn-open-cart')?.addEventListener('click', openCartDrawer);

  // Role toggle
  document.getElementById('btn-role-switcher-toggle')?.addEventListener('click', (e) => {
    e.stopPropagation();
    const dropdown = document.getElementById('role-switcher-dropdown');
    if (dropdown) dropdown.classList.toggle('hidden');
  });

  document.addEventListener('click', () => {
    const dropdown = document.getElementById('role-switcher-dropdown');
    if (dropdown) dropdown.classList.add('hidden');
  });

  // Forms
  document.getElementById('checkout-form')?.addEventListener('submit', submitCheckoutOrder);
  document.getElementById('add-product-form')?.addEventListener('submit', submitNewProduct);
  document.getElementById('payout-form')?.addEventListener('submit', submitPayout);
  document.getElementById('review-form')?.addEventListener('submit', submitReview);
  document.getElementById('settings-form')?.addEventListener('submit', saveSystemSettings);
  document.getElementById('sa-all-settings-form')?.addEventListener('submit', saveAllSuperAdminSettings);
  document.getElementById('sa-provision-admin-form')?.addEventListener('submit', submitProvisionAdmin);
  document.getElementById('sa-settle-payout-form')?.addEventListener('submit', submitSettlePayout);
  document.getElementById('sa-create-role-form')?.addEventListener('submit', submitCreateRole);
}
