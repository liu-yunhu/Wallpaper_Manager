// Main application JavaScript
class WallpaperManager {
    constructor() {
        this.wallpapers = {
            subscribed: [],
            unsubscribed: []
        };
        this.selectedWallpapers = new Set();
        this.currentWallpaper = null;
        this.users = [];
        this.currentUserFilter = 'all';
        this.currentSearchQuery = '';
        this.searchHistory = [];

        // 分页相关状态
        this.subscribedPage = 1;
        this.unsubscribedPage = 1;
        this.pageSize = 20;
        this.pageSizeOptions = [10, 20, 50];
        this.subscribedTotal = 0;
        this.unsubscribedTotal = 0;
        this.subscribedTotalPages = 1;
        this.unsubscribedTotalPages = 1;

        this.init();
    }
    
    init() {
        this.setupEventListeners();
        this.loadConfiguration();
        this.loadUsers();
        this.loadSearchHistory();
        this.loadData();
    }
    
    setupEventListeners() {
        // 搜索按钮点击触发搜索
        const searchButton = document.getElementById('searchButton');
        if (searchButton) {
            searchButton.addEventListener('click', () => this.executeSearch());
        }

        // 搜索输入框回车键触发搜索
        const searchInput = document.getElementById('searchInput');
        if (searchInput) {
            searchInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    this.executeSearch();
                }
            });
            // 点击输入框时显示搜索历史
            searchInput.addEventListener('focus', () => {
                if (this.searchHistory.length > 0) {
                    this.showHistoryDropdown();
                }
            });
        }

        // 搜索历史切换按钮
        const historyToggle = document.getElementById('searchHistoryToggle');
        if (historyToggle) {
            historyToggle.addEventListener('click', (e) => {
                e.stopPropagation();
                this.toggleHistoryDropdown();
            });
        }

        // 清除历史按钮
        const clearHistoryButton = document.getElementById('clearHistoryButton');
        if (clearHistoryButton) {
            clearHistoryButton.addEventListener('click', (e) => {
                e.stopPropagation();
                this.clearSearchHistory();
            });
        }

        // 点击页面其他地方关闭历史下拉
        document.addEventListener('click', (e) => {
            const dropdown = document.getElementById('searchHistoryDropdown');
            const wrapper = document.querySelector('.search-wrapper');
            if (dropdown && wrapper && !wrapper.contains(e.target)) {
                dropdown.style.display = 'none';
            }
        });
        
        // User filter
        const userFilter = document.getElementById('userFilter');
        if (userFilter) {
            userFilter.addEventListener('change', (e) => {
                this.currentUserFilter = e.target.value;
                this.loadData();
                this.loadStatistics(); // Also update statistics when user changes
            });
        }
        
        // Select all checkbox
        const selectAll = document.getElementById('selectAll');
        if (selectAll) {
            selectAll.addEventListener('change', (e) => {
                this.toggleSelectAll(e.target.checked);
            });
        }
        
        // Tab change events
        const tabLinks = document.querySelectorAll('[data-bs-toggle="tab"]');
        tabLinks.forEach(tab => {
            tab.addEventListener('shown.bs.tab', () => {
                this.updateSelectAllState();
            });
        });
    }
    
    async loadConfiguration() {
        try {
            const response = await fetch('/api/config');
            const result = await response.json();
            
            if (result.success) {
                this.populateConfigForm(result.data);
            }
        } catch (error) {
            console.error('Error loading configuration:', error);
        }
    }
    
    populateConfigForm(config) {
        const steamLibraryPath = document.getElementById('steamLibraryPath');
        const steamUserdataPath = document.getElementById('steamUserdataPath');
        const serverPort = document.getElementById('serverPort');
        const debugMode = document.getElementById('debugMode');
        
        if (steamLibraryPath) steamLibraryPath.value = config.steam_library_path || '';
        if (steamUserdataPath) steamUserdataPath.value = config.steam_userdata_path || '';
        if (serverPort) serverPort.value = config.server?.port || 5000;
        if (debugMode) debugMode.checked = config.server?.debug || false;
    }
    
    async loadUsers() {
        try {
            const response = await fetch('/api/users');
            const result = await response.json();
            
            if (result.success) {
                this.users = result.data;
                this.populateUserFilter();
            } else {
                console.error('Error loading users:', result.error);
            }
        } catch (error) {
            console.error('Error loading users:', error);
        }
    }
    
    populateUserFilter() {
        const userFilter = document.getElementById('userFilter');
        if (!userFilter) return;
        
        // Clear existing options except "所有用户"
        while (userFilter.children.length > 1) {
            userFilter.removeChild(userFilter.lastChild);
        }
        
        // Add user options
        this.users.forEach(user => {
            const option = document.createElement('option');
            option.value = user.id;
            option.textContent = `${user.display_name} (${user.subscription_count} 订阅)`;
            userFilter.appendChild(option);
        });
    }
    
    async loadData() {
        this.showLoading(true);
        try {
            // 使用单个请求加载数据，但传递各自的页码
            await this.loadWallpaperData();
            
            this.renderWallpapers();
            this.renderPagination();
            this.loadStatistics();
            
            setTimeout(() => {
                if (typeof checkSteamPathStatus === 'function') {
                    checkSteamPathStatus();
                }
            }, 100);
        } catch (error) {
            console.error('Error loading data:', error);
            this.showToast('Error loading data: ' + error.message, 'error');
        } finally {
            this.showLoading(false);
        }
    }

    async loadWallpaperData() {
        try {
            let url = '/api/wallpapers?';
            const params = new URLSearchParams();
            if (this.currentSearchQuery) {
                params.append('search', this.currentSearchQuery);
            }
            if (this.currentUserFilter && this.currentUserFilter !== 'all') {
                params.append('user', this.currentUserFilter);
            }
            // 分别传递已订阅和未订阅的页码
            params.append('subscribed_page', this.subscribedPage);
            params.append('unsubscribed_page', this.unsubscribedPage);
            params.append('page_size', this.pageSize);
            url += params.toString();
            
            const wallpaperResponse = await fetch(url);
            const wallpaperResult = await wallpaperResponse.json();
            
            if (wallpaperResult.success) {
                // 处理已订阅数据
                if (Array.isArray(wallpaperResult.data.subscribed)) {
                    this.wallpapers.subscribed = wallpaperResult.data.subscribed;
                    this.subscribedTotal = this.wallpapers.subscribed.length;
                    this.subscribedTotalPages = 1;
                } else {
                    const sub = wallpaperResult.data.subscribed;
                    this.wallpapers.subscribed = sub.wallpapers || [];
                    this.subscribedTotal = sub.total || 0;
                    this.subscribedTotalPages = sub.total_pages || 1;
                    // 服务端自动修正页码，前端同步
                    if (sub.page && sub.page !== this.subscribedPage) {
                        this.subscribedPage = sub.page;
                    }
                }

                // 处理未订阅数据
                if (Array.isArray(wallpaperResult.data.unsubscribed)) {
                    this.wallpapers.unsubscribed = wallpaperResult.data.unsubscribed;
                    this.unsubscribedTotal = this.wallpapers.unsubscribed.length;
                    this.unsubscribedTotalPages = 1;
                } else {
                    const unsub = wallpaperResult.data.unsubscribed;
                    this.wallpapers.unsubscribed = unsub.wallpapers || [];
                    this.unsubscribedTotal = unsub.total || 0;
                    this.unsubscribedTotalPages = unsub.total_pages || 1;
                    // 服务端自动修正页码，前端同步
                    if (unsub.page && unsub.page !== this.unsubscribedPage) {
                        this.unsubscribedPage = unsub.page;
                    }
                }
            } else {
                this.showToast('Error loading wallpapers: ' + wallpaperResult.error, 'error');
            }
        } catch (error) {
            console.error('Error loading wallpaper data:', error);
            throw error;
        }
    }

    // ==================== 搜索功能 ====================

    executeSearch() {
        const searchInput = document.getElementById('searchInput');
        if (!searchInput) return;
        const keyword = searchInput.value.trim();
        this.currentSearchQuery = keyword;
        // 重置分页到第一页
        this.subscribedPage = 1;
        this.unsubscribedPage = 1;
        this.loadData();
        // 保存搜索关键词到历史
        if (keyword) {
            this.saveSearchHistory(keyword);
        }
        // 关闭历史下拉
        const dropdown = document.getElementById('searchHistoryDropdown');
        if (dropdown) dropdown.style.display = 'none';
    }

    async loadSearchHistory() {
        try {
            const response = await fetch('/api/search-history');
            const result = await response.json();
            if (result.success) {
                this.searchHistory = result.data || [];
            }
        } catch (error) {
            console.error('加载搜索历史失败:', error);
        }
    }

    async saveSearchHistory(keyword) {
        try {
            const response = await fetch('/api/search-history', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ keyword })
            });
            const result = await response.json();
            if (result.success) {
                this.searchHistory = result.data || [];
                this.renderSearchHistory();
            }
        } catch (error) {
            console.error('保存搜索历史失败:', error);
        }
    }

    async clearSearchHistory() {
        try {
            const response = await fetch('/api/search-history', {
                method: 'DELETE'
            });
            const result = await response.json();
            if (result.success) {
                this.searchHistory = [];
                this.renderSearchHistory();
                const dropdown = document.getElementById('searchHistoryDropdown');
                if (dropdown) dropdown.style.display = 'none';
            }
        } catch (error) {
            console.error('清除搜索历史失败:', error);
        }
    }

    showHistoryDropdown() {
        this.renderSearchHistory();
        const dropdown = document.getElementById('searchHistoryDropdown');
        if (dropdown) dropdown.style.display = 'block';
    }

    toggleHistoryDropdown() {
        const dropdown = document.getElementById('searchHistoryDropdown');
        if (!dropdown) return;
        if (dropdown.style.display === 'none' || !dropdown.style.display) {
            this.showHistoryDropdown();
        } else {
            dropdown.style.display = 'none';
        }
    }

    renderSearchHistory() {
        const list = document.getElementById('searchHistoryList');
        if (!list) return;
        if (this.searchHistory.length === 0) {
            list.innerHTML = '<li class="search-history-empty">暂无搜索历史</li>';
            return;
        }
        list.innerHTML = '';
        this.searchHistory.forEach(keyword => {
            const li = document.createElement('li');
            li.className = 'search-history-item';
            li.title = `点击重新搜索: ${keyword}`;
            li.dataset.keyword = keyword;
            li.innerHTML = `
                <i class="fas fa-search search-history-item-icon"></i>
                <span class="search-history-item-text"></span>
            `;
            li.querySelector('.search-history-item-text').textContent = keyword;
            li.addEventListener('click', (e) => {
                e.stopPropagation();
                this.searchFromHistory(keyword);
            });
            list.appendChild(li);
        });
    }

    searchFromHistory(keyword) {
        const searchInput = document.getElementById('searchInput');
        if (searchInput) searchInput.value = keyword;
        this.currentSearchQuery = keyword;
        this.subscribedPage = 1;
        this.unsubscribedPage = 1;
        this.loadData();
        const dropdown = document.getElementById('searchHistoryDropdown');
        if (dropdown) dropdown.style.display = 'none';
    }

    renderPagination() {
        // 已订阅分页
        this.renderPageInfo('subscribedPageInfo', this.subscribedPage, this.pageSize, this.subscribedTotal);
        this.renderPaginationControls('subscribedPaginationControls', 'subscribed',
            this.subscribedPage, this.subscribedTotal, this.subscribedTotalPages,
            (page) => { this.subscribedPage = page; this.loadData(); });

        // 未订阅分页
        this.renderPageInfo('unsubscribedPageInfo', this.unsubscribedPage, this.pageSize, this.unsubscribedTotal);
        this.renderPaginationControls('unsubscribedPaginationControls', 'unsubscribed',
            this.unsubscribedPage, this.unsubscribedTotal, this.unsubscribedTotalPages,
            (page) => { this.unsubscribedPage = page; this.loadData(); });
    }

    /**
     * 渲染分页控件区：翻页按钮 + 每页条数选择器 + 页码跳转
     */
    renderPaginationControls(containerId, prefix, currentPage, totalItems, totalPages, onPageChange) {
        const container = document.getElementById(containerId);
        if (!container) return;
        container.innerHTML = '';

        // 空数据：隐藏整个工具栏
        if (totalItems === 0) {
            const toolbar = document.getElementById(prefix + 'Toolbar');
            if (toolbar) toolbar.style.display = 'none';
            return;
        }
        const toolbar = document.getElementById(prefix + 'Toolbar');
        if (toolbar) toolbar.style.display = '';

        // 翻页按钮
        const nav = document.createElement('nav');
        nav.setAttribute('aria-label', 'Pagination');
        const ul = document.createElement('ul');
        ul.className = 'pagination mb-0';
        this._buildPaginationButtons(ul, currentPage, totalPages, onPageChange);
        nav.appendChild(ul);
        container.appendChild(nav);

        // 每页条数选择器
        container.appendChild(this._createPageSizeSelect());

        // 页码跳转
        container.appendChild(this._createPageJump(currentPage, totalPages, onPageChange));
    }

    /**
     * 构建翻页按钮（首页 + 上一页 + 页码 + 下一页 + 尾页）
     */
    _buildPaginationButtons(ul, currentPage, totalPages, onPageChange) {
        // 首页
        const firstLi = document.createElement('li');
        firstLi.className = 'page-item' + (currentPage <= 1 ? ' disabled' : '');
        firstLi.innerHTML = `<a class="page-link" href="#" aria-label="首页"><i class="fas fa-angle-double-left"></i></a>`;
        firstLi.onclick = (e) => { e.preventDefault(); if (currentPage > 1) onPageChange(1); };
        ul.appendChild(firstLi);

        // 上一页
        const prevLi = document.createElement('li');
        prevLi.className = 'page-item' + (currentPage <= 1 ? ' disabled' : '');
        prevLi.innerHTML = `<a class="page-link" href="#" aria-label="上一页"><i class="fas fa-chevron-left"></i></a>`;
        prevLi.onclick = (e) => { e.preventDefault(); if (currentPage > 1) onPageChange(currentPage - 1); };
        ul.appendChild(prevLi);

        // 页码按钮
        const pages = this._buildPageNumbers(currentPage, totalPages);
        pages.forEach(p => {
            if (p === '...') {
                const li = document.createElement('li');
                li.className = 'page-item disabled';
                li.innerHTML = `<span class="page-link">...</span>`;
                ul.appendChild(li);
            } else {
                const li = document.createElement('li');
                li.className = 'page-item' + (p === currentPage ? ' active' : '');
                li.innerHTML = `<a class="page-link" href="#">${p}</a>`;
                li.onclick = (e) => { e.preventDefault(); if (p !== currentPage) onPageChange(p); };
                ul.appendChild(li);
            }
        });

        // 下一页
        const nextLi = document.createElement('li');
        nextLi.className = 'page-item' + (currentPage >= totalPages ? ' disabled' : '');
        nextLi.innerHTML = `<a class="page-link" href="#" aria-label="下一页"><i class="fas fa-chevron-right"></i></a>`;
        nextLi.onclick = (e) => { e.preventDefault(); if (currentPage < totalPages) onPageChange(currentPage + 1); };
        ul.appendChild(nextLi);

        // 尾页
        const lastLi = document.createElement('li');
        lastLi.className = 'page-item' + (currentPage >= totalPages ? ' disabled' : '');
        lastLi.innerHTML = `<a class="page-link" href="#" aria-label="尾页"><i class="fas fa-angle-double-right"></i></a>`;
        lastLi.onclick = (e) => { e.preventDefault(); if (currentPage < totalPages) onPageChange(totalPages); };
        ul.appendChild(lastLi);
    }

    /**
     * 创建每页条数选择器 DOM
     */
    _createPageSizeSelect() {
        const wrapper = document.createElement('div');
        wrapper.className = 'page-size-wrap';
        const select = document.createElement('select');
        select.className = 'form-select page-size-select';
        select.setAttribute('aria-label', '每页条数');
        this.pageSizeOptions.forEach(opt => {
            const option = document.createElement('option');
            option.value = opt;
            option.textContent = `${opt} 条/页`;
            if (opt === this.pageSize) option.selected = true;
            select.appendChild(option);
        });
        select.addEventListener('change', (e) => {
            this.onPageSizeChange(parseInt(e.target.value));
        });
        wrapper.appendChild(select);
        return wrapper;
    }

    /**
     * 创建页码跳转组件 DOM
     */
    _createPageJump(currentPage, totalPages, onPageChange) {
        const wrapper = document.createElement('div');
        wrapper.className = 'page-jump-wrap';

        const label = document.createElement('span');
        label.className = 'page-jump-label';
        label.textContent = '跳至';

        const input = document.createElement('input');
        input.type = 'text';
        input.className = 'page-jump-input';
        input.placeholder = String(currentPage);
        input.setAttribute('aria-label', '跳转页码');
        input.maxLength = 6;

        const total = document.createElement('span');
        total.className = 'page-jump-total';
        total.textContent = `/ ${totalPages} 页`;

        const btn = document.createElement('button');
        btn.className = 'page-jump-btn';
        btn.textContent = 'GO';
        btn.setAttribute('aria-label', '跳转');

        const doJump = () => {
            const val = parseInt(input.value, 10);
            if (isNaN(val) || val < 1) {
                input.value = '';
                input.focus();
                return;
            }
            const target = Math.min(val, totalPages);
            if (target !== currentPage) {
                onPageChange(target);
            }
            input.value = '';
        };

        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                doJump();
            }
        });
        btn.addEventListener('click', doJump);

        wrapper.appendChild(label);
        wrapper.appendChild(input);
        wrapper.appendChild(total);
        wrapper.appendChild(btn);
        return wrapper;
    }

    /**
     * 构建页码数组，自动处理省略号
     * 始终显示首页、末页、当前页及前后各2页；仅跳过 >=2 页的间隙才显示省略号
     */
    _buildPageNumbers(currentPage, totalPages) {
        if (totalPages <= 7) {
            return Array.from({ length: totalPages }, (_, i) => i + 1);
        }

        // 收集必须显示的页码：首页、末页、当前页 ±2
        const range = new Set();
        range.add(1);
        range.add(totalPages);
        for (let i = Math.max(1, currentPage - 2); i <= Math.min(totalPages, currentPage + 2); i++) {
            range.add(i);
        }

        let sorted = [...range].sort((a, b) => a - b);

        // 消除仅1页的孤立间隙：gap==2 时把中间那页也纳入显示
        const expanded = new Set(sorted);
        for (let i = 0; i < sorted.length - 1; i++) {
            if (sorted[i + 1] - sorted[i] === 2) {
                expanded.add(sorted[i] + 1);
            }
        }
        sorted = [...expanded].sort((a, b) => a - b);

        // 拼接结果：gap > 2 处插入省略号
        const pages = [];
        for (let i = 0; i < sorted.length - 1; i++) {
            pages.push(sorted[i]);
            if (sorted[i + 1] - sorted[i] > 2) {
                pages.push('...');
            }
        }
        pages.push(sorted[sorted.length - 1]);
        return pages;
    }

    /**
     * 渲染"第 X-Y 条，共 Z 条"分页信息
     */
    renderPageInfo(containerId, currentPage, pageSize, totalItems) {
        const container = document.getElementById(containerId);
        if (!container) return;
        if (totalItems === 0) {
            container.textContent = '';
            return;
        }
        const start = (currentPage - 1) * pageSize + 1;
        const end = Math.min(currentPage * pageSize, totalItems);
        container.textContent = `第 ${start}-${end} 条，共 ${totalItems} 条`;
    }

    /**
     * 每页条数变更：重置到第一页并重新加载
     */
    onPageSizeChange(newSize) {
        if (newSize === this.pageSize) return;
        this.pageSize = newSize;
        this.subscribedPage = 1;
        this.unsubscribedPage = 1;
        this.loadData();
    }

    updateStatistics(stats) {
        document.getElementById('totalCount').textContent = stats.total.count;
        document.getElementById('totalSize').textContent = stats.total.size_formatted;
        
        document.getElementById('subscribedCount').textContent = stats.subscribed.count;
        document.getElementById('subscribedSize').textContent = stats.subscribed.size_formatted;
        
        document.getElementById('unsubscribedCount').textContent = stats.unsubscribed.count;
        document.getElementById('unsubscribedSize').textContent = stats.unsubscribed.size_formatted;
        
        document.getElementById('reclaimableSize').textContent = stats.unsubscribed.size_formatted;
        
        // Update badges
        document.getElementById('subscribedBadge').textContent = stats.subscribed.count;
        document.getElementById('unsubscribedBadge').textContent = stats.unsubscribed.count;
        
        // Update progress bar widths
        const totalSize = stats.total.size || 1; // Avoid division by zero
        const subscribedSize = stats.subscribed.size || 0;
        const unsubscribedSize = stats.unsubscribed.size || 0;
        
        const subscribedPercent = (subscribedSize / totalSize) * 100;
        const unsubscribedPercent = (unsubscribedSize / totalSize) * 100;
        
        const subscribedSegment = document.getElementById('subscribedSegment');
        const unsubscribedSegment = document.getElementById('unsubscribedSegment');
        
        if (subscribedSegment && unsubscribedSegment) {
            subscribedSegment.style.width = subscribedPercent + '%';
            unsubscribedSegment.style.width = unsubscribedPercent + '%';
            
            // Hide label if segment is too small
            const subscribedLabel = subscribedSegment.querySelector('.storage-label');
            const unsubscribedLabel = unsubscribedSegment.querySelector('.storage-label');
            
            if (subscribedLabel) {
                subscribedLabel.style.display = subscribedPercent < 15 ? 'none' : 'block';
            }
            if (unsubscribedLabel) {
                unsubscribedLabel.style.display = unsubscribedPercent < 15 ? 'none' : 'block';
            }
        }
    }
    
    async loadStatistics() {
        try {
            // Build stats URL with user filter
            let statsUrl = '/api/stats';
            if (this.currentUserFilter && this.currentUserFilter !== 'all') {
                statsUrl += `?user=${this.currentUserFilter}`;
            }
            
            const statsResponse = await fetch(statsUrl);
            const statsResult = await statsResponse.json();
            
            if (statsResult.success) {
                this.updateStatistics(statsResult.data);
            }
        } catch (error) {
            console.error('Error loading statistics:', error);
        }
    }
    
    renderWallpapers() {
        this.renderWallpaperGrid('subscribedWallpapers', this.wallpapers.subscribed, false);
        this.renderWallpaperGrid('unsubscribedWallpapers', this.wallpapers.unsubscribed, true);
    }
    
    renderWallpaperGrid(containerId, wallpapers, showCheckbox = false) {
        const container = document.getElementById(containerId);
        if (!container) return;
        
        if (wallpapers.length === 0) {
            container.innerHTML = `
                <div class="empty-state col-12">
                    <i class="fas fa-images"></i>
                    <h5>没有找到壁纸</h5>
                    <p class="text-muted">当前分类下暂无壁纸数据</p>
                </div>
            `;
            return;
        }
        
        // log
        // console.log(`[DEBUG] 渲染 ${containerId}，加载壁纸数量:`, wallpapers.length);
        // wallpapers.slice(0, 5).forEach((wp, idx) => {
        //     console.log(`[DEBUG] 壁纸${idx+1}:`, wp.id, wp.title, wp.size_formatted);
        // });


        container.innerHTML = wallpapers.map(wallpaper => 
            this.createWallpaperCard(wallpaper, showCheckbox)
        ).join('');
        
        // Load preview images
        this.loadPreviewImages(container);
    }
    
    createWallpaperCard(wallpaper, showCheckbox = false) {
        const statusClass = wallpaper.subscribed ? 'status-subscribed' : 'status-unsubscribed';
        const statusText = wallpaper.subscribed ? '已订阅' : '未订阅';
        
        // Create user subscription info
        let userInfo = '';
        if (wallpaper.subscribed_by_users !== undefined) {
            if (wallpaper.subscribed_by_users > 0) {
                userInfo = `<small class="text-muted">👥 ${wallpaper.subscribed_by_users} 用户订阅</small>`;
            } else {
                userInfo = `<small class="text-muted">👥 无用户订阅</small>`;
            }
        }
        
        return `
            <div class="wallpaper-card" data-id="${wallpaper.id}" onclick="wallpaperManager.showWallpaperDetail('${wallpaper.id}')">
                ${showCheckbox ? `
                    <div class="wallpaper-checkbox">
                        <input type="checkbox" class="form-check-input" 
                               onclick="event.stopPropagation(); wallpaperManager.toggleWallpaperSelection('${wallpaper.id}', this.checked)">
                    </div>
                ` : ''}
                
                <div class="wallpaper-preview loading" data-id="${wallpaper.id}">
                    <i class="fas fa-image fa-2x"></i>
                </div>
                
                <div class="wallpaper-info">
                    <div class="wallpaper-title">${wallpaper.title}</div>
                    <div class="wallpaper-meta">
                        <span class="wallpaper-id">ID: ${wallpaper.id}</span>
                        <span class="wallpaper-size">${wallpaper.size_formatted}</span>
                    </div>
                    <div class="wallpaper-status">
                        <span class="badge ${statusClass}">${statusText}</span>
                        ${userInfo}
                    </div>
                </div>
            </div>
        `;
    }
    
    async loadPreviewImages(container) {
        const previewElements = container.querySelectorAll('.wallpaper-preview[data-id]');
        
        for (const element of previewElements) {
            const wallpaperId = element.dataset.id;
            try {
                const img = document.createElement('img');
                img.src = `/api/wallpapers/${wallpaperId}/preview`;
                img.alt = 'Preview';
                img.onerror = () => {
                    element.innerHTML = '<i class="fas fa-image-slash fa-2x"></i><br><small>无预览</small>';
                    element.classList.remove('loading');
                };
                img.onload = () => {
                    element.innerHTML = '';
                    element.appendChild(img);
                    element.classList.remove('loading');
                };
            } catch (error) {
                element.innerHTML = '<i class="fas fa-exclamation-triangle fa-2x"></i><br><small>加载失败</small>';
                element.classList.remove('loading');
            }
        }
        // 统计当前页面 img 元素数量和总像素
        // setTimeout(() => {
        //     const imgs = container.querySelectorAll('img');
        //     let totalPixels = 0;
        //     imgs.forEach(img => {
        //         totalPixels += (img.naturalWidth || 0) * (img.naturalHeight || 0);
        //     });
        //     console.log(`[DEBUG] 当前页面图片数量: ${imgs.length}, 总像素: ${totalPixels}`);
        //     imgs.forEach((img, idx) => {
        //         console.log(`[DEBUG] 图片${idx+1}: src=${img.src}, size=${img.naturalWidth}x${img.naturalHeight}`);
        //     });
        // }, 1000);
    }
    
    toggleWallpaperSelection(wallpaperId, selected) {
        if (selected) {
            this.selectedWallpapers.add(wallpaperId);
        } else {
            this.selectedWallpapers.delete(wallpaperId);
        }
        
        this.updateSelectAllState();
    }
    
    toggleSelectAll(selectAll) {
        const activeTab = document.querySelector('.tab-pane.active');
        const checkboxes = activeTab.querySelectorAll('.wallpaper-checkbox input[type="checkbox"]');
        
        checkboxes.forEach(checkbox => {
            checkbox.checked = selectAll;
            const wallpaperId = checkbox.closest('.wallpaper-card').dataset.id;
            this.toggleWallpaperSelection(wallpaperId, selectAll);
        });
    }
    
    updateSelectAllState() {
        const activeTab = document.querySelector('.tab-pane.active');
        const checkboxes = activeTab.querySelectorAll('.wallpaper-checkbox input[type="checkbox"]');
        const selectAllCheckbox = document.getElementById('selectAll');
        
        if (!selectAllCheckbox || checkboxes.length === 0) return;
        
        const checkedCount = Array.from(checkboxes).filter(cb => cb.checked).length;
        
        if (checkedCount === 0) {
            selectAllCheckbox.indeterminate = false;
            selectAllCheckbox.checked = false;
        } else if (checkedCount === checkboxes.length) {
            selectAllCheckbox.indeterminate = false;
            selectAllCheckbox.checked = true;
        } else {
            selectAllCheckbox.indeterminate = true;
        }
    }
    
    async showWallpaperDetail(wallpaperId) {
        try {
            const response = await fetch(`/api/wallpapers/${wallpaperId}`);
            const result = await response.json();
            
            if (result.success) {
                this.currentWallpaper = result.data;
                this.populateDetailModal(result.data);
                
                const modal = new bootstrap.Modal(document.getElementById('wallpaperModal'));
                modal.show();
            } else {
                this.showToast('Error loading wallpaper details: ' + result.error, 'error');
            }
        } catch (error) {
            console.error('Error loading wallpaper details:', error);
            this.showToast('Error loading wallpaper details: ' + error.message, 'error');
        }
    }
    
    populateDetailModal(wallpaper) {
        document.getElementById('wallpaperModalTitle').textContent = wallpaper.title;
        document.getElementById('wallpaperDetailId').textContent = wallpaper.id;
        document.getElementById('wallpaperDetailTitle').textContent = wallpaper.title;
        document.getElementById('wallpaperDetailSize').textContent = wallpaper.size_formatted;
        document.getElementById('wallpaperDetailStatus').innerHTML = 
            `<span class="badge ${wallpaper.subscribed ? 'status-subscribed' : 'status-unsubscribed'}">
                ${wallpaper.subscribed ? '已订阅' : '未订阅'}
            </span>`;
        
        // Display subscription details by user
        const subscriptionDetailsElement = document.getElementById('wallpaperSubscriptionDetails');
        if (subscriptionDetailsElement && wallpaper.subscription_details) {
            let subscriptionHtml = '';
            
            if (wallpaper.subscription_details.length > 0) {
                subscriptionHtml = '<h6>订阅详情:</h6><ul class="list-unstyled">';
                wallpaper.subscription_details.forEach(detail => {
                    const statusIcon = detail.is_active ? '✅' : '❌';
                    const statusText = detail.is_active ? '活跃' : '已禁用';
                    const subscribeDate = detail.time_subscribed !== 'Unknown' ? 
                        new Date(parseInt(detail.time_subscribed) * 1000).toLocaleDateString() : '未知';
                    
                    subscriptionHtml += `
                        <li class="mb-2">
                            ${statusIcon} <strong>用户 ${detail.user_id}</strong> - ${statusText}
                            <br><small class="text-muted">订阅时间: ${subscribeDate}</small>
                        </li>
                    `;
                });
                subscriptionHtml += '</ul>';
            } else {
                subscriptionHtml = '<p class="text-muted">📭 没有任何用户订阅此项目</p>';
            }
            
            subscriptionDetailsElement.innerHTML = subscriptionHtml;
        }
        
        // Display path with proper formatting
        const pathElement = document.getElementById('wallpaperDetailPath');
        pathElement.textContent = wallpaper.path;
        pathElement.title = wallpaper.path; // Show full path on hover
        
        // Load large preview
        const previewImg = document.getElementById('wallpaperPreviewLarge');
        previewImg.src = `/api/wallpapers/${wallpaper.id}/preview`;
        
        // Show/hide delete button based on subscription status
        const deleteButton = document.getElementById('deleteButton');
        if (deleteButton) {
            deleteButton.style.display = wallpaper.subscribed ? 'none' : 'inline-block';
        }
    }
    
    filterWallpapers(searchTerm) {
        const term = searchTerm.toLowerCase();
        const cards = document.querySelectorAll('.wallpaper-card');
        
        cards.forEach(card => {
            const title = card.querySelector('.wallpaper-title').textContent.toLowerCase();
            const id = card.dataset.id.toLowerCase();
            
            if (title.includes(term) || id.includes(term)) {
                card.style.display = 'block';
            } else {
                card.style.display = 'none';
            }
        });
    }
    
    filterByStatus(status) {
        const subscribedTab = document.getElementById('subscribed-tab');
        const unsubscribedTab = document.getElementById('unsubscribed-tab');
        
        switch (status) {
            case 'subscribed':
                subscribedTab.click();
                break;
            case 'unsubscribed':
                unsubscribedTab.click();
                break;
            case 'all':
            default:
                // Show all - keep current tab
                break;
        }
    }
    
    showLoading(show) {
        const overlay = document.getElementById('loadingOverlay');
        if (overlay) {
            overlay.classList.toggle('hidden', !show);
        }
    }
    
    showToast(message, type = 'info') {
        const toast = document.getElementById('toast');
        const toastMessage = document.getElementById('toastMessage');
        
        if (toast && toastMessage) {
            toastMessage.textContent = message;
            
            // Update toast header icon based on type
            const icon = toast.querySelector('.toast-header i');
            if (icon) {
                icon.className = `fas ${type === 'error' ? 'fa-exclamation-triangle text-danger' : 'fa-info-circle text-primary'} me-2`;
            }
            
            const bsToast = new bootstrap.Toast(toast);
            bsToast.show();
        }
    }
}

