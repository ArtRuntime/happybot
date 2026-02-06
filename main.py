import asyncio
import os
import sys
import psutil
import platform
from datetime import datetime
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import uvicorn

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    yield
    # Shutdown
    pass

app = FastAPI(lifespan=lifespan)

def get_size(bytes):
    """Convert bytes to human readable format"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes < 1024.0:
            return f"{bytes:.2f} {unit}"
        bytes /= 1024.0
    return f"{bytes:.2f} PB"

def get_system_stats():
    """Get comprehensive system statistics"""
    # CPU Info
    cpu_percent = psutil.cpu_percent(interval=1, percpu=False)
    cpu_per_core = psutil.cpu_percent(interval=1, percpu=True)
    cpu_count_physical = psutil.cpu_count(logical=False)
    cpu_count_logical = psutil.cpu_count(logical=True)
    
    try:
        cpu_freq = psutil.cpu_freq()
        cpu_freq_current = f"{cpu_freq.current:.0f} MHz" if cpu_freq else "N/A"
        cpu_freq_min = f"{cpu_freq.min:.0f} MHz" if cpu_freq and cpu_freq.min else "N/A"
        cpu_freq_max = f"{cpu_freq.max:.0f} MHz" if cpu_freq and cpu_freq.max else "N/A"
    except:
        cpu_freq_current = cpu_freq_min = cpu_freq_max = "N/A"
    
    # Memory Info
    memory = psutil.virtual_memory()
    swap = psutil.swap_memory()
    
    # Disk Info
    disk = psutil.disk_usage('/')
    
    # Network Info
    net_io = psutil.net_io_counters()
    
    # Process Info
    process_count = len(psutil.pids())
    
    # Boot time and uptime
    boot_time = datetime.fromtimestamp(psutil.boot_time())
    uptime = datetime.now() - boot_time
    uptime_str = f"{uptime.days}d {uptime.seconds//3600}h {(uptime.seconds//60)%60}m {uptime.seconds%60}s"
    
    # Load average (Unix only)
    try:
        load_avg = os.getloadavg()
        load_1, load_5, load_15 = load_avg
    except:
        load_1 = load_5 = load_15 = 0
    
    return {
        # CPU
        'cpu_percent': cpu_percent,
        'cpu_per_core': cpu_per_core,
        'cpu_count_physical': cpu_count_physical or cpu_count_logical,
        'cpu_count_logical': cpu_count_logical,
        'cpu_freq_current': cpu_freq_current,
        'cpu_freq_min': cpu_freq_min,
        'cpu_freq_max': cpu_freq_max,
        'load_1': load_1,
        'load_5': load_5,
        'load_15': load_15,
        
        # Memory
        'memory_total': memory.total,
        'memory_available': memory.available,
        'memory_used': memory.used,
        'memory_percent': memory.percent,
        'swap_total': swap.total,
        'swap_used': swap.used,
        'swap_percent': swap.percent,
        
        # Disk
        'disk_total': disk.total,
        'disk_used': disk.used,
        'disk_free': disk.free,
        'disk_percent': disk.percent,
        
        # Network
        'net_sent': net_io.bytes_sent,
        'net_recv': net_io.bytes_recv,
        'net_packets_sent': net_io.packets_sent,
        'net_packets_recv': net_io.packets_recv,
        
        # System
        'platform': platform.system(),
        'platform_release': platform.release(),
        'platform_version': platform.version(),
        'architecture': platform.machine(),
        'hostname': platform.node(),
        'python_version': platform.python_version(),
        'process_count': process_count,
        'boot_time': boot_time.strftime('%Y-%m-%d %H:%M:%S'),
        'uptime': uptime_str,
    }

@app.get("/", response_class=HTMLResponse)
async def read_root():
    stats = get_system_stats()
    
    # Generate per-core CPU bars
    cpu_core_html = ""
    for i, percent in enumerate(stats['cpu_per_core']):
        cpu_core_html += f"""
        <div class="core-row">
            <span class="core-label">Core {i}</span>
            <div class="mini-progress">
                <div class="mini-fill {'warning' if percent > 80 else ''}" style="width: {percent}%"></div>
            </div>
            <span class="core-value">{percent:.1f}%</span>
        </div>
        """
    
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>System Monitor - Bot Status</title>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }}
            
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                background: #0f172a;
                color: #e2e8f0;
                min-height: 100vh;
                padding: 20px;
            }}
            
            .container {{
                max-width: 1400px;
                margin: 0 auto;
            }}
            
            .header {{
                background: linear-gradient(135deg, #1e293b 0%, #334155 100%);
                padding: 30px;
                border-radius: 12px;
                margin-bottom: 25px;
                box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
            }}
            
            .header h1 {{
                font-size: 2em;
                font-weight: 600;
                margin-bottom: 8px;
                color: #f1f5f9;
            }}
            
            .header-meta {{
                display: flex;
                gap: 30px;
                flex-wrap: wrap;
                margin-top: 15px;
                font-size: 0.9em;
                color: #94a3b8;
            }}
            
            .header-meta-item {{
                display: flex;
                align-items: center;
                gap: 8px;
            }}
            
            .status-indicator {{
                width: 10px;
                height: 10px;
                background: #10b981;
                border-radius: 50%;
                animation: pulse 2s infinite;
            }}
            
            @keyframes pulse {{
                0%, 100% {{ opacity: 1; box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7); }}
                50% {{ opacity: 0.8; box-shadow: 0 0 0 6px rgba(16, 185, 129, 0); }}
            }}
            
            .grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
                gap: 20px;
                margin-bottom: 20px;
            }}
            
            .card {{
                background: #1e293b;
                border: 1px solid #334155;
                border-radius: 12px;
                padding: 24px;
                box-shadow: 0 4px 6px rgba(0, 0, 0, 0.2);
            }}
            
            .card-header {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 20px;
                padding-bottom: 12px;
                border-bottom: 1px solid #334155;
            }}
            
            .card-title {{
                font-size: 1.1em;
                font-weight: 600;
                color: #f1f5f9;
            }}
            
            .card-badge {{
                background: #334155;
                padding: 4px 12px;
                border-radius: 12px;
                font-size: 0.85em;
                color: #94a3b8;
            }}
            
            .stat-row {{
                display: flex;
                justify-content: space-between;
                padding: 10px 0;
                border-bottom: 1px solid #2d3748;
            }}
            
            .stat-row:last-child {{
                border-bottom: none;
            }}
            
            .stat-label {{
                color: #94a3b8;
                font-size: 0.9em;
            }}
            
            .stat-value {{
                color: #f1f5f9;
                font-weight: 600;
                font-size: 0.9em;
            }}
            
            .progress-container {{
                margin: 15px 0;
            }}
            
            .progress-label {{
                display: flex;
                justify-content: space-between;
                margin-bottom: 8px;
                font-size: 0.9em;
            }}
            
            .progress-bar {{
                width: 100%;
                height: 8px;
                background: #334155;
                border-radius: 4px;
                overflow: hidden;
            }}
            
            .progress-fill {{
                height: 100%;
                background: linear-gradient(90deg, #3b82f6, #2563eb);
                transition: width 0.3s ease;
                border-radius: 4px;
            }}
            
            .progress-fill.warning {{
                background: linear-gradient(90deg, #f59e0b, #d97706);
            }}
            
            .progress-fill.danger {{
                background: linear-gradient(90deg, #ef4444, #dc2626);
            }}
            
            .core-row {{
                display: grid;
                grid-template-columns: 60px 1fr 50px;
                gap: 10px;
                align-items: center;
                padding: 6px 0;
                font-size: 0.85em;
            }}
            
            .core-label {{
                color: #94a3b8;
            }}
            
            .mini-progress {{
                height: 6px;
                background: #334155;
                border-radius: 3px;
                overflow: hidden;
            }}
            
            .mini-fill {{
                height: 100%;
                background: #3b82f6;
                border-radius: 3px;
            }}
            
            .mini-fill.warning {{
                background: #f59e0b;
            }}
            
            .core-value {{
                color: #f1f5f9;
                text-align: right;
                font-weight: 500;
            }}
            
            .footer {{
                text-align: center;
                margin-top: 30px;
                padding: 20px;
                color: #64748b;
                font-size: 0.85em;
            }}
            
            .refresh-timer {{
                display: inline-block;
                background: #1e293b;
                padding: 8px 16px;
                border-radius: 6px;
                border: 1px solid #334155;
            }}
            
            @media (max-width: 768px) {{
                .grid {{
                    grid-template-columns: 1fr;
                }}
                
                .header h1 {{
                    font-size: 1.5em;
                }}
                
                .header-meta {{
                    gap: 15px;
                }}
            }}
        </style>
        <script>
            let countdown = 5;
            setInterval(() => {{
                countdown--;
                if (countdown <= 0) {{
                    location.reload();
                }}
                const timer = document.getElementById('countdown');
                if (timer) timer.textContent = countdown;
            }}, 1000);
        </script>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>System Monitor</h1>
                <div class="header-meta">
                    <div class="header-meta-item">
                        <div class="status-indicator"></div>
                        <span>ONLINE</span>
                    </div>
                    <div class="header-meta-item">
                        <span>Hostname: {stats['hostname']}</span>
                    </div>
                    <div class="header-meta-item">
                        <span>Uptime: {stats['uptime']}</span>
                    </div>
                    <div class="header-meta-item">
                        <span>Processes: {stats['process_count']}</span>
                    </div>
                </div>
            </div>
            
            <div class="grid">
                <!-- CPU Card -->
                <div class="card">
                    <div class="card-header">
                        <span class="card-title">CPU Usage</span>
                        <span class="card-badge">{stats['cpu_count_logical']} Cores</span>
                    </div>
                    
                    <div class="progress-container">
                        <div class="progress-label">
                            <span>Overall Usage</span>
                            <span>{stats['cpu_percent']:.1f}%</span>
                        </div>
                        <div class="progress-bar">
                            <div class="progress-fill {'danger' if stats['cpu_percent'] > 90 else 'warning' if stats['cpu_percent'] > 70 else ''}" 
                                 style="width: {stats['cpu_percent']}%"></div>
                        </div>
                    </div>
                    
                    <div style="margin-top: 20px;">
                        {cpu_core_html}
                    </div>
                    
                    <div class="stat-row" style="margin-top: 15px;">
                        <span class="stat-label">Physical Cores</span>
                        <span class="stat-value">{stats['cpu_count_physical']}</span>
                    </div>
                    <div class="stat-row">
                        <span class="stat-label">Logical Cores</span>
                        <span class="stat-value">{stats['cpu_count_logical']}</span>
                    </div>
                    <div class="stat-row">
                        <span class="stat-label">Current Frequency</span>
                        <span class="stat-value">{stats['cpu_freq_current']}</span>
                    </div>
                    <div class="stat-row">
                        <span class="stat-label">Load Average (1m/5m/15m)</span>
                        <span class="stat-value">{stats['load_1']:.2f} / {stats['load_5']:.2f} / {stats['load_15']:.2f}</span>
                    </div>
                </div>
                
                <!-- Memory Card -->
                <div class="card">
                    <div class="card-header">
                        <span class="card-title">Memory Usage</span>
                        <span class="card-badge">{get_size(stats['memory_total'])}</span>
                    </div>
                    
                    <div class="progress-container">
                        <div class="progress-label">
                            <span>RAM Usage</span>
                            <span>{stats['memory_percent']:.1f}%</span>
                        </div>
                        <div class="progress-bar">
                            <div class="progress-fill {'danger' if stats['memory_percent'] > 90 else 'warning' if stats['memory_percent'] > 70 else ''}" 
                                 style="width: {stats['memory_percent']}%"></div>
                        </div>
                    </div>
                    
                    <div class="stat-row">
                        <span class="stat-label">Total</span>
                        <span class="stat-value">{get_size(stats['memory_total'])}</span>
                    </div>
                    <div class="stat-row">
                        <span class="stat-label">Used</span>
                        <span class="stat-value">{get_size(stats['memory_used'])}</span>
                    </div>
                    <div class="stat-row">
                        <span class="stat-label">Available</span>
                        <span class="stat-value">{get_size(stats['memory_available'])}</span>
                    </div>
                    
                    <div class="progress-container" style="margin-top: 20px;">
                        <div class="progress-label">
                            <span>Swap Usage</span>
                            <span>{stats['swap_percent']:.1f}%</span>
                        </div>
                        <div class="progress-bar">
                            <div class="progress-fill {'danger' if stats['swap_percent'] > 90 else 'warning' if stats['swap_percent'] > 70 else ''}" 
                                 style="width: {stats['swap_percent']}%"></div>
                        </div>
                    </div>
                    
                    <div class="stat-row">
                        <span class="stat-label">Swap Total</span>
                        <span class="stat-value">{get_size(stats['swap_total'])}</span>
                    </div>
                    <div class="stat-row">
                        <span class="stat-label">Swap Used</span>
                        <span class="stat-value">{get_size(stats['swap_used'])}</span>
                    </div>
                </div>
                
                <!-- Disk Card -->
                <div class="card">
                    <div class="card-header">
                        <span class="card-title">Disk Usage</span>
                        <span class="card-badge">{get_size(stats['disk_total'])}</span>
                    </div>
                    
                    <div class="progress-container">
                        <div class="progress-label">
                            <span>Storage Usage</span>
                            <span>{stats['disk_percent']:.1f}%</span>
                        </div>
                        <div class="progress-bar">
                            <div class="progress-fill {'danger' if stats['disk_percent'] > 90 else 'warning' if stats['disk_percent'] > 70 else ''}" 
                                 style="width: {stats['disk_percent']}%"></div>
                        </div>
                    </div>
                    
                    <div class="stat-row">
                        <span class="stat-label">Total</span>
                        <span class="stat-value">{get_size(stats['disk_total'])}</span>
                    </div>
                    <div class="stat-row">
                        <span class="stat-label">Used</span>
                        <span class="stat-value">{get_size(stats['disk_used'])}</span>
                    </div>
                    <div class="stat-row">
                        <span class="stat-label">Free</span>
                        <span class="stat-value">{get_size(stats['disk_free'])}</span>
                    </div>
                </div>
                
                <!-- Network Card -->
                <div class="card">
                    <div class="card-header">
                        <span class="card-title">Network Statistics</span>
                        <span class="card-badge">Total</span>
                    </div>
                    
                    <div class="stat-row">
                        <span class="stat-label">Bytes Sent</span>
                        <span class="stat-value">{get_size(stats['net_sent'])}</span>
                    </div>
                    <div class="stat-row">
                        <span class="stat-label">Bytes Received</span>
                        <span class="stat-value">{get_size(stats['net_recv'])}</span>
                    </div>
                    <div class="stat-row">
                        <span class="stat-label">Packets Sent</span>
                        <span class="stat-value">{stats['net_packets_sent']:,}</span>
                    </div>
                    <div class="stat-row">
                        <span class="stat-label">Packets Received</span>
                        <span class="stat-value">{stats['net_packets_recv']:,}</span>
                    </div>
                </div>
                
                <!-- System Info Card -->
                <div class="card">
                    <div class="card-header">
                        <span class="card-title">System Information</span>
                        <span class="card-badge">{stats['platform']}</span>
                    </div>
                    
                    <div class="stat-row">
                        <span class="stat-label">Operating System</span>
                        <span class="stat-value">{stats['platform']} {stats['platform_release']}</span>
                    </div>
                    <div class="stat-row">
                        <span class="stat-label">Architecture</span>
                        <span class="stat-value">{stats['architecture']}</span>
                    </div>
                    <div class="stat-row">
                        <span class="stat-label">Python Version</span>
                        <span class="stat-value">{stats['python_version']}</span>
                    </div>
                    <div class="stat-row">
                        <span class="stat-label">Boot Time</span>
                        <span class="stat-value">{stats['boot_time']}</span>
                    </div>
                    <div class="stat-row">
                        <span class="stat-label">System Uptime</span>
                        <span class="stat-value">{stats['uptime']}</span>
                    </div>
                </div>
            </div>
            
            <div class="footer">
                <div class="refresh-timer">
                    Auto-refresh in <span id="countdown">5</span> seconds
                </div>
            </div>
        </div>
    </body>
    </html>
    """

@app.get("/api/stats")
async def get_stats():
    """API endpoint for getting stats as JSON"""
    return get_system_stats()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    uvicorn.run(app, host="0.0.0.0", port=port)

