(function () {
  'use strict';

  // Cache Chart instances by canvas element so we can destroy before re-render
  var chartRegistry = new Map();

  // Cache fetch promises by URL
  var fetchCache = {};

  function fetchFlavors(url) {
    if (!fetchCache[url]) {
      fetchCache[url] = fetch(url).then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status + ' loading ' + url);
        return r.json();
      });
    }
    return fetchCache[url];
  }

  document.addEventListener('DOMContentLoaded', function () {
    var explorerEl = document.getElementById('coffee-flavor-explorer');
    var radarEls = Array.from(document.querySelectorAll('.coffee-radar-chart'));

    if (!explorerEl && radarEls.length === 0) return;

    if (explorerEl) {
      var explorerUrl = explorerEl.dataset.flavorsUrl;
      fetchFlavors(explorerUrl)
        .then(function (data) { renderExplorer(explorerEl, data); })
        .catch(function (err) {
          explorerEl.textContent = 'Failed to load coffee data.';
          console.error('[CFE]', err);
        });
    }

    radarEls.forEach(function (el) {
      var url = el.dataset.flavorsUrl;
      var productId = el.dataset.productId;
      fetchFlavors(url)
        .then(function (data) {
          var product = data.products.find(function (p) { return p.id === productId; });
          if (product) renderStandaloneRadar(el, product);
        })
        .catch(function (err) {
          console.error('[CFE] Failed to load radar for ' + productId, err);
        });
    });
  });

  // ---------------------------------------------------------------------------
  // Explorer widget
  // ---------------------------------------------------------------------------

  function renderExplorer(container, data) {
    var families = data.families;
    var allProducts = data.products;

    // State
    var activeFamilies = new Set();
    var activeNote = null;
    var sortBy = 'relevance';

    // Build skeleton
    var familyBar = document.createElement('div');
    familyBar.className = 'cfe-family-filters';

    var noteBar = document.createElement('div');
    noteBar.className = 'cfe-note-filters';

    var controls = document.createElement('div');
    controls.className = 'cfe-controls';

    var countEl = document.createElement('div');
    countEl.className = 'cfe-count';

    var grid = document.createElement('div');
    grid.className = 'cfe-grid';

    container.appendChild(familyBar);
    container.appendChild(noteBar);
    container.appendChild(controls);
    container.appendChild(countEl);
    container.appendChild(grid);

    // Sort control
    var sortLabel = document.createElement('span');
    sortLabel.className = 'cfe-sort-label';
    sortLabel.textContent = 'Sort by:';
    controls.appendChild(sortLabel);

    var sortModes = [
      { key: 'relevance', label: 'Relevance' },
      { key: 'price',     label: 'Price/oz (low)' },
      { key: 'rating',    label: 'Rating' },
    ];
    sortModes.forEach(function (mode) {
      var btn = document.createElement('button');
      btn.className = 'cfe-sort-btn' + (mode.key === sortBy ? ' active' : '');
      btn.dataset.sort = mode.key;
      btn.textContent = mode.label;
      btn.addEventListener('click', function () {
        sortBy = mode.key;
        controls.querySelectorAll('.cfe-sort-btn').forEach(function (b) {
          b.classList.toggle('active', b.dataset.sort === mode.key);
        });
        update();
      });
      controls.appendChild(btn);
    });

    // "All" button
    var allBtn = document.createElement('button');
    allBtn.className = 'cfe-family-btn active';
    allBtn.textContent = 'All';
    allBtn.addEventListener('click', function () {
      activeFamilies.clear();
      activeNote = null;
      syncFamilyButtons();
      update();
    });
    familyBar.appendChild(allBtn);

    // Per-family buttons
    families.forEach(function (family) {
      var btn = document.createElement('button');
      btn.className = 'cfe-family-btn';
      btn.dataset.family = family;
      btn.textContent = family;
      btn.addEventListener('click', function () {
        if (activeFamilies.has(family)) {
          activeFamilies.delete(family);
        } else {
          activeFamilies.add(family);
        }
        // Clear note filter if it no longer appears in filtered set
        if (activeNote) {
          var afterFamily = filterByFamilies(allProducts, activeFamilies);
          if (!collectNotes(afterFamily).includes(activeNote)) {
            activeNote = null;
          }
        }
        syncFamilyButtons();
        update();
      });
      familyBar.appendChild(btn);
    });

    // Listen for note-click events bubbling up from product cards
    container.addEventListener('cfe:note-click', function (e) {
      activeNote = (activeNote === e.detail.note) ? null : e.detail.note;
      update();
    });

    function syncFamilyButtons() {
      allBtn.classList.toggle('active', activeFamilies.size === 0);
      familyBar.querySelectorAll('.cfe-family-btn[data-family]').forEach(function (btn) {
        btn.classList.toggle('active', activeFamilies.has(btn.dataset.family));
      });
    }

    function update() {
      var afterFamily = filterByFamilies(allProducts, activeFamilies);
      var availableNotes = collectNotes(afterFamily);

      // Rebuild note tag bar
      noteBar.innerHTML = '';
      availableNotes.forEach(function (note) {
        var tag = document.createElement('button');
        tag.className = 'cfe-note-tag' + (note === activeNote ? ' active' : '');
        tag.textContent = note;
        tag.addEventListener('click', function () {
          activeNote = (activeNote === note) ? null : note;
          update();
        });
        noteBar.appendChild(tag);
      });

      // Apply note sub-filter
      var afterNote = activeNote
        ? afterFamily.filter(function (p) { return p.flavor_notes.indexOf(activeNote) !== -1; })
        : afterFamily;

      // Sort
      var displayed = sortProducts(afterNote, sortBy, activeFamilies);

      countEl.textContent = 'Showing ' + displayed.length + ' of ' + allProducts.length + ' beans';

      // Re-render grid
      destroyCharts(grid);
      grid.innerHTML = '';
      displayed.forEach(function (product) {
        grid.appendChild(buildCard(product));
      });

      // Init mini radar charts after insertion
      grid.querySelectorAll('.cfe-radar-canvas').forEach(function (canvas) {
        var pid = canvas.dataset.productId;
        var product = allProducts.find(function (p) { return p.id === pid; });
        if (product) {
          var chart = buildRadarChart(canvas, product.scores, 120, false);
          chartRegistry.set(canvas, chart);
        }
      });
    }

    update();
  }

  // ---------------------------------------------------------------------------
  // Filter / sort helpers
  // ---------------------------------------------------------------------------

  function filterByFamilies(products, activeFamilies) {
    if (activeFamilies.size === 0) return products;
    return products.filter(function (p) {
      return p.note_families.some(function (f) { return activeFamilies.has(f); });
    });
  }

  function collectNotes(products) {
    var notes = [];
    products.forEach(function (p) {
      p.flavor_notes.forEach(function (n) {
        if (notes.indexOf(n) === -1) notes.push(n);
      });
    });
    return notes;
  }

  function sortProducts(products, sortBy, activeFamilies) {
    var result = products.slice();
    if (sortBy === 'relevance' && activeFamilies.size > 0) {
      result.sort(function (a, b) {
        var aScore = a.note_families.filter(function (f) { return activeFamilies.has(f); }).length;
        var bScore = b.note_families.filter(function (f) { return activeFamilies.has(f); }).length;
        return bScore - aScore;
      });
    } else if (sortBy === 'price') {
      result.sort(function (a, b) {
        var ap = (a.price_per_oz != null) ? a.price_per_oz : Infinity;
        var bp = (b.price_per_oz != null) ? b.price_per_oz : Infinity;
        return ap - bp;
      });
    } else if (sortBy === 'rating') {
      result.sort(function (a, b) {
        var aSum = Object.values(a.scores).reduce(function (s, v) { return s + v; }, 0);
        var bSum = Object.values(b.scores).reduce(function (s, v) { return s + v; }, 0);
        return bSum - aSum;
      });
    }
    return result;
  }

  // ---------------------------------------------------------------------------
  // Product card
  // ---------------------------------------------------------------------------

  function buildCard(product) {
    var card = document.createElement('div');
    card.className = 'cfe-card';

    var nameEl = document.createElement('h3');
    nameEl.className = 'cfe-card-name';
    var nameLink = document.createElement('a');
    nameLink.href = '/' + product.review_slug + '/';
    nameLink.textContent = product.name;
    nameEl.appendChild(nameLink);
    card.appendChild(nameEl);

    var meta = document.createElement('div');
    meta.className = 'cfe-card-meta';
    meta.textContent = product.brand + ' · ' + product.roast_level;
    card.appendChild(meta);

    var canvas = document.createElement('canvas');
    canvas.className = 'cfe-radar-canvas';
    canvas.dataset.productId = product.id;
    canvas.width = 120;
    canvas.height = 120;
    card.appendChild(canvas);

    var notesDiv = document.createElement('div');
    notesDiv.className = 'cfe-card-notes';
    product.flavor_notes.forEach(function (note) {
      var pill = document.createElement('button');
      pill.className = 'cfe-note-pill';
      pill.textContent = note;
      pill.addEventListener('click', function () {
        pill.dispatchEvent(new CustomEvent('cfe:note-click', {
          bubbles: true,
          detail: { note: note },
        }));
      });
      notesDiv.appendChild(pill);
    });
    card.appendChild(notesDiv);

    var actions = document.createElement('div');
    actions.className = 'cfe-card-actions';

    var reviewBtn = document.createElement('a');
    reviewBtn.href = '/' + product.review_slug + '/';
    reviewBtn.className = 'cfe-btn cfe-btn-review';
    reviewBtn.textContent = 'View Review';
    actions.appendChild(reviewBtn);

    if (product.affiliate_url) {
      var priceBtn = document.createElement('a');
      priceBtn.href = product.affiliate_url;
      priceBtn.className = 'cfe-btn cfe-btn-price';
      priceBtn.textContent = 'Check Price →';
      priceBtn.target = '_blank';
      priceBtn.rel = 'noopener nofollow';
      actions.appendChild(priceBtn);
    }

    card.appendChild(actions);
    return card;
  }

  // ---------------------------------------------------------------------------
  // Standalone radar (coffee_profile shortcode)
  // ---------------------------------------------------------------------------

  function renderStandaloneRadar(el, product) {
    var canvas = document.createElement('canvas');
    canvas.className = 'cfe-standalone-canvas';
    canvas.width = 250;
    canvas.height = 250;
    el.appendChild(canvas);

    var chart = buildRadarChart(canvas, product.scores, 250, true);
    chartRegistry.set(canvas, chart);

    var notesDiv = document.createElement('div');
    notesDiv.className = 'cfe-standalone-notes';
    product.flavor_notes.forEach(function (note) {
      var tag = document.createElement('span');
      tag.className = 'cfe-standalone-note';
      tag.textContent = note;
      notesDiv.appendChild(tag);
    });
    el.appendChild(notesDiv);
  }

  // ---------------------------------------------------------------------------
  // Chart creation
  // ---------------------------------------------------------------------------

  function buildRadarChart(canvas, scores, size, showLabels) {
    var rootStyle = getComputedStyle(document.documentElement);
    var fill   = rootStyle.getPropertyValue('--cfe-radar-fill').trim()   || 'rgba(139, 90, 43, 0.25)';
    var border = rootStyle.getPropertyValue('--cfe-radar-border').trim() || 'rgba(139, 90, 43, 0.8)';

    return new Chart(canvas, {
      type: 'radar',
      data: {
        labels: ['Acidity', 'Body', 'Sweetness', 'Bitterness', 'Roast'],
        datasets: [{
          data: [
            scores.acidity,
            scores.body,
            scores.sweetness,
            scores.bitterness,
            scores.roast_intensity,
          ],
          backgroundColor: fill,
          borderColor: border,
          borderWidth: 2,
          pointRadius: 2,
          pointBackgroundColor: border,
        }],
      },
      options: {
        responsive: false,
        plugins: {
          legend: { display: false },
        },
        scales: {
          r: {
            min: 0,
            max: 5,
            ticks: {
              stepSize: 1,
              display: false,
            },
            grid: {
              lineWidth: 0.5,
              color: 'rgba(0, 0, 0, 0.08)',
            },
            angleLines: {
              lineWidth: 0.5,
              color: 'rgba(0, 0, 0, 0.08)',
            },
            pointLabels: {
              display: showLabels,
              font: { size: 10 },
            },
          },
        },
      },
    });
  }

  // ---------------------------------------------------------------------------
  // Chart cleanup
  // ---------------------------------------------------------------------------

  function destroyCharts(container) {
    container.querySelectorAll('canvas').forEach(function (canvas) {
      if (chartRegistry.has(canvas)) {
        chartRegistry.get(canvas).destroy();
        chartRegistry.delete(canvas);
      }
    });
  }

})();
