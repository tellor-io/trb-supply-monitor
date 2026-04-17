/**
 * Block Time Analytics Dashboard
 * 
 * Manages the block time analytics interface including:
 * - Chart visualization of block times over time
 * - Data table display
 * - Time range selection
 * - Export functionality
 */

class BlockTimeAnalytics {
    constructor() {
        this.chart = null;
        this.currentData = null;
        this.currentTimeRange = 24; // Default to 24 hours
        this.blockSizeLimit = 1000; // Number of time buckets to divide the chart range into
        
        // API base URL with root path support
        this.apiBase = window.ROOT_PATH ? `${window.ROOT_PATH}/api` : '/api';
        
        this.init();
    }
    
    init() {
        console.log('Initializing Block Time Analytics Dashboard');
        
        // Set up event listeners
        this.setupEventListeners();
        
        // Initialize chart
        this.initChart();
        
        // Load initial data
        this.loadBlockTimeData();
    }
    
    setupEventListeners() {
        // Time range selector
        const timeRangeSelect = document.getElementById('timeRangeSelect');
        if (timeRangeSelect) {
            timeRangeSelect.addEventListener('change', (e) => {
                this.currentTimeRange = parseInt(e.target.value);
                this.loadBlockTimeData();
            });
        }
        
        // Refresh button
        const refreshBtn = document.getElementById('refreshBtn');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => {
                this.loadBlockTimeData();
            });
        }
        
        // Export button
        const exportBtn = document.getElementById('exportDataBtn');
        if (exportBtn) {
            exportBtn.addEventListener('click', () => {
                this.exportData();
            });
        }
        
        // Estimation form
        const estimateBtn = document.getElementById('estimateBtn');
        if (estimateBtn) {
            estimateBtn.addEventListener('click', () => {
                this.estimateBlockHeight();
            });
        }
        
        // Allow Enter key in the input field
        const targetHeightInput = document.getElementById('targetHeightInput');
        if (targetHeightInput) {
            targetHeightInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    this.estimateBlockHeight();
                }
            });
        }
    }
    
    initChart() {
        const ctx = document.getElementById('blockTimeChart');
        if (!ctx) {
            console.error('Block time chart canvas not found');
            return;
        }
        
        this.chart = new Chart(ctx, {
            type: 'line',
            data: {
                datasets: [
                    {
                        label: 'Block Time (seconds)',
                        data: [],
                        borderColor: '#3b82f6',
                        backgroundColor: 'rgba(59, 130, 246, 0.1)',
                        borderWidth: 2,
                        fill: true,
                        tension: 0.1,
                        pointRadius: 3,
                        pointHoverRadius: 5,
                        yAxisID: 'yTime'
                    },
                    {
                        // Block sizes bucketed evenly across the chart's time range
                        label: 'Block Size (KB)',
                        data: [],
                        borderColor: '#10b981',
                        backgroundColor: 'rgba(16, 185, 129, 0.08)',
                        borderWidth: 2,
                        fill: false,
                        tension: 0.0,
                        pointRadius: 0,
                        pointHoverRadius: 4,
                        yAxisID: 'ySize'
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: {
                    intersect: false,
                    mode: 'index'
                },
                scales: {
                    x: {
                        type: 'time',
                        time: {
                            displayFormats: {
                                hour: 'MMM dd HH:mm',
                                day: 'MMM dd',
                                week: 'MMM dd',
                                month: 'MMM yyyy'
                            }
                        },
                        title: {
                            display: true,
                            text: 'Time'
                        }
                    },
                    yTime: {
                        position: 'left',
                        title: {
                            display: true,
                            text: 'Block Time (seconds)'
                        },
                        beginAtZero: false
                    },
                    ySize: {
                        position: 'right',
                        title: {
                            display: true,
                            text: 'Block Size (KB)'
                        },
                        beginAtZero: true,
                        grid: {
                            drawOnChartArea: false
                        }
                    }
                },
                plugins: {
                    title: {
                        display: true,
                        text: 'Tellor Layer Block Time & Block Size Over Time'
                    },
                    legend: {
                        display: true,
                        position: 'top'
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                if (context.datasetIndex === 0) {
                                    return `Block Time: ${context.parsed.y.toFixed(3)} seconds`;
                                } else {
                                    const raw = context.raw;
                                    const kb = context.parsed.y.toFixed(2);
                                    if (raw && raw.is_spike) {
                                        const h = raw.height ? ` — block ${raw.height}` : '';
                                        return `⚠ SPIKE: ${kb} KB${h}`;
                                    }
                                    const extra = raw && raw.block_count ? ` (avg of ${raw.block_count} blocks)` : '';
                                    return `Block Size: ${kb} KB${extra}`;
                                }
                            },
                            afterLabel: function(context) {
                                if (context.datasetIndex !== 0) return [];
                                const dataPoint = context.raw.originalData;
                                if (!dataPoint) return [];
                                const lines = [
                                    `Height Range: ${dataPoint.height_range}`,
                                    `Blocks: ${dataPoint.blocks_counted}`,
                                    `Time Span: ${dataPoint.time_span_seconds}s`
                                ];
                                if (dataPoint.max_block_size_bytes != null) {
                                    lines.push(`Max Block Size: ${(dataPoint.max_block_size_bytes / 1024).toFixed(2)} KB`);
                                }
                                if (dataPoint.avg_tx_count != null) {
                                    lines.push(`Avg Txs/Block: ${dataPoint.avg_tx_count}`);
                                }
                                return lines;
                            }
                        }
                    }
                }
            }
        });
    }
    
    async loadBlockTimeData() {
        this.showLoading(true);
        
        try {
            console.log(`Loading block time data for ${this.currentTimeRange} hours`);
            
            // Fetch block-time intervals and recent block sizes in parallel.
            // Pass the same hours_back so block size buckets span the full chart window.
            const [blockTimeResponse, blockSizeResponse] = await Promise.all([
                fetch(`${this.apiBase}/block-time/data?hours_back=${this.currentTimeRange}`),
                fetch(`${this.apiBase}/block-size/recent?hours_back=${this.currentTimeRange}&buckets=${this.blockSizeLimit}`)
            ]);
            
            if (!blockTimeResponse.ok) {
                throw new Error(`HTTP error! status: ${blockTimeResponse.status}`);
            }
            
            const data = await blockTimeResponse.json();
            console.log('Block time data loaded:', data);
            
            // Individual block sizes (best-effort; don't fail if endpoint missing)
            let recentBlocks = [];
            if (blockSizeResponse.ok) {
                const bsData = await blockSizeResponse.json();
                recentBlocks = bsData.blocks || [];
                console.log(`Loaded ${recentBlocks.length} individual block size records`);
            } else {
                console.warn('Could not load individual block sizes:', blockSizeResponse.status);
            }
            
            this.currentData = data;
            this.updateChart(data, recentBlocks);
            this.updateTable(data);
            this.updateStats(data);
            
            // Load current block height separately
            await this.loadCurrentBlockHeight();
            
        } catch (error) {
            console.error('Error loading block time data:', error);
            this.showError('Failed to load block time data');
        } finally {
            this.showLoading(false);
        }
    }
    
    async loadCurrentBlockHeight() {
        try {
            // Use the estimation API with a dummy future height to get current height
            // We'll handle the expected error and extract the current height from it
            const response = await fetch(`${this.apiBase}/block-time/estimate?target_height=999999999`);
            
            if (response.status === 400) {
                // Expected error, extract current height from error message
                const errorData = await response.json();
                const match = errorData.detail.match(/current height \((\d+)\)/);
                if (match) {
                    const currentHeight = parseInt(match[1]);
                    this.updateCurrentBlockHeight(currentHeight);
                    return;
                }
            } else if (response.ok) {
                // Shouldn't happen with our dummy height, but handle it anyway
                const data = await response.json();
                if (data.current_height) {
                    this.updateCurrentBlockHeight(data.current_height);
                    return;
                }
            }
            
            // If we get here, try getting it from the unified summary API
            const summaryResponse = await fetch(`${this.apiBase}/unified/summary`);
            if (summaryResponse.ok) {
                const summaryData = await summaryResponse.json();
                if (summaryData.latest_snapshot && summaryData.latest_snapshot.layer_block_height) {
                    this.updateCurrentBlockHeight(summaryData.latest_snapshot.layer_block_height);
                }
            }
            
        } catch (error) {
            console.error('Error loading current block height:', error);
            // Don't show error to user, just leave it as '--'
        }
    }
    
    updateCurrentBlockHeight(height) {
        const element = document.getElementById('currentBlockHeight');
        if (element && height) {
            element.textContent = height.toString();
        }
    }
    
    updateChart(data, recentBlocks = []) {
        if (!this.chart || !data.block_times) {
            return;
        }
        
        // Dataset 0: block time intervals
        const blockTimeData = data.block_times.map(item => ({
            x: new Date(item.datetime),
            y: item.block_time_seconds,
            originalData: item
        }));
        
        // Dataset 1: block sizes bucketed evenly across the chart's time range,
        // with spike blocks injected at their actual timestamps so they are never averaged away.
        const filteredBlocks = recentBlocks.filter(b => b.block_size_bytes != null && b.timestamp);
        const individualSizeData = filteredBlocks.map(b => ({
            x: new Date(b.timestamp),
            y: b.block_size_bytes / 1024,
            block_count: b.block_count,
            is_spike: b.is_spike || false,
            height: b.height || null,
        }));

        // Per-point styling arrays: spike blocks get a visible red dot, others get no dot
        const pointRadii         = filteredBlocks.map(b => b.is_spike ? 5 : 0);
        const pointHoverRadii    = filteredBlocks.map(b => b.is_spike ? 7 : 4);
        const pointColors        = filteredBlocks.map(b => b.is_spike ? '#ff4444' : '#10b981');
        const pointBorderColors  = filteredBlocks.map(b => b.is_spike ? '#ff0000' : '#10b981');

        this.chart.data.datasets[0].data = blockTimeData;
        this.chart.data.datasets[1].data = individualSizeData;
        this.chart.data.datasets[1].pointRadius        = pointRadii;
        this.chart.data.datasets[1].pointHoverRadius   = pointHoverRadii;
        this.chart.data.datasets[1].pointBackgroundColor = pointColors;
        this.chart.data.datasets[1].pointBorderColor   = pointBorderColors;
        this.chart.update('none');
        
        console.log(`Chart updated: ${blockTimeData.length} block-time points, ${individualSizeData.length} block-size points`);
    }
    
    updateTable(data) {
        const tableBody = document.getElementById('blockTimeTableBody');
        if (!tableBody || !data.block_times) {
            return;
        }
        
        if (data.block_times.length === 0) {
            tableBody.innerHTML = '<tr><td colspan="7" class="text-center">No block time data available for this time range</td></tr>';
            return;
        }
        
        // Sort by timestamp descending (newest first)
        const sortedData = [...data.block_times].sort((a, b) => b.timestamp - a.timestamp);
        
        tableBody.innerHTML = sortedData.map(item => {
            const date = new Date(item.datetime);
            const formattedDate = date.toLocaleString();
            const avgSize = item.avg_block_size_bytes != null
                ? `${(item.avg_block_size_bytes / 1024).toFixed(2)} KB`
                : '—';
            const maxSize = item.max_block_size_bytes != null
                ? `${(item.max_block_size_bytes / 1024).toFixed(2)} KB`
                : '—';
            
            return `
                <tr>
                    <td>${formattedDate}</td>
                    <td>${item.block_time_seconds.toFixed(3)}</td>
                    <td>${item.height_range}</td>
                    <td>${item.blocks_counted}</td>
                    <td>${item.time_span_seconds}</td>
                    <td>${avgSize}</td>
                    <td>${maxSize}</td>
                </tr>
            `;
        }).join('');
        
        console.log(`Table updated with ${sortedData.length} rows`);
    }
    
    updateStats(data) {
        // Update average block time
        const avgBlockTimeEl = document.getElementById('avgBlockTime');
        if (avgBlockTimeEl) {
            if (data.average_block_time) {
                avgBlockTimeEl.textContent = `${data.average_block_time.toFixed(3)}s`;
            } else {
                avgBlockTimeEl.textContent = '--';
            }
        }
        
        // Update data point count
        const dataPointCountEl = document.getElementById('dataPointCount');
        if (dataPointCountEl) {
            dataPointCountEl.textContent = data.count || 0;
        }
        
        // Update time range display
        const timeRangeDisplayEl = document.getElementById('timeRangeDisplay');
        if (timeRangeDisplayEl) {
            const hours = data.hours_back || this.currentTimeRange;
            if (hours < 24) {
                timeRangeDisplayEl.textContent = `${hours} hours`;
            } else if (hours < 168) {
                timeRangeDisplayEl.textContent = `${Math.round(hours / 24)} days`;
            } else if (hours < 720) {
                timeRangeDisplayEl.textContent = `${Math.round(hours / 168)} weeks`;
            } else {
                timeRangeDisplayEl.textContent = `${Math.round(hours / 720)} months`;
            }
        }

        // Block size stats (only present when layer_block_sizes has data)
        const sizePoints = (data.block_times || []).filter(p => p.avg_block_size_bytes != null);

        const avgBlockSizeEl = document.getElementById('avgBlockSize');
        const maxBlockSizeEl = document.getElementById('maxBlockSize');
        const blocksTrackedEl = document.getElementById('blocksTracked');

        if (sizePoints.length > 0) {
            const overallAvg = sizePoints.reduce((s, p) => s + p.avg_block_size_bytes, 0) / sizePoints.length;
            const overallMax = Math.max(...sizePoints.map(p => p.max_block_size_bytes));
            const totalBlocks = sizePoints.reduce((s, p) => s + p.blocks_counted, 0);

            if (avgBlockSizeEl) avgBlockSizeEl.textContent = `${(overallAvg / 1024).toFixed(2)} KB`;
            if (maxBlockSizeEl) maxBlockSizeEl.textContent = `${(overallMax / 1024).toFixed(2)} KB`;
            if (blocksTrackedEl) blocksTrackedEl.textContent = totalBlocks.toLocaleString();
        } else {
            if (avgBlockSizeEl) avgBlockSizeEl.textContent = 'No data yet';
            if (maxBlockSizeEl) maxBlockSizeEl.textContent = 'No data yet';
            if (blocksTrackedEl) blocksTrackedEl.textContent = '0';
        }
    }
    
    exportData() {
        if (!this.currentData || !this.currentData.block_times) {
            alert('No data available to export');
            return;
        }
        
        // Convert data to CSV
        const headers = ['Timestamp', 'DateTime', 'Block Time (seconds)', 'Height Range', 'Blocks Counted', 'Time Span (seconds)', 'Avg Block Size (bytes)', 'Max Block Size (bytes)'];
        const csvContent = [
            headers.join(','),
            ...this.currentData.block_times.map(item => [
                item.timestamp,
                `"${item.datetime}"`,
                item.block_time_seconds,
                `"${item.height_range}"`,
                item.blocks_counted,
                item.time_span_seconds,
                item.avg_block_size_bytes ?? '',
                item.max_block_size_bytes ?? ''
            ].join(','))
        ].join('\n');
        
        // Create and download file
        const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
        const link = document.createElement('a');
        const url = URL.createObjectURL(blob);
        link.setAttribute('href', url);
        link.setAttribute('download', `tellor-block-time-${this.currentTimeRange}h-${new Date().toISOString().split('T')[0]}.csv`);
        link.style.visibility = 'hidden';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        
        console.log('Data exported to CSV');
    }
    
    async estimateBlockHeight() {
        const targetHeightInput = document.getElementById('targetHeightInput');
        const estimateBtn = document.getElementById('estimateBtn');
        
        if (!targetHeightInput || !estimateBtn) {
            return;
        }
        
        const targetHeight = parseInt(targetHeightInput.value);
        
        // Validate input
        if (isNaN(targetHeight) || targetHeight <= 0) {
            this.showEstimationError('Please enter a valid block height');
            return;
        }
        
        // Disable button and show loading state
        estimateBtn.disabled = true;
        estimateBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Estimating...';
        
        this.hideEstimationError();
        this.hideEstimationResults();
        
        try {
            console.log(`Estimating arrival time for block height ${targetHeight}`);
            
            const response = await fetch(`${this.apiBase}/block-time/estimate?target_height=${targetHeight}`);
            
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || `HTTP error! status: ${response.status}`);
            }
            
            const data = await response.json();
            console.log('Estimation data received:', data);
            
            this.displayEstimationResults(data);
            
        } catch (error) {
            console.error('Error estimating block height:', error);
            this.showEstimationError(error.message || 'Failed to estimate block height');
        } finally {
            // Re-enable button
            estimateBtn.disabled = false;
            estimateBtn.innerHTML = '<i class="fas fa-calculator"></i> Estimate';
        }
    }
    
    displayEstimationResults(data) {
        // Hide any existing error messages
        this.hideEstimationError();
        
        // Show results section
        const resultsSection = document.getElementById('estimationResults');
        if (resultsSection) {
            resultsSection.classList.remove('hidden');
        }
        
        // Update current network status
        this.updateElement('currentHeight', data.current_height?.toLocaleString() || '--');
        this.updateElement('currentTime', this.formatDateTime(data.current_datetime) || '--');
        this.updateElement('avgBlockTimeUsed', `${data.avg_block_time_seconds}s` || '--');
        this.updateElement('dataSource', data.data_source || '--');
        
        // Update estimation results
        this.updateElement('targetHeightDisplay', data.target_height?.toLocaleString() || '--');
        this.updateElement('blocksRemaining', data.blocks_remaining?.toLocaleString() || '--');
        this.updateElement('timeUntil', data.time_until_formatted || '--');
        this.updateElement('estimatedArrival', data.estimated_arrival_formatted || '--');
        
        // Calculate and display local time
        if (data.estimated_arrival_utc) {
            try {
                const utcDate = new Date(data.estimated_arrival_utc);
                const localTime = utcDate.toLocaleString();
                this.updateElement('estimatedArrivalLocal', localTime);
            } catch (e) {
                console.error('Error formatting local time:', e);
                this.updateElement('estimatedArrivalLocal', 'Error formatting time');
            }
        } else {
            this.updateElement('estimatedArrivalLocal', '--');
        }
    }
    
    updateElement(id, text) {
        const element = document.getElementById(id);
        if (element) {
            element.textContent = text;
        }
    }
    
    formatDateTime(dateTimeString) {
        if (!dateTimeString) return null;
        
        try {
            const date = new Date(dateTimeString);
            return date.toLocaleString();
        } catch (e) {
            return dateTimeString; // Return original if parsing fails
        }
    }
    
    showEstimationError(message) {
        const errorDiv = document.getElementById('estimationError');
        if (errorDiv) {
            errorDiv.innerHTML = `
                <div class="alert alert-error">
                    <i class="fas fa-exclamation-triangle"></i>
                    <span>${message}</span>
                </div>
            `;
        }
    }
    
    hideEstimationError() {
        const errorDiv = document.getElementById('estimationError');
        if (errorDiv) {
            errorDiv.innerHTML = '';
        }
    }
    
    hideEstimationResults() {
        const resultsSection = document.getElementById('estimationResults');
        if (resultsSection) {
            resultsSection.classList.add('hidden');
        }
    }
    
    showLoading(show) {
        const overlay = document.getElementById('loadingOverlay');
        if (overlay) {
            if (show) {
                overlay.classList.remove('hidden');
            } else {
                overlay.classList.add('hidden');
            }
        }
        
        // Disable/enable controls
        const controls = ['timeRangeSelect', 'refreshBtn', 'exportDataBtn'];
        controls.forEach(id => {
            const element = document.getElementById(id);
            if (element) {
                element.disabled = show;
            }
        });
    }
    
    showError(message) {
        console.error('Block Time Analytics Error:', message);
        
        // Update table to show error
        const tableBody = document.getElementById('blockTimeTableBody');
        if (tableBody) {
            tableBody.innerHTML = `<tr><td colspan="7" class="text-center text-error">Error: ${message}</td></tr>`;
        }
        
        // Update stats to show error (but preserve current block height if available)
        const elements = ['avgBlockTime', 'dataPointCount', 'timeRangeDisplay'];
        elements.forEach(id => {
            const element = document.getElementById(id);
            if (element) {
                element.textContent = 'Error';
            }
        });
        
        // Only clear current block height if it's not already set
        const currentHeightEl = document.getElementById('currentBlockHeight');
        if (currentHeightEl && currentHeightEl.textContent === '--') {
            currentHeightEl.textContent = 'Error';
        }
    }
}

// Initialize the dashboard when the DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    console.log('DOM loaded, initializing Block Time Analytics');
    new BlockTimeAnalytics();
});
