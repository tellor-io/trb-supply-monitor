# Unified Style Template

A comprehensive CSS template system extracted from the tellor-supply-analytics project, designed to create consistent, modern web interfaces with a dark theme aesthetic.

## 🎨 Features

- **Modern Dark Theme**: Cyberpunk-inspired color scheme with neon accents
- **Responsive Design**: Mobile-first approach with breakpoints for all devices  
- **Component System**: Pre-built components for rapid development
- **CSS Custom Properties**: Easy theming and customization
- **Accessibility**: WCAG compliant with focus states and reduced motion support
- **Typography System**: Consistent text styling with multiple weights and sizes
- **Grid & Flexbox Utilities**: Modern layout system
- **Animation Library**: Smooth transitions and hover effects

## 🚀 Quick Start

1. **Include the CSS file**:
```html
<link rel="stylesheet" href="unified-style-template.css">
```

2. **Add required fonts**:
```html
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
```

3. **Basic HTML structure**:
```html
<div class="app">
  <main class="main">
    <!-- Your content here -->
  </main>
</div>
```

## 🎯 Core Components

### Cards
```html
<div class="card">
  <div class="card-header">
    <h2>Card Title</h2>
  </div>
  <div class="card-body">
    <p>Card content goes here</p>
  </div>
</div>
```

### Buttons
```html
<button class="btn btn-primary">Primary Button</button>
<button class="btn btn-secondary">Secondary Button</button>
<button class="btn btn-outline">Outline Button</button>
```

### Stat Cards
```html
<div class="stat-card clickable">
  <div class="stat-icon">
    <i class="fas fa-users"></i>
  </div>
  <div class="stat-content">
    <div class="stat-number">1,234</div>
    <div class="stat-title">Total Users</div>
    <div class="stat-subtitle">+12% from last month</div>
  </div>
</div>
```

### Forms
```html
<div class="form-group">
  <label class="form-label">Name</label>
  <input type="text" class="form-input" placeholder="Enter name">
</div>

<div class="search-box">
  <i class="fas fa-search"></i>
  <input type="text" placeholder="Search...">
</div>
```

### Tables
```html
<div class="table-container">
  <table class="data-table">
    <thead>
      <tr>
        <th>Header 1</th>
        <th>Header 2</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td>Data 1</td>
        <td>Data 2</td>
      </tr>
    </tbody>
  </table>
</div>
```

### Badges
```html
<span class="badge badge-success">Success</span>
<span class="badge badge-danger">Danger</span>
<span class="badge badge-info">Info</span>
<span class="badge badge-warning">Warning</span>
```

### Modals
```html
<div class="modal" id="myModal">
  <div class="modal-content">
    <div class="modal-header">
      <h3>Modal Title</h3>
      <button class="modal-close">&times;</button>
    </div>
    <div class="modal-body">
      <p>Modal content</p>
    </div>
  </div>
</div>
```

## 🛠 Customization

### Color Scheme
Modify the CSS custom properties in the `:root` selector:

```css
:root {
  /* Primary Colors */
  --primary-green: #00ff88;   /* Your brand primary */
  --primary-blue: #00d4ff;    /* Your brand secondary */
  --primary-purple: #a855f7;  /* Your brand accent */
  --accent-orange: #ff6b35;   /* Warning/error color */
  
  /* Backgrounds */
  --bg-primary: linear-gradient(135deg, #0a0a0a 0%, #1a0a1a 50%, #0a0a0a 100%);
  --bg-secondary: rgba(25, 25, 35, 0.95);
  --bg-tertiary: #1a1a2e;
}
```

### Typography
Change font families:
```css
:root {
  --font-primary: 'Your Font', sans-serif;
  --font-mono: 'Your Mono Font', monospace;
}
```

### Spacing
Adjust spacing scale:
```css
:root {
  --spacing-xs: 0.25rem;
  --spacing-sm: 0.5rem;
  --spacing-md: 0.75rem;
  --spacing-lg: 1rem;
  --spacing-xl: 1.5rem;
  --spacing-2xl: 2rem;
}
```

## 📱 Responsive Design