// Global functions
function refreshData() {
    if (window.wallpaperManager) {
        window.wallpaperManager.loadData();
    }
}

async function saveConfig() {
    // 获取表单数据并进行验证
    const steamLibraryPath = document.getElementById('steamLibraryPath')?.value || '';
    const steamUserdataPath = document.getElementById('steamUserdataPath')?.value || '';
    const serverPortInput = document.getElementById('serverPort');
    const debugModeInput = document.getElementById('debugMode');
    
    // 验证端口号
    const serverPort = serverPortInput ? parseInt(serverPortInput.value) : 5000;
    if (isNaN(serverPort) || serverPort < 1 || serverPort > 65535) {
        window.wallpaperManager.showToast('请输入有效的端口号 (1-65535)', 'error');
        return;
    }
    
    const debugMode = debugModeInput ? debugModeInput.checked : false;
    
    const config = {
        steam_library_path: steamLibraryPath,
        steam_userdata_path: steamUserdataPath,
        server: {
            host: '127.0.0.1',
            port: serverPort,
            debug: debugMode
        }
    };
    
    console.log('Sending config:', config); // Debug log
    
    try {
        const response = await fetch('/api/config', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(config)
        });
        
        console.log('Response status:', response.status); // Debug log
        
        if (!response.ok) {
            console.error('HTTP error:', response.status, response.statusText);
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        const result = await response.json();
        console.log('Response data:', result); // Debug log
        
        if (result.success) {
            window.wallpaperManager.showToast('配置保存成功', 'info');
            const modal = bootstrap.Modal.getInstance(document.getElementById('configModal'));
            if (modal) {
                modal.hide();
            }
            
            // Check Steam path status after saving config
            setTimeout(() => {
                if (typeof checkSteamPathStatus === 'function') {
                    checkSteamPathStatus();
                }
            }, 500);
            
            // Reload data with new configuration
            setTimeout(() => {
                refreshData();
            }, 500);
        } else {
            const errorMsg = result.error || result.message || '配置保存失败';
            console.error('Config save failed:', errorMsg);
            window.wallpaperManager.showToast('配置保存失败: ' + errorMsg, 'error');
        }
    } catch (error) {
        console.error('Config save error:', error);
        let errorMsg = '网络连接错误';
        if (error.message) {
            errorMsg = error.message;
        }
        window.wallpaperManager.showToast('配置保存失败: ' + errorMsg, 'error');
    }
}

