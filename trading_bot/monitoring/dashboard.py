"""Streamlit dashboard for monitoring."""

from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from trading_bot.config import get_logger

logger = get_logger(__name__)


class Dashboard:
    """Monitoring dashboard."""
    
    def __init__(self, data_path: Optional[Path] = None):
        """Initialize dashboard.
        
        Args:
            data_path: Path to data directory
        """
        self.data_path = data_path or Path("./data")
    
    def create_equity_curve_chart(
        self,
        equity_curve: pd.Series,
        trades: Optional[pd.DataFrame] = None,
    ) -> go.Figure:
        """Create equity curve chart.
        
        Args:
            equity_curve: Equity curve series
            trades: Trades dataframe
            
        Returns:
            Plotly figure
        """
        fig = go.Figure()
        
        # Equity curve
        fig.add_trace(go.Scatter(
            x=equity_curve.index,
            y=equity_curve.values,
            mode='lines',
            name='Equity',
            line=dict(color='blue', width=2),
        ))
        
        # Add trade markers if provided
        if trades is not None and not trades.empty:
            # Entry points
            fig.add_trace(go.Scatter(
                x=trades['entry_time'] if 'entry_time' in trades.columns else trades.index,
                y=[equity_curve.loc[t] if t in equity_curve.index else None 
                   for t in (trades['entry_time'] if 'entry_time' in trades.columns else trades.index)],
                mode='markers',
                name='Entries',
                marker=dict(color='green', size=8, symbol='triangle-up'),
            ))
        
        fig.update_layout(
            title='Equity Curve',
            xaxis_title='Date',
            yaxis_title='Equity ($)',
            template='plotly_white',
            height=500,
        )
        
        return fig
    
    def create_drawdown_chart(self, equity_curve: pd.Series) -> go.Figure:
        """Create drawdown chart.
        
        Args:
            equity_curve: Equity curve series
            
        Returns:
            Plotly figure
        """
        # Calculate drawdown
        peak = equity_curve.expanding().max()
        drawdown = (peak - equity_curve) / peak
        
        fig = go.Figure()
        
        fig.add_trace(go.Scatter(
            x=drawdown.index,
            y=drawdown.values * 100,
            mode='lines',
            fill='tozeroy',
            name='Drawdown',
            line=dict(color='red', width=1),
            fillcolor='rgba(255, 0, 0, 0.2)',
        ))
        
        fig.update_layout(
            title='Drawdown',
            xaxis_title='Date',
            yaxis_title='Drawdown (%)',
            template='plotly_white',
            height=300,
        )
        
        return fig
    
    def create_monthly_returns_heatmap(
        self,
        returns: pd.Series,
    ) -> go.Figure:
        """Create monthly returns heatmap.
        
        Args:
            returns: Daily returns series
            
        Returns:
            Plotly figure
        """
        # Calculate monthly returns
        monthly_returns = returns.resample('M').apply(lambda x: (1 + x).prod() - 1)
        monthly_returns.index = monthly_returns.index.to_period('M')
        
        # Create pivot table
        df = pd.DataFrame({
            'year': monthly_returns.index.year,
            'month': monthly_returns.index.month,
            'return': monthly_returns.values,
        })
        
        pivot = df.pivot(index='year', columns='month', values='return')
        pivot.columns = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                        'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        
        # Create heatmap
        fig = go.Figure(data=go.Heatmap(
            z=pivot.values,
            x=pivot.columns,
            y=pivot.index,
            colorscale='RdYlGn',
            zmid=0,
            text=[[f"{v:.1%}" if not pd.isna(v) else "" for v in row] 
                  for row in pivot.values],
            texttemplate="%{text}",
            textfont={"size": 10},
        ))
        
        fig.update_layout(
            title='Monthly Returns Heatmap',
            xaxis_title='Month',
            yaxis_title='Year',
            template='plotly_white',
            height=400,
        )
        
        return fig
    
    def create_trade_distribution_chart(self, trades: pd.DataFrame) -> go.Figure:
        """Create trade distribution chart.
        
        Args:
            trades: Trades dataframe
            
        Returns:
            Plotly figure
        """
        if trades.empty or 'pnl' not in trades.columns:
            return go.Figure()
        
        fig = make_subplots(
            rows=2, cols=2,
            subplot_titles=('PnL Distribution', 'Cumulative PnL', 
                          'Trade Duration', 'Win/Loss Ratio'),
        )
        
        # PnL Distribution
        fig.add_trace(
            go.Histogram(x=trades['pnl'], nbinsx=30, name='PnL'),
            row=1, col=1,
        )
        
        # Cumulative PnL
        if 'pnl' in trades.columns:
            cumulative = trades['pnl'].cumsum()
            fig.add_trace(
                go.Scatter(x=cumulative.index, y=cumulative.values, 
                          mode='lines', name='Cumulative PnL'),
                row=1, col=2,
            )
        
        # Trade Duration
        if 'duration' in trades.columns:
            fig.add_trace(
                go.Histogram(x=trades['duration'], nbinsx=20, name='Duration'),
                row=2, col=1,
            )
        
        # Win/Loss Ratio
        wins = (trades['pnl'] > 0).sum()
        losses = (trades['pnl'] < 0).sum()
        fig.add_trace(
            go.Pie(labels=['Wins', 'Losses'], values=[wins, losses], 
                  name='Win/Loss'),
            row=2, col=2,
        )
        
        fig.update_layout(
            title='Trade Analysis',
            template='plotly_white',
            height=700,
            showlegend=False,
        )
        
        return fig
    
    def create_metrics_summary(self, metrics: Dict) -> str:
        """Create metrics summary HTML.
        
        Args:
            metrics: Performance metrics
            
        Returns:
            HTML string
        """
        html = f"""
        <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px;">
            <div style="background: #f0f0f0; padding: 15px; border-radius: 8px;">
                <h4 style="margin: 0; color: #666;">Total Return</h4>
                <p style="font-size: 24px; margin: 5px 0; color: {'green' if metrics.get('total_return', 0) > 0 else 'red'};">
                    {metrics.get('total_return', 0):.2%}
                </p>
            </div>
            <div style="background: #f0f0f0; padding: 15px; border-radius: 8px;">
                <h4 style="margin: 0; color: #666;">Sharpe Ratio</h4>
                <p style="font-size: 24px; margin: 5px 0;">
                    {metrics.get('sharpe_ratio', 0):.2f}
                </p>
            </div>
            <div style="background: #f0f0f0; padding: 15px; border-radius: 8px;">
                <h4 style="margin: 0; color: #666;">Max Drawdown</h4>
                <p style="font-size: 24px; margin: 5px 0; color: red;">
                    {metrics.get('max_drawdown', 0):.2%}
                </p>
            </div>
            <div style="background: #f0f0f0; padding: 15px; border-radius: 8px;">
                <h4 style="margin: 0; color: #666;">Win Rate</h4>
                <p style="font-size: 24px; margin: 5px 0;">
                    {metrics.get('win_rate', 0):.1%}
                </p>
            </div>
        </div>
        """
        return html


