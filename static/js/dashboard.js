// Tellor Supply Analytics - Historical Dashboard JavaScript

class HistoricalDashboard {
    constructor() {
        this.apiBase = window.ROOT_PATH || '';
        this.currentPage = 0;
        this.currentLimit = 100;
        this.currentSearch = '';
        this.currentTimeRange = 24; // Default to 24 hours
        this.historicalData = [];
        this.charts = {
            supply: null,
            bridge: null,
            balance: null
        };
        
        this.init();
    }
    
    init() {
        this.bindEvents();
        // Read the actual selected value from the dropdown
        const timeRangeSelect = document.getElementById('timeRangeSelect');
        if (timeRangeSelect) {
            this.currentTimeRange = parseInt(timeRangeSelect.value);
        }
        this.loadInitialData();
    }
    
    bindEvents() {
        // Historical data buttons
        document.getElementById('timeRangeSelect').addEventListener('change', (e) => this.changeTimeRange(e.target.value));
        
        // Legacy buttons
        document.getElementById('refreshBtn').addEventListener('click', () => this.loadInitialData());
        document.getElementById('exportDataBtn').addEventListener('click', () => this.exportData());
        
        // Chart tab switching
        this.bindChartTabs();
    }
    
    bindChartTabs() {
        // Get all chart tab buttons
        const chartTabs = document.querySelectorAll('.chart-tab');
        
        chartTabs.forEach(tab => {
            tab.addEventListener('click', (e) => {
                const targetChart = e.target.getAttribute('data-chart');
                this.switchToChart(targetChart);
            });
        });
    }
    
