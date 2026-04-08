---
name: analytics-data-analysis
description: Performs data analysis, visualization, and Jupyter development using Python libraries including pandas, matplotlib, seaborn, and numpy. Use when analyzing datasets, creating visualizations, working with Jupyter notebooks, performing statistical analysis, or processing tabular data.
---

# Analytics and Data Analysis

## Key Principles

- Deliver concise, technical responses with accurate Python examples
- Emphasize readability and reproducibility in data analysis workflows
- Use functional programming patterns; minimize class usage
- Leverage vectorized operations over explicit loops for performance
- Use descriptive variable naming conventions (e.g., is_valid, has_data, total_count)
- Adhere to PEP 8 style guidelines

## Data Analysis with Pandas

### Data Manipulation Best Practices

Use pandas for all data manipulation and analysis tasks:

```python
import pandas as pd
import numpy as np

# Method chaining for clean transformations
df = (pd.read_csv('data.csv')
        .dropna(subset=['critical_column'])
        .assign(processed_date=lambda x: pd.to_datetime(x['date']))
        .query('value > 0'))

# Explicit selection with loc/iloc
subset = df.loc[df['category'] == 'A', ['col1', 'col2']]

# Efficient aggregation with groupby
summary = df.groupby('category').agg({
    'value': ['sum', 'mean', 'count'],
    'date': 'max'
}).reset_index()

# Appropriate merge/join usage
merged = df1.merge(df2, on='key', how='left')
```

### Performance Optimization

- Use vectorized operations instead of loops
- Utilize categorical data types for low-cardinality strings
- Consider dask for larger-than-memory datasets
- Profile code to identify bottlenecks
- Use appropriate dtypes to minimize memory usage

```python
# Vectorized operations
df['doubled'] = df['value'] * 2  # Fast

# Categorical dtype for memory efficiency
df['category'] = df['category'].astype('category')

# Memory optimization
df['int_col'] = df['int_col'].astype('int32')
```

### Data Validation

```python
# Validate data types and ranges
assert df['value'].dtype == np.float64
assert df['value'].min() >= 0

# Handle missing values appropriately
missing_count = df.isnull().sum()
df_clean = df.dropna()  # or df.fillna(method='ffill')

# Verify shape after transformations
assert df_clean.shape[0] > 0, "Dataset is empty after cleaning"
```

## Visualization Standards

### Matplotlib Guidelines

Use matplotlib for fine-grained control:

```python
import matplotlib.pyplot as plt

fig, ax = plt.subplots(figsize=(10, 6))
ax.plot(x, y, label='Series A', color='#2E86AB')
ax.set_xlabel('Time Period', fontsize=12)
ax.set_ylabel('Value', fontsize=12)
ax.set_title('Time Series Analysis', fontsize=14, fontweight='bold')
ax.legend()
ax.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig('output.png', dpi=300, bbox_inches='tight')
```

### Seaborn for Statistical Visualizations

```python
import seaborn as sns

# Set theme for consistency
sns.set_theme(style='whitegrid', palette='colorblind')

# Appropriate plot types
sns.scatterplot(data=df, x='x_col', y='y_col', hue='category')
sns.lineplot(data=df, x='date', y='value', errorbar='ci')
sns.barplot(data=df, x='category', y='value')
sns.heatmap(corr_matrix, annot=True, cmap='coolwarm', center=0)
```

### Accessibility in Visualizations

- Use colorblind-friendly palettes (e.g., 'colorblind', 'viridis')
- Include alternative text descriptions
- Ensure sufficient contrast
- Provide data tables as alternatives to complex charts

## Jupyter Notebook Best Practices

### Notebook Structure

Structure notebooks with clear sections:

```markdown
# Analysis Title

## 1. Introduction & Overview
Brief description of the analysis goals.

## 2. Data Loading
Import libraries and load datasets.

## 3. Data Exploration
Initial exploration and profiling.

## 4. Data Cleaning
Handle missing values, outliers, etc.

## 5. Analysis
Main analysis steps.

## 6. Visualization
Create plots and charts.

## 7. Conclusions
Key findings and recommendations.
```

### Code Organization

```python
# Cell 1: Imports
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

%matplotlib inline

# Cell 2: Helper functions
def load_and_validate_data(filepath):
    """Load data with validation."""
    df = pd.read_csv(filepath)
    assert not df.empty, "Dataset is empty"
    return df

# Cell 3: Main analysis
df = load_and_validate_data('data.csv')
```

### Execution and Reproducibility

- Maintain meaningful cell execution order
- Clear outputs before sharing notebooks
- Use requirements.txt for dependencies
- Document data sources and access methods
- Include date/version information

## Technical Requirements

### Core Dependencies

```
pandas>=1.5.0
numpy>=1.21.0
matplotlib>=3.5.0
seaborn>=0.12.0
jupyter>=1.0.0
```

### Extended Libraries

- scikit-learn: Machine learning tasks
- scipy: Scientific computing
- plotly: Interactive visualizations
- statsmodels: Statistical modeling

## Analytics Implementation

### Tracking and Measurement

```python
# Define clear metrics before analysis
metrics = {
    'total_revenue': df['revenue'].sum(),
    'avg_order_value': df['order_value'].mean(),
    'conversion_rate': df['converted'].mean()
}

# Document data collection methodology
print(f"Data collected from: {source}")
print(f"Collection period: {start_date} to {end_date}")
print(f"Total records: {len(df)}")
```

### Statistical Analysis

```python
from scipy import stats

# Use appropriate statistical tests
t_stat, p_value = stats.ttest_ind(group_a, group_b)

# Report confidence intervals
confidence_interval = stats.t.interval(
    confidence=0.95,
    df=len(data)-1,
    loc=np.mean(data),
    scale=stats.sem(data)
)

# Consider effect sizes
def cohens_d(group1, group2):
    """Calculate Cohen's d effect size."""
    pooled_std = np.sqrt(((len(group1)-1)*group1.var() + 
                          (len(group2)-1)*group2.var()) / 
                         (len(group1) + len(group2) - 2))
    return (group1.mean() - group2.mean()) / pooled_std
```

## Error Handling and Logging

```python
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def safe_data_load(filepath):
    """Load data with error handling."""
    try:
        df = pd.read_csv(filepath)
        logger.info(f"Loaded {len(df)} rows from {filepath}")
        
        # Data sanity checks
        assert df.shape[0] > 0, "Empty dataset"
        assert df.shape[1] > 0, "No columns found"
        
        return df
    except FileNotFoundError:
        logger.error(f"File not found: {filepath}")
        raise
    except pd.errors.EmptyDataError:
        logger.error(f"Empty file: {filepath}")
        raise

# Validation checkpoints
def validate_checkpoint(df, stage_name):
    """Log validation checkpoint."""
    logger.info(f"Checkpoint {stage_name}: {df.shape}")
    logger.info(f"Missing values: {df.isnull().sum().sum()}")
```

## Quick Reference

### Common Patterns

```python
# Quick profile
df.info()
df.describe()
df.isnull().sum()

# Filter and transform
filtered = df[df['value'] > threshold].copy()
filtered['normalized'] = (filtered['value'] - filtered['value'].mean()) / filtered['value'].std()

# Pivot and reshape
pivot = df.pivot_table(values='sales', index='month', columns='region', aggfunc='sum')
melted = pd.melt(df, id_vars=['id'], value_vars=['col1', 'col2'])

# Time series
df['date'] = pd.to_datetime(df['date'])
df.set_index('date', inplace=True)
monthly = df.resample('M').sum()
```