async function deleteSelected() {
    if (!window.wallpaperManager.selectedWallpapers.size) {
        window.wallpaperManager.showToast('请先选择要删除的壁纸', 'error');
        return;
    }
    
    const count = window.wallpaperManager.selectedWallpapers.size;
    if (!confirm(`确定要删除选中的 ${count} 个壁纸吗？此操作不可撤销！`)) {
        return;
    }
    
    window.wallpaperManager.showLoading(true);
    
    let successCount = 0;
    for (const wallpaperId of window.wallpaperManager.selectedWallpapers) {
        try {
            const response = await fetch(`/api/wallpapers/${wallpaperId}`, {
                method: 'DELETE'
            });
            const result = await response.json();
            
            if (result.success) {
                successCount++;
            }
        } catch (error) {
            console.error('Error deleting wallpaper:', error);
        }
    }
    
    window.wallpaperManager.showLoading(false);
    window.wallpaperManager.showToast(`成功删除 ${successCount} 个壁纸`, 'info');
    window.wallpaperManager.selectedWallpapers.clear();
    refreshData();
}

async function deleteAll() {
    const count = window.wallpaperManager.wallpapers.unsubscribed.length;
    if (count === 0) {
        window.wallpaperManager.showToast('没有可删除的未订阅壁纸', 'info');
        return;
    }
    
    if (!confirm(`确定要删除所有 ${count} 个未订阅壁纸吗？此操作不可撤销！`)) {
        return;
    }
    
    window.wallpaperManager.showLoading(true);
    
    let successCount = 0;
    for (const wallpaper of window.wallpaperManager.wallpapers.unsubscribed) {
        try {
            const response = await fetch(`/api/wallpapers/${wallpaper.id}`, {
                method: 'DELETE'
            });
            const result = await response.json();
            
            if (result.success) {
                successCount++;
            }
        } catch (error) {
            console.error('Error deleting wallpaper:', error);
        }
    }
    
    window.wallpaperManager.showLoading(false);
    window.wallpaperManager.showToast(`成功删除 ${successCount} 个壁纸`, 'info');
    refreshData();
}

