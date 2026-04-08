# LaTeX Formatting Guide

Professional formatting for market research reports using LaTeX.

## Document Setup

```latex
\documentclass[11pt,letterpaper]{report}
\usepackage{market_research}
```

## Box Environments

### Key Insight Box (Blue)

```latex
\begin{keyinsightbox}[Key Finding]
The market is projected to grow at 15.3% CAGR through 2030.
\end{keyinsightbox}
```

### Market Data Box (Green)

```latex
\begin{marketdatabox}[Market Snapshot]
\begin{itemize}
    \item Market Size (2024): \$45.2B
    \item Projected Size (2030): \$98.7B
    \item CAGR: 15.3\%
\end{itemize}
\end{marketdatabox}
```

### Risk Box (Orange/Warning)

```latex
\begin{riskbox}[Critical Risk]
Regulatory changes could impact 40% of market participants.
\end{riskbox}
```

### Recommendation Box (Purple)

```latex
\begin{recommendationbox}[Strategic Recommendation]
Prioritize market entry in the Asia-Pacific region.
\end{recommendationbox}
```

### Callout Box (Gray)

```latex
\begin{calloutbox}[Definition]
TAM (Total Addressable Market) represents the total revenue opportunity.
\end{calloutbox}
```

## Figure Formatting

```latex
\begin{figure}[htbp]
\centering
\includegraphics[width=0.9\textwidth]{../figures/market_growth.png}
\caption{Market Growth Trajectory (2020-2030). Source: Industry analysis, company data.}
\label{fig:market_growth}
\end{figure}
```

### Figure Placement Options
- `h` — here (approximately)
- `t` — top of page
- `b` — bottom of page
- `p` — special float page
- `!` — override restrictions

### Sizing
- Full width: `width=0.9\textwidth`
- Half width: `width=0.45\textwidth`
- Specific size: `width=4in`

## Table Formatting

```latex
\begin{table}[htbp]
\centering
\caption{Market Size by Region (2024)}
\begin{tabular}{@{}lrrr@{}}
\toprule
\textbf{Region} & \textbf{Size (USD)} & \textbf{Share} & \textbf{CAGR} \\
\midrule
North America & \$18.2B & 40.3\% & 12.5\% \\
\rowcolor{tablealt} Europe & \$12.1B & 26.8\% & 14.2\% \\
Asia-Pacific & \$10.5B & 23.2\% & 18.7\% \\
\rowcolor{tablealt} Rest of World & \$4.4B & 9.7\% & 11.3\% \\
\midrule
\textbf{Total} & \textbf{\$45.2B} & \textbf{100\%} & \textbf{15.3\%} \\
\bottomrule
\end{tabular}
\label{tab:market_by_region}
\end{table}
```

### Table Best Practices
- Use `@{}` to remove column spacing at edges
- Use `\toprule`, `\midrule`, `\bottomrule` from booktabs
- Alternate row colors with `\rowcolor{tablealt}`
- Right-align numbers, left-align text
- Include units in column headers

## Cross-References

### Figures
```latex
As shown in Figure~\ref{fig:market_growth}, the market...
```

### Tables
```latex
Table~\ref{tab:market_by_region} presents the regional breakdown.
```

### Chapters/Sections
```latex
See Chapter~\ref{ch:competitive} for competitive analysis.
Section~\ref{sec:methodology} describes the methodology.
```

## Bibliography

### BibTeX Entry Types

```bibtex
@article{varady2022,
  author = {Varady, K. A. and others},
  title = {Clinical application of intermittent fasting for weight loss},
  journal = {Nature Reviews Endocrinology},
  year = {2022}
}

@report{mckinsey2024,
  author = {{McKinsey Global Institute}},
  title = {The Economic Potential of Generative AI},
  institution = {McKinsey \& Company},
  year = {2024}
}

@misc{statista2024,
  author = {Statista},
  title = {Global AI Market Size},
  year = {2024},
  howpublished = {\url{https://www.statista.com}}
}
```

### In-Text Citations
```latex
Studies show significant growth potential \cite{mckinsey2024}.
According to \citeauthor{varady2022}, the market...
```

## Special Elements

### Executive Summary Box

```latex
\begin{execbox}[Executive Summary]
\textbf{Key Findings:}
\begin{enumerate}
    \item Market size projected to reach \$100B by 2030
    \item CAGR of 15\% driven by digital transformation
    \item Asia-Pacific emerging as fastest-growing region
\end{enumerate}

\textbf{Strategic Recommendations:}
\begin{enumerate}
    \item Prioritize Asia-Pacific market entry
    \item Invest in AI/ML capabilities
    \item Build strategic partnerships
\end{enumerate}
\end{execbox}
```

### Two-Column Layout

```latex
\begin{multicols}{2}
\textbf{Strengths}
\begin{itemize}
    \item Strong brand recognition
    \item Established distribution network
\end{itemize}

\textbf{Weaknesses}
\begin{itemize}
    \item Limited R\&D investment
    \item Geographic concentration
\end{itemize}
\end{multicols}
```

### SWOT Table

```latex
\begin{table}[htbp]
\centering
\caption{SWOT Analysis}
\begin{tabular}{@{}p{0.45\textwidth}p{0.45\textwidth}@{}}
\toprule
\textbf{Strengths} & \textbf{Weaknesses} \\
\midrule
Strong brand & Limited R\&D \\
Distribution network & Geographic concentration \\
\toprule
\textbf{Opportunities} & \textbf{Threats} \\
\midrule
Emerging markets & New entrants \\
Technology adoption & Regulatory changes \\
\bottomrule
\end{tabular}
\end{table}
```

## Common Issues

### Figure Overflow
```latex
% Use resizebox for large figures
\begin{figure}[htbp]
\centering
\resizebox{0.9\textwidth}{!}{\includegraphics{large_figure.png}}
\caption{...}
\end{figure}
```

### Table Too Wide
```latex
% Use adjustbox package
\usepackage{adjustbox}

\begin{table}[htbp]
\centering
\begin{adjustbox}{max width=\textwidth}
\begin{tabular}{...}
...
\end{tabular}
\end{adjustbox}
\end{table}
```

### Bibliography Not Showing
Run the full compilation sequence:
```bash
xelatex report.tex
bibtex report
xelatex report.tex
xelatex report.tex
```

## Compilation Command

```bash
cd writing_outputs/[project_folder]/drafts/
xelatex v1_market_report.tex
bibtex v1_market_report
xelatex v1_market_report.tex
xelatex v1_market_report.tex
```
