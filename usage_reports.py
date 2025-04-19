import os
import matplotlib.pyplot as plt
import pandas as pd
import io
import base64
from datetime import datetime, timedelta
from collections import Counter
import firebase_admin
from firebase_admin import firestore

# This module is responsible for generating usage reports for the Spanking Chat application

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
    """
    Collect daily usage metrics from Firestore
    Returns a dictionary with the collected metrics
    """
    today = datetime.now().date()
    yesterday = today - timedelta(days=1)
    yesterday_str = yesterday.isoformat()
    
    # Initialize metrics dictionary
    metrics = {
        'date': yesterday_str,
        'total_users': 0,
        'new_users': 0,
        'total_tokens': 0,
        'total_voice_tokens': 0,
        'total_queries': 0,
        'active_users': 0,
        'persona_usage': Counter(),
        'user_origins': Counter(),
        'hourly_usage': {str(i).zfill(2): 0 for i in range(24)}
    }
    
    # Get daily logs collection for yesterday
    daily_logs_ref = db.collection('daily_logs').document(yesterday_str)
    daily_log = daily_logs_ref.get()
    
    if daily_log.exists:
        log_data = daily_log.to_dict()
        metrics.update({
            'total_tokens': log_data.get('total_tokens', 0),
            'total_voice_tokens': log_data.get('total_voice_tokens', 0),
            'total_queries': log_data.get('total_queries', 0),
            'active_users': log_data.get('active_users', 0),
            'persona_usage': Counter(log_data.get('persona_usage', {})),
            'hourly_usage': log_data.get('hourly_usage', metrics['hourly_usage']),
            'user_origins': Counter(log_data.get('user_origins', {}))
        })
    
    # Get user metrics
    users_ref = db.collection('users')
    all_users = list(users_ref.stream())
    metrics['total_users'] = len(all_users)
    
    # Count new users from yesterday
    new_users = users_ref.where('created_at', '>=', yesterday).where('created_at', '<', today).stream()
    metrics['new_users'] = sum(1 for _ in new_users)
    
    # Get historical data for trends (last 7 days)
    historical_data = {
        'dates': [],
        'tokens': [],
        'voice_tokens': [],
        'queries': [],
        'active_users': []
    }
    
    for i in range(7, 0, -1):
        past_date = today - timedelta(days=i)
        past_date_str = past_date.isoformat()
        past_log_ref = db.collection('daily_logs').document(past_date_str)
        past_log = past_log_ref.get()
        
        if past_log.exists:
            log_data = past_log.to_dict()
            historical_data['dates'].append(past_date_str)
            historical_data['tokens'].append(log_data.get('total_tokens', 0))
            historical_data['voice_tokens'].append(log_data.get('total_voice_tokens', 0))
            historical_data['queries'].append(log_data.get('total_queries', 0))
            historical_data['active_users'].append(log_data.get('active_users', 0))
    
    metrics['historical_data'] = historical_data
    
    # Get token usage breakdown by user type
    token_usage = {
        'free_users': 0,
        'patreon_users': 0
    }
    
    all_token_usages = db.collection('token_usage').stream()
    for usage in all_token_usages:
        user_data = usage.to_dict()
        user_id = usage.id
        
        # Try to determine if this is a Patreon user
        user_ref = db.collection('users').where('email', '==', user_id).limit(1).stream()
        user_docs = list(user_ref)
        
        if user_docs and len(user_docs) > 0:
            user_doc = user_docs[0].to_dict()
            is_patreon = user_doc.get('patreon_status', 'inactive') == 'active'
            
            if is_patreon:
                token_usage['patreon_users'] += user_data.get('tokens', 0)
            else:
                token_usage['free_users'] += user_data.get('tokens', 0)
        else:
            # If we can't determine, assume it's a free user
            token_usage['free_users'] += user_data.get('tokens', 0)
    
    metrics['token_usage_breakdown'] = token_usage
    
    return metrics

def generate_report_html(metrics):
    """
    Generate an HTML report with charts based on the metrics
    Returns HTML content as a string
    """
    # Generate charts
    persona_chart = create_bar_chart(
        metrics['persona_usage'], 
        'Persona Usage Distribution', 
        'Persona', 
        'Usage Count',
        'persona_usage.png'
    )
    
    origin_chart = create_bar_chart(
        metrics['user_origins'], 
        'User Origin Distribution', 
        'Origin', 
        'Count',
        'user_origins.png'
    )
    
    hourly_chart = create_bar_chart(
        metrics['hourly_usage'], 
        'Hourly Usage Distribution', 
        'Hour of Day', 
        'Usage Count',
        'hourly_usage.png'
    )
    
    # Create trend charts if we have historical data
    hist_data = metrics['historical_data']
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
    
    # Create token usage breakdown chart
    token_breakdown = create_bar_chart(
        metrics['token_usage_breakdown'],
        'Token Usage by User Type',
        'User Type',
        'Token Count',
        'token_breakdown.png'
    )
    
    # Format HTML
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Spanking Chat Usage Report - {metrics['date']}</title>
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
            <h1>Spanking Chat Usage Report</h1>
            <p style="text-align: center;">Report for: {metrics['date']}</p>
            
            <div class="metrics-row">
                <div class="metrics-box metric-card">
                    <div class="metric-value">{metrics['total_users']}</div>
                    <div class="metric-label">Total Users</div>
                </div>
                <div class="metrics-box metric-card">
                    <div class="metric-value">{metrics['new_users']}</div>
                    <div class="metric-label">New Users</div>
                </div>
                <div class="metrics-box metric-card">
                    <div class="metric-value">{metrics['active_users']}</div>
                    <div class="metric-label">Active Users</div>
                </div>
            </div>
            
            <div class="metrics-row">
                <div class="metrics-box metric-card">
                    <div class="metric-value">{metrics['total_queries']}</div>
                    <div class="metric-label">Total Queries</div>
                </div>
                <div class="metrics-box metric-card">
                    <div class="metric-value">{metrics['total_tokens']:,}</div>
                    <div class="metric-label">Total Tokens</div>
                </div>
                <div class="metrics-box metric-card">
                    <div class="metric-value">{metrics['total_voice_tokens']:,}</div>
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
            
            <h2>Token Usage Breakdown</h2>
            <div class="chart">
                <img src="data:image/png;base64,{token_breakdown}" alt="Token Usage Breakdown">
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
                <p>Generated automatically on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} by Spanking Chat Analytics</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    return html