async function deleteWallpaper() {
    if (!window.wallpaperManager.currentWallpaper) return;
    
    const wallpaper = window.wallpaperManager.currentWallpaper;
    if (!confirm(`确定要删除壁纸 "${wallpaper.title}" 吗？此操作不可撤销！`)) {
        return;
    }
    
    try {
        const response = await fetch(`/api/wallpapers/${wallpaper.id}`, {
            method: 'DELETE'
        });
        const result = await response.json();
        
        if (result.success) {
            window.wallpaperManager.showToast('壁纸删除成功', 'info');
            const modal = bootstrap.Modal.getInstance(document.getElementById('wallpaperModal'));
            modal.hide();
            refreshData();
        } else {
            window.wallpaperManager.showToast('壁纸删除失败: ' + result.error, 'error');
        }
    } catch (error) {
        window.wallpaperManager.showToast('壁纸删除失败: ' + error.message, 'error');
    }
}

async function openFolder() {
    if (!window.wallpaperManager.currentWallpaper) {
        window.wallpaperManager.showToast('没有选中的壁纸', 'error');
        return;
    }
    
    const wallpaper = window.wallpaperManager.currentWallpaper;
    
    try {
        const response = await fetch(`/api/wallpapers/${wallpaper.id}/open-folder`, {
            method: 'POST'
        });
    } catch (error) {
        console.error('Error opening folder:', error);
        // Fallback: show path in toast
        window.wallpaperManager.showToast(`打开文件夹失败，路径: ${wallpaper.path}`, 'error');
    }
}

