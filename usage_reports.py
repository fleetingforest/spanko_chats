import os
import matplotlib.pyplot as plt
import pandas as pd
import io
import base64
from datetime import datetime, timedelta, date, timezone
from collections import Counter
import firebase_admin
from firebase_admin import firestore
from google.cloud.firestore_v1.base_query import FieldFilter # Import FieldFilter for modern queries

# This module is responsible for generating usage reports for the Discipline Chat application

def create_bar_chart(data, title, xlabel, ylabel, filename):
    """Create a bar chart from data and return as base64 encoded image"""
    plt.figure(figsize=(10, 6))
    plt.bar(data.keys(), data.values(), color='purple')
    plt.title(title)
    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    plt.grid(axis='y', linestyle='--', alpha=0.7)
    plt.xticks(rotation=45)
    plt.tight_layout()
    
    # Save to a BytesIO object
    buffer = io.BytesIO()
    plt.savefig(buffer, format='png')
    plt.close()
    buffer.seek(0)
    
    # Convert to base64
    image_png = buffer.getvalue()
    buffer.close()
    encoded = base64.b64encode(image_png).decode('utf-8')
    return encoded

def create_line_chart(dates, values, title, xlabel, ylabel):
    """Create a line chart for time series data and return as base64 encoded image"""
    plt.figure(figsize=(10, 6))
    plt.plot(dates, values, marker='o', linestyle='-', color='purple')
    plt.title(title)
    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    plt.grid(True, linestyle='--', alpha=0.7)
    plt.xticks(rotation=45)
    plt.tight_layout()
    
    # Save to a BytesIO object
    buffer = io.BytesIO()
    plt.savefig(buffer, format='png')
    plt.close()
    buffer.seek(0)
    
    # Convert to base64
    image_png = buffer.getvalue()
    buffer.close()
    encoded = base64.b64encode(image_png).decode('utf-8')
    return encoded

def collect_daily_metrics(db):
    """Collect usage metrics for the previous day and the past week."""
    today_date = date.today()
    yesterday_date = today_date - timedelta(days=1)
    seven_days_ago_date = today_date - timedelta(days=7)

    # --- Get Yesterday's Metrics ---
    start_of_yesterday = datetime.combine(yesterday_date, datetime.min.time(), tzinfo=timezone.utc)
    start_of_today = datetime.combine(today_date, datetime.min.time(), tzinfo=timezone.utc)

    yesterday_log_ref = db.collection('daily_logs').document(yesterday_date.isoformat())
    yesterday_log_doc = yesterday_log_ref.get()
    yesterday_data = yesterday_log_doc.to_dict() if yesterday_log_doc.exists else {}

    total_tokens_yesterday = yesterday_data.get('total_tokens', 0)
    total_voice_tokens_yesterday = yesterday_data.get('total_voice_tokens', 0)
    total_queries_yesterday = yesterday_data.get('total_queries', 0)
    active_users_yesterday = yesterday_data.get('active_users', 0)
    hourly_usage = yesterday_data.get('hourly_usage', {})
    persona_usage = yesterday_data.get('persona_usage', {})
    user_origins = yesterday_data.get('user_origins', {})

    # --- Calculate New Users Yesterday ---
    users_ref = db.collection('users')
    # Use modern FieldFilter for queries
    new_users_query = users_ref.where(filter=FieldFilter('created_at', '>=', start_of_yesterday)).where(filter=FieldFilter('created_at', '<', start_of_today))
    new_users_stream = new_users_query.stream()
    new_users_count = len(list(new_users_stream))

    # --- Calculate Current Active Patreon Users (Total) ---
    # Note: This is the total count, not just those active yesterday.
    patreon_users_ref = db.collection('users').where(filter=FieldFilter('patreon_status', '==', 'active'))
    patreon_users_stream = patreon_users_ref.stream()
    active_patreon_count_total = len(list(patreon_users_stream))

    # --- Get Historical Data (Last 7 Days) ---
    historical_data = {'dates': [], 'tokens': [], 'queries': [], 'active_users': []}
    date_range = [seven_days_ago_date + timedelta(days=i) for i in range(7)] # Dates from 7 days ago up to yesterday

    # Fetch logs for the date range using document ID range query
    # Use FIELD_PATH_DOCUMENT_ID for document ID queries
    docs = db.collection('daily_logs') \
        .where(filter=FieldFilter(firestore.FIELD_PATH_DOCUMENT_ID, '>=', seven_days_ago_date.isoformat())) \
        .where(filter=FieldFilter(firestore.FIELD_PATH_DOCUMENT_ID, '<', today_date.isoformat())) \
        .stream()

    logs_by_date = {doc.id: doc.to_dict() for doc in docs}

    for day in date_range:
        day_str = day.isoformat()
        log_data = logs_by_date.get(day_str, {}) # Get log data or empty dict if missing
        historical_data['dates'].append(day_str)
        historical_data['tokens'].append(log_data.get('total_tokens', 0))
        historical_data['queries'].append(log_data.get('total_queries', 0))
        historical_data['active_users'].append(log_data.get('active_users', 0))

    # --- Prepare Final Metrics Dictionary ---
    metrics = {
        'date': yesterday_date.isoformat(),
        'total_tokens': total_tokens_yesterday,
        'total_voice_tokens': total_voice_tokens_yesterday,
        'total_queries': total_queries_yesterday,
        'active_users': active_users_yesterday,
        'new_users': new_users_count,
        'active_patreon_users': active_patreon_count_total, # Reporting total current Patreon users
        'hourly_usage': hourly_usage,
        'persona_usage': persona_usage,
        'user_origins': user_origins,
        'historical_data': historical_data, # Add historical data
    }
    return metrics

