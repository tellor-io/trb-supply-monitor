#!/bin/bash
# Setup script for Tellor Balance Analytics

echo "Setting up Tellor Balance Analytics..."

# Create directories
mkdir -p templates static/css static/js logs backups

# Copy style template
cp style_template/unified-style-template.css static/css/

# Install Python dependencies
echo "Installing Python dependencies..."
pip install fastapi uvicorn requests

# Create cron job (optional)
if [ "$1" = "--cron" ]; then
    CRON_JOB="0 * * * * cd $(pwd) && python3 scheduler.py >> logs/cron.log 2>&1"
    (crontab -l 2>/dev/null; echo "$CRON_JOB") | crontab -
    echo "Cron job installed"
fi

# Create systemd service (optional)
if [ "$1" = "--systemd" ]; then
    sudo tee /etc/systemd/system/tellor-balance-collector.service > /dev/null <<EOF
[Unit]
Description=Tellor Balance Collector
After=network.target

[Service]
Type=oneshot
User=$(whoami)
WorkingDirectory=$(pwd)
ExecStart=$(which python3) scheduler.py
Environment=PATH=/usr/bin:/bin
EOF

    sudo tee /etc/systemd/system/tellor-balance-collector.timer > /dev/null <<EOF
[Unit]
Description=Run Tellor Balance Collector every hour
Requires=tellor-balance-collector.service

[Timer]
OnCalendar=hourly
Persistent=true

[Install]
WantedBy=timers.target
EOF

    sudo systemctl daemon-reload
    sudo systemctl enable tellor-balance-collector.timer
    sudo systemctl start tellor-balance-collector.timer
    
    echo "Systemd timer installed and started"
fi

echo "Setup complete!"
echo ""
echo "To start the web interface:"
echo "  python api.py"
echo ""
echo "To run manual collection:"
echo "  python -m src.tellor_supply_analytics.get_active_balances"
echo ""
echo "Web dashboard will be available at: http://localhost:8001" 