The template uses a mobile-first approach with these breakpoints:

- **Mobile**: Default (up to 768px)
- **Tablet**: 768px and up
- **Desktop**: 1024px and up

### Responsive Utilities
```html
<!-- Grid system -->
<div class="grid grid-cols-1 grid-cols-2@md grid-cols-4@lg">
  <!-- Content -->
</div>

<!-- Responsive text -->
<h1 class="text-lg text-xl@md text-2xl@lg">Responsive Heading</h1>
```

## 🎨 Layout System

### Grid System
```html
<div class="grid grid-cols-3 gap-lg">
  <div>Column 1</div>
  <div>Column 2</div>
  <div>Column 3</div>
</div>

<div class="grid grid-auto-fit gap-md">
  <!-- Auto-fitting columns -->
</div>
```

### Flexbox Utilities
```html
<div class="flex items-center justify-between">
  <div>Left content</div>
  <div>Right content</div>
</div>
```

### Spacing Utilities
```html
<div class="p-lg m-xl">Padded and margined content</div>
<div class="mb-lg">Content with bottom margin</div>
```

## 🔧 JavaScript Integration

### Modal Control
```javascript
function openModal(modalId) {
  document.getElementById(modalId).classList.add('show');
}

function closeModal(modalId) {
  document.getElementById(modalId).classList.remove('show');
}
```

### Loading States
```javascript
function showLoading() {
  document.getElementById('loadingOverlay').classList.remove('hidden');
}

function hideLoading() {
  document.getElementById('loadingOverlay').classList.add('hidden');
}
```

## 🎭 Theme Variants

### Light Theme
```html
<body class="theme-light">
  <!-- Content -->
</body>
```

### Extra Dark Theme
```html
<body class="theme-dark">
  <!-- Content -->
</body>
```

## ♿ Accessibility Features

- **Focus States**: All interactive elements have visible focus indicators
- **Color Contrast**: WCAG AA compliant color combinations
- **Reduced Motion**: Respects `prefers-reduced-motion` setting
- **High Contrast**: Supports `prefers-contrast: high`
- **Semantic HTML**: Encourages proper markup structure

## 🏗 Best Practices

1. **Use Semantic HTML**: Always use appropriate HTML elements
2. **Follow BEM-like Naming**: Component-based class names
3. **Leverage Utility Classes**: Use utilities for spacing, colors, etc.
4. **Mobile First**: Design for mobile, enhance for larger screens
5. **Performance**: Minimize CSS overrides, use efficient selectors

## 📦 File Structure

```
project/
├── unified-style-template.css    # Main CSS file
├── template-example.html         # Example implementation
└── STYLE-TEMPLATE-README.md     # This documentation
```

## 🎨 Color Palette

| Color | Hex | Usage |
|-------|-----|-------|
| Primary Green | `#00ff88` | Primary actions, success states |
| Primary Blue | `#00d4ff` | Secondary actions, info states |
| Primary Purple | `#a855f7` | Accent elements, highlights |
| Accent Orange | `#ff6b35` | Warnings, urgent states |
| Accent Red | `#ff4757` | Errors, danger states |

## 🚀 Example Projects

The template works great for:
- **Dashboards**: Analytics, admin panels, business intelligence
- **SaaS Applications**: Web apps, tools, platforms  
- **Portfolio Sites**: Developer portfolios, agencies
- **Documentation**: API docs, guides, wikis
- **E-commerce**: Product catalogs, checkout flows

## 📈 Performance

- **Minified Size**: ~45KB (uncompressed)
- **No Dependencies**: Pure CSS, no frameworks required
- **Modern CSS**: Uses CSS Grid, Flexbox, Custom Properties
- **Optimized**: Efficient selectors, minimal specificity

## 🤝 Contributing

To customize this template for your projects:

1. Fork the template files
2. Modify the CSS custom properties for your brand
3. Add your own components following the established patterns
4. Test across different devices and browsers
5. Document your customizations

## 📄 License

This template is extracted from open-source analytics software and is provided as-is for educational and commercial use. Feel free to modify and distribute.

---

**Built with ❤️ for modern web development**