function copyPath() {
    if (!window.wallpaperManager.currentWallpaper) {
        window.wallpaperManager.showToast('没有选中的壁纸', 'error');
        return;
    }
    
    const path = window.wallpaperManager.currentWallpaper.path;
    
    // Try to copy to clipboard
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(path).then(() => {
            window.wallpaperManager.showToast('路径已复制到剪贴板', 'info');
        }).catch(err => {
            console.error('Failed to copy to clipboard:', err);
            window.wallpaperManager.showToast(`路径: ${path}`, 'info');
        });
    } else {
        // Fallback for older browsers
        const textArea = document.createElement('textarea');
        textArea.value = path;
        document.body.appendChild(textArea);
        textArea.select();
        try {
            document.execCommand('copy');
            window.wallpaperManager.showToast('路径已复制到剪贴板', 'info');
        } catch (err) {
            window.wallpaperManager.showToast(`路径: ${path}`, 'info');
        }
        document.body.removeChild(textArea);
    }
}

async function exportData(type) {
    try {
        window.wallpaperManager.showLoading(true);
        
        // 获取所有数据（不分页）
        let url = '/api/wallpapers?';
        const params = new URLSearchParams();
        if (window.wallpaperManager.currentSearchQuery) {
            params.append('search', window.wallpaperManager.currentSearchQuery);
        }
        if (window.wallpaperManager.currentUserFilter && window.wallpaperManager.currentUserFilter !== 'all') {
            params.append('user', window.wallpaperManager.currentUserFilter);
        }
        // page_size=0 表示返回全部数据
        params.append('subscribed_page', 1);
        params.append('unsubscribed_page', 1);
        params.append('page_size', 0);
        url += params.toString();
        
        const response = await fetch(url);
        const result = await response.json();
        
        if (!result.success) {
            window.wallpaperManager.showToast('获取数据失败', 'error');
            return;
        }
        
        // 根据类型选择数据
        let data;
        if (type === 'subscribed') {
            data = Array.isArray(result.data.subscribed) ? 
                result.data.subscribed : 
                (result.data.subscribed.wallpapers || []);
        } else {
            data = Array.isArray(result.data.unsubscribed) ? 
                result.data.unsubscribed : 
                (result.data.unsubscribed.wallpapers || []);
        }
        
        if (data.length === 0) {
            window.wallpaperManager.showToast('没有数据可导出', 'info');
            return;
        }
        
        // Create CSV content
        const headers = ['ID', '标题', '大小', '状态', '路径'];
        const csvContent = [
            headers.join(','),
            ...data.map(wp => [
                wp.id,
                `"${wp.title.replace(/"/g, '""')}"`,
                wp.size_formatted,
                wp.subscribed ? '已订阅' : '未订阅',
                `"${wp.path.replace(/"/g, '""')}"`
            ].join(','))
        ].join('\n');
        
        // Download file
        const blob = new Blob(['\ufeff' + csvContent], { type: 'text/csv;charset=utf-8;' });
        const link = document.createElement('a');
        link.href = URL.createObjectURL(blob);
        link.download = `wallpapers_${type}_${new Date().toISOString().split('T')[0]}.csv`;
        link.click();
        
        window.wallpaperManager.showToast(`成功导出 ${data.length} 条数据`, 'info');
    } catch (error) {
        console.error('Error exporting data:', error);
        window.wallpaperManager.showToast('导出数据失败: ' + error.message, 'error');
    } finally {
        window.wallpaperManager.showLoading(false);
    }
}

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.wallpaperManager = new WallpaperManager();
});