    switchToChart(chartType) {
        // Remove active class from all tabs and panels
        document.querySelectorAll('.chart-tab').forEach(tab => {
            tab.classList.remove('active');
        });
        document.querySelectorAll('.chart-panel').forEach(panel => {
            panel.classList.remove('active');
        });
        
        // Add active class to selected tab and panel
        const activeTab = document.querySelector(`.chart-tab[data-chart="${chartType}"]`);
        const activePanel = document.querySelector(`.chart-panel[data-chart="${chartType}"]`);
        
        if (activeTab) activeTab.classList.add('active');
        if (activePanel) activePanel.classList.add('active');
        
        // Trigger chart resize if needed (for Chart.js)
        setTimeout(() => {
            if (this.charts[chartType]) {
                this.charts[chartType].resize();
            }
        }, 300); // Wait for CSS transition to complete
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
            this.updateCharts(data);
            
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
                    <td colspan="11" class="text-center text-muted">
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
            
            return `
                <tr title="ETH Block: ${snapshot.eth_block_number || 'N/A'}" data-timestamp="${timestamp}" id="row-${timestamp}">
                    <td class="font-mono text-xs">
                        ${datetime.toLocaleString()}
                        <br><small class="text-muted">${datetime.toISOString().slice(0, 19)}Z</small>
                    </td>
                    <td class="font-mono text-xs">
                        ${this.formatNumber(snapshot.eth_block_number, 0, false) || 'N/A'}
                    </td>
                    <td class="font-mono text-xs">
                        ${this.formatNumber(snapshot.layer_block_height, 0, false) || 'N/A'}
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
                    <td class="font-mono text-purple">
                        ${this.formatNumber(snapshot.total_reporter_power) || '0'}
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
        document.querySelector('#historicalSection h2').textContent = 
            `TRB Supply Data - Last ${hours == 168 ? '7 days' : hours + ' hours'}`;
        this.loadHistoricalData();
    }
    

    
    async loadSummary() {
        try {
            const response = await fetch(`${this.apiBase}/api/summary`);
            const data = await response.json();
            this.updateCompactStats(data);
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
    
    updateCompactStats(data) {
        // Update total addresses
        const totalAddressesEl = document.getElementById('compactTotalAddresses');
        if (totalAddressesEl) {
            totalAddressesEl.textContent = this.formatNumber(data.total_addresses);
        }
        
        // Update addresses with balance (with percentage)
        const addressesWithBalanceEl = document.getElementById('compactAddressesWithBalance');
        if (addressesWithBalanceEl) {
            const percentage = ((data.addresses_with_balance / data.total_addresses) * 100).toFixed(1);
            addressesWithBalanceEl.textContent = `${this.formatNumber(data.addresses_with_balance)} (${percentage}%)`;
        }
        
        // Update layer supply (just the layer supply)
        const layerSupplyEl = document.getElementById('compactLayerSupply');
        if (layerSupplyEl) {
            layerSupplyEl.textContent = `${this.formatNumber(data.total_trb_balance, 2)} TRB`;
        }
        
        // Update bridge balance
        const bridgeBalanceEl = document.getElementById('compactBridgeBalance');
        if (bridgeBalanceEl) {
            bridgeBalanceEl.textContent = `${this.formatNumber(data.bridge_balance_trb, 2)} TRB`;
        }
        
        // Update block height (without commas)
        const blockHeightEl = document.getElementById('compactBlockHeight');
        if (blockHeightEl) {
            blockHeightEl.textContent = data.layer_block_height ? data.layer_block_height.toString() : '--';
        }
        
        // Update free floating TRB
        const freeFloatingEl = document.getElementById('compactFreeFloating');
        if (freeFloatingEl) {
            freeFloatingEl.textContent = `${this.formatNumber(data.free_floating_trb, 2)} TRB`;
        }
        
        // Update historical points
        const historicalPointsEl = document.getElementById('compactHistoricalPoints');
        if (historicalPointsEl) {
            historicalPointsEl.textContent = `${this.historicalData.length}`;
        }
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
    formatNumber(num, decimals = 0, useCommas = true) {
        if (num === null || num === undefined) return '0';
        if (!useCommas) {
            return Number(num).toFixed(decimals);
        }
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
    
    // Chart Management Methods - Removed chart toggling, now showing all charts simultaneously
    
    updateCharts(data) {
        if (!data.timeline || data.timeline.length === 0) {
            // If no data, destroy existing charts
            Object.values(this.charts).forEach(chart => {
                if (chart) chart.destroy();
            });
            this.charts = {
                supply: null,
                bridge: null,
                balance: null
            };
            return;
        }

        // Create or update charts
        this.createCharts(data.timeline);
        
        // Calculate and display average block time
        this.updateAverageBlockTime(data.timeline);
    }
    
    createCharts(timeline) {
        // Sort timeline by timestamp for proper chart display
        const sortedTimeline = [...timeline].sort((a, b) => (a.timestamp || 0) - (b.timestamp || 0));
        
        // Create datasets
        const labels = sortedTimeline.map(d => new Date((d.timestamp || 0) * 1000));
        
        // Supply Overview Chart
        if (this.charts.supply) {
            this.charts.supply.destroy();
        }
        
        const supplyOptions = this.getChartOptions('TRB Supply Overview', 'TRB Amount');
        console.log('Supply chart options:', supplyOptions);
        
        this.charts.supply = new Chart(document.getElementById('supplyChart').getContext('2d'), {
            type: 'line',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: 'Total Layer Supply',
                        data: sortedTimeline.map(d => d.layer_total_supply_trb || 0),
                        borderColor: '#00ff88',
                        backgroundColor: 'rgba(0, 255, 136, 0.1)',
                        fill: true,
                        tension: 0.1,
                        pointRadius: 1,
                        pointHoverRadius: 4
                    },
                    {
                        label: 'Free Floating TRB',
                        data: sortedTimeline.map(d => d.free_floating_trb || 0),
                        borderColor: '#00d4ff',
                        backgroundColor: 'rgba(0, 212, 255, 0.1)',
                        fill: true,
                        tension: 0.1,
                        pointRadius: 2,
                        pointHoverRadius: 6
                    },
                    {
                        label: 'Bridge Balance',
                        data: sortedTimeline.map(d => d.bridge_balance_trb || 0),
                        borderColor: '#ff6b6b',
                        backgroundColor: 'rgba(255, 107, 107, 0.1)',
                        fill: false,
                        tension: 0.1,
                        pointRadius: 2,
                        pointHoverRadius: 6
                    }
                ]
            },
            options: supplyOptions
        });
        
        // Bridge & Staking Chart
        if (this.charts.bridge) {
            this.charts.bridge.destroy();
        }
        
        this.charts.bridge = new Chart(document.getElementById('bridgeChart').getContext('2d'), {
            type: 'line',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: 'Bridge Balance',
                        data: sortedTimeline.map(d => d.bridge_balance_trb || 0),
                        borderColor: '#ff6b6b',
                        backgroundColor: 'rgba(255, 107, 107, 0.2)',
                        fill: true,
                        tension: 0.1,
                        pointRadius: 3,
                        pointHoverRadius: 7,
                        yAxisID: 'y'
                    },
                    {
                        label: 'Bonded Tokens',
                        data: sortedTimeline.map(d => d.bonded_tokens || 0),
                        borderColor: '#00ff88',
                        backgroundColor: 'rgba(0, 255, 136, 0.1)',
                        fill: false,
                        tension: 0.1,
                        pointRadius: 2,
                        pointHoverRadius: 6,
                        yAxisID: 'y1'
                    },
                    {
                        label: 'Not Bonded Tokens',
                        data: sortedTimeline.map(d => d.not_bonded_tokens || 0),
                        borderColor: '#ffd700',
                        backgroundColor: 'rgba(255, 215, 0, 0.1)',
                        fill: false,
                        tension: 0.1,
                        pointRadius: 2,
                        pointHoverRadius: 6,
                        yAxisID: 'y1'
                    },
                    {
                        label: 'Total Reporter Power',
                        data: sortedTimeline.map(d => d.total_reporter_power || 0),
                        borderColor: '#9370db',
                        backgroundColor: 'rgba(147, 112, 219, 0.1)',
                        fill: false,
                        tension: 0.1,
                        pointRadius: 2,
                        pointHoverRadius: 6,
                        yAxisID: 'y1'
                    }
                ]
            },
            options: {
                ...this.getChartOptions('Bridge & Staking Metrics', 'TRB Amount'),
                scales: {
                    ...this.getChartOptions('Bridge & Staking Metrics', 'TRB Amount').scales,
                    y1: {
                        type: 'linear',
                        display: true,
                        position: 'right',
                        title: {
                            display: true,
                            text: 'Tokens / Reporter Power',
                            color: '#a0a0a0'
                        },
                        ticks: {
                            color: '#a0a0a0',
                            callback: function(value) {
                                return value.toLocaleString();
                            }
                        },
                        grid: {
                            drawOnChartArea: false,
                        },
                    }
                }
            }
        });
        
        // Active Balances Chart
        if (this.charts.balance) {
            this.charts.balance.destroy();
        }
        
        this.charts.balance = new Chart(document.getElementById('balanceChart').getContext('2d'), {
            type: 'line',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: 'Total Active Balance',
                        data: sortedTimeline.map(d => d.total_trb_balance || 0),
                        borderColor: '#00d4ff',
                        backgroundColor: 'rgba(0, 212, 255, 0.2)',
                        fill: true,
                        tension: 0.1,
                        pointRadius: 3,
                        pointHoverRadius: 7,
                        yAxisID: 'y'
                    },
                    {
                        label: 'Addresses with Balance',
                        data: sortedTimeline.map(d => d.addresses_with_balance || 0),
                        borderColor: '#00ff88',
                        backgroundColor: 'rgba(0, 255, 136, 0.1)',
                        fill: false,
                        tension: 0.1,
                        pointRadius: 2,
                        pointHoverRadius: 6,
                        yAxisID: 'y1'
                    }
                ]
            },
            options: {
                ...this.getChartOptions('Active Balance Metrics', 'TRB Amount'),
                scales: {
                    ...this.getChartOptions('Active Balance Metrics', 'TRB Amount').scales,
                    y1: {
                        type: 'linear',
                        display: true,
                        position: 'right',
                        title: {
                            display: true,
                            text: 'Address Count',
                            color: '#a0a0a0'
                        },
                        ticks: {
                            color: '#a0a0a0',
                            callback: function(value) {
                                return value.toLocaleString();
                            }
                        },
                        grid: {
                            drawOnChartArea: false,
                        },
                    }
                }
            }
        });
        
        // Add fallback click listeners to canvas elements
        this.addFallbackClickListeners();
    }

    addFallbackClickListeners() {
        console.log('Adding fallback click listeners to chart canvases');
        
        const chartCanvases = ['supplyChart', 'bridgeChart', 'balanceChart'];
        
        chartCanvases.forEach(chartId => {
            const canvas = document.getElementById(chartId);
            if (canvas) {
                // Remove existing click listeners
                canvas.removeEventListener('click', this.handleCanvasClick);
                
                // Add new click listener
                canvas.addEventListener('click', (event) => this.handleCanvasClick(event, chartId));
                console.log(`Added fallback click listener to ${chartId}`);
            }
        });
    }

    handleCanvasClick(event, chartId) {
        console.log(`Canvas clicked: ${chartId}`, event);
        
        // Get the chart instance
        const chartInstance = this.charts[chartId.replace('Chart', '')];
        if (!chartInstance) {
            console.warn(`No chart instance found for ${chartId}`);
            return;
        }
        
        // Get the elements at the click position
        const rect = event.target.getBoundingClientRect();
        const x = event.clientX - rect.left;
        const y = event.clientY - rect.top;
        
        const elements = chartInstance.getElementsAtEventForMode(event, 'nearest', { intersect: false }, false);
        console.log('Fallback click elements:', elements);
        
        if (elements.length > 0) {
            const index = elements[0].index;
            const timestamp = Math.floor(chartInstance.data.labels[index].getTime() / 1000);
            console.log('Fallback click timestamp:', timestamp);
            this.scrollToTableRow(timestamp);
        }
    }
    
    getChartOptions(title, yAxisLabel) {
        return {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                mode: 'index',
                intersect: false,
            },
            onClick: (event, elements) => {
                console.log('Chart clicked!', elements);
                if (elements.length > 0) {
                    const datasetIndex = elements[0].datasetIndex;
                    const index = elements[0].index;
                    const chart = elements[0].chart;
                    
                    console.log('Click details:', { datasetIndex, index, chart });
                    
                    // Get the timestamp from the chart data
                    const timestamp = Math.floor(chart.data.labels[index].getTime() / 1000);
                    console.log('Calculated timestamp:', timestamp);
                    
                    // Get the dashboard instance from the global scope
                    if (window.dashboard && window.dashboard.scrollToTableRow) {
                        window.dashboard.scrollToTableRow(timestamp);
                    } else {
                        console.error('Dashboard instance not found');
                    }
                } else {
                    console.log('No chart elements found in click');
                }
            },
            plugins: {
                title: {
                    display: true,
                    text: title,
                    color: '#ffffff',
                    font: {
                        size: 16,
                        weight: 'bold'
                    }
                },
                legend: {
                    labels: {
                        color: '#a0a0a0',
                        usePointStyle: true,
                        padding: 20
                    }
                },
                tooltip: {
                    backgroundColor: 'rgba(20, 20, 30, 0.95)',
                    titleColor: '#ffffff',
                    bodyColor: '#a0a0a0',
                    borderColor: '#00ff88',
                    borderWidth: 1,
                    callbacks: {
                        title: function(context) {
                            return new Date(context[0].parsed.x).toLocaleString();
                        },
                        label: function(context) {
                            const label = context.dataset.label || '';
                            const value = context.parsed.y;
                            if (label.includes('Balance') || label.includes('TRB') || label.includes('Bonded Tokens') || label.includes('Not Bonded Tokens')) {
                                return `${label}: ${value.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 6})} TRB`;
                            } else if (label.includes('Reporter Power')) {
                                return `${label}: ${value.toLocaleString()}`;
                            } else {
                                return `${label}: ${value.toLocaleString()}`;
                            }
                        },
                        afterBody: function(context) {
                            return ['', '💡 Click to view details in table below'];
                        }
                    }
                }
            },
            scales: {
                x: {
                    type: 'time',
                    time: {
                        displayFormats: {
                            hour: 'MMM d, HH:mm',
                            day: 'MMM d',
                            week: 'MMM d',
                            month: 'MMM yyyy'
                        }
                    },
                    title: {
                        display: true,
                        text: 'Time',
                        color: '#a0a0a0'
                    },
                    ticks: {
                        color: '#a0a0a0',
                        maxTicksLimit: 8
                    },
                    grid: {
                        color: 'rgba(160, 160, 160, 0.1)'
                    }
                },
                y: {
                    title: {
                        display: true,
                        text: yAxisLabel,
                        color: '#a0a0a0'
                    },
                    ticks: {
                        color: '#a0a0a0',
                        callback: function(value) {
                            if (value >= 1000000) {
                                return (value / 1000000).toFixed(1) + 'M';
                            } else if (value >= 1000) {
                                return (value / 1000).toFixed(1) + 'K';
                            }
                            return value.toLocaleString();
                        }
                    },
                    grid: {
                        color: 'rgba(160, 160, 160, 0.1)'
                    }
                }
            }
        };
    }

    scrollToTableRow(timestamp) {
        console.log(`scrollToTableRow called with timestamp: ${timestamp}`);
        
        // Find the table row with the matching timestamp
        const targetRow = document.getElementById(`row-${timestamp}`);
        console.log(`Found target row:`, targetRow);
        
        if (targetRow) {
            // Remove any existing highlights
            document.querySelectorAll('.chart-clicked-row').forEach(row => {
                row.classList.remove('chart-clicked-row');
            });
            
            // Highlight the target row
            targetRow.classList.add('chart-clicked-row');
            console.log('Added highlight class to row');
            
            // Scroll to the row with smooth behavior
            targetRow.scrollIntoView({ 
                behavior: 'smooth', 
                block: 'center',
                inline: 'nearest'
            });
            
            // Remove highlight after 3 seconds
            setTimeout(() => {
                targetRow.classList.remove('chart-clicked-row');
                console.log('Removed highlight class from row');
            }, 3000);
            
            console.log(`✅ Scrolled to row for timestamp: ${timestamp}`);
        } else {
            console.warn(`❌ Could not find table row for timestamp: ${timestamp}`);
            
            // Debug: List all available row IDs
            const allRows = document.querySelectorAll('[id^="row-"]');
            console.log('Available row IDs:', Array.from(allRows).map(row => row.id));
        }
    }

    // Test function for debugging chart clicks
    testChartClick(timestamp) {
        console.log('🧪 Testing chart click functionality...');
        
        if (!timestamp) {
            // Use the first available timestamp from the table
            const firstRow = document.querySelector('[id^="row-"]');
            if (firstRow) {
                timestamp = firstRow.id.replace('row-', '');
                console.log(`Using first available timestamp: ${timestamp}`);
            } else {
                console.error('No table rows found to test with');
                return;
            }
        }
        
        this.scrollToTableRow(parseInt(timestamp));
    }
    
    updateAverageBlockTime(timeline) {
        const display = document.getElementById('avgBlockTimeDisplay');
        if (!display || !timeline || timeline.length < 2) {
            if (display) {
                display.style.display = 'none';
            }
            return;
        }
        
        // Filter out data points without layer block height
        const validData = timeline.filter(d => d.layer_block_height && d.timestamp);
        
        if (validData.length < 2) {
            display.style.display = 'none';
            return;
        }
        
        // Sort by timestamp to ensure proper order
        const sortedData = [...validData].sort((a, b) => (a.timestamp || 0) - (b.timestamp || 0));
        
        // Get start and end points
        const startPoint = sortedData[0];
        const endPoint = sortedData[sortedData.length - 1];
        
        // Calculate differences
        const blockDifference = endPoint.layer_block_height - startPoint.layer_block_height;
        const timeDifference = endPoint.timestamp - startPoint.timestamp; // in seconds
        
        if (blockDifference <= 0 || timeDifference <= 0) {
            display.style.display = 'none';
            return;
        }
        
        // Calculate average block time in seconds
        const avgBlockTimeSeconds = timeDifference / blockDifference;
        
        // Format the time nicely
        let timeString;
        if (avgBlockTimeSeconds < 60) {
            timeString = `${avgBlockTimeSeconds.toFixed(3)} seconds`;
        } else if (avgBlockTimeSeconds < 3600) {
            const minutes = avgBlockTimeSeconds / 60;
            timeString = `${minutes.toFixed(3)} minutes`;
        } else {
            const hours = avgBlockTimeSeconds / 3600;
            timeString = `${hours.toFixed(3)} hours`;
        }
        
        // Get timeframe description
        const timeframeHours = this.currentTimeRange;
        let timeframeDesc;
        if (timeframeHours === 8760) {
            timeframeDesc = "all available data";
        } else if (timeframeHours < 24) {
            timeframeDesc = `past ${timeframeHours} hours`;
        } else if (timeframeHours < 168) {
            const days = timeframeHours / 24;
            timeframeDesc = `past ${days} days`;
        } else if (timeframeHours === 168) {
            timeframeDesc = "past 7 days";
        } else if (timeframeHours === 720) {
            timeframeDesc = "past 30 days";
        } else {
            const days = Math.round(timeframeHours / 24);
            timeframeDesc = `past ${days} days`;
        }
        
        // Display the result
        display.innerHTML = `Average block time for ${timeframeDesc}: <strong>${timeString}</strong>`;
        display.style.display = 'block';
    }
}

// Initialize the dashboard when page loads
document.addEventListener('DOMContentLoaded', () => {
    window.dashboard = new HistoricalDashboard();
    
    // Add test function to global scope for debugging
    window.testChartClick = (timestamp) => {
        if (window.dashboard) {
            window.dashboard.testChartClick(timestamp);
        } else {
            console.error('Dashboard not initialized');
        }
    };
    
    console.log('🎯 Chart click debugging enabled. Try: testChartClick() in console');
});

// Make dashboard available globally for debugging
window.HistoricalDashboard = HistoricalDashboard;
