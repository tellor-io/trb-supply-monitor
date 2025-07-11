// Tellor Supply Analytics - Historical Dashboard JavaScript

class HistoricalDashboard {
    constructor() {
        this.apiBase = '';
        this.currentPage = 0;
        this.currentLimit = 100;
        this.currentSearch = '';
        this.currentTimeRange = 24;
        this.historicalData = [];
        
        this.init();
    }
    
    init() {
        this.bindEvents();
        this.loadInitialData();
    }
    
    bindEvents() {
        // Historical data buttons
        document.getElementById('refreshHistoryBtn').addEventListener('click', () => this.loadHistoricalData());
        document.getElementById('collectUnifiedBtn').addEventListener('click', () => this.triggerUnifiedCollection());
        document.getElementById('timeRangeSelect').addEventListener('change', (e) => this.changeTimeRange(e.target.value));
        
        // Legacy buttons
        document.getElementById('refreshBtn').addEventListener('click', () => this.loadInitialData());
        document.getElementById('collectBtn').addEventListener('click', () => this.triggerCollection());
        document.getElementById('exportDataBtn').addEventListener('click', () => this.exportData());
        
        // Chart buttons (placeholder)
        document.getElementById('toggleSupplyChart').addEventListener('click', () => this.showMessage('Charts coming soon!'));
        document.getElementById('toggleBridgeChart').addEventListener('click', () => this.showMessage('Charts coming soon!'));
    }
    
