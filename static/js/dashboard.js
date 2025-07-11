// Tellor Layer Balance Analytics Dashboard JavaScript

class BalanceDashboard {
    constructor() {
        this.apiBase = '';
        this.currentPage = 0;
        this.currentLimit = 100;
        this.currentSearch = '';
        
        this.init();
    }
    
    init() {
        this.bindEvents();
        this.loadInitialData();
    }
    
    bindEvents() {
        // Buttons
        document.getElementById('refreshBtn').addEventListener('click', () => this.loadInitialData());
        document.getElementById('collectBtn').addEventListener('click', () => this.triggerCollection());
        document.getElementById('viewHistoryBtn').addEventListener('click', () => this.showHistory());
    }
    
    async loadInitialData() {
        this.showLoading();
        try {
            await Promise.all([
                this.loadSummary(),
                this.loadBalances()
            ]);
        } catch (error) {
            console.error('Error loading initial data:', error);
            this.showError('Failed to load dashboard data');
        } finally {
            this.hideLoading();
        }
    }
    
    async loadSummary() {
        try {
            const response = await fetch(`${this.apiBase}/api/summary`);
            const data = await response.json();
            this.updateStatsCards(data);
        } catch (error) {
            console.error('Error loading summary:', error);
        }
    }
    
    async loadBalances() {
        try {
            const params = new URLSearchParams({
                limit: this.currentLimit,
                offset: this.currentPage * this.currentLimit
            });
            
            if (this.currentSearch) {
                params.append('search', this.currentSearch);
            }
            
            const response = await fetch(`${this.apiBase}/api/balances?${params}`);
            const data = await response.json();
            this.updateBalancesTable(data);
        } catch (error) {
            console.error('Error loading balances:', error);
        }
    }
    
    updateStatsCards(data) {
        const statsGrid = document.getElementById('statsGrid');
        const lastUpdated = new Date(data.run_time).toLocaleString();
        
        statsGrid.innerHTML = `
            <div class="stat-card clickable">
                <div class="stat-icon">
                    <i class="fas fa-users"></i>
                </div>
                <div class="stat-content">
                    <div class="stat-number">${this.formatNumber(data.total_addresses)}</div>
                    <div class="stat-title">Total Addresses</div>
                    <div class="stat-subtitle">Last updated: ${lastUpdated}</div>
                </div>
            </div>
            
            <div class="stat-card clickable">
                <div class="stat-icon">
                    <i class="fas fa-wallet"></i>
                </div>
                <div class="stat-content">
                    <div class="stat-number">${this.formatNumber(data.addresses_with_balance)}</div>
                    <div class="stat-title">Addresses with Balance</div>
                    <div class="stat-subtitle">${((data.addresses_with_balance / data.total_addresses) * 100).toFixed(1)}% of total</div>
                </div>
            </div>
            
            <div class="stat-card clickable">
                <div class="stat-icon">
                    <i class="fas fa-coins"></i>
                </div>
                <div class="stat-content">
                    <div class="stat-number">${this.formatNumber(data.free_floating_trb, 2)} TRB</div>
                    <div class="stat-title">Free Floating TRB</div>
                </div>
            </div>
            
            <div class="stat-card clickable" style="position: relative;">
                <div class="stat-icon">
                    <i class="fas fa-exchange-alt"></i>
                </div>
                <div class="stat-content">
                    <div class="stat-number">${this.formatNumber(data.total_trb_balance, 2)} TRB</div>
                    <div class="stat-title">Layer Total Supply</div>
                    <div class="stat-subtitle" style="font-size: 0.7rem; line-height: 1.2;">
                        Bridge: ${this.formatNumber(data.bridge_balance_trb, 2)} TRB<br>
                        ${this.calculateSupplyDifference(data.total_trb_balance, data.bridge_balance_trb)}
                    </div>
                </div>
            </div>
            
            <div class="stat-card clickable">
                <div class="stat-icon">
                    <i class="fas fa-cube"></i>
                </div>
                <div class="stat-content">
                    <div class="stat-number">${this.formatNumber(data.layer_block_height)}</div>
                    <div class="stat-title">Block Height</div>
                    <div class="stat-subtitle">Height of Data Shown</div>
                </div>
            </div>
        `;
    }
    
    updateBalancesTable(data) {
        const tbody = document.getElementById('balancesTableBody');
        
        tbody.innerHTML = data.balances.map(balance => `
            <tr>
                <td class="font-mono text-xs">${this.truncateAddress(balance.address)}</td>
                <td><span class="badge ${this.getAccountTypeBadgeClass(balance.account_type)}">${balance.account_type}</span></td>
                <td class="font-mono text-primary">${this.formatNumber(balance.loya_balance_trb, 6)} TRB</td>
                <td class="text-sm text-muted">${new Date(balance.snapshot_time).toLocaleString()}</td>
                <td>
                    <button class="btn btn-sm btn-outline" onclick="navigator.clipboard.writeText('${balance.address}')">
                        <i class="fas fa-copy"></i>
                    </button>
                </td>
            </tr>
        `).join('');
    }
    
    async triggerCollection() {
        if (!confirm('This will trigger a new balance collection. This may take several minutes. Continue?')) {
            return;
        }
        
        this.showLoading('Collecting balance data...');
        try {
            const response = await fetch(`${this.apiBase}/api/collect`, { method: 'POST' });
            const data = await response.json();
            
            if (data.status === 'success') {
                this.showSuccess('Balance collection completed successfully');
                this.loadInitialData();
            } else {
                this.showError('Collection failed');
            }
        } catch (error) {
            console.error('Error triggering collection:', error);
            this.showError('Failed to trigger collection');
        } finally {
            this.hideLoading();
        }
    }
    
    async showHistory() {
        alert('History view will be implemented in the next version');
    }
    
    // Utility functions
    formatNumber(num, decimals = 0) {
        if (num === null || num === undefined) return '0';
        return Number(num).toLocaleString('en-US', { 
            minimumFractionDigits: decimals,
            maximumFractionDigits: decimals 
        });
    }
    
    calculateSupplyDifference(totalSupply, bridgeBalance) {
        const difference = totalSupply - bridgeBalance;
        const percentage = ((difference / totalSupply) * 100);
        
        if (difference > 0) {
            return `Native: ${this.formatNumber(difference, 2)} TRB (${percentage.toFixed(1)}%)`;
        } else if (difference < 0) {
            return `Difference: ${this.formatNumber(Math.abs(difference), 2)}`;
        } else {
            return `Balanced: 0.00 TRB (0.0%)`;
        }
    }
    
    truncateAddress(address) {
        if (!address) return '';
        return `${address.slice(0, 8)}...${address.slice(-6)}`;
    }
    
    getAccountTypeBadgeClass(type) {
        if (type.includes('Module')) return 'badge-info';
        if (type.includes('Base')) return 'badge-success';
        return 'badge-warning';
    }
    
    showLoading(message = 'Loading...') {
        const overlay = document.getElementById('loadingOverlay');
        const text = overlay.querySelector('.loading-text');
        text.textContent = message;
        overlay.classList.remove('hidden');
    }
    
    hideLoading() {
        document.getElementById('loadingOverlay').classList.add('hidden');
    }
    
    showError(message) {
        alert('Error: ' + message);
    }
    
    showSuccess(message) {
        alert('Success: ' + message);
    }
}

// Initialize dashboard when page loads
document.addEventListener('DOMContentLoaded', function() {
    window.dashboard = new BalanceDashboard();
});
