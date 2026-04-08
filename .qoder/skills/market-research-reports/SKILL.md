---
name: market-research-reports
description: Generate professional-grade market research reports (50+ pages) with comprehensive analysis, frameworks (Porter's Five Forces, PESTLE, SWOT, TAM/SAM/SOM), and extensive visual content. Use when creating market analysis, industry reports, competitive landscapes, investment due diligence, or strategic planning documents.
---

# Market Research Reports

Comprehensive strategic documents analyzing industries, markets, and competitive landscapes to inform business decisions. Modeled after deliverables from top consulting firms like McKinsey, BCG, Bain, Gartner, and Forrester.

## Key Features

- **Comprehensive length:** Reports designed to be 50+ pages
- **Visual-rich content:** 5-6 key diagrams generated at start
- **Data-driven analysis:** Deep integration with research for market data
- **Multi-framework approach:** Porter's Five Forces, PESTLE, SWOT, BCG Matrix, TAM/SAM/SOM
- **Professional formatting:** Consulting-firm quality typography, colors, and layout
- **Actionable recommendations:** Strategic focus with implementation roadmaps

**Output Format:** LaTeX with professional styling, compiled to PDF.

## When to Use

- Creating comprehensive market analysis for investment decisions
- Developing industry reports for strategic planning
- Analyzing competitive landscapes and market dynamics
- Conducting market sizing exercises (TAM/SAM/SOM)
- Evaluating market entry opportunities
- Preparing due diligence materials for M&A activities
- Creating thought leadership content for industry positioning
- Developing go-to-market strategy documentation

## Visual Enhancement Requirements

CRITICAL: Market research reports should include key visual content.

Generate 6 essential visuals at the start:
1. **Market growth trajectory chart** — Historical + projected growth
2. **TAM/SAM/SOM breakdown** — Concentric circles diagram
3. **Porter's Five Forces diagram** — Industry analysis
4. **Competitive positioning matrix** — 2x2 matrix
5. **Risk heatmap** — Probability vs impact
6. **Executive summary infographic** — Visual synthesis

## Report Structure (50+ Pages)

### Front Matter (~5 pages)
- Cover Page with hero visualization
- Table of Contents
- List of Figures
- List of Tables

### Executive Summary (2-3 pages)
- Market Snapshot Box: Key metrics at a glance
- Investment Thesis: 3-5 bullet point summary
- Key Findings: Major discoveries and insights
- Strategic Recommendations: Top 3-5 actionable recommendations

### Core Analysis (~35 pages)
1. **Market Overview & Definition** (4-5 pages)
2. **Market Size & Growth Analysis** (6-8 pages)
3. **Industry Drivers & Trends** (5-6 pages)
4. **Competitive Landscape** (6-8 pages)
5. **Customer Analysis & Segmentation** (4-5 pages)
6. **Technology & Innovation Landscape** (4-5 pages)
7. **Regulatory & Policy Environment** (3-4 pages)
8. **Risk Analysis** (3-4 pages)

### Strategic Recommendations (~10 pages)
9. **Strategic Opportunities & Recommendations** (4-5 pages)
10. **Implementation Roadmap** (3-4 pages)
11. **Investment Thesis & Financial Projections** (3-4 pages)

### Back Matter (~5 pages)
- Appendix A: Methodology & Data Sources
- Appendix B: Detailed Market Data Tables
- Appendix C: Company Profiles
- References/Bibliography

## Workflow

### Phase 1: Research & Data Gathering

**Step 1: Define Scope**
- Clarify market definition
- Set geographic boundaries
- Determine time horizon
- Identify key questions to answer

**Step 2: Conduct Deep Research**
Research market data including:
- Market size and growth data
- Competitive landscape
- Industry trends
- Regulatory environment

**Step 3: Data Organization**
- Create sources/ folder with research notes
- Organize data by section
- Identify data gaps
- Conduct follow-up research as needed

### Phase 2: Analysis & Framework Application

**Step 4: Apply Analysis Frameworks**
- Market Sizing: TAM → SAM → SOM with clear assumptions
- Porter's Five Forces: Rate each force High/Medium/Low
- PESTLE: Analyze each dimension with trends and impacts
- SWOT: Internal strengths/weaknesses, external opportunities/threats
- Competitive Positioning: Define axes, plot competitors

**Step 5: Develop Insights**
- Synthesize findings into key insights
- Identify strategic implications
- Develop recommendations
- Prioritize opportunities

### Phase 3: Visual Generation

**Step 6: Generate All Visuals**
Generate visuals BEFORE writing the report. See [reference/visual-guide.md](reference/visual-guide.md) for detailed prompts.

### Phase 4: Report Writing

**Step 7: Initialize Project Structure**
```
writing_outputs/YYYYMMDD_HHMMSS_market_report_[topic]/
├── progress.md
├── drafts/
│   └── v1_market_report.tex
├── references/
│   └── references.bib
├── figures/
│   └── [all generated visuals]
├── sources/
│   └── [research notes]
└── final/
```

**Step 8: Write Report Using Template**
Ensure:
- Comprehensive coverage: Every subsection addressed
- Data-driven content: Claims supported by research
- Visual integration: Reference all generated figures
- Professional tone: Consulting-style writing
- No token constraints: Write fully, don't abbreviate

### Phase 5: Compilation & Review

**Step 9: Compile LaTeX**
```bash
cd writing_outputs/[project_folder]/drafts/
xelatex v1_market_report.tex
bibtex v1_market_report
xelatex v1_market_report.tex
xelatex v1_market_report.tex
```

**Step 10: Quality Review**
Verify:
- [ ] Total page count is 50+ pages
- [ ] All essential visuals are included
- [ ] Executive summary captures key findings
- [ ] All data points have sources cited
- [ ] Analysis frameworks are properly applied
- [ ] Recommendations are actionable and prioritized
- [ ] PDF renders without errors

## Analysis Frameworks

### Porter's Five Forces
Rate each force High/Medium/Low with rationale:
- Competitive Rivalry
- Threat of New Entrants
- Bargaining Power of Suppliers
- Bargaining Power of Buyers
- Threat of Substitutes

### PESTLE Analysis
Analyze each dimension:
- **P**olitical factors
- **E**conomic factors
- **S**ocial factors
- **T**echnological factors
- **L**egal factors
- **E**nvironmental factors

### TAM/SAM/SOM
- **TAM** (Total Addressable Market): Total revenue opportunity
- **SAM** (Serviceable Addressable Market): Segment you can target
- **SOM** (Serviceable Obtainable Market): Realistic market share

## Quality Standards

### Page Count Targets

| Section | Minimum | Target |
|---------|---------|--------|
| Front Matter | 4 | 5 |
| Market Overview | 4 | 5 |
| Market Size & Growth | 5 | 7 |
| Industry Drivers | 4 | 6 |
| Competitive Landscape | 5 | 7 |
| Customer Analysis | 3 | 5 |
| Technology Landscape | 3 | 5 |
| Regulatory Environment | 2 | 4 |
| Risk Analysis | 2 | 4 |
| Strategic Recommendations | 3 | 5 |
| Implementation Roadmap | 2 | 4 |
| Investment Thesis | 2 | 4 |
| Back Matter | 4 | 5 |
| **TOTAL** | **43** | **66** |

### Visual Quality Requirements
- Resolution: 300 DPI minimum
- Format: PNG for raster, PDF for vector
- Accessibility: Colorblind-friendly palettes
- Consistency: Same color scheme throughout
- Labeling: All axes, legends, and data points labeled

### Data Quality Requirements
- Currency: Data no older than 2 years (prefer current year)
- Sourcing: All statistics attributed to specific sources
- Validation: Cross-reference multiple sources when possible
- Assumptions: All projections state underlying assumptions

## Additional Resources

- For detailed section requirements, see [reference/report-structure.md](reference/report-structure.md)
- For visual generation prompts, see [reference/visual-guide.md](reference/visual-guide.md)
- For LaTeX formatting, see [reference/formatting-guide.md](reference/formatting-guide.md)

## Checklist: 50+ Page Validation

### Structure Completeness
- [ ] Cover page with hero visual
- [ ] Table of contents
- [ ] Executive summary (2-3 pages)
- [ ] All 11 core chapters present
- [ ] Appendices complete
- [ ] References/Bibliography

### Visual Completeness
- [ ] Market growth trajectory chart
- [ ] TAM/SAM/SOM diagram
- [ ] Porter's Five Forces
- [ ] Competitive positioning matrix
- [ ] Risk heatmap
- [ ] Additional visuals as needed

### Content Quality
- [ ] All statistics have sources
- [ ] Projections include assumptions
- [ ] Frameworks properly applied
- [ ] Recommendations are actionable
- [ ] No placeholder or incomplete sections
