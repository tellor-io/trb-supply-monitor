// Tellor Supply Analytics - Snapshot Detail Page JavaScript

class SnapshotDetailPage {
    constructor(ethTimestamp) {
        this.apiBase = window.ROOT_PATH || '';
        this.ethTimestamp = ethTimestamp;
        this.snapshotData = null;
        this.balancesData = [];
        this.filteredBalances = [];

        this.init();
    }

    init() {
        this.bindEvents();
        this.loadSnapshotData();
    }

    bindEvents() {
        // Search functionality
        const searchInput = document.getElementById('searchInput');
        if (searchInput) {
            searchInput.addEventListener('input', () => this.filterBalances());
        }

        // Account type filter
        const accountTypeFilter = document.getElementById('accountTypeFilter');
        if (accountTypeFilter) {
            accountTypeFilter.addEventListener('change', () => this.filterBalances());
        }

        // Export button
        const exportBtn = document.getElementById('exportBalancesBtn');
        if (exportBtn) {
            exportBtn.addEventListener('click', () => this.exportBalances());
        }
    }

    async loadSnapshotData() {
        this.showLoading();
        try {
            // Load both snapshot overview and balances in parallel
            const [snapshotResponse, balancesResponse] = await Promise.all([
                fetch(`${this.apiBase}/api/unified/snapshot/${this.ethTimestamp}`),
                fetch(`${this.apiBase}/api/unified/balances/${this.ethTimestamp}`)
            ]);

            if (!snapshotResponse.ok) {
                throw new Error('Failed to load snapshot data');
            }

            this.snapshotData = await snapshotResponse.json();

            if (balancesResponse.ok) {
                const balancesData = await balancesResponse.json();
                this.balancesData = balancesData.balances || [];
            } else {
                console.warn('No balance data found for this snapshot');
                this.balancesData = [];
            }

            this.updateSnapshotOverview();
            this.filterBalances(); // This will also update the table

        } catch (error) {
            console.error('Error loading snapshot data:', error);
            this.showError('Failed to load snapshot data');
        } finally {
            this.hideLoading();
        }
    }

    updateSnapshotOverview() {
        if (!this.snapshotData) return;

        // Update timestamp in header
        const timestamp = this.snapshotData.eth_block_timestamp || this.ethTimestamp;
        const datetime = new Date(timestamp * 1000);
        document.getElementById('snapshotTimestamp').textContent =
            `${datetime.toLocaleString()} (${datetime.toISOString()})`;

        // Update Ethereum block info
        document.getElementById('ethBlockNumber').textContent =
            this.formatNumber(this.snapshotData.eth_block_number, 0, false) || '--';
        document.getElementById('ethBlockTime').textContent =
            this.snapshotData.eth_block_datetime || '--';

        // Update Tellor Layer block info
        document.getElementById('layerBlockHeight').textContent =
            this.formatNumber(this.snapshotData.layer_block_height, 0, false) || '--';
        document.getElementById('layerBlockTime').textContent =
            this.snapshotData.layer_block_datetime || '--';

        // Update supply metrics
        document.getElementById('bridgeBalance').textContent =
            this.formatTRB(this.snapshotData.bridge_balance_trb);
        document.getElementById('layerSupply').textContent =
            this.formatTRB(this.snapshotData.layer_total_supply_trb);
        document.getElementById('freeFloating').textContent =
            this.formatTRB(this.snapshotData.free_floating_trb);
        document.getElementById('totalBalance').textContent =
            this.formatTRB(this.snapshotData.total_trb_balance);

        // Update staking & reporter metrics
        document.getElementById('bondedTokens').textContent =
            this.formatTRB(this.snapshotData.bonded_tokens);
        document.getElementById('notBondedTokens').textContent =
            this.formatTRB(this.snapshotData.not_bonded_tokens);
        document.getElementById('reporterPower').textContent =
            this.formatNumber(this.snapshotData.total_reporter_power) || '0';
        document.getElementById('activeAddresses').textContent =
            this.formatNumber(this.snapshotData.addresses_with_balance) || '0';
        document.getElementById('totalAddresses').textContent =
            this.formatNumber(this.snapshotData.total_addresses) || '0';
    }

