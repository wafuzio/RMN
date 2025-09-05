// Global state for products and filters
let currentProducts = [];
let activeFilters = new Set();

document.addEventListener('DOMContentLoaded', function() {
    // Initialize secondary search toggle
    document.getElementById('enableSecondarySearch').addEventListener('change', function() {
        document.getElementById('secondarySearchSection').style.display = this.checked ? 'block' : 'none';
        if (!this.checked) {
            document.getElementById('secondaryQuery').value = '';
        }
    });
    // Initialize view toggle
    document.querySelectorAll('input[name="viewType"]').forEach(radio => {
        radio.addEventListener('change', function() {
            document.getElementById('resultsContainer').className = this.value + '-view';
        });
    });

    // Initialize sort select
    document.getElementById('sortSelect').addEventListener('change', function() {
        sortProducts(this.value);
    });

    // Initialize jQuery UI sortable
    $('#resultsGrid').sortable({
        items: '.col-md-4',
        handle: '.product-card',
        placeholder: 'col-md-4 ui-sortable-placeholder',
        update: updateSelectedAsins
    });

    // Initialize clipboard functionality
    document.getElementById('copyAsins').addEventListener('click', function() {
        const asinsText = document.getElementById('selectedAsins').value;
        if (asinsText) {
            navigator.clipboard.writeText(asinsText).then(() => {
                const tooltip = bootstrap.Tooltip.getInstance(this);
                this.setAttribute('data-bs-original-title', 'Copied!');
                tooltip.show();
                setTimeout(() => {
                    this.setAttribute('data-bs-original-title', 'Copy ASINs');
                    tooltip.hide();
                }, 2000);
            });
        }
    });

    // Initialize tooltips
    function initializeTooltips() {
        const tooltips = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
        tooltips.map(function (tooltipEl) {
            return new bootstrap.Tooltip(tooltipEl);
        });
    }
    initializeTooltips();
    // Handle search type toggle
    document.querySelectorAll('input[name="searchType"]').forEach(radio => {
        radio.addEventListener('change', function() {
            document.getElementById('keywordInput').style.display = 
                this.value === 'keyword' ? 'block' : 'none';
            document.getElementById('asinInput').style.display = 
                this.value === 'asin' ? 'block' : 'none';
        });
    });

    // Handle page type toggle
    document.querySelectorAll('input[name="pageType"]').forEach(radio => {
        radio.addEventListener('change', function() {
            document.getElementById('singlePageInput').style.display = 
                this.value === 'single' ? 'block' : 'none';
            document.getElementById('pageRangeInput').style.display = 
                this.value === 'range' ? 'block' : 'none';
        });
    });

    // Handle form submission
    document.getElementById('searchForm').addEventListener('submit', async function(e) {
        e.preventDefault();
        
        // Show loading spinner
        document.getElementById('loadingSpinner').style.display = 'block';
        document.getElementById('resultsGrid').innerHTML = '';
        
        // Gather form data
        const searchType = document.querySelector('input[name="searchType"]:checked').value;
        const pageType = document.querySelector('input[name="pageType"]:checked').value;
        
        const searchData = {
            maxItems: parseInt(document.getElementById('maxItems').value),
            mustInclude: document.getElementById('mustInclude').value,
            mustExclude: document.getElementById('mustExclude').value,
            matchType: document.querySelector('input[name="includeMatchType"]:checked').value,
            organicOnly: document.getElementById('organicOnly').checked,
            pages: pageType === 'single' 
                ? [parseInt(document.getElementById('pageNumber').value)]
                : Array.from(
                    { length: document.getElementById('endPage').value - document.getElementById('startPage').value + 1 },
                    (_, i) => parseInt(document.getElementById('startPage').value) + i
                  )
        };

        if (searchType === 'keyword') {
            searchData.primaryQuery = document.getElementById('searchQuery').value;
            searchData.secondaryQuery = document.getElementById('secondaryQuery').value;
            searchData.booleanOperator = document.getElementById('booleanOperator').value;
        }

        if (searchType === 'keyword') {
            searchData.query = document.getElementById('searchQuery').value;
        } else {
            searchData.asins = document.getElementById('asinList').value
                .split('\n')
                .map(asin => asin.trim())
                .filter(asin => asin);
        }

        try {
            const response = await fetch('/search', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(searchData)
            });

            const data = await response.json();
            
            if (data.error) {
                throw new Error(data.error);
            }
            
            if (!data.products || !Array.isArray(data.products)) {
                throw new Error('Invalid response format');
            }
            
            if (data.products.length === 0) {
                document.getElementById('resultsGrid').innerHTML = `
                    <div class="col-12 text-center mt-4">
                        <div class="alert alert-info" role="alert">
                            No products found matching your criteria. Try adjusting your search terms or filters.
                        </div>
                    </div>
                `;
            } else {
                displayResults(data.products);
                updateAnalysis(data.analysis);
            }
        } catch (error) {
            console.error('Error:', error);
            document.getElementById('resultsGrid').innerHTML = `
                <div class="col-12 text-center mt-4">
                    <div class="alert alert-danger" role="alert">
                        <h4 class="alert-heading">Error</h4>
                        <p>${error.message || 'An error occurred while fetching results.'}</p>
                        <hr>
                        <p class="mb-0">Please try again. If the problem persists, try adjusting your search parameters.</p>
                    </div>
                </div>
            `;
        } finally {
            document.getElementById('loadingSpinner').style.display = 'none';
        }
    });

    // Function to display search results
    function displayResults(products) {
        currentProducts = products; // Store products globally
        const resultsGrid = document.getElementById('resultsGrid');
        resultsGrid.innerHTML = '';

        products.forEach(product => {
            const card = document.createElement('div');
            card.className = 'col-md-4 col-lg-3';
            card.setAttribute('data-asin', product.asin);
            
            // Format rank display
            const rankNumber = product.primary_rank || '';
            
            card.innerHTML = `
                <div class="product-card">
                    <div class="product-actions">
                        <input type="checkbox" class="product-selector" data-asin="${product.asin}">
                    </div>
                    <div class="product-image">
                        <img src="${product.image_url}" alt="${product.title}" 
                             data-bs-toggle="modal" data-bs-target="#imageModal"
                             data-full-image="${product.image_url}">
                        ${rankNumber ? `<div class="product-rank">Rank ${rankNumber}</div>` : ''}
                    </div>
                    <div class="product-details">
                        <h3 class="product-title">${product.title}</h3>
                        <div class="product-price">$${parseFloat(product.price).toFixed(2)}</div>
                        <div class="product-meta">
                            <div>Rating: ${product.rating} ⭐ (${product.reviews_count} reviews)</div>
                            <div>ASIN: ${product.asin}</div>
                            ${product.rank_1 ? `<div>Rank: #${product.rank_1} in ${product.category_1}</div>` : ''}
                            ${product.ships_from ? `<div>Ships from: ${product.ships_from}</div>` : ''}
                            ${product.sold_by ? `<div>Sold by: ${product.sold_by}</div>` : ''}
                        </div>
                        <a href="https://www.amazon.com/dp/${product.asin}" target="_blank" class="amazon-link">
                            <i class="bi bi-box-arrow-up-right"></i> View on Amazon
                        </a>
                    </div>
                </div>
            `;
            resultsGrid.appendChild(card);
        });

        // Initialize image modal functionality
        document.querySelectorAll('.product-image img').forEach(img => {
            img.addEventListener('click', function() {
                document.getElementById('modalImage').src = this.dataset.fullImage;
            });
        });
    }

    // Function to update analysis section
    function updateAnalysis(analysis) {
        // Update common words
        const wordsContainer = document.getElementById('commonWords');
        wordsContainer.innerHTML = analysis.words.map(item => `
            <span class="tag">
                ${item.word}
                <span class="count">(${item.count})</span>
            </span>
        `).join('');

        // Update common phrases with click handlers
        const phrasesContainer = document.getElementById('commonPhrases');
        phrasesContainer.innerHTML = analysis.phrases.map(item => `
            <span class="tag" data-phrase="${item.phrase}">
                ${item.phrase}
                <span class="count">(${item.count})</span>
            </span>
        `).join('');

        // Add click handlers for phrase filtering
        phrasesContainer.querySelectorAll('.tag').forEach(tag => {
            tag.addEventListener('click', function() {
                const phrase = this.dataset.phrase;
                togglePhraseFilter(phrase);
            });
        });
    }

    // Function to update selected ASINs
    // Function to sort products
    function sortProducts(sortType) {
        if (!currentProducts.length) return;
        
        const sortedProducts = [...currentProducts];
        
        switch (sortType) {
            case 'price-asc':
                sortedProducts.sort((a, b) => parseFloat(a.price) - parseFloat(b.price));
                break;
            case 'price-desc':
                sortedProducts.sort((a, b) => parseFloat(b.price) - parseFloat(a.price));
                break;
            case 'rating-desc':
                sortedProducts.sort((a, b) => parseFloat(b.rating) - parseFloat(a.rating));
                break;
            case 'reviews-desc':
                sortedProducts.sort((a, b) => parseInt(b.reviews_count.replace(',', '')) - parseInt(a.reviews_count.replace(',', '')));
                break;
            default:
                // Keep original order
                return;
        }
        
        displayResults(sortedProducts);
    }

    // Function to toggle phrase filters
    function togglePhraseFilter(phrase) {
        const activeFiltersDiv = document.getElementById('activeFilters');
        const filtersList = document.getElementById('activeFiltersList');
        const phraseTag = document.querySelector(`[data-phrase="${phrase}"]`);
        
        if (activeFilters.has(phrase)) {
            activeFilters.delete(phrase);
            phraseTag.classList.remove('active');
            
            // If no filters remain, show all products
            if (activeFilters.size === 0) {
                displayResults(currentProducts);
                activeFiltersDiv.style.display = 'none';
                return;
            }
        } else {
            activeFilters.add(phrase);
            phraseTag.classList.add('active');
        }
        
        // Update active filters display
        filtersList.innerHTML = Array.from(activeFilters).map(filter => `
            <span class="filter-badge">
                ${filter}
                <span class="remove" onclick="removeFilter('${filter}')">×</span>
            </span>
        `).join('');
        activeFiltersDiv.style.display = activeFilters.size > 0 ? 'block' : 'none';
        
        // Filter products
        const filteredProducts = currentProducts.filter(product => {
            const title = product.title.toLowerCase();
            return Array.from(activeFilters).some(filter => title.includes(filter.toLowerCase()));
        });
        
        displayResults(filteredProducts);
    }

    // Function to remove a specific filter
    window.removeFilter = function(phrase) {
        togglePhraseFilter(phrase);
    };

    // Function to clear all filters
    window.clearFilters = function() {
        activeFilters.clear();
        document.querySelectorAll('#commonPhrases .tag').forEach(tag => {
            tag.classList.remove('active');
        });
        document.getElementById('activeFilters').style.display = 'none';
        displayResults(currentProducts);
    };

    function updateSelectedAsins() {
        const selectedProducts = document.querySelectorAll('.product-selector:checked');
        const asins = Array.from(selectedProducts).map(checkbox => checkbox.dataset.asin);
        const asinsSection = document.getElementById('selectedAsinsSection');
        
        if (asins.length > 0) {
            document.getElementById('selectedAsins').value = asins.join(', ');
            asinsSection.style.display = 'block';
            asinsSection.classList.remove('hidden');
        } else {
            asinsSection.classList.add('hidden');
            setTimeout(() => {
                asinsSection.style.display = 'none';
            }, 300);
        }
    }

    // Handle product selection
    document.addEventListener('change', function(e) {
        if (e.target.classList.contains('product-selector')) {
            updateSelectedAsins();
        }
    });

    // Initialize tooltips
    function initializeTooltips() {
        const tooltips = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
        tooltips.map(function (tooltipEl) {
            return new bootstrap.Tooltip(tooltipEl);
        });
    }
    initializeTooltips();
});
