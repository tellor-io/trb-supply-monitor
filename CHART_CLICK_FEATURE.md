# Chart Click to Table Navigation Feature

This feature allows users to click on any data point in the supply trends charts to automatically scroll to the corresponding row in the TRB Supply Data table below.

## How it Works

### User Experience
1. **Hover over charts**: Cursor changes to a pointer to indicate charts are clickable
2. **Tooltip hint**: Tooltips now include "💡 Click to view details in table below"
3. **Click any chart point**: Clicking on a data point in any of the three charts will:
   - Scroll smoothly to the corresponding table row
   - Highlight the row with a green glow effect
   - Remove the highlight after 3 seconds

### Visual Feedback
- **Cursor**: Changes to pointer on chart hover
- **Row Highlight**: Clicked row gets a green background with border
- **Animation**: Smooth pulse animation when row is highlighted
- **Scroll**: Smooth scroll to center the row in the viewport

## Technical Implementation

### Chart Configuration
- Added `onClick` handler to all chart options
- Extracts timestamp from clicked data point
- Calls `scrollToTableRow(timestamp)` method

### Table Row Identification
- Each table row has `data-timestamp` attribute
- Each table row has unique ID: `row-${timestamp}`
- Timestamp matching ensures precise navigation

### CSS Styling
```css
.chart-clicked-row {
    background-color: rgba(0, 255, 136, 0.2) !important;
    border-left: 4px solid var(--color-primary) !important;
    animation: highlightPulse 0.5s ease-in-out;
}
```

### JavaScript Method
```javascript
scrollToTableRow(timestamp) {
    const targetRow = document.getElementById(`row-${timestamp}`);
    if (targetRow) {
        // Remove existing highlights
        document.querySelectorAll('.chart-clicked-row').forEach(row => {
            row.classList.remove('chart-clicked-row');
        });
        
        // Highlight and scroll to target row
        targetRow.classList.add('chart-clicked-row');
        targetRow.scrollIntoView({ behavior: 'smooth', block: 'center' });
        
        // Remove highlight after 3 seconds
        setTimeout(() => {
            targetRow.classList.remove('chart-clicked-row');
        }, 3000);
    }
}
```

## Benefits

1. **Improved Navigation**: Easy way to jump from visual data to detailed information
2. **Better User Experience**: Intuitive interaction between charts and table
3. **Visual Feedback**: Clear indication of which row corresponds to clicked chart point
4. **Accessibility**: Smooth scrolling and temporary highlighting help users follow the action

## Charts Supported

This feature works on all three supply trends charts:
1. **Supply Overview Chart** (Total Layer Supply, Free Floating TRB, Bridge Balance)
2. **Bridge & Staking Chart** (Bridge Balance, Bonded Tokens, Not Bonded Tokens)
3. **Active Balance Chart** (Total Active Balance, Addresses with Balance)

## Browser Compatibility

- Modern browsers with ES6+ support
- Smooth scrolling supported in Chrome, Firefox, Safari, Edge
- Fallback to instant scroll if smooth scrolling not supported

## Debugging

Console logs are included for troubleshooting:
- Success: "Scrolled to row for timestamp: {timestamp}"
- Error: "Could not find table row for timestamp: {timestamp}"

## Future Enhancements

Potential improvements for this feature:
1. Keyboard navigation (arrow keys to move between rows)
2. Bidirectional linking (click table row to highlight chart point)
3. Multi-point selection and comparison
4. Export selected data points
5. Bookmark specific timestamps 