    async loadInitialData() {
        this.showLoading();
        try {
            await Promise.all([
                this.loadHistoricalData(),
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
    
    async loadHistoricalData() {
        try {
            console.log(`Loading historical data for ${this.currentTimeRange} hours`);
            
            const response = await fetch(`${this.apiBase}/api/unified/timeline?hours_back=${this.currentTimeRange}&min_completeness=0.0`);
            const data = await response.json();
            
            this.historicalData = data.timeline || [];
            this.updateHistoricalTable(data);
            this.updateTimelineStats(data);
            
            console.log(`Loaded ${this.historicalData.length} historical data points`);
        } catch (error) {
            console.error('Error loading historical data:', error);
            this.showError('Failed to load historical data');
        }
    }
    
    updateHistoricalTable(data) {
        const tbody = document.getElementById('historicalTableBody');
        
        if (!data.timeline || data.timeline.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="10" class="text-center text-muted">
                        No historical data available for the selected time range.
                        <br><small>Try triggering a collection or selecting a different time range.</small>
                    </td>
                </tr>
            `;
            return;
        }
        
        tbody.innerHTML = data.timeline.map(snapshot => {
            // Fix: Use 'timestamp' instead of 'eth_timestamp' and add null check
            const timestamp = snapshot.timestamp;
            if (!timestamp) {
                console.warn('Snapshot missing timestamp:', snapshot);
                return ''; // Skip this row
            }
            
            const datetime = new Date(timestamp * 1000);
            const completenessScore = snapshot.completeness_score || snapshot.data_completeness_score || 0;
            const completenessClass = completenessScore >= 0.8 ? 'text-primary' : 
                                    completenessScore >= 0.5 ? 'text-accent' : 'text-muted';
            
            return `
                <tr title="ETH Block: ${snapshot.eth_block_number || 'N/A'}">
                    <td class="font-mono text-xs">
                        ${datetime.toLocaleString()}
                        <br><small class="text-muted">${datetime.toISOString().slice(0, 19)}Z</small>
                    </td>
                    <td class="font-mono text-xs">
                        ${this.formatNumber(snapshot.eth_block_number) || 'N/A'}
                    </td>
                    <td class="font-mono text-primary">
                        ${this.formatTRB(snapshot.bridge_balance_trb)}
                    </td>
                    <td class="font-mono text-secondary">
                        ${this.formatTRB(snapshot.layer_total_supply_trb)}
                    </td>
                    <td class="font-mono text-tertiary">
                        ${this.formatTRB(snapshot.free_floating_trb)}
                    </td>
                    <td class="font-mono text-sm">
                        ${this.formatTRB(snapshot.bonded_tokens)}
                    </td>
                    <td class="font-mono text-sm">
                        ${this.formatTRB(snapshot.not_bonded_tokens)}
                    </td>
                    <td class="font-mono">
                        ${this.formatNumber(snapshot.total_addresses) || 'N/A'}
                        ${snapshot.addresses_with_balance ? 
                            `<br><small class="text-muted">${this.formatNumber(snapshot.addresses_with_balance)} active</small>` : 
                            ''
                        }
                    </td>
                    <td class="font-mono text-accent">
                        ${this.formatTRB(snapshot.total_trb_balance)}
                    </td>
                    <td class="text-center">
                        <span class="badge ${completenessClass}" style="font-size: 0.7rem;">
                            ${(completenessScore * 100).toFixed(0)}%
                        </span>
                    </td>
                </tr>
            `;
        }).filter(row => row !== '').join(''); // Filter out empty rows
    }
    
    updateTimelineStats(data) {
        const countElement = document.getElementById('timelineCount');
        const completenessElement = document.getElementById('timelineCompleteness');
        const latestElement = document.getElementById('timelineLatest');
        const oldestElement = document.getElementById('timelineOldest');
        
        if (!data.timeline || data.timeline.length === 0) {
            countElement.textContent = '0';
            completenessElement.textContent = 'N/A';
            latestElement.textContent = 'No Data';
            oldestElement.textContent = 'No Data';
            return;
        }
        
        // Calculate average completeness
        const avgCompleteness = data.timeline.reduce((sum, s) => {
            const score = s.completeness_score || s.data_completeness_score || 0;
            return sum + score;
        }, 0) / data.timeline.length;
        
        // Get timestamps - fix: use 'timestamp' instead of 'eth_timestamp'
        const latest = data.timeline[0];
        const oldest = data.timeline[data.timeline.length - 1];
        
        countElement.textContent = this.formatNumber(data.timeline.length);
        completenessElement.textContent = `${(avgCompleteness * 100).toFixed(1)}%`;
        
        if (latest && latest.timestamp) {
            const latestDate = new Date(latest.timestamp * 1000);
            latestElement.textContent = latestDate.toLocaleString().split(',')[1].trim();
        } else {
            latestElement.textContent = 'N/A';
        }
        
        if (oldest && oldest.timestamp) {
            const oldestDate = new Date(oldest.timestamp * 1000);
            oldestElement.textContent = oldestDate.toLocaleString().split(',')[1].trim();
        } else {
            oldestElement.textContent = 'N/A';
        }
    }
    
    changeTimeRange(hours) {
        this.currentTimeRange = parseInt(hours);
        document.querySelector('#historicalSection h1').textContent = 
            `Historical Supply Data - Last ${hours == 168 ? '7 days' : hours + ' hours'}`;
        this.loadHistoricalData();
    }
    
    async triggerUnifiedCollection() {
        if (!confirm('This will trigger unified data collection. This may take several minutes. Continue?')) {
            return;
        }
        
        this.showLoading('Collecting unified data...');
        try {
            const hours_back = Math.min(this.currentTimeRange, 24); // Limit collection scope
            const response = await fetch(`${this.apiBase}/api/unified/collect?hours_back=${hours_back}&max_blocks=50`, { 
                method: 'POST' 
            });
            const data = await response.json();
            
            if (data.status === 'success') {
                this.showSuccess(`Unified collection completed: ${data.message || 'Success'}`);
                // Wait a moment then refresh data
                setTimeout(() => this.loadHistoricalData(), 2000);
            } else {
                this.showError(`Collection failed: ${data.message || 'Unknown error'}`);
            }
        } catch (error) {
            console.error('Error triggering unified collection:', error);
            this.showError('Failed to trigger unified collection');
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
            
            <div class="stat-card clickable">
                <div class="stat-icon">
                    <i class="fas fa-clock"></i>
                </div>
                <div class="stat-content">
                    <div class="stat-number">${this.historicalData.length}</div>
                    <div class="stat-title">Historical Points</div>
                    <div class="stat-subtitle">Last ${this.currentTimeRange}h data</div>
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
    
    async exportData() {
        try {
            this.showLoading('Preparing data export...');
            
            // Create CSV content from historical data
            if (this.historicalData.length === 0) {
                this.showError('No historical data to export');
                return;
            }
            
            const headers = [
                'timestamp', 'eth_block_number', 'bridge_balance_trb', 'layer_total_supply_trb', 
                'free_floating_trb', 'bonded_tokens', 'not_bonded_tokens', 
                'total_addresses', 'addresses_with_balance', 'total_trb_balance', 'data_completeness_score'
            ];
            
            const csvContent = [
                headers.join(','),
                ...this.historicalData.map(row => 
                    headers.map(header => row[header] || '').join(',')
                )
            ].join('\n');
            
            // Download CSV
            const blob = new Blob([csvContent], { type: 'text/csv' });
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `tellor-supply-historical-${this.currentTimeRange}h-${new Date().toISOString().slice(0,10)}.csv`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            window.URL.revokeObjectURL(url);
            
            this.showSuccess('Data exported successfully');
        } catch (error) {
            console.error('Error exporting data:', error);
            this.showError('Failed to export data');
        } finally {
            this.hideLoading();
        }
    }
    
    // Utility functions
    formatNumber(num, decimals = 0) {
        if (num === null || num === undefined) return '0';
        return Number(num).toLocaleString('en-US', { 
            minimumFractionDigits: decimals,
            maximumFractionDigits: decimals 
        });
    }
    
    formatTRB(amount, decimals = 2) {
        if (amount === null || amount === undefined) return 'N/A';
        return this.formatNumber(amount, decimals);
    }
    
    calculateSupplyDifference(totalSupply, bridgeBalance) {
        if (!totalSupply || !bridgeBalance) return 'N/A';
        
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
        if (!address) return 'N/A';
        return `${address.slice(0, 6)}...${address.slice(-4)}`;
    }
    
    getAccountTypeBadgeClass(type) {
        const badges = {
            'validator': 'badge-success',
            'delegator': 'badge-info',
            'contract': 'badge-warning',
            'user': 'badge-secondary'
        };
        return badges[type?.toLowerCase()] || 'badge-secondary';
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
        // Simple alert for now, could be enhanced with better UI
        alert(`Error: ${message}`);
        console.error(message);
    }
    
    showSuccess(message) {
        // Simple alert for now, could be enhanced with better UI
        alert(`Success: ${message}`);
        console.log(message);
    }
    
    showMessage(message) {
        alert(message);
    }
}

// Initialize the dashboard when page loads
document.addEventListener('DOMContentLoaded', () => {
    window.dashboard = new HistoricalDashboard();
});

// Make dashboard available globally for debugging
window.HistoricalDashboard = HistoricalDashboard;
