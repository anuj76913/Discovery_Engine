---
name: Lumina Analytics
colors:
  surface: '#f8f9ff'
  surface-dim: '#cbdbf5'
  surface-bright: '#f8f9ff'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#eff4ff'
  surface-container: '#e5eeff'
  surface-container-high: '#dce9ff'
  surface-container-highest: '#d3e4fe'
  on-surface: '#0b1c30'
  on-surface-variant: '#5b4042'
  inverse-surface: '#213145'
  inverse-on-surface: '#eaf1ff'
  outline: '#8f6f72'
  outline-variant: '#e3bdc0'
  surface-tint: '#bd0043'
  primary: '#b90041'
  on-primary: '#ffffff'
  primary-container: '#df2457'
  on-primary-container: '#fffbff'
  inverse-primary: '#ffb2ba'
  secondary: '#515f74'
  on-secondary: '#ffffff'
  secondary-container: '#d5e3fd'
  on-secondary-container: '#57657b'
  tertiary: '#595c5e'
  on-tertiary: '#ffffff'
  tertiary-container: '#727577'
  on-tertiary-container: '#fbfdff'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#ffd9dc'
  primary-fixed-dim: '#ffb2ba'
  on-primary-fixed: '#400011'
  on-primary-fixed-variant: '#910031'
  secondary-fixed: '#d5e3fd'
  secondary-fixed-dim: '#b9c7e0'
  on-secondary-fixed: '#0d1c2f'
  on-secondary-fixed-variant: '#3a485c'
  tertiary-fixed: '#e0e3e5'
  tertiary-fixed-dim: '#c4c7c9'
  on-tertiary-fixed: '#191c1e'
  on-tertiary-fixed-variant: '#444749'
  background: '#f8f9ff'
  on-background: '#0b1c30'
  surface-variant: '#d3e4fe'
typography:
  display-lg:
    fontFamily: Hanken Grotesk
    fontSize: 36px
    fontWeight: '700'
    lineHeight: 44px
    letterSpacing: -0.02em
  headline-md:
    fontFamily: Hanken Grotesk
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
  section-label:
    fontFamily: Hanken Grotesk
    fontSize: 12px
    fontWeight: '800'
    lineHeight: 16px
    letterSpacing: 0.05em
  body-regular:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  data-tabular:
    fontFamily: JetBrains Mono
    fontSize: 13px
    fontWeight: '500'
    lineHeight: 18px
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  grid-columns: '12'
  gutter: 24px
  margin-desktop: 40px
  margin-mobile: 16px
  stack-sm: 8px
  stack-md: 16px
  stack-lg: 32px
---

## Brand & Style
The design system is engineered for high-density data exploration within the fashion-retail sector. It balances the rigor of business intelligence with the aesthetic polish of premium e-commerce. The brand personality is **Insightful, Precise, and Sophisticated**.

The visual direction follows a **Corporate Modern** style with **Minimalist** leanings. It prioritizes clarity and rapid scannability, using white space not just for aesthetics, but as a functional separator for complex datasets. The emotional response should be one of "effortless mastery"—transforming overwhelming raw data into actionable retail strategy through a clean, structured interface.

## Colors
The palette is dominated by neutral "Slate" tones to ensure the primary accent maintains maximum impact. 

- **Primary (#FF3F6C):** Reserved exclusively for interactive elements, key performance indicators (KPIs), and primary data series in charts. 
- **Secondary (#334155):** Used for primary text and iconography to maintain high contrast without the harshness of pure black.
- **Tertiary/Surface (#F8FAFC):** An off-white used for card backgrounds and subtle section nesting to reduce eye strain.
- **Data Visualization:** For heatmaps and multi-series charts, use a monochromatic scale of the primary pink (varying from 10% to 100% opacity) to maintain brand cohesion.

## Typography
The typographic hierarchy is designed for a "scan-and-drill" workflow. 

- **Headings:** Use Hanken Grotesk for its geometric precision and modern weight distribution. 
- **Section Headers:** Implement small-caps with increased letter spacing to create clear structural boundaries without using heavy lines.
- **Data & Tables:** JetBrains Mono is utilized for all numeric values and table content. Monospaced characters ensure that columns of numbers align perfectly, allowing users to compare magnitudes at a glance.
- **Body:** Inter provides maximum legibility for tooltips, descriptions, and methodology notes.

## Layout & Spacing
This design system employs a **Fixed Grid** model for desktop to ensure data visualizations maintain their intended aspect ratios, transitioning to a **Fluid** model for tablet and mobile.

- **Desktop (1440px+):** 12-column grid, 24px gutters, 40px side margins. 
- **Internal Card Spacing:** Use a strict 8px base unit. Elements within cards should typically be separated by 16px (stack-md).
- **Density:** The dashboard is high-density. Vertical rhythm is maintained by 8px increments to keep the UI compact yet breathable.

## Elevation & Depth
Depth is communicated through **Tonal Layering** and **Low-Contrast Outlines** rather than heavy shadows.

- **Surface Level 0 (Background):** Pure white or dark charcoal.
- **Surface Level 1 (Cards):** Tertiary off-white with a 1px border (#E2E8F0 in light mode).
- **Interactive States:** On hover, cards transition to a 2px primary-colored left border or a very soft ambient shadow (0px 4px 12px rgba(0, 0, 0, 0.05)) to indicate focus.
- **Depth Hierarchy:** Modals and dropdowns use a sharp 1px border and a medium-diffused shadow to sit clearly above the data plane.

## Shapes
The shape language is "Softly Geometric." All containers and primary components utilize a consistent 8px-12px radius to soften the technical nature of the analytics.

- **Standard Cards:** 12px corner radius.
- **Input Fields & Buttons:** 8px corner radius.
- **Data Bars:** Fully rounded (pill-shaped) ends for horizontal bar charts to feel more modern and less "industrial."
- **Selection Indicators:** 4px radius for small chips and tags.

## Components

### Charts & Visualizations
- **Horizontal Bar Charts:** Stacked or ranked. Use the primary pink for the "active" metric and varying shades of slate for comparative or secondary data.
- **Heatmaps:** Use a 5-step monochromatic scale of the primary pink. Labels within heatmaps must switch to white text when the background color exceeds 50% opacity.

### Buttons & Controls
- **Primary Button:** Solid primary pink, white text, bold weight.
- **Segmented Control:** A pill-shaped toggle used for switching between "Mentions" and "% of Relevant" views. High contrast active state.

### Data Tables
- **Header:** Small-caps, bold, slate gray.
- **Rows:** Alternating subtle zebra striping (Tertiary color). 1px bottom border only.
- **Cells:** Tabular mono font for all numbers.

### Cards
- **Structure:** 12px padding. Title at the top-left in bold; optional "Info" icon at top-right for methodology tooltips.
- **Interaction:** Subtle lift on hover or border-color shift to primary pink.

### Input Fields
- **Search/Filter:** Minimalist design with a 1px border and a leading search icon. Focus state uses a 2px primary pink ring.