def generate_report_html(metrics):
    """
    Generate an HTML report with charts based on the metrics
    Returns HTML content as a string
    """
    # Generate charts
    persona_chart = create_bar_chart(
        metrics.get('persona_usage', {}), # Use .get()
        'Persona Usage Distribution', 
        'Persona', 
        'Usage Count',
        'persona_usage.png'
    )
    
    origin_chart = create_bar_chart(
        metrics.get('user_origins', {}), # Use .get()
        'User Origin Distribution', 
        'Origin', 
        'Count',
        'user_origins.png'
    )
    
    hourly_chart = create_bar_chart(
        metrics.get('hourly_usage', {}), # Use .get()
        'Hourly Usage Distribution', 
        'Hour of Day', 
        'Usage Count',
        'hourly_usage.png'
    )
    
    # Create trend charts if we have historical data
    # Use .get() with default empty dict/list
    hist_data = metrics.get('historical_data', {'dates': [], 'tokens': [], 'queries': [], 'active_users': []})
    token_trend = ""
    query_trend = ""
    user_trend = ""
    
    if hist_data['dates'] and len(hist_data['dates']) > 1:
        token_trend = create_line_chart(
            hist_data['dates'],
            hist_data['tokens'],
            'Token Usage Trend (7 Days)',
            'Date',
            'Tokens'
        )
        
        query_trend = create_line_chart(
            hist_data['dates'],
            hist_data['queries'],
            'Queries Trend (7 Days)',
            'Date',
            'Queries'
        )
        
        user_trend = create_line_chart(
            hist_data['dates'],
            hist_data['active_users'],
            'Active Users Trend (7 Days)',
            'Date',
            'Users'
        )
    
    # Format HTML
    # Use .get() for metrics values in HTML to avoid KeyErrors if collect_daily_metrics changes
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Discipline Chat Usage Report - {metrics.get('date', 'N/A')}</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                margin: 0;
                padding: 20px;
                background-color: #f9f9f9;
                color: #333;
            }}
            .container {{
                max-width: 1000px;
                margin: 0 auto;
                background-color: #fff;
                padding: 30px;
                border-radius: 8px;
                box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
            }}
            h1, h2 {{
                color: #6a1b9a;
                margin-top: 30px;
            }}
            h1 {{
                border-bottom: 2px solid #6a1b9a;
                padding-bottom: 10px;
                text-align: center;
            }}
            .metric-card {{
                background-color: #f3e5f5;
                border-radius: 8px;
                padding: 15px;
                margin-bottom: 15px;
                box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
            }}
            .metric-value {{
                font-size: 24px;
                font-weight: bold;
                color: #6a1b9a;
            }}
            .metric-label {{
                font-size: 14px;
                color: #666;
            }}
            .metrics-row {{
                display: flex;
                justify-content: space-between;
                margin-bottom: 30px;
            }}
            .metrics-box {{
                flex: 1;
                margin: 0 10px;
            }}
            .chart {{
                margin: 30px 0;
                text-align: center;
            }}
            .chart img {{
                max-width: 100%;
                border-radius: 8px;
                box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
            }}
            .footer {{
                text-align: center;
                margin-top: 40px;
                font-size: 12px;
                color: #888;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Discipline Chat Usage Report</h1>
            <p style="text-align: center;">Report for: {metrics.get('date', 'N/A')}</p>
            
            <div class="metrics-row">
                <div class="metrics-box metric-card">
                    <div class="metric-value">{metrics.get('total_users', 0)}</div>
                    <div class="metric-label">Total Users</div>
                </div>
                <div class="metrics-box metric-card">
                    <div class="metric-value">{metrics.get('new_users', 0)}</div>
                    <div class="metric-label">New Users</div>
                </div>
                <div class="metrics-box metric-card">
                    <div class="metric-value">{metrics.get('active_users', 0)}</div>
                    <div class="metric-label">Active Users</div>
                </div>
            </div>
            
            <div class="metrics-row">
                <div class="metrics-box metric-card">
                    <div class="metric-value">{metrics.get('total_queries', 0)}</div>
                    <div class="metric-label">Total Queries</div>
                </div>
                <div class="metrics-box metric-card">
                    <div class="metric-value">{metrics.get('total_tokens', 0):,}</div>
                    <div class="metric-label">Total Tokens</div>
                </div>
                <div class="metrics-box metric-card">
                    <div class="metric-value">{metrics.get('total_voice_tokens', 0):,}</div>
                    <div class="metric-label">Voice Tokens</div>
                </div>
            </div>
            
            <h2>Usage Trends (Last 7 Days)</h2>
            
            <div class="chart">
                <img src="data:image/png;base64,{token_trend}" alt="Token Usage Trend">
            </div>
            
            <div class="chart">
                <img src="data:image/png;base64,{query_trend}" alt="Query Trend">
            </div>
            
            <div class="chart">
                <img src="data:image/png;base64,{user_trend}" alt="User Trend">
            </div>
            
            <h2>Persona Popularity</h2>
            <div class="chart">
                <img src="data:image/png;base64,{persona_chart}" alt="Persona Usage Distribution">
            </div>
            
            <h2>User Origin Distribution</h2>
            <div class="chart">
                <img src="data:image/png;base64,{origin_chart}" alt="User Origin Distribution">
            </div>
            
            <h2>Hourly Usage Distribution</h2>
            <div class="chart">
                <img src="data:image/png;base64,{hourly_chart}" alt="Hourly Usage Distribution">
            </div>
            
            <div class="footer">
                <p>Generated automatically on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} by Discipline Chat Analytics</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    return html