# Streamlit app function
def run_dashboard():
    """Run Streamlit dashboard."""
    try:
        import streamlit as st
    except ImportError:
        print("Streamlit not installed. Install with: pip install streamlit")
        return
    
    st.set_page_config(
        page_title="Trading Bot Dashboard",
        page_icon="📈",
        layout="wide",
    )
    
    st.title("🤖 AI Trading Bot Dashboard")
    
    # Sidebar
    st.sidebar.header("Settings")
    
    # Load data
    data_path = st.sidebar.text_input("Data Path", "./data")
    
    # Tabs
    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 Performance", "📈 Charts", "📋 Trades", "⚙️ Settings"
    ])
    
    dashboard = Dashboard(Path(data_path))
    
    with tab1:
        st.header("Performance Metrics")
        
        # Placeholder metrics
        metrics = {
            "total_return": 0.15,
            "sharpe_ratio": 1.5,
            "max_drawdown": 0.08,
            "win_rate": 0.55,
        }
        
        st.markdown(dashboard.create_metrics_summary(metrics), unsafe_allow_html=True)
    
    with tab2:
        st.header("Charts")
        
        # Placeholder equity curve
        dates = pd.date_range(start='2024-01-01', periods=100, freq='D')
        equity = 10000 * (1 + pd.Series(range(100), index=dates) * 0.001)
        
        fig = dashboard.create_equity_curve_chart(equity)
        st.plotly_chart(fig, use_container_width=True)
        
        fig2 = dashboard.create_drawdown_chart(equity)
        st.plotly_chart(fig2, use_container_width=True)
    
    with tab3:
        st.header("Trade History")
        st.write("No trades yet")
    
    with tab4:
        st.header("Bot Settings")
        st.json({
            "symbols": ["BTC/USDT", "ETH/USDT"],
            "timeframe": "1h",
            "risk_per_trade": 0.02,
        })


if __name__ == "__main__":
    run_dashboard()