    filterBalances() {
        const searchTerm = document.getElementById('searchInput').value.toLowerCase();
        const accountType = document.getElementById('accountTypeFilter').value.toLowerCase();

        this.filteredBalances = this.balancesData.filter(balance => {
            const matchesSearch = !searchTerm ||
                balance.address.toLowerCase().includes(searchTerm);
            const matchesType = !accountType ||
                balance.account_type.toLowerCase() === accountType;

            return matchesSearch && matchesType;
        });

        // Update counts
        document.getElementById('displayedCount').textContent = this.filteredBalances.length;
        document.getElementById('totalBalancesCount').textContent = this.balancesData.length;

        this.updateBalancesTable();
    }

    updateBalancesTable() {
        const tbody = document.getElementById('balancesTableBody');

        if (this.filteredBalances.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="5" class="text-center text-muted">
                        No balances found matching the current filters.
                    </td>
                </tr>
            `;
            return;
        }

        // Sort by balance descending
        const sortedBalances = [...this.filteredBalances].sort((a, b) =>
            (b.loya_balance_trb || 0) - (a.loya_balance_trb || 0)
        );

        tbody.innerHTML = sortedBalances.map(balance => `
            <tr>
                <td class="font-mono text-xs">
                    ${this.truncateAddress(balance.address)}
                    <br><small class="text-muted">${balance.address}</small>
                </td>
                <td>
                    <span class="badge ${this.getAccountTypeBadgeClass(balance.account_type)}">
                        ${balance.account_type}
                    </span>
                </td>
                <td class="font-mono">
                    ${this.formatNumber(balance.loya_balance, 0)}
                </td>
                <td class="font-mono text-primary">
                    ${this.formatTRB(balance.loya_balance_trb, 6)}
                </td>
                <td>
                    <button
                        class="btn btn-sm btn-outline"
                        onclick="navigator.clipboard.writeText('${balance.address}')"
                        title="Copy address"
                    >
                        <i class="fas fa-copy"></i>
                    </button>
                </td>
            </tr>
        `).join('');
    }

    async exportBalances() {
        try {
            if (this.filteredBalances.length === 0) {
                alert('No balance data to export');
                return;
            }

            const headers = ['address', 'account_type', 'loya_balance', 'loya_balance_trb'];
            const csvContent = [
                headers.join(','),
                ...this.filteredBalances.map(balance =>
                    headers.map(header => balance[header] || '').join(',')
                )
            ].join('\n');

            // Download CSV
            const blob = new Blob([csvContent], { type: 'text/csv' });
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            const datetime = new Date(this.ethTimestamp * 1000).toISOString().slice(0, 19).replace(/:/g, '-');
            a.download = `snapshot-balances-${this.ethTimestamp}-${datetime}.csv`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            window.URL.revokeObjectURL(url);

            console.log('Balances exported successfully');
        } catch (error) {
            console.error('Error exporting balances:', error);
            alert('Failed to export balances');
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
        return `${this.formatNumber(amount, decimals)} TRB`;
    }

    truncateAddress(address) {
        if (!address) return 'N/A';
        return `${address.slice(0, 10)}...${address.slice(-8)}`;
    }

    getAccountTypeBadgeClass(type) {
        const badges = {
            'validator': 'badge-success',
            'reporter': 'badge-info',
            'delegator': 'badge-info',
            'contract': 'badge-warning',
            'module': 'badge-warning',
            'user': 'badge-secondary'
        };
        return badges[type?.toLowerCase()] || 'badge-secondary';
    }

    showLoading() {
        const overlay = document.getElementById('loadingOverlay');
        if (overlay) {
            overlay.classList.remove('hidden');
        }
    }

    hideLoading() {
        const overlay = document.getElementById('loadingOverlay');
        if (overlay) {
            overlay.classList.add('hidden');
        }
    }

    showError(message) {
        alert(`Error: ${message}`);
        console.error(message);
    }
}

// Initialize the page when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    const ethTimestamp = window.ETH_TIMESTAMP;
    if (!ethTimestamp) {
        alert('Error: No timestamp provided');
        return;
    }

    window.snapshotDetailPage = new SnapshotDetailPage(ethTimestamp);
});
