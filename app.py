import json
import os
import certifi  # Meka aluthin danna
from flask import Flask, jsonify, redirect, render_template_string, render_template, request, url_for, session, flash, abort
from flask_socketio import SocketIO, emit
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix  # <--- MEKA ALUTHIN DAMMA (Render HTTPS session fix karanna)
from pymongo import MongoClient
from functools import wraps
from bson.objectid import ObjectId

app = Flask(__name__)

# Render proxy headers handle karanna meka aniwa ooni (Session loss wenna nodi thiyaganna)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'syntaxcore_pos_2026_secret')
socketio = SocketIO(app, cors_allowed_origins="*")

# Render environment variable eken MONGO_URI eka gannawa (Nathnam local fallback ekak thiyenawa)
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017/")

# MongoDB Client eka certifi saha connection ekka connect karanawa
client = MongoClient(MONGO_URI, tlsCAFile=certifi.where())

# Database name eka set karanawa
db = client['triple_eight_pos_db']  
orders_collection = db['orders']

# MongoDB Collections
tables_collection = db['tables']
waiters_collection = db['waiters']
inventory_collection = db['inventory']
held_orders_collection = db['held_orders']
users_collection = db['users']  # User accounts save karanna

UPLOAD_FOLDER = 'static/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def init_db():
    print("MongoDB collections ready!")
    
    # System eke user kenek wath nathnam, default Admin account ekak auto create karayi
    if users_collection.count_documents({}) == 0:
        hashed_password = generate_password_hash('admin123')
        users_collection.insert_one({
            'username': 'admin',
            'password': hashed_password,
            'role': 'Admin'
        })
        print("Default admin user created successfully! (Username: admin | Password: admin123)")

def get_next_id(counter_name='order_id'):
    counter = db.counters.find_one_and_update(
        {'_id': counter_name},
        {'$inc': {'sequence_value': 1}},
        upsert=True,
        return_document=True
    )
    return counter['sequence_value']

# --- Role Required Decorator ---
def role_required(allowed_roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user_role = session.get('role')
            if not user_role:
                return redirect(url_for('login'))
            if user_role not in allowed_roles:
                return abort(403)
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# --- Custom Template Renderer Helper ---
def render_template_custom(template_str, **kwargs):
    try:
        return render_template_string(template_str, **kwargs)
    except Exception:
        return render_template(template_str, **kwargs)

init_db()



# --- HTML TEMPLATES ---

BASE_LAYOUT = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ title }} - SyntaxCore POS</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.7.2/socket.io.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        .no-scrollbar::-webkit-scrollbar { display: none; }
        .no-scrollbar { -ms-overflow-style: none; scrollbar-width: none; }
    </style>
</head>
<body class="bg-slate-100 font-sans min-h-screen lg:h-screen flex flex-col overflow-x-hidden lg:overflow-hidden select-none">
    <header class="bg-indigo-900 text-white px-4 md:px-6 py-3 md:py-4 flex justify-between items-center shadow-lg print:hidden relative z-50">
        <div class="flex items-center gap-3">
            <!-- Logo Image -->
            <img src="{{ url_for('static', filename='images/logo.png') }}" alt="The 888 Logo" class="w-10 h-10 md:w-11 md:h-11 rounded-2xl object-cover border border-indigo-700 shadow-md">
            <div>
                <h1 class="text-base md:text-lg font-black tracking-wide">888 Restaurant</h1>
                <p class="text-[10px] md:text-xs text-indigo-300">Smart Restaurant Management</p>
            </div>
        </div>

        <!-- Desktop Navigation -->
        <nav class="hidden lg:flex items-center gap-1.5 text-xs font-bold flex-wrap">
            {% if session.get('role') == 'Admin' %}
                <a href="/" class="px-3 py-2 rounded-xl bg-white/10 hover:bg-white/20 transition flex items-center gap-1.5"><i class="fa-solid fa-chart-pie"></i> Dashboard</a>
                <a href="/pos" class="px-3 py-2 rounded-xl bg-white/10 hover:bg-white/20 transition flex items-center gap-1.5"><i class="fa-solid fa-cash-register"></i> POS</a>
                <a href="/kitchen" class="px-3 py-2 rounded-xl bg-white/10 hover:bg-white/20 transition flex items-center gap-1.5"><i class="fa-solid fa-utensils"></i> KOT</a>
                <a href="/tables" class="px-3 py-2 rounded-xl bg-white/10 hover:bg-white/20 transition flex items-center gap-1.5"><i class="fa-solid fa-chair"></i> Tables</a>
                <a href="/admin/running-orders" class="px-3 py-2 rounded-xl bg-orange-600/30 hover:bg-orange-600 text-orange-200 hover:text-white transition flex items-center gap-1.5"><i class="fa-solid fa-shield-halved"></i> Active Orders</a>
                <a href="/inventory" class="px-3 py-2 rounded-xl bg-white/10 hover:bg-white/20 transition flex items-center gap-1.5"><i class="fa-solid fa-boxes-stacked"></i> Inventory</a>
                <a href="/waiters" class="px-3 py-2 rounded-xl bg-white/10 hover:bg-white/20 transition flex items-center gap-1.5"><i class="fa-solid fa-user-tie"></i> Waiters</a>
                <a href="/reports" class="px-3 py-2 rounded-xl bg-white/10 hover:bg-white/20 transition flex items-center gap-1.5"><i class="fa-solid fa-chart-line"></i> Reports</a>
                <a href="/users" class="px-3 py-2 rounded-xl bg-white/10 hover:bg-white/20 transition flex items-center gap-1.5 text-orange-300"><i class="fa-solid fa-users-cog"></i> Users</a>
                <a href="/settings/service-charge" class="px-3 py-2 rounded-xl bg-white/10 hover:bg-white/20 transition flex items-center gap-1.5"><i class="fa-solid fa-gear"></i> Settings</a>
            {% elif session.get('role') == 'Cashier' or session.get('role') == 'Waiter' %}
                <a href="/pos" class="px-3 py-2 rounded-xl bg-white/10 hover:bg-white/20 transition flex items-center gap-1.5"><i class="fa-solid fa-cash-register"></i> POS</a>
                <a href="/kitchen" class="px-3 py-2 rounded-xl bg-white/10 hover:bg-white/20 transition flex items-center gap-1.5"><i class="fa-solid fa-utensils"></i> KOT</a>
                <a href="/tables" class="px-3 py-2 rounded-xl bg-white/10 hover:bg-white/20 transition flex items-center gap-1.5"><i class="fa-solid fa-chair"></i> Tables</a>
            {% endif %}
            <a href="/logout" class="px-3 py-2 rounded-xl bg-red-600/30 hover:bg-red-600 text-red-200 hover:text-white transition flex items-center gap-1.5 ml-2"><i class="fa-solid fa-sign-out-alt"></i> Logout</a>
        </nav>

        <!-- Mobile & Tablet Menu Toggle Button -->
        <button onclick="toggleMobileMenu()" class="lg:hidden text-white p-2.5 rounded-xl bg-white/10 hover:bg-white/20 transition text-base">
            <i class="fa-solid fa-bars"></i>
        </button>
    </header>

    <!-- Mobile & Tablet Dropdown Navigation Menu -->
    <div id="mobile-menu" class="hidden lg:hidden bg-indigo-950 text-white px-6 py-4 flex flex-col gap-2 shadow-2xl z-40 print:hidden border-t border-indigo-800">
        {% if session.get('role') == 'Admin' %}
            <a href="/" class="px-3 py-2.5 rounded-xl bg-white/10 hover:bg-white/20 transition flex items-center gap-3 text-sm font-bold"><i class="fa-solid fa-chart-pie text-orange-400"></i> Dashboard</a>
            <a href="/pos" class="px-3 py-2.5 rounded-xl bg-white/10 hover:bg-white/20 transition flex items-center gap-3 text-sm font-bold"><i class="fa-solid fa-cash-register text-orange-400"></i> POS</a>
            <a href="/kitchen" class="px-3 py-2.5 rounded-xl bg-white/10 hover:bg-white/20 transition flex items-center gap-3 text-sm font-bold"><i class="fa-solid fa-utensils text-orange-400"></i> KOT</a>
            <a href="/tables" class="px-3 py-2.5 rounded-xl bg-white/10 hover:bg-white/20 transition flex items-center gap-3 text-sm font-bold"><i class="fa-solid fa-chair text-orange-400"></i> Tables</a>
            <a href="/admin/running-orders" class="px-3 py-2.5 rounded-xl bg-orange-600/30 text-orange-200 hover:bg-orange-600 hover:text-white transition flex items-center gap-3 text-sm font-bold"><i class="fa-solid fa-shield-halved"></i> Active Orders (Admin)</a>
            <a href="/inventory" class="px-3 py-2.5 rounded-xl bg-white/10 hover:bg-white/20 transition flex items-center gap-3 text-sm font-bold"><i class="fa-solid fa-boxes-stacked text-orange-400"></i> Inventory</a>
            <a href="/waiters" class="px-3 py-2.5 rounded-xl bg-white/10 hover:bg-white/20 transition flex items-center gap-3 text-sm font-bold"><i class="fa-solid fa-user-tie text-orange-400"></i> Waiters</a>
            <a href="/reports" class="px-3 py-2.5 rounded-xl bg-white/10 hover:bg-white/20 transition flex items-center gap-3 text-sm font-bold"><i class="fa-solid fa-chart-line text-orange-400"></i> Reports</a>
            <a href="/users" class="px-3 py-2.5 rounded-xl bg-orange-600/20 text-orange-300 hover:bg-orange-600 hover:text-white transition flex items-center gap-3 text-sm font-bold"><i class="fa-solid fa-users-cog"></i> Users Management</a>
            <a href="/settings/service-charge" class="px-3 py-2.5 rounded-xl bg-white/10 hover:bg-white/20 transition flex items-center gap-3 text-sm font-bold"><i class="fa-solid fa-gear text-orange-400"></i> Settings</a>
        {% elif session.get('role') == 'Cashier' or session.get('role') == 'Waiter' %}
            <a href="/pos" class="px-3 py-2.5 rounded-xl bg-white/10 hover:bg-white/20 transition flex items-center gap-3 text-sm font-bold"><i class="fa-solid fa-cash-register text-orange-400"></i> POS</a>
            <a href="/kitchen" class="px-3 py-2.5 rounded-xl bg-white/10 hover:bg-white/20 transition flex items-center gap-3 text-sm font-bold"><i class="fa-solid fa-utensils text-orange-400"></i> KOT</a>
            <a href="/tables" class="px-3 py-2.5 rounded-xl bg-white/10 hover:bg-white/20 transition flex items-center gap-3 text-sm font-bold"><i class="fa-solid fa-chair text-orange-400"></i> Tables</a>
        {% endif %}
        <a href="/logout" class="px-3 py-2.5 rounded-xl bg-red-600/30 hover:bg-red-600 text-red-200 hover:text-white transition flex items-center gap-3 text-sm font-bold"><i class="fa-solid fa-sign-out-alt"></i> Logout</a>
    </div>

    <!-- Main Container Responsive Fix -->
    <main class="flex-1 overflow-y-auto lg:overflow-hidden flex flex-col p-3 md:p-6 print:p-0">
        {{ content | safe }}
    </main>

    <script>
        function toggleMobileMenu() {
            const menu = document.getElementById('mobile-menu');
            menu.classList.toggle('hidden');
        }
    </script>
</body>
</html>
"""


def render_template_custom(template_str, **kwargs):
    return render_template_string(
        BASE_LAYOUT, content=render_template_string(template_str, **kwargs), **kwargs
    )
    
LOGIN_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ title }}</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
</head>
<body class="bg-slate-950 font-sans antialiased min-h-screen flex items-center justify-center p-4">

    <div class="max-w-md w-full bg-white rounded-3xl shadow-2xl p-6 sm:p-8 border border-slate-100">
        <!-- Logo and Header -->
        <div class="text-center mb-6">
            <img src="{{ url_for('static', filename='images/logo.png') }}" alt="888 Restaurant Logo" class="w-16 h-16 sm:w-20 sm:h-20 rounded-2xl object-cover mx-auto mb-4 shadow-md border border-slate-200">
            <h1 class="text-2xl font-black text-slate-800">888 Restaurant</h1>
            <p class="text-xs text-slate-400 mt-1 font-medium">Smart Restaurant Management - Please sign in</p>
        </div>

        <!-- Flash Messages -->
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="mb-4 p-3 rounded-xl text-xs font-bold text-white {% if category == 'error' %}bg-red-500{% else %}bg-green-500{% endif %} shadow-sm">
                        {{ message }}
                    </div>
                {% endfor %}
            {% endif %}
        {% endwith %}

        <!-- Login Form -->
        <form action="/login" method="POST" class="space-y-4">
            <div>
                <label class="block text-xs font-bold text-slate-700 uppercase mb-1">Username</label>
                <div class="relative">
                    <span class="absolute inset-y-0 left-0 flex items-center pl-3 text-slate-400">
                        <i class="fas fa-user"></i>
                    </span>
                    <input type="text" name="username" required placeholder="Enter username" class="w-full pl-10 pr-4 py-3 bg-slate-50 border border-slate-200 rounded-2xl focus:outline-none focus:border-orange-500 text-sm font-medium text-slate-800">
                </div>
            </div>

            <div>
                <label class="block text-xs font-bold text-slate-700 uppercase mb-1">Password</label>
                <div class="relative">
                    <span class="absolute inset-y-0 left-0 flex items-center pl-3 text-slate-400">
                        <i class="fas fa-lock"></i>
                    </span>
                    <input type="password" name="password" required placeholder="Enter password" class="w-full pl-10 pr-4 py-3 bg-slate-50 border border-slate-200 rounded-2xl focus:outline-none focus:border-orange-500 text-sm font-medium text-slate-800">
                </div>
            </div>

            <button type="submit" class="w-full py-3.5 bg-orange-500 hover:bg-orange-600 text-white rounded-2xl font-black text-sm shadow-lg shadow-orange-500/30 transition active:scale-95 flex items-center justify-center gap-2 mt-2">
                <i class="fas fa-sign-in-alt"></i> Sign In
            </button>
        </form>
    </div>

</body>
</html>
"""



    
DASHBOARD_HTML = """
<div class="flex-1 overflow-y-auto flex flex-col gap-6 max-w-7xl mx-auto w-full p-2 md:p-0">
    <div>
        <h2 class="text-2xl font-black text-slate-800">Dashboard Overview</h2>
        <p class="text-xs text-slate-400 font-semibold">Real-time metrics, analytics and active tables</p>
    </div>
    
    <!-- Top Stats Cards: Responsive grid (1 col on mobile, 2 cols on tablet, 4 cols on PC) -->
    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 md:gap-5">
        <div class="bg-white p-5 md:p-6 rounded-3xl border border-slate-200 shadow-sm flex items-center gap-4">
            <div class="w-14 h-14 bg-indigo-50 text-indigo-600 rounded-2xl flex items-center justify-center text-2xl font-bold flex-shrink-0"><i class="fa-solid fa-wallet"></i></div>
            <div>
                <p class="text-xs font-bold uppercase text-slate-400">Total Revenue</p>
                <h3 class="text-lg md:text-xl font-black text-slate-800 font-mono mt-0.5">LKR {{ "%.2f"|format(total_revenue) }}</h3>
            </div>
        </div>
        <div class="bg-white p-5 md:p-6 rounded-3xl border border-slate-200 shadow-sm flex items-center gap-4">
            <div class="w-14 h-14 bg-emerald-50 text-emerald-600 rounded-2xl flex items-center justify-center text-2xl font-bold flex-shrink-0"><i class="fa-solid fa-receipt"></i></div>
            <div>
                <p class="text-xs font-bold uppercase text-slate-400">Total Orders</p>
                <h3 class="text-lg md:text-xl font-black text-slate-800 font-mono mt-0.5">{{ total_orders }}</h3>
            </div>
        </div>
        <div class="bg-white p-5 md:p-6 rounded-3xl border border-slate-200 shadow-sm flex items-center gap-4">
            <div class="w-14 h-14 bg-amber-50 text-amber-600 rounded-2xl flex items-center justify-center text-2xl font-bold flex-shrink-0"><i class="fa-solid fa-boxes-stacked"></i></div>
            <div>
                <p class="text-xs font-bold uppercase text-slate-400">Inventory Items</p>
                <h3 class="text-lg md:text-xl font-black text-slate-800 font-mono mt-0.5">{{ total_inventory }}</h3>
            </div>
        </div>
        <div class="bg-white p-5 md:p-6 rounded-3xl border border-slate-200 shadow-sm flex items-center gap-4">
            <div class="w-14 h-14 bg-rose-50 text-rose-600 rounded-2xl flex items-center justify-center text-2xl font-bold flex-shrink-0"><i class="fa-solid fa-chair"></i></div>
            <div>
                <p class="text-xs font-bold uppercase text-slate-400">Occupied Tables</p>
                <h3 class="text-lg md:text-xl font-black text-slate-800 font-mono mt-0.5">{{ occupied_count }} / {{ total_tables }}</h3>
            </div>
        </div>
    </div>

    <!-- Charts & Tables Section: Responsive grid (1 col on mobile/tablet, 2 cols on PC) -->
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div class="bg-white p-5 md:p-6 rounded-3xl border border-slate-200 shadow-sm">
            <h3 class="font-black text-slate-800 mb-4">Revenue Trend</h3>
            <canvas id="revenueChart" height="120"></canvas>
        </div>
        <div class="bg-white p-5 md:p-6 rounded-3xl border border-slate-200 shadow-sm">
            <h3 class="font-black text-slate-800 mb-4">Active Tables Status</h3>
            <!-- Tables Status Grid: 2 cols on mobile, 3 cols on tablet/PC -->
            <div class="grid grid-cols-2 sm:grid-cols-3 gap-3">
                {% for t in tables %}
                <div class="p-3 md:p-4 rounded-2xl border flex flex-col justify-between {{ 'bg-rose-50 border-rose-200 text-rose-800' if t.status == 'Occupied' else 'bg-emerald-50 border-emerald-200 text-emerald-800' }}">
                    <div class="flex justify-between items-center"><span class="font-black text-sm md:text-base">Table {{ t.table_number }}</span><i class="fa-solid fa-circle text-[10px]"></i></div>
                    <span class="text-[10px] md:text-xs font-bold uppercase mt-2">{{ t.status }}</span>
                    {% if t.status == 'Occupied' %}
                    <a href="/tables/clear/{{ t.table_number }}" class="mt-3 text-center text-xs bg-white text-rose-600 font-extrabold py-1.5 rounded-xl shadow-sm hover:bg-rose-600 hover:text-white transition">Clear Table</a>
                    {% endif %}
                </div>
                {% endfor %}
            </div>
        </div>
    </div>

    <!-- Live QR Orders (Pending) Section -->
    <div class="bg-white p-5 md:p-6 rounded-3xl border border-slate-200 shadow-sm overflow-hidden">
        <div class="flex justify-between items-center mb-4">
            <h3 class="font-black text-slate-800 text-base md:text-lg">Live QR Orders (Pending)</h3>
            <span class="bg-indigo-100 text-indigo-700 text-xs font-extrabold px-3 py-1 rounded-full">Real-time</span>
        </div>
        
        <div class="overflow-x-auto">
            <table class="w-full text-left border-collapse min-w-[600px]">
                <thead>
                    <tr class="border-b border-slate-100 text-xs font-bold uppercase text-slate-400">
                        <th class="pb-3">Order ID</th>
                        <th class="pb-3">Table No</th>
                        <th class="pb-3">Items & Details</th>
                        <th class="pb-3">Total (LKR)</th>
                        <th class="pb-3">Status</th>
                        <th class="pb-3 text-right">Action</th>
                    </tr>
                </thead>
                <tbody class="divide-y divide-slate-100 text-sm">
                    {% if orders %}
                        {% for order in orders %}
                        <tr class="hover:bg-slate-50/50">
                            <td class="py-4 font-bold text-slate-800">#{{ order.id }}</td>
                            <td class="py-4 font-black text-indigo-600">Table {{ order.table_number }}</td>
                            <td class="py-4 text-slate-600 font-medium">
                                <span class="text-xs bg-slate-100 p-2 rounded-xl block max-w-xs truncate">{{ order.items }}</span>
                            </td>
                            <td class="py-4 font-mono font-bold text-slate-800">LKR {{ "%.2f"|format(order.total) }}</td>
                            <td class="py-4">
                                <span class="bg-amber-50 text-amber-700 text-xs font-extrabold px-2.5 py-1 rounded-lg border border-amber-200">{{ order.status }}</span>
                            </td>
                            <td class="py-4 text-right">
                                <a href="/orders/complete/{{ order.id }}" class="bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-extrabold px-3 py-1.5 rounded-xl transition shadow-sm inline-block">Complete</a>
                            </td>
                        </tr>
                        {% endfor %}
                    {% else %}
                        <tr>
                            <td colspan="6" class="text-center py-8 text-slate-400 font-medium">No pending QR orders right now.</td>
                        </tr>
                    {% endif %}
                </tbody>
            </table>
        </div>
    </div>
</div>

<script>
    const ctx = document.getElementById('revenueChart').getContext('2d');
    new Chart(ctx, {
        type: 'line',
        data: {
            labels: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
            datasets: [{
                label: 'Revenue (LKR)',
                data: [12000, 19000, 15000, 25000, 32000, 45000, 38000],
                borderColor: '#4f46e5',
                backgroundColor: 'rgba(79, 70, 229, 0.1)',
                fill: true,
                tension: 0.3,
                borderWidth: 3
            }]
        },
        options: { responsive: true, plugins: { legend: { display: false } } }
    });
</script>
"""

SETTINGS_HTML = """
<div class="max-w-2xl mx-auto p-4 md:p-6 bg-white rounded-3xl border border-slate-200 shadow-sm font-sans mt-4 md:mt-6 w-full">
    <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3 mb-6 pb-4 border-b border-slate-100">
        <div>
            <h2 class="text-xl md:text-2xl font-black text-slate-800">System Settings</h2>
            <p class="text-xs text-slate-400 font-medium">Configure restaurant service charge and billing policies.</p>
        </div>
        <a href="/pos" class="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-xl font-bold text-xs transition flex items-center gap-1.5 flex-shrink-0">
            <i class="fa-solid fa-arrow-left"></i> Back to POS
        </a>
    </div>

    <form method="POST" action="/settings/service-charge" class="space-y-6">
        <!-- Service Charge Box -->
        <div class="bg-slate-50 p-4 md:p-5 rounded-2xl border border-slate-200/80 space-y-4">
            <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3">
                <div>
                    <h3 class="font-black text-slate-800 text-sm">Service Charge Configuration</h3>
                    <p class="text-xs text-slate-500 font-medium">Automatically add service charge to customer bills.</p>
                </div>
                <!-- Toggle Switch for Enable/Disable -->
                <label class="relative inline-flex items-center cursor-pointer">
                    <input type="checkbox" name="enabled" class="sr-only peer" {% if settings.enabled %}checked{% endif %}>
                    <div class="w-11 h-6 bg-slate-300 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-orange-500"></div>
                </label>
            </div>

            <!-- Percentage Input -->
            <div class="pt-3 border-t border-slate-200/60 flex items-center justify-between">
                <span class="text-xs font-bold text-slate-700">Service Charge Percentage (%)</span>
                <div class="flex items-center gap-2">
                    <input type="number" step="0.1" name="percentage" value="{{ settings.percentage }}" class="w-24 p-2 bg-white border border-slate-300 rounded-xl text-right font-mono font-bold text-slate-900 text-sm outline-none focus:border-orange-500">
                    <span class="text-xs font-bold text-slate-500">%</span>
                </div>
            </div>
        </div>

        <!-- Save Button -->
        <button type="submit" class="w-full py-3 bg-orange-500 hover:bg-orange-600 text-white rounded-xl font-black text-sm shadow-md transition active:scale-95 flex items-center justify-center gap-2">
            <i class="fa-solid fa-floppy-disk"></i> Save Settings
        </button>
    </form>
</div>
"""

USERS_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ title }}</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
</head>
<body class="bg-gray-100 font-sans antialiased">

    <nav class="bg-indigo-600 text-white shadow-lg">
        <div class="max-w-7xl mx-auto px-4 py-3 flex justify-between items-center">
            <h1 class="text-xl font-bold"><i class="fas fa-users-cog mr-2"></i> User Management</h1>
            <div class="space-x-4">
                <a href="/" class="bg-indigo-700 px-3 py-2 rounded hover:bg-indigo-800 text-sm">Dashboard</a>
                <a href="/pos" class="bg-indigo-700 px-3 py-2 rounded hover:bg-indigo-800 text-sm">POS Panel</a>
                <a href="/logout" class="bg-red-600 px-3 py-2 rounded hover:bg-red-700 text-sm">Logout</a>
            </div>
        </div>
    </nav>

    <div class="max-w-7xl mx-auto px-4 py-8">
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="mb-4 p-4 rounded text-white {% if category == 'error' %}bg-red-500{% else %}bg-green-500{% endif %}">
                        {{ message }}
                    </div>
                {% endfor %}
            {% endif %}
        {% endwith %}

        <div class="grid grid-cols-1 md:grid-cols-3 gap-8">
            <div class="bg-white p-6 rounded-lg shadow-md h-fit">
                <h2 class="text-lg font-bold text-gray-800 mb-4 border-b pb-2"><i class="fas fa-user-plus mr-2 text-indigo-600"></i> Add New User</h2>
                <form action="/users" method="POST" class="space-y-4">
                    <div>
                        <label class="block text-sm font-medium text-gray-700 mb-1">Username</label>
                        <input type="text" name="username" required class="w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500">
                    </div>
                    <div>
                        <label class="block text-sm font-medium text-gray-700 mb-1">Password</label>
                        <input type="password" name="password" required class="w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500">
                    </div>
                    <div>
                        <label class="block text-sm font-medium text-gray-700 mb-1">Role</label>
                        <select name="role" class="w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500">
                            <option value="Admin">Admin</option>
                            <option value="Cashier">Cashier</option>
                            <option value="Waiter">Waiter</option>
                        </select>
                    </div>
                    <button type="submit" class="w-full bg-indigo-600 text-white py-2 rounded-lg hover:bg-indigo-700 font-semibold transition">
                        Create User
                    </button>
                </form>
            </div>

            <div class="bg-white p-6 rounded-lg shadow-md md:col-span-2">
                <h2 class="text-lg font-bold text-gray-800 mb-4 border-b pb-2"><i class="fas fa-list mr-2 text-indigo-600"></i> Existing Users</h2>
                <div class="overflow-x-auto">
                    <table class="w-full text-left border-collapse">
                        <thead>
                            <tr class="bg-gray-100 text-gray-600 text-sm">
                                <th class="py-3 px-4 border-b">Username</th>
                                <th class="py-3 px-4 border-b">Role</th>
                                <th class="py-3 px-4 border-b text-center">Action</th>
                            </tr>
                        </thead>
                        <tbody class="text-gray-700 text-sm">
                            {% for user in users %}
                            <tr class="border-b hover:bg-gray-50">
                                <td class="py-3 px-4 font-medium">{{ user.username }}</td>
                                <td class="py-3 px-4">
                                    <span class="px-2 py-1 rounded text-xs font-semibold 
                                        {% if user.role == 'Admin' %} bg-purple-100 text-purple-700 
                                        {% elif user.role == 'Cashier' %} bg-blue-100 text-blue-700 
                                        {% else %} bg-green-100 text-green-700 {% endif %}">
                                        {{ user.role }}
                                    </span>
                                </td>
                                <td class="py-3 px-4 text-center">
                                    {% if user.username != session.get('username') %}
                                    <a href="/users/delete/{{ user._id }}" onclick="return confirm('Are you sure you want to delete this user?');" class="text-red-500 hover:text-red-700">
                                        <i class="fas fa-trash-alt"></i> Delete
                                    </a>
                                    {% else %}
                                    <span class="text-gray-400 italic">Current User</span>
                                    {% endif %}
                                </td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    </div>
</body>
</html>
"""


POS_HTML = """
<div class="grid grid-cols-1 lg:grid-cols-12 gap-4 lg:gap-6 h-full font-sans">
    <!-- Main Center Area: Categories, Products & Bottom Action Controls (Col Span 7) -->
    <div class="lg:col-span-7 flex flex-col gap-4 overflow-hidden">
        <!-- Search & Table Quick Switch Bar -->
        <div class="flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
            <div class="relative flex-1">
                <i class="fa-solid fa-magnifying-glass absolute left-4 top-3.5 text-slate-400"></i>
                <input type="text" id="search" placeholder="Search food..." onkeyup="filterProducts()" class="w-full pl-11 pr-4 py-3 bg-white border border-slate-200 rounded-2xl font-medium outline-none focus:ring-2 focus:ring-orange-500 shadow-sm text-sm">
            </div>
            <div class="flex items-center gap-2">
                <!-- Live Active Tables Modal Button -->
                <button onclick="openActiveTablesModal()" class="flex-1 sm:flex-initial py-3 px-4 bg-slate-900 hover:bg-slate-800 text-white rounded-2xl font-black text-xs sm:text-sm shadow-md transition flex items-center justify-center gap-2 flex-shrink-0">
                    <i class="fa-solid fa-chair text-orange-400"></i> Tables (<span id="active-tables-count" class="bg-orange-500 text-white px-2 py-0.5 rounded-full text-xs font-black">0</span>)
                </button>
                <!-- Live QR Orders Modal Button -->
                <button onclick="openQrOrdersModal()" class="flex-1 sm:flex-initial py-3 px-4 bg-orange-600 hover:bg-orange-700 text-white rounded-2xl font-black text-xs sm:text-sm shadow-md transition flex items-center justify-center gap-2 flex-shrink-0">
                    <i class="fa-solid fa-qrcode text-white"></i> QR Orders
                </button>
            </div>
        </div>
        
        <!-- Customer QR Orders Live Panel Modal -->
        <div id="qr-orders-modal" class="fixed inset-0 bg-slate-900/50 backdrop-blur-sm hidden items-center justify-center z-50 p-4">
            <div class="bg-white p-6 sm:p-8 rounded-3xl shadow-2xl max-w-2xl w-full">
                <div class="flex justify-between items-center mb-4">
                    <div>
                        <h3 class="text-lg sm:text-xl font-black text-slate-800">Incoming Customer QR Orders</h3>
                        <p class="text-xs text-slate-400 font-medium">Review customer mobile orders, send KOT, and assign to tables.</p>
                    </div>
                    <button onclick="closeQrOrdersModal()" class="text-slate-400 hover:text-slate-600 font-bold"><i class="fa-solid fa-xmark text-lg"></i></button>
                </div>
                <div id="qr-incoming-list" class="space-y-3 max-h-[380px] overflow-y-auto pr-1 mb-6">
                    <!-- Dynamically loaded QR orders -->
                </div>
                <button onclick="closeQrOrdersModal()" class="w-full py-3 bg-slate-100 hover:bg-slate-200 text-slate-600 rounded-xl font-bold text-sm transition">Close Window</button>
            </div>
        </div>
        
        <!-- Explore Categories Pills -->
        <div class="flex items-center gap-3 overflow-x-auto pb-1 no-scrollbar">
            <div onclick="filterCategory('All', this)" class="category-pill px-4 py-2.5 bg-orange-500 text-white rounded-2xl font-bold text-xs cursor-pointer shadow-sm flex items-center gap-2 flex-shrink-0 transition">
                <i class="fa-solid fa-utensils"></i> All Items
            </div>
            <div onclick="filterCategory('Burgers', this)" class="category-pill px-4 py-2.5 bg-white text-slate-600 border border-slate-200 rounded-2xl font-bold text-xs cursor-pointer shadow-sm flex items-center gap-2 flex-shrink-0 hover:bg-slate-50 transition">
                <i class="fa-solid fa-burger text-orange-500"></i> Burgers
            </div>
            <div onclick="filterCategory('Beverages', this)" class="category-pill px-4 py-2.5 bg-white text-slate-600 border border-slate-200 rounded-2xl font-bold text-xs cursor-pointer shadow-sm flex items-center gap-2 flex-shrink-0 hover:bg-slate-50 transition">
                <i class="fa-solid fa-cup-hot text-amber-500"></i> Beverages
            </div>
            <div onclick="filterCategory('Desserts', this)" class="category-pill px-4 py-2.5 bg-white text-slate-600 border border-slate-200 rounded-2xl font-bold text-xs cursor-pointer shadow-sm flex items-center gap-2 flex-shrink-0 hover:bg-slate-50 transition">
                <i class="fa-solid fa-ice-cream text-pink-500"></i> Desserts
            </div>
        </div>

        <!-- Product Grid - Responsive Columns Grid (Click to Add) -->
        <div id="product-grid" class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3 overflow-y-auto flex-1 p-1">
            {% for item in inventory %}
            <div onclick="addToCart('{{ item.sku }}', '{{ item.name }}', {{ item.price }})" class="product-card bg-white p-2.5 rounded-2xl border border-slate-200/80 shadow-sm flex flex-col justify-between relative group hover:shadow-md hover:border-orange-500 cursor-pointer transition active:scale-95 aspect-square" data-category="{{ item.category|lower }}">
                
                <!-- Top Image & Rating Badge -->
                <div class="flex justify-center relative mb-1">
                    {% if item.image %}
                    <img src="{{ item.image }}" class="w-full h-16 rounded-xl object-cover shadow-inner group-hover:scale-[1.02] transition">
                    {% else %}
                    <div class="w-full h-16 rounded-xl bg-orange-50 text-orange-500 flex items-center justify-center text-xl font-bold shadow-inner"><i class="fa-solid fa-burger"></i></div>
                    {% endif %}
                    <span class="absolute top-1 right-1 bg-slate-900/70 backdrop-blur-md text-white text-[9px] font-bold px-1.5 py-0.5 rounded-md flex items-center gap-0.5">
                        <i class="fa-solid fa-star text-amber-400 text-[8px]"></i> 4.8
                    </span>
                </div>

                <!-- Product Name, Price & Plus Icon -->
                <div class="flex flex-col justify-between flex-1">
                    <h4 class="font-bold text-slate-800 text-[11px] mb-0.5 line-clamp-2 leading-tight">{{ item.name }}</h4>
                    <div class="flex items-center justify-between pt-1 border-t border-slate-100">
                        <span class="font-mono font-black text-slate-900 text-[11px]">LKR {{ "%.2f"|format(item.price) }}</span>
                        <span class="w-5 h-5 rounded-lg bg-orange-50 text-orange-600 flex items-center justify-center text-[10px] group-hover:bg-orange-500 group-hover:text-white transition shadow-sm">
                            <i class="fa-solid fa-plus text-[9px]"></i>
                        </span>
                    </div>
                </div>
            </div>
            {% endfor %}
        </div>

        <!-- PAYMENT METHODS & ACTION BUTTONS MOVED HERE (Under Product Grid) -->
        <div class="bg-white p-3 rounded-2xl border border-slate-200 shadow-sm flex flex-col gap-2 flex-shrink-0">
            <!-- Payment Method Selectors (6 in a row or grid) -->
            <div class="grid grid-cols-6 gap-1.5">
                <button onclick="setPaymentMethod('Cash')" id="pm-Cash" class="pay-method-btn p-2 bg-orange-50 border-2 border-orange-500 rounded-xl flex items-center justify-center gap-1.5 text-orange-600 font-bold text-xs shadow-sm">
                    <i class="fa-solid fa-money-bill-wave text-xs"></i> Cash
                </button>
                <button onclick="setPaymentMethod('Card')" id="pm-Card" class="pay-method-btn p-2 bg-white border border-slate-200 rounded-xl flex items-center justify-center gap-1.5 text-slate-600 font-bold text-xs shadow-sm">
                    <i class="fa-solid fa-credit-card text-xs"></i> Card
                </button>
                <button onclick="setPaymentMethod('Visa')" id="pm-Visa" class="pay-method-btn p-2 bg-white border border-slate-200 rounded-xl flex items-center justify-center gap-1.5 text-indigo-700 font-bold text-xs shadow-sm">
                    <i class="fa-brands fa-cc-visa text-xs"></i> Visa
                </button>
                <button onclick="setPaymentMethod('Online')" id="pm-Online" class="pay-method-btn p-2 bg-white border border-slate-200 rounded-xl flex items-center justify-center gap-1.5 text-blue-600 font-bold text-xs shadow-sm">
                    <i class="fa-brands fa-paypal text-xs"></i> Online
                </button>
                <button onclick="setPaymentMethod('UberEats')" id="pm-UberEats" class="pay-method-btn p-2 bg-white border border-slate-200 rounded-xl flex items-center justify-center gap-1.5 text-emerald-600 font-bold text-xs shadow-sm">
                    <i class="fa-solid fa-utensils text-xs"></i> Uber
                </button>
                <button onclick="setPaymentMethod('PickMe')" id="pm-PickMe" class="pay-method-btn p-2 bg-white border border-slate-200 rounded-xl flex items-center justify-center gap-1.5 text-amber-600 font-bold text-xs shadow-sm">
                    <i class="fa-solid fa-taxi text-xs"></i> PickMe
                </button>
            </div>
            
            <!-- Action Buttons Grid -->
            <div class="grid grid-cols-5 gap-1.5">
                <button onclick="holdOrder()" class="py-2 bg-amber-500 hover:bg-amber-600 text-white rounded-xl font-black text-xs shadow-sm transition active:scale-95 flex items-center justify-center gap-1"><i class="fa-solid fa-floppy-disk"></i> Hold</button>
                <button onclick="printKOTDirect()" class="py-2 bg-slate-800 hover:bg-slate-900 text-white rounded-xl font-black text-xs shadow-sm transition active:scale-95 flex items-center justify-center gap-1"><i class="fa-solid fa-utensils"></i> KOT</button>
                <button onclick="printPreBill()" class="py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl font-black text-xs shadow-sm transition active:scale-95 flex items-center justify-center gap-1">
                    <i class="fa-solid fa-file-invoice"></i> Pre-Bill
                </button>
                <button onclick="openBillHistoryModal()" class="py-2 bg-slate-800 hover:bg-slate-900 text-white rounded-xl font-black text-xs shadow-sm transition flex items-center justify-center gap-1 active:scale-95">
                    <i class="fa-solid fa-clock-rotate-left text-amber-300"></i> History
                </button>
                <button onclick="processCheckout()" class="py-2 bg-orange-500 hover:bg-orange-600 text-white rounded-xl font-black text-xs shadow-md transition active:scale-95 flex items-center justify-center gap-1">
                    <i class="fa-solid fa-print"></i> Close Bill
                </button>
            </div>
        </div>
    </div>
    
    <!-- Right Sidebar: Cashier Billing Invoice (Col Span 5 - Fully Dedicated to Cart & Totals) -->
    <div class="lg:col-span-5 bg-white rounded-3xl border border-slate-200 shadow-xl p-4 flex flex-col h-auto lg:h-full overflow-hidden">
        <!-- Top Title & Table Info -->
        <div class="flex justify-between items-center mb-2.5 flex-shrink-0">
            <h3 class="font-black text-lg text-slate-800">Cashier Billing</h3>
            <span id="active-table-badge" class="text-xs bg-amber-50 text-amber-700 px-2.5 py-1 rounded-lg font-black hidden">Running Order</span>
        </div>

        <div class="grid grid-cols-2 gap-2 mb-2 flex-shrink-0">
            <select id="pos-table" onchange="checkTableSelection()" class="p-2 bg-slate-50 border rounded-xl font-bold text-slate-700 text-xs outline-none">
                {% for t in tables %}<option value="{{ t.table_number }}">Table {{ t.table_number }}</option>{% endfor %}
            </select>
            <select id="pos-waiter" class="p-2 bg-slate-50 border rounded-xl font-bold text-slate-700 text-xs outline-none">
                <option value="" disabled selected>-- Waiter --</option>
                {% for w in waiters %}
                <option value="{{ w.name }}">{{ w.name }}</option>
                {% endfor %}
            </select>
        </div>

        <input type="text" id="pos-comment" placeholder="Special Billing / KOT Note" class="w-full p-2 bg-slate-50 border rounded-xl font-medium text-slate-700 text-xs outline-none mb-2 flex-shrink-0">

        <!-- CART ITEMS LIST (Maximized height now since payment buttons moved to left side!) -->
        <div id="cart-list" class="space-y-2 overflow-y-auto max-h-[420px] lg:max-h-none flex-1 pr-1 mb-2 border-y border-slate-100 py-2">
            <!-- Dynamically added items will appear here -->
        </div>

        <!-- BOTTOM TOTALS & CALCULATIONS CONTAINER -->
        <div class="space-y-2 flex-shrink-0">
            <!-- Service Charge Quick Control Bar -->
            <div class="bg-indigo-50/60 px-3 py-2 rounded-xl border border-indigo-100 flex items-center justify-between">
                <div class="flex items-center gap-2">
                    <input type="checkbox" id="pos-service-charge-toggle" checked onchange="renderCart()" class="w-4 h-4 text-orange-500 rounded focus:ring-orange-400 cursor-pointer">
                    <label for="pos-service-charge-toggle" class="text-xs font-black text-slate-700 cursor-pointer">Service Charge</label>
                </div>
                <div class="flex items-center gap-1">
                    <input type="number" id="pos-service-charge-rate" value="10" oninput="renderCart()" class="w-12 p-1 bg-white border border-indigo-200 rounded-lg text-right font-mono text-xs font-bold outline-none">
                    <span class="text-xs font-bold text-slate-500">%</span>
                </div>
            </div>

            <!-- Payment Summary Box -->
            <div class="bg-slate-50 p-2.5 rounded-xl border border-slate-100 space-y-1.5">
                <div class="flex justify-between items-center text-xs font-bold text-slate-500">
                    <span>Sub Total</span> <span id="cart-subtotal" class="font-mono text-slate-700 text-xs">LKR 0.00</span>
                </div>

                <div id="service-charge-row" class="flex justify-between items-center text-xs font-bold text-slate-500">
                    <span id="service-charge-label">Service Charge (10%)</span> <span id="cart-service-charge" class="font-mono text-slate-700 text-xs">LKR 0.00</span>
                </div>

                <div class="flex justify-between items-center text-xs font-bold text-slate-500">
                    <span>Discount</span> 
                    <div class="flex gap-1 items-center">
                        <input type="number" id="discount-val" placeholder="0" oninput="renderCart()" class="w-14 p-1 bg-white border rounded-lg text-right text-xs font-bold outline-none">
                        <select id="discount-type" onchange="renderCart()" class="p-1 bg-white border rounded-lg text-xs font-bold outline-none">
                            <option value="lkr">LKR</option>
                            <option value="percent">%</option>
                        </select>
                    </div>
                </div>
                
                <!-- Total Amount -->
                <div class="flex justify-between items-center font-black pt-1.5 border-t border-slate-200">
                    <span class="text-slate-900 text-sm">TOTAL</span> <span id="cart-total" class="text-orange-600 font-mono text-lg">LKR 0.00</span>
                </div>

                <!-- Cash Tendered & Balance -->
                <div id="inline-cash-box" class="pt-1.5 border-t border-slate-200 space-y-1 bg-orange-50/50 p-2 rounded-xl border border-orange-100">
                    <div class="flex justify-between items-center">
                        <span class="text-xs font-black uppercase text-slate-700">Given Cash:</span>
                        <input type="number" id="inline-cash-tendered" placeholder="0.00" oninput="calculateInlineChange()" class="w-28 p-1.5 bg-white border border-orange-300 rounded-lg text-right font-mono font-black text-slate-900 text-xs outline-none focus:border-orange-500 shadow-inner">
                    </div>
                    <div class="flex justify-between items-center">
                        <span class="text-xs font-black uppercase text-emerald-700">Change:</span>
                        <span id="inline-modal-change" class="font-mono font-black text-emerald-600 text-sm">LKR 0.00</span>
                    </div>
                </div>
            </div>
        </div>
    </div>
</div>

<!-- Bill History / Re-Print Modal -->
<div id="bill-history-modal" class="fixed inset-0 bg-slate-900/50 backdrop-blur-sm hidden items-center justify-center z-50 p-4">
    <div class="bg-white p-6 sm:p-8 rounded-3xl shadow-2xl max-w-xl w-full">
        <div class="flex justify-between items-center mb-4">
            <div>
                <h3 class="text-lg sm:text-xl font-black text-slate-800">Completed Bills History</h3>
                <p class="text-xs text-slate-400 font-medium">Select any previous bill to re-print or review.</p>
            </div>
            <button onclick="closeBillHistoryModal()" class="text-slate-400 hover:text-slate-600 font-bold"><i class="fa-solid fa-xmark text-lg"></i></button>
        </div>
        <div id="bill-history-list" class="space-y-2.5 max-h-[350px] overflow-y-auto pr-1 mb-6"></div>
        <button onclick="closeBillHistoryModal()" class="w-full py-3 bg-slate-100 hover:bg-slate-200 text-slate-600 rounded-xl font-bold text-sm transition">Close</button>
    </div>
</div>

<!-- Active Tables & Running Orders Overview Modal -->
<div id="active-tables-modal" class="fixed inset-0 bg-slate-900/50 backdrop-blur-sm hidden items-center justify-center z-50 p-4">
    <div class="bg-white p-6 sm:p-8 rounded-3xl shadow-2xl max-w-2xl w-full">
        <div class="flex justify-between items-center mb-4">
            <div>
                <h3 class="text-lg sm:text-xl font-black text-slate-800">Restaurant Tables Status</h3>
                <p class="text-xs text-slate-400 font-medium">Click any occupied table to load items and settle bill or print KOT</p>
            </div>
            <button onclick="closeActiveTablesModal()" class="text-slate-400 hover:text-slate-600 font-bold"><i class="fa-solid fa-xmark text-lg"></i></button>
        </div>
        <div id="active-tables-list" class="grid grid-cols-1 sm:grid-cols-2 gap-3 max-h-[380px] overflow-y-auto pr-1 mb-6"></div>
        <button onclick="closeActiveTablesModal()" class="w-full py-3 bg-slate-100 hover:bg-slate-200 text-slate-600 rounded-xl font-bold text-sm transition">Close Window</button>
    </div>
</div>

<!-- Unified 80mm Print Area -->
<div id="printable-asset-area" class="hidden p-2 font-mono text-xs text-black bg-white"></div>

<style>
    @media print {
        body * { visibility: hidden; }
        #printable-asset-area, #printable-asset-area * { visibility: visible; }
        #printable-asset-area { position: absolute; left: 0; top: 0; width: 80mm; display: block !important; }
    }
    .no-scrollbar::-webkit-scrollbar { display: none; }
    .no-scrollbar { -ms-overflow-style: none; scrollbar-width: none; }
</style>





<script>
let cart = [];
let currentPaymentMethod = 'Cash';
let activeRunningOrderId = null;
let isKotPrintedStatus = false;

// Dynamic Service Charge Configuration (Fetched from Database Settings)
let serviceChargeConfig = {
    enabled: false,
    percentage: 10,
    label: "Service Charge (10%)"
};

// Fetch service charge settings from backend API on page load
fetch('/api/settings/service-charge')
    .then(res => res.json())
    .then(data => {
        serviceChargeConfig.enabled = data.enabled;
        serviceChargeConfig.percentage = data.percentage;
        serviceChargeConfig.label = `Service Charge (${data.percentage}%)`;
        renderCart(); // Recalculate bill with fetched settings
    })
    .catch(err => console.log('Could not load service charge settings:', err));

window.calculatedSubtotal = 0;
window.calculatedServiceCharge = 0;
window.calculatedDiscount = 0;
window.calculatedTotal = 0;

const socket = io();

socket.on('refresh_orders', function(data) {
    fetchActiveTablesCount();
    checkTableSelection();
    let modal = document.getElementById('active-tables-modal');
    if(modal && modal.classList.contains('flex')) {
        openActiveTablesModal();
    }
});

// Initial check on load
fetchActiveTablesCount();
checkTableSelection();
renderCart();

function setPaymentMethod(method) {
    currentPaymentMethod = method;
    document.querySelectorAll('.pay-method-btn').forEach(btn => {
        btn.classList.remove('border-orange-500', 'bg-orange-50', 'text-orange-600');
        btn.classList.add('border-slate-200', 'bg-white', 'text-slate-600');
    });
    let activeBtn = document.getElementById('pm-' + method);
    if(activeBtn) {
        activeBtn.classList.remove('border-slate-200', 'bg-white', 'text-slate-600');
        activeBtn.classList.add('border-orange-500', 'bg-orange-50', 'text-orange-600');
    }
    let cashBox = document.getElementById('inline-cash-box');
    if(cashBox) cashBox.style.display = (method === 'Cash') ? 'block' : 'none';
}

function addToCart(sku, name, price, qty = 1) {
    let item = cart.find(i => (i.sku && i.sku === sku) || (i.id && i.id === sku));
    if(item) { 
        item.qty += parseInt(qty); 
    } else { 
        cart.push({sku: sku, id: sku, name: name, price: parseFloat(price), qty: parseInt(qty), note: ''}); 
    }
    renderCart();
}

function renderCart() {
    let html = ''; 
    let subtotal = 0;
    
    cart.forEach((i, idx) => {
        subtotal += i.price * i.qty;
        html += `
            <div class="bg-slate-50 p-2.5 rounded-2xl border border-slate-100 flex flex-col gap-2">
                <div class="flex justify-between items-center">
                    <div>
                        <h5 class="font-bold text-xs text-slate-800">${i.name}</h5>
                        <span class="text-[10px] text-slate-400">LKR ${i.price} × ${i.qty}</span>
                    </div>
                    <div class="flex items-center gap-2">
                        <span class="font-mono font-bold text-xs text-orange-600">LKR ${(i.price * i.qty).toFixed(2)}</span>
                        <button onclick="cart.splice(${idx},1);renderCart()" class="text-red-400 hover:text-red-600 p-1"><i class="fa-solid fa-trash"></i></button>
                    </div>
                </div>
                <!-- Item-wise Note Input -->
                <input type="text" placeholder="Add note (e.g., No salt, Extra spicy)" value="${i.note || ''}" oninput="updateItemNote(${idx}, this.value)" class="w-full px-2.5 py-1.5 bg-white border border-slate-200 rounded-xl text-[11px] font-medium text-slate-700 outline-none focus:border-orange-500">
            </div>`;
    });
    
    let cartListEl = document.getElementById('cart-list');
    if(cartListEl) cartListEl.innerHTML = html || '<p class="text-center py-6 text-slate-400 font-semibold text-xs">Invoice is empty</p>';
    
    // Service Charge Calculation directly from POS Panel inputs
    let serviceCharge = 0;
    let scRow = document.getElementById('service-charge-row');
    let scToggle = document.getElementById('pos-service-charge-toggle');
    let scRateInput = document.getElementById('pos-service-charge-rate');
    
    let isScEnabled = scToggle ? scToggle.checked : true;
    let scRate = scRateInput ? (parseFloat(scRateInput.value) || 0) : 10;

    if (isScEnabled && subtotal > 0 && scRate > 0) {
        serviceCharge = (subtotal * scRate) / 100;
        if(scRow) scRow.classList.remove('hidden');
        if(document.getElementById('service-charge-label')) document.getElementById('service-charge-label').innerText = `Service Charge (${scRate}%)`;
        if(document.getElementById('cart-service-charge')) document.getElementById('cart-service-charge').innerText = 'LKR ' + serviceCharge.toFixed(2);
    } else {
        if(scRow) scRow.classList.add('hidden');
    }

    let discountVal = parseFloat(document.getElementById('discount-val')?.value) || 0;
    let discountType = document.getElementById('discount-type')?.value || 'lkr';
    let discount = discountType === 'percent' ? (subtotal * discountVal / 100) : discountVal;
    
    // Total = Subtotal + Service Charge - Discount
    let total = Math.max(0, (subtotal + serviceCharge) - discount);

    if(document.getElementById('cart-subtotal')) document.getElementById('cart-subtotal').innerText = 'LKR ' + subtotal.toFixed(2);
    if(document.getElementById('cart-total')) document.getElementById('cart-total').innerText = 'LKR ' + total.toFixed(2);
    
    window.calculatedSubtotal = subtotal;
    window.calculatedServiceCharge = serviceCharge;
    window.calculatedDiscount = discount;
    window.calculatedTotal = total;
    
    calculateInlineChange();
}

function updateItemNote(index, value) {
    if(cart[index]) {
        cart[index].note = value;
    }
}

function calculateInlineChange() {
    let tendered = parseFloat(document.getElementById('inline-cash-tendered')?.value) || 0;
    let change = tendered - (window.calculatedTotal || 0);
    let changeEl = document.getElementById('inline-modal-change');
    if(changeEl) changeEl.innerText = 'LKR ' + (change >= 0 ? change.toFixed(2) : '0.00');
}

function holdOrder() {
    if(cart.length === 0) return alert('Invoice is empty!');
    
    let selectedWaiter = document.getElementById('pos-waiter')?.value;
    if (!selectedWaiter) {
        alert('Please select a waiter first!');
        document.getElementById('pos-waiter')?.focus();
        return;
    }

    let table = document.getElementById('pos-table').value;
    let comment = document.getElementById('pos-comment').value;

    fetch('/api/order/hold', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            order_id: activeRunningOrderId,
            table_number: table,
            waiter_name: selectedWaiter,
            items: cart,
            comment: comment,
            subtotal: window.calculatedSubtotal,
            service_charge: window.calculatedServiceCharge,
            discount: window.calculatedDiscount,
            total: window.calculatedTotal,
            is_kot_printed: isKotPrintedStatus
        })
    }).then(res => res.json()).then(data => {
        if(data.order_id && !activeRunningOrderId) {
            activeRunningOrderId = data.order_id;
        }
        alert('Table ' + table + ' order saved successfully with waiter: ' + selectedWaiter);
        fetchActiveTablesCount();
        checkTableSelection();
    });
}

function fetchActiveTablesCount() {
    fetch('/api/orders/held').then(res => res.json()).then(orders => {
        let countEl = document.getElementById('active-tables-count');
        if(countEl) countEl.innerText = orders.length;
    });
}

function openActiveTablesModal() {
    fetch('/api/orders/held').then(res => res.json()).then(orders => {
        let html = '';
        if(orders.length === 0) {
            html = '<div class="col-span-2 text-center py-8 text-slate-400 font-semibold text-xs">No active running orders on tables right now.</div>';
        } else {
            orders.forEach(o => {
                let itemsParsed = typeof o.items === 'string' ? JSON.parse(o.items) : o.items;
                let itemsSummary = itemsParsed.map(i => `${i.name} (x${i.qty || i.quantity})`).join(', ');
                let kotBadge = o.is_kot_printed ? 
                    '<span class="bg-emerald-100 text-emerald-700 px-2 py-0.5 rounded-full text-[10px] font-black"><i class="fa-solid fa-check"></i> KOT Sent</span>' : 
                    '<span class="bg-rose-100 text-rose-700 px-2 py-0.5 rounded-full text-[10px] font-black animate-pulse"><i class="fa-solid fa-triangle-exclamation"></i> KOT NOT Sent!</span>';

                let deleteButtonHtml = `
                    <button onclick="deleteRunningOrder(${o.id}, '${o.table_number}')" class="w-full py-2 bg-rose-500 hover:bg-rose-600 text-white rounded-xl font-bold text-xs shadow transition active:scale-95 flex items-center justify-center gap-1.5">
                        <i class="fa-solid fa-trash"></i> Delete Order (Admin)
                    </button>
                `;

                // Safe waiter name escape
                let waiterNameVal = o.waiter_name || '';

                html += `
                    <div class="bg-slate-50 p-4 rounded-2xl border border-slate-200 flex flex-col justify-between gap-3">
                        <div>
                            <div class="flex justify-between items-center mb-1">
                                <h4 class="font-black text-slate-800 text-sm">Table ${o.table_number}</h4>
                                ${kotBadge}
                            </div>
                            <p class="text-xs text-slate-500 truncate max-w-[280px]">${itemsSummary}</p>
                            <span class="font-mono font-bold text-orange-600 text-xs mt-1 block">Total: LKR ${(o.total || 0).toFixed(2)}</span>
                            <span class="text-[10px] text-slate-500 block">Waiter: <b>${waiterNameVal || 'Not Assigned'}</b></span>
                        </div>
                        <div class="flex flex-col gap-2">
                            <button onclick='loadTableOrder(${o.id}, "${o.table_number}", ${o.subtotal || 0}, ${o.service_charge || 0}, ${o.discount || 0}, ${o.total || 0}, "${o.comment || ''}", ${JSON.stringify(o.items)}, ${o.is_kot_printed || false}, "${waiterNameVal}")' class="w-full py-2 bg-orange-500 hover:bg-orange-600 text-white rounded-xl font-bold text-xs shadow transition active:scale-95">Select Table Order</button>
                            ${deleteButtonHtml}
                        </div>
                    </div>
                `;
            });
        }
        document.getElementById('active-tables-list').innerHTML = html;
        let modal = document.getElementById('active-tables-modal');
        if(modal) {
            modal.classList.remove('hidden');
            modal.classList.add('flex');
        }
    });
}


// Order Delete Function for Admin
function deleteRunningOrder(orderId, tableNumber) {
    if (!confirm(`Are you sure you want to delete/cancel the running order for Table ${tableNumber}? This cannot be undone.`)) {
        return;
    }

    fetch(`/api/order/${orderId}`, {
        method: 'DELETE',
        headers: {'Content-Type': 'application/json'}
    })
    .then(res => res.json())
    .then(data => {
        if (data.success || data.message) {
            alert('Order deleted successfully by Admin.');
            openActiveTablesModal(); // Refresh modal list
            fetchActiveTablesCount();
            checkTableSelection();
        } else {
            alert(data.message || 'Failed to delete order. Unauthorized or error occurred.');
        }
    })
    .catch(err => {
        alert('Access denied or server error. Only Admin can delete active orders.');
        console.error(err);
    });
}

function closeActiveTablesModal() {
    let modal = document.getElementById('active-tables-modal');
    if(modal) {
        modal.classList.remove('flex');
        modal.classList.add('hidden');
    }
}

function loadTableOrder(orderId, tableNumber, subtotal, serviceCharge, discount, total, comment, items, isKotPrinted) {
    activeRunningOrderId = orderId;
    isKotPrintedStatus = Boolean(isKotPrinted);
    
    let tableSelect = document.getElementById('pos-table');
    if(tableSelect) {
        for (let option of tableSelect.options) {
            if (String(option.value).trim() === String(tableNumber).trim()) {
                tableSelect.value = option.value;
                break;
            }
        }
    }
    
    let commentInput = document.getElementById('pos-comment');
    if(commentInput) commentInput.value = comment || '';
    
    let parsedItems = [];
    try {
        parsedItems = typeof items === 'string' ? JSON.parse(items) : (items || []);
    } catch (e) {
        parsedItems = [];
    }

    cart = parsedItems.map(item => ({
        sku: item.sku || item.id || item.product_id || '',
        id: item.id || item.sku || '',
        name: item.name || '',
        price: parseFloat(item.price) || 0,
        qty: parseInt(item.qty || item.quantity) || 1,
        note: item.note || ''
    }));

    renderCart();
    updateKotIndicatorUI();
    
    let badge = document.getElementById('active-table-badge');
    if(badge) {
        badge.innerText = 'Table ' + tableNumber + ' Active';
        badge.classList.remove('hidden');
    }
    
    closeActiveTablesModal();
}

function checkTableSelection() {
    let selectedTable = String(document.getElementById('pos-table').value).trim();
    
    fetch('/api/orders/held').then(res => res.json()).then(orders => {
        let foundOrder = orders.find(o => String(o.table_number).trim() === selectedTable);
        
        if (foundOrder) {
            activeRunningOrderId = foundOrder.id;
            isKotPrintedStatus = Boolean(foundOrder.is_kot_printed);
            
            let commentInput = document.getElementById('pos-comment');
            if(commentInput) commentInput.value = foundOrder.comment || '';
            
            let parsedItems = [];
            try {
                parsedItems = typeof foundOrder.items === 'string' ? JSON.parse(foundOrder.items) : (foundOrder.items || []);
            } catch (e) {
                parsedItems = [];
            }

            cart = parsedItems.map(item => ({
                sku: item.sku || item.id || item.product_id || '',
                id: item.id || item.sku || '',
                name: item.name || '',
                price: parseFloat(item.price) || 0,
                qty: parseInt(item.qty || item.quantity) || 1,
                note: item.note || ''
            }));

            renderCart();
            updateKotIndicatorUI();
            
            let badge = document.getElementById('active-table-badge');
            if(badge) {
                badge.innerText = 'Table ' + selectedTable + ' Active';
                badge.classList.remove('hidden');
            }
        } else {
            activeRunningOrderId = null;
            isKotPrintedStatus = false;
            cart = [];
            renderCart();
            if(document.getElementById('pos-comment')) document.getElementById('pos-comment').value = '';
            if(document.getElementById('active-table-badge')) document.getElementById('active-table-badge').classList.add('hidden');
            updateKotIndicatorUI();
        }
    });
}

function updateKotIndicatorUI() {
    let indicator = document.getElementById('kot-status-indicator');
    if(!indicator) return;
    if(isKotPrintedStatus) {
        indicator.className = "p-2.5 bg-emerald-50 border border-emerald-200 rounded-xl text-center font-bold text-[11px] text-emerald-700 flex items-center justify-center gap-1";
        indicator.innerHTML = '<i class="fa-solid fa-check-circle"></i> KOT Sent to Kitchen';
    } else {
        indicator.className = "p-2.5 bg-rose-50 border border-rose-200 rounded-xl text-center font-bold text-[11px] text-rose-700 flex items-center justify-center gap-1 animate-pulse";
        indicator.innerHTML = '<i class="fa-solid fa-triangle-exclamation"></i> KOT NOT Yet Sent!';
    }
}

function printKOTDirect() {
    if(cart.length === 0) return alert('Invoice is empty!');
    
    let selectedWaiter = document.getElementById('pos-waiter')?.value;
    if (!selectedWaiter) {
        alert('Please select a waiter first!');
        document.getElementById('pos-waiter')?.focus();
        return;
    }

    let table = document.getElementById('pos-table').value;
    let comment = document.getElementById('pos-comment').value;
    
    fetch('/api/order/hold', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            order_id: activeRunningOrderId,
            table_number: table,
            waiter_name: selectedWaiter,
            items: cart,
            comment: comment,
            subtotal: window.calculatedSubtotal,
            service_charge: window.calculatedServiceCharge,
            discount: window.calculatedDiscount,
            total: window.calculatedTotal,
            is_kot_printed: true
        })
    }).then(res => res.json()).then(data => {
        if(data.order_id) {
            activeRunningOrderId = data.order_id;
        }
        isKotPrintedStatus = true;
        updateKotIndicatorUI();
        
        // Generate KOT HTML string and print via isolated iframe to avoid multi-page print issues
        let kotHtml = generateKOTHtmlString(table, cart, comment, selectedWaiter);
        printViaIframe(kotHtml);
        
        fetchActiveTablesCount();
        checkTableSelection();
    });
}

function generateKOTHtmlString(table, items, comment, waiterName) {
    let itemsStr = items.map(i => `
        <div style="display:flex; justify-content:space-between; font-size:12px; margin-bottom:4px;">
            <span><b>${i.name}</b> (x<b>${i.qty}</b>)</span>
        </div>
        ${i.note ? `<div style="font-size:10px; font-style:italic; padding-left:10px; margin-bottom:4px;">Note: ${i.note}</div>` : ''}
    `).join('');

    let commentSection = comment ? `<div style="margin-top:6px; font-size:11px; border-top:1px dashed black; padding-top:4px;"><b>Comment:</b> ${comment}</div>` : '';

    return `
        <div style="text-align:center; font-weight:bold; font-size:16px; margin-bottom:4px;">KITCHEN ORDER (KOT)</div>
        <div style="border-top:1px solid black; margin:4px 0;"></div>
        <div style="font-size:11px; margin-bottom:2px;">Table: <b>Table ${table}</b></div>
        <div style="font-size:11px; margin-bottom:2px;">Waiter: <b>${waiterName}</b></div>
        <div style="font-size:11px; margin-bottom:6px;">Time: ${new Date().toLocaleString()}</div>
        <div style="border-top:1px dashed black; margin:4px 0;"></div>
        <div style="margin-bottom:6px;">${itemsStr}</div>
        ${commentSection}
        <div style="border-top:1px dashed black; margin:4px 0;"></div>
        <div style="text-align:center; font-size:10px; margin-top:6px;">*** KITCHEN COPY ***</div>
    `;
}



function generateKOTHtml(table, items, comment, waiterName) {
    let itemsStr = '';
    
    items.forEach(i => {
        let qty = parseInt(i.qty || i.quantity) || 1;
        let itemNoteHtml = i.note ? `<div style="font-size:10px; font-style:italic; padding-left:10px; margin-bottom:2px;">↳ Note: ${i.note}</div>` : '';
        
        for (let q = 0; q < qty; q++) {
            itemsStr += `
                <div style="margin-bottom:4px;">
                    <div style="display:flex; justify-content:space-between; font-size:12px; font-weight:bold;">
                        <span>${i.name}</span><span>x1</span>
                    </div>
                    ${itemNoteHtml}
                </div>
            `;
        }
    });

    // Corrected ID to match HTML (#printable-asset-area)
    let area = document.getElementById('printable-asset-area');
    if(area) {
        area.innerHTML = `
            <div style="text-align:center; font-weight:black; font-size:14px; margin-bottom:4px;">*** KITCHEN ORDER (KOT) ***</div>
            <div style="font-size:11px; margin-bottom:2px;">Table: <b>${table}</b> | Waiter: <b>${waiterName || 'Cashier'}</b></div>
            <div style="font-size:11px; margin-bottom:6px;">Time: ${new Date().toLocaleTimeString()}</div>
            <div style="border-top:1px dashed black; margin:4px 0;"></div>
            <div style="margin-bottom:6px;">${itemsStr}</div>
            ${comment ? `<div style="border-top:1px dashed black; margin:4px 0;"></div><div style="font-size:11px;"><b>Overall Note:</b> ${comment}</div>` : ''}
            <div style="border-top:1px dashed black; margin:4px 0;"></div>
        `;
    }
}


function openQrOrdersModal() {
    fetch('/api/orders/held').then(res => res.json()).then(orders => {
        let html = '';
        let qrOrders = orders.filter(o => o.waiter_name === 'QR Customer');
        
        if(qrOrders.length === 0) {
            html = '<div class="text-center py-8 text-slate-400 font-semibold text-xs">No pending customer QR orders right now.</div>';
        } else {
            qrOrders.forEach(o => {
                let itemsParsed = typeof o.items === 'string' ? JSON.parse(o.items) : o.items;
                let itemsSummary = itemsParsed.map(i => `${i.name} (x${i.qty || i.quantity})`).join(', ');

                html += `
                    <div class="bg-slate-50 p-4 rounded-2xl border border-slate-200 flex flex-col justify-between gap-3">
                        <div>
                            <div class="flex justify-between items-center mb-1">
                                <h4 class="font-black text-slate-800 text-sm">Table ${o.table_number} <span class="text-[10px] bg-orange-100 text-orange-700 px-2 py-0.5 rounded-full font-bold">QR Order</span></h4>
                                <span class="font-mono font-bold text-orange-600 text-xs">LKR ${(o.total || 0).toFixed(2)}</span>
                            </div>
                            <p class="text-xs text-slate-500 truncate max-w-[400px]">${itemsSummary}</p>
                            <span class="text-[10px] text-slate-400 mt-1 block">Note: ${o.comment || 'None'}</span>
                        </div>
                        <div class="flex gap-2">
                            <button onclick='loadTableOrder(${o.id}, "${o.table_number}", ${o.subtotal || 0}, ${o.service_charge || 0}, ${o.discount || 0}, ${o.total || 0}, "${o.comment || ''}", ${JSON.stringify(o.items)}, false); closeQrOrdersModal();' class="flex-1 py-2 bg-slate-900 hover:bg-black text-white rounded-xl font-bold text-xs shadow transition active:scale-95">Load to POS & Send KOT</button>
                        </div>
                    </div>
                `;
            });
        }
        document.getElementById('qr-incoming-list').innerHTML = html;
        let modal = document.getElementById('qr-orders-modal');
        if(modal) {
            modal.classList.remove('hidden');
            modal.classList.add('flex');
        }
    });
}

function closeQrOrdersModal() {
    let modal = document.getElementById('qr-orders-modal');
    if(modal) {
        modal.classList.remove('flex');
        modal.classList.add('hidden');
    }
}

function processCheckout() {
    if(cart.length === 0) return alert('Invoice is empty!');
    
    let selectedWaiter = document.getElementById('pos-waiter')?.value;
    if (!selectedWaiter) {
        alert('Please select a waiter first!');
        document.getElementById('pos-waiter')?.focus();
        return;
    }

    let table = document.getElementById('pos-table').value;
    let comment = document.getElementById('pos-comment').value;

    fetch('/api/order', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            order_id: activeRunningOrderId,
            table_number: table,
            waiter_name: selectedWaiter,
            items: cart,
            comment: comment,
            subtotal: window.calculatedSubtotal,
            service_charge: window.calculatedServiceCharge,
            discount: window.calculatedDiscount,
            total: window.calculatedTotal,
            payment_method: currentPaymentMethod,
            is_kot_printed: true
        })
    }).then(res => res.json()).then(data => {
        generateReceiptHtml(table, cart, window.calculatedSubtotal, window.calculatedServiceCharge, window.calculatedDiscount, window.calculatedTotal, currentPaymentMethod, selectedWaiter);
        // window.print(); ---> Me parana line eka ain kala!
        resetPOS();
        fetchActiveTablesCount();
    });
}

function resetPOS() {
    cart = [];
    activeRunningOrderId = null;
    isKotPrintedStatus = false;
    if(document.getElementById('active-table-badge')) document.getElementById('active-table-badge').classList.add('hidden');
    if(document.getElementById('inline-cash-tendered')) document.getElementById('inline-cash-tendered').value = '';
    if(document.getElementById('pos-comment')) document.getElementById('pos-comment').value = '';
    if(document.getElementById('discount-val')) document.getElementById('discount-val').value = '';
    renderCart();
    updateKotIndicatorUI();
}

function generateReceiptHtml(table, items, sub, sc, disc, tot, method) {
    let itemsStr = items.map(i => `
        <div style="display:flex; justify-content:space-between; font-size:11px; margin-bottom:2px;">
            <span>${i.name} x${i.qty}</span>
            <span>LKR ${(i.price * i.qty).toFixed(2)}</span>
        </div>
        ${i.note ? `<div style="font-size:9px; font-style:italic; padding-left:8px; margin-bottom:2px;">- ${i.note}</div>` : ''}
    `).join('');
    
    let tendered = parseFloat(document.getElementById('inline-cash-tendered')?.value) || tot;
    let change = tendered - tot;
    let receiptNo = "26-" + Math.floor(100 + Math.random() * 900) + "-" + Math.floor(100000 + Math.random() * 900000);
    
    let scPrintLine = sc > 0 ? `<div style="display:flex; justify-content:space-between;"><span>Service Charge:</span><span>LKR ${sc.toFixed(2)}</span></div>` : '';

    let receiptHtmlString = `
        <div style="text-align:center; font-weight:bold; font-size:15px; line-height:1.2;">THE TRIPLE EIGHT</div>
        <div style="text-align:center; font-weight:bold; font-size:14px; margin-bottom:4px;">RESTAURANT</div>
        <div style="text-align:center; font-size:10px; line-height:1.2; margin-bottom:2px;">Lake Road, Boralegamuwa,</div>
        <div style="text-align:center; font-size:10px; line-height:1.2; margin-bottom:4px;">Maharagama</div>
        <div style="text-align:center; font-size:10px; font-weight:bold; margin-bottom:6px;">Tel: 0112-888888</div>
        <div style="border-top:1px dashed black; margin:4px 0;"></div>
        <div style="font-size:10px; line-height:1.3;">
            <b>Receipt No.:</b> ${receiptNo}<br>
            <b>Date:</b> ${new Date().toLocaleString()}<br>
            <b>Table:</b> ${table}<br>
            <b>Payment:</b> ${method}
        </div>
        <div style="border-top:1px dashed black; margin:4px 0;"></div>
        <div style="font-weight:bold; font-size:11px; margin-bottom:4px;">ITEMS:</div>
        <div>${itemsStr}</div>
        <div style="border-top:1px dashed black; margin:4px 0;"></div>
        <div style="font-size:11px; line-height:1.4;">
            <div style="display:flex; justify-content:space-between;"><span>Subtotal:</span><span>LKR ${sub.toFixed(2)}</span></div>
            ${scPrintLine}
            <div style="display:flex; justify-content:space-between;"><span>Discount:</span><span>LKR ${disc.toFixed(2)}</span></div>
            <div style="display:flex; justify-content:space-between; font-weight:bold; font-size:12px; margin-top:2px;"><span>TOTAL:</span><span>LKR ${tot.toFixed(2)}</span></div>
            <div style="display:flex; justify-content:space-between; margin-top:2px;"><span>Paid Amount:</span><span>LKR ${tendered.toFixed(2)}</span></div>
            <div style="display:flex; justify-content:space-between;"><span>Change:</span><span>LKR ${change >= 0 ? change.toFixed(2) : '0.00'}</span></div>
        </div>
        <div style="border-top:1px dashed black; margin:6px 0;"></div>
        <div style="text-align:center; font-size:9px; color:#333;">software@syntaxcore</div>
        <div style="text-align:center; font-size:10px; font-weight:bold;">0788909801</div>
        <div style="text-align:center; font-size:10px; font-weight:bold; margin-top:4px;">THANK YOU! COME AGAIN</div>
    `;

    // Print using isolated iframe to avoid multi-page dashboard layout bugs
    printViaIframe(receiptHtmlString);
}

// Shared iframe print helper function (danna nathnam mekakuth daaganna)
function printViaIframe(htmlContent) {
    let iframe = document.getElementById('thermal-print-iframe');
    if (!iframe) {
        iframe = document.createElement('iframe');
        iframe.id = 'thermal-print-iframe';
        iframe.style.position = 'fixed';
        iframe.style.right = '0';
        iframe.style.bottom = '0';
        iframe.style.width = '0';
        iframe.style.height = '0';
        iframe.style.border = 'none';
        document.body.appendChild(iframe);
    }
    
    let doc = iframe.contentWindow.document;
    doc.open();
    doc.write(`
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                @page {
                    size: 80mm auto;
                    margin: 0mm;
                }
                body {
                    width: 80mm;
                    margin: 0;
                    padding: 4mm;
                    font-family: monospace;
                    font-size: 11px;
                    background: #fff;
                    color: #000;
                }
                * { box-sizing: border-box; }
            </style>
        </head>
        <body>
            ${htmlContent}
        </body>
        </html>
    `);
    doc.close();
    
    setTimeout(() => {
        iframe.contentWindow.focus();
        iframe.contentWindow.print();
    }, 300);
}




function filterProducts() {
    let q = document.getElementById('search')?.value.toLowerCase() || '';
    document.querySelectorAll('.product-card').forEach(el => {
        el.style.display = el.innerText.toLowerCase().includes(q) ? 'flex' : 'none';
    });
}

function filterCategory(cat, element) {
    document.querySelectorAll('.category-pill').forEach(p => {
        p.classList.remove('bg-orange-500', 'text-white');
        p.classList.add('bg-white', 'text-slate-600', 'border', 'border-slate-200');
    });
    if(element) {
        element.classList.remove('bg-white', 'text-slate-600', 'border', 'border-slate-200');
        element.classList.add('bg-orange-500', 'text-white');
    }

    let q = cat.toLowerCase();
    document.querySelectorAll('.product-card').forEach(el => {
        let itemCat = el.getAttribute('data-category');
        if(cat === 'All' || itemCat === q) {
            el.style.display = 'flex';
        } else {
            el.style.display = 'none';
        }
    });
}

function openBillHistoryModal() {
    fetch('/api/orders/completed').then(res => res.json()).then(bills => {
        let html = '';
        if(!bills || bills.length === 0) {
            html = '<p class="text-center py-8 text-slate-400 font-semibold text-xs">No completed bills found for today.</p>';
        } else {
            bills.forEach(b => {
                let itemsParsed = typeof b.items === 'string' ? JSON.parse(b.items) : (b.items || []);
                let itemsSummary = itemsParsed.map(i => `${i.name} (x${i.qty || i.quantity})`).join(', ');
                
                html += `
                    <div class="bg-slate-50 p-4 rounded-2xl border border-slate-200 flex justify-between items-center">
                        <div>
                            <h4 class="font-black text-slate-800 text-sm">Table ${b.table_number} <span class="text-[10px] bg-emerald-100 text-emerald-700 px-2 py-0.5 rounded-full font-bold ml-1">${b.payment_method || 'Cash'}</span></h4>
                            <p class="text-xs text-slate-500 truncate max-w-[260px] mt-1">${itemsSummary}</p>
                            <span class="font-mono font-bold text-orange-600 text-xs mt-1 block">Total: LKR ${(b.total || 0).toFixed(2)} | Time: ${b.created_at || 'Just now'}</span>
                        </div>
                        <button onclick='reprintBill(${JSON.stringify(b)})' class="py-2 px-4 bg-slate-900 hover:bg-black text-white rounded-xl font-bold text-xs shadow transition active:scale-95 flex items-center gap-1.5 flex-shrink-0">
                            <i class="fa-solid fa-print"></i> Re-Print
                        </button>
                    </div>
                `;
            });
        }
        let listEl = document.getElementById('bill-history-list');
        if(listEl) listEl.innerHTML = html;
        
        let modal = document.getElementById('bill-history-modal');
        if(modal) {
            modal.classList.remove('flex');
            modal.classList.add('hidden');
        }
    }).catch(err => {
        alert('Could not fetch bill history from server.');
    });
}

function closeBillHistoryModal() {
    let modal = document.getElementById('bill-history-modal');
    if(modal) {
        modal.classList.remove('flex');
        modal.classList.add('hidden');
    }
}

function reprintBill(billData) {
    let itemsParsed = typeof billData.items === 'string' ? JSON.parse(billData.items) : (billData.items || []);
    let itemsStr = itemsParsed.map(i => `
        <div style="display:flex; justify-content:space-between; font-size:11px; margin-bottom:2px;">
            <span>${i.name} x${i.qty || i.quantity}</span>
            <span>LKR ${((i.price || 0)*(i.qty || i.quantity || 1)).toFixed(2)}</span>
        </div>
        ${i.note ? `<div style="font-size:9px; font-style:italic; padding-left:8px; margin-bottom:2px;">- ${i.note}</div>` : ''}
    `).join('');
    
    let sub = billData.subtotal || billData.total || 0;
    let sc = billData.service_charge || 0;
    let disc = billData.discount || 0;
    let tot = billData.total || 0;
    let method = billData.payment_method || 'Cash';
    
    let scPrintLine = sc > 0 ? `Service Charge: LKR ${sc.toFixed(2)}<br>` : '';

    let reprintHtml = `
        <div style="text-align:center; font-weight:bold; font-size:13px;">THE TRIPLE EIGHT</div>
        <div style="text-align:center; font-size:9px; margin-bottom:4px;">*** DUPLICATE / RE-PRINT BILL ***</div>
        <div style="border-top:1px dashed black; margin:4px 0;"></div>
        <div style="font-size:10px;">Table: ${billData.table_number}<br>Date: ${billData.created_at || new Date().toLocaleString()}<br>Payment: ${method}</div>
        <div style="border-top:1px dashed black; margin:4px 0;"></div>
        <div>${itemsStr}</div>
        <div style="border-top:1px dashed black; margin:4px 0;"></div>
        <div style="font-size:11px;">Subtotal: LKR ${sub.toFixed(2)}<br>${scPrintLine}Discount: LKR ${disc.toFixed(2)}<br><b>TOTAL: LKR ${tot.toFixed(2)}</b></div>
        <div style="border-top:1px dashed black; margin:4px 0;"></div>
        <div style="text-align:center; font-size:10px; margin-top:6px; font-weight:bold;">THANK YOU! COME AGAIN</div>
    `;

    // Print using isolated iframe to avoid multi-page layout issues
    printViaIframe(reprintHtml);
    closeBillHistoryModal();
}

function printPreBill() {
    if(cart.length === 0) return alert('Invoice is empty!');
    
    let selectedWaiter = document.getElementById('pos-waiter')?.value || 'Cashier';
    let table = document.getElementById('pos-table').value;
    let subtotal = window.calculatedSubtotal || 0;
    let serviceCharge = window.calculatedServiceCharge || 0;
    let discount = window.calculatedDiscount || 0;
    let total = window.calculatedTotal || 0;

    let preBillHtml = generatePreBillHtmlString(table, cart, subtotal, serviceCharge, discount, total, selectedWaiter);
    
    // Print using isolated iframe
    printViaIframe(preBillHtml);
}

// Helper function to generate Pre-Bill HTML string (if not already there)
function generatePreBillHtmlString(table, items, subtotal, serviceCharge, discount, total, waiterName) {
    let itemsStr = items.map(i => `
        <div style="display:flex; justify-content:space-between; font-size:11px; margin-bottom:2px;">
            <span>${i.name} (x${i.qty})</span>
            <span>LKR ${(i.price * i.qty).toFixed(2)}</span>
        </div>
        ${i.note ? `<div style="font-size:9px; font-style:italic; padding-left:8px; margin-bottom:2px;">- ${i.note}</div>` : ''}
    `).join('');

    let scPrintLine = serviceCharge > 0 ? `<div style="display:flex; justify-content:space-between; font-size:11px;"><span>Service Charge:</span><span>LKR ${serviceCharge.toFixed(2)}</span></div>` : '';

    return `
        <div style="text-align:center; font-weight:black; font-size:15px; margin-bottom:2px;">THE TRIPLE EIGHT</div>
        <div style="text-align:center; font-size:10px; margin-bottom:6px;">*** TEMPORARY PRE-BILL ***</div>
        <div style="font-size:10px; margin-bottom:2px;">Table: <b>Table ${table}</b> | Waiter: <b>${waiterName}</b></div>
        <div style="font-size:10px; margin-bottom:6px;">Time: ${new Date().toLocaleString()}</div>
        <div style="border-top:1px dashed black; margin:4px 0;"></div>
        <div style="margin-bottom:6px;">${itemsStr}</div>
        <div style="border-top:1px dashed black; margin:4px 0;"></div>
        <div style="display:flex; justify-content:space-between; font-size:11px;"><span>Subtotal:</span><span>LKR ${subtotal.toFixed(2)}</span></div>
        ${scPrintLine}
        <div style="display:flex; justify-content:space-between; font-size:11px;"><span>Discount:</span><span>LKR ${discount.toFixed(2)}</span></div>
        <div style="display:flex; justify-content:space-between; font-size:13px; font-weight:bold; margin-top:2px;"><span>TOTAL DUE:</span><span>LKR ${total.toFixed(2)}</span></div>
        <div style="border-top:1px dashed black; margin:4px 0;"></div>
        <div style="text-align:center; font-size:9px; margin-top:6px;">* This is not a final tax invoice *</div>
    `;
}
</script>
"""

KITCHEN_HTML = """
<div class="flex-1 overflow-y-auto flex flex-col p-2 sm:p-4">
    <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3 mb-6">
        <div>
            <h2 class="text-xl sm:text-2xl font-black text-slate-800">Kitchen Order Tickets (KOT)</h2>
            <p class="text-xs text-slate-400 font-semibold">Live incoming kitchen orders</p>
        </div>
        <button onclick="window.print()" class="w-full sm:w-auto px-5 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl font-bold text-xs shadow-md transition flex items-center justify-center gap-2">
            <i class="fa-solid fa-print"></i> Print KOT
        </button>
    </div>
    <div id="kot-container" class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 sm:gap-6"></div>
</div>

<script>
    const socket = io();
    socket.on('new_kot', (o) => { appendKotCard(o); });
    function appendKotCard(o) {
        let container = document.getElementById('kot-container');
        let div = document.createElement('div');
        div.className = 'bg-white p-6 rounded-3xl border-2 border-indigo-500 shadow-lg flex flex-col justify-between animate-pulse';
        setTimeout(() => div.classList.remove('animate-pulse'), 2000);
        let itemsHtml = JSON.parse(o.items).map(i => `<div class="flex justify-between font-bold text-slate-700 text-base py-1 border-b border-slate-100"><span>${i.name}</span><span class="bg-indigo-50 text-indigo-700 px-2.5 py-0.5 rounded-lg">x${i.qty}</span></div>`).join('');
        div.innerHTML = `
            <div>
                <div class="flex justify-between items-center mb-4">
                    <span class="bg-indigo-600 text-white px-4 py-1.5 rounded-xl font-black text-sm shadow-sm">Table ${o.table_number}</span>
                    <span class="text-xs font-extrabold text-slate-400 uppercase">Waiter: ${o.waiter_name}</span>
                </div>
                <div class="space-y-1 mb-4">${itemsHtml}</div>
                ${o.comment ? `<div class="bg-amber-50 border border-amber-200 text-amber-800 p-3 rounded-xl text-xs font-bold mb-4 flex items-center gap-2"><i class="fa-solid fa-triangle-exclamation"></i> Note: ${o.comment}</div>` : ''}
            </div>
            <button onclick="this.parentElement.remove()" class="w-full py-3.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-2xl font-black text-sm shadow-md transition active:scale-95">Mark Done & Clear</button>
        `;
        container.prepend(div);
    }
</script>
"""

QR_HTML = """
<div class="max-w-md mx-auto bg-white p-6 sm:p-8 rounded-3xl shadow-sm border border-slate-200 my-auto w-full">
    <div class="text-center mb-6">
        <div class="w-16 h-16 bg-indigo-50 text-indigo-600 rounded-3xl flex items-center justify-center text-2xl font-bold mx-auto mb-3 shadow-inner"><i class="fa-solid fa-qrcode"></i></div>
        <h2 class="text-xl sm:text-2xl font-black text-slate-800">Table {{ table_id }} Menu</h2>
        <p class="text-xs font-semibold text-slate-400">Scan & order directly from your table</p>
    </div>
    <div class="space-y-4">
        <div>
            <label class="text-xs font-bold uppercase text-slate-400 block mb-1">Select Item</label>
            <select id="qr-item" class="w-full p-3 sm:p-3.5 bg-slate-50 border rounded-xl font-bold text-slate-700 text-sm outline-none focus:border-indigo-500">
                {% for i in inventory %}<option value="{{ i.sku }}" data-price="{{ i.price }}">{{ i.name }} - LKR {{ i.price }}</option>{% endfor %}
            </select>
        </div>
        <div>
            <label class="text-xs font-bold uppercase text-slate-400 block mb-1">Quantity</label>
            <input type="number" id="qr-qty" value="1" min="1" class="w-full p-3 sm:p-3.5 bg-slate-50 border rounded-xl font-bold text-slate-700 text-sm outline-none focus:border-indigo-500">
        </div>
        <div>
            <label class="text-xs font-bold uppercase text-slate-400 block mb-1">Special Request / Comment</label>
            <input type="text" id="qr-comment" placeholder="e.g. No onions" class="w-full p-3 sm:p-3.5 bg-slate-50 border rounded-xl font-medium text-slate-700 text-sm outline-none focus:border-indigo-500">
        </div>
        <button onclick="submitQrOrder()" class="w-full py-3.5 sm:py-4 bg-indigo-600 hover:bg-indigo-700 text-white rounded-2xl font-black text-sm sm:text-base shadow-lg transition active:scale-95 flex items-center justify-center gap-2">
            <i class="fa-solid fa-paper-plane text-xs"></i> Place Order
        </button>
    </div>
</div>


<script>
    function submitQrOrder() {
        let itemSel = document.getElementById('qr-item');
        let sku = itemSel.value;
        let name = itemSel.options[itemSel.selectedIndex].text.split(' - ')[0];
        let price = parseFloat(itemSel.options[itemSel.selectedIndex].getAttribute('data-price'));
        let qty = parseInt(document.getElementById('qr-qty').value);
        let comment = document.getElementById('qr-comment').value;

        fetch('/api/order', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({table_number: '{{ table_id }}', waiter_name: 'Customer (QR)', items: [{sku, name, price, qty}], comment: comment, subtotal: price*qty, discount: 0, total: price*qty, payment_method: 'Pending'})
        }).then(res => res.json()).then(data => {
            alert('Order placed successfully via QR!');
        });
    }
</script>
"""

ADMIN_ORDERS_HTML = """
<div class="flex flex-col h-full font-sans gap-4 p-2 sm:p-4 bg-slate-100 overflow-hidden">
    
    <!-- Top Header Bar -->
    <div class="bg-white p-4 sm:p-5 rounded-3xl border border-slate-200 shadow-sm flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
            <h2 class="font-black text-xl sm:text-2xl text-slate-800"><i class="fa-solid fa-shield-halved text-orange-500 mr-2"></i> Admin: Active Running Orders</h2>
            <p class="text-xs text-slate-400 font-medium">Monitor all active table orders in real-time and manage cancellations.</p>
        </div>
        <div class="flex items-center gap-2 w-full sm:w-auto">
            <button onclick="loadAdminRunningOrders()" class="flex-1 sm:flex-none py-2.5 px-4 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-2xl font-black text-xs shadow-sm transition active:scale-95 flex items-center justify-center gap-2">
                <i class="fa-solid fa-rotate"></i> Refresh
            </button>
            <a href="/" class="flex-1 sm:flex-none py-2.5 px-5 bg-slate-900 hover:bg-black text-white rounded-2xl font-black text-xs shadow transition active:scale-95 flex items-center justify-center gap-2">
                <i class="fa-solid fa-arrow-left"></i> Back to POS
            </a>
        </div>
    </div>

    <!-- Active Orders Grid Area -->
    <div class="flex-1 overflow-y-auto pr-1">
        <div id="admin-orders-grid" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            <div class="col-span-full text-center py-12 text-slate-400 font-semibold text-sm bg-white rounded-3xl border border-slate-200">
                Loading active orders...
            </div>
        </div>
    </div>
</div>

<script>
    document.addEventListener("DOMContentLoaded", function() {
        loadAdminRunningOrders();
        // Auto refresh every 10 seconds
        setInterval(loadAdminRunningOrders, 10000);
    });

    function loadAdminRunningOrders() {
        fetch('/api/orders/held')
            .then(res => res.json())
            .then(orders => {
                let container = document.getElementById('admin-orders-grid');
                let html = '';

                if(!orders || orders.length === 0) {
                    container.innerHTML = '<div class="col-span-full text-center py-16 text-slate-400 font-semibold text-sm bg-white rounded-3xl border border-slate-200">No active running orders on tables right now.</div>';
                    return;
                }

                orders.forEach(o => {
                    let itemsParsed = typeof o.items === 'string' ? JSON.parse(o.items) : o.items;
                    let itemsSummary = itemsParsed.map(i => `${i.name} (x${i.qty || i.quantity})`).join(', ');
                    let kotBadge = o.is_kot_printed ? 
                        '<span class="bg-emerald-100 text-emerald-700 px-2.5 py-1 rounded-full text-[10px] font-black"><i class="fa-solid fa-check"></i> KOT Sent</span>' : 
                        '<span class="bg-rose-100 text-rose-700 px-2.5 py-1 rounded-full text-[10px] font-black animate-pulse"><i class="fa-solid fa-triangle-exclamation"></i> KOT NOT Sent!</span>';

                    let waiterNameVal = o.waiter_name || 'Not Assigned';

                    html += `
                        <div class="bg-white p-5 rounded-3xl border border-slate-200 shadow-sm flex flex-col justify-between gap-4">
                            <div>
                                <div class="flex justify-between items-center mb-3">
                                    <h4 class="font-black text-slate-800 text-base flex items-center gap-2">
                                        <i class="fa-solid fa-utensils text-orange-500 text-sm"></i> Table ${o.table_number}
                                    </h4>
                                    ${kotBadge}
                                </div>
                                <p class="text-xs text-slate-500 mb-3 bg-slate-50 p-3 rounded-2xl border border-slate-100 line-clamp-3">${itemsSummary}</p>
                                <div class="space-y-1 text-xs">
                                    <p class="text-slate-500">Assigned Waiter: <b class="text-slate-800">${waiterNameVal}</b></p>
                                    <p class="font-mono font-black text-orange-600 text-sm mt-1">Total: LKR ${(o.total || 0).toFixed(2)}</p>
                                </div>
                            </div>
                            <div>
                                <button onclick="deleteAdminOrder(${o.id}, '${o.table_number}')" class="w-full py-2.5 bg-rose-500 hover:bg-rose-600 text-white rounded-2xl font-black text-xs shadow transition active:scale-95 flex items-center justify-center gap-2">
                                    <i class="fa-solid fa-trash"></i> Delete Order (Admin)
                                </button>
                            </div>
                        </div>
                    `;
                });
                container.innerHTML = html;
            }).catch(err => {
                console.error("Error loading running orders:", err);
            });
    }

    function deleteAdminOrder(orderId, tableNum) {
        if(!confirm(`Are you sure you want to delete the active running order for Table ${tableNum}?`)) return;

        fetch(`/api/order/${orderId}`, {
            method: 'DELETE'
        })
        .then(res => res.json())
        .then(data => {
            alert('Running order deleted successfully!');
            loadAdminRunningOrders();
        })
        .catch(err => {
            alert('Error deleting order!');
        });
    }
</script>
"""

TABLES_HTML = """
<div class="flex-1 p-2 sm:p-4 overflow-y-auto flex flex-col font-sans">
    <div class="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-6">
        <div>
            <h2 class="text-xl sm:text-2xl font-black text-slate-800">Table Management & QR Codes</h2>
            <p class="text-xs text-slate-400 font-semibold">Manage tables and view status</p>
        </div>
        <form method="POST" class="flex flex-col sm:flex-row gap-2 w-full md:w-auto">
            <input type="text" name="table_number" placeholder="Table Number" required class="p-3 bg-white border rounded-xl font-bold shadow-sm outline-none text-sm w-full sm:w-auto focus:border-indigo-500">
            <button type="submit" class="px-6 py-3 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl font-bold text-sm shadow-md transition active:scale-95 flex items-center justify-center gap-2">
                <i class="fa-solid fa-plus text-xs"></i> Add Table
            </button>
        </form>
    </div>
    <div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
        {% for t in tables %}
        <div class="bg-white p-5 sm:p-6 rounded-3xl border border-slate-200 shadow-sm flex flex-col justify-between hover:shadow-md transition">
            <div>
                <div class="flex justify-between items-center mb-2">
                    <h3 class="font-black text-lg sm:text-xl text-slate-800">Table {{ t.table_number }}</h3>
                    <span class="w-3 h-3 rounded-full {{ 'bg-rose-500 animate-pulse' if t.status == 'Occupied' else 'bg-emerald-500' }}"></span>
                </div>
                <span class="text-xs font-bold text-slate-400 uppercase tracking-wider">Status: <span class="{{ 'text-rose-600' if t.status == 'Occupied' else 'text-emerald-600' }}">{{ t.status }}</span></span>
            </div>
            <div class="mt-6 pt-4 border-t border-slate-100 flex justify-between items-center gap-2">
                <a href="/qr/{{ t.table_number }}" target="_blank" class="text-xs font-extrabold bg-indigo-50 text-indigo-700 hover:bg-indigo-100 px-3 sm:px-4 py-2.5 rounded-xl transition flex items-center gap-1.5"><i class="fa-solid fa-qrcode"></i> QR</a>
                {% if t.status == 'Occupied' %}
                <a href="/tables/clear/{{ t.table_number }}" class="text-xs font-bold bg-rose-50 text-rose-600 hover:bg-rose-100 px-3 py-2.5 rounded-xl transition">Clear</a>
                {% endif %}
                <a href="/tables/delete/{{ t.id }}" class="w-9 h-9 rounded-xl bg-slate-50 text-slate-400 hover:bg-red-50 hover:text-red-500 flex items-center justify-center font-bold transition flex-shrink-0"><i class="fa-solid fa-trash"></i></a>
            </div>
        </div>
        {% endfor %}
    </div>
</div>
"""

WAITERS_HTML = """
<div class="flex-1 p-2 sm:p-4 overflow-y-auto max-w-5xl mx-auto w-full flex flex-col font-sans">
    <div class="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-6">
        <div>
            <h2 class="text-xl sm:text-2xl font-black text-slate-800">Waiter Management</h2>
            <p class="text-xs text-slate-400 font-semibold">Add and manage restaurant staff</p>
        </div>
        <form method="POST" class="flex flex-col sm:flex-row gap-2 w-full md:w-auto">
            <input type="text" name="name" placeholder="Waiter Name" required class="p-3 bg-white border rounded-xl font-bold shadow-sm outline-none text-sm w-full sm:w-auto focus:border-indigo-500">
            <input type="text" name="phone" placeholder="Phone Number" required class="p-3 bg-white border rounded-xl font-bold shadow-sm outline-none text-sm w-full sm:w-auto focus:border-indigo-500">
            <button type="submit" class="px-6 py-3 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl font-bold text-sm shadow-md transition active:scale-95 flex items-center justify-center gap-2 flex-shrink-0">
                <i class="fa-solid fa-user-plus text-xs"></i> Add Waiter
            </button>
        </form>
    </div>
    
    <div class="bg-white rounded-3xl border border-slate-200 shadow-sm overflow-hidden">
        <div class="overflow-x-auto">
            <table class="w-full text-left border-collapse">
                <thead>
                    <tr class="bg-slate-50 border-b border-slate-200 text-xs font-black text-slate-400 uppercase tracking-wider">
                        <th class="p-4">ID</th>
                        <th class="p-4">Waiter Name</th>
                        <th class="p-4">Phone Number</th>
                        <th class="p-4 text-center">Action</th>
                    </tr>
                </thead>
                <tbody class="divide-y divide-slate-100">
                    {% for w in waiters %}
                    <tr class="hover:bg-slate-50/50 transition font-medium text-slate-700 text-sm">
                        <td class="p-4 font-mono font-bold text-slate-500">#{{ w.id }}</td>
                        <td class="p-4 font-bold text-slate-800">{{ w.name }}</td>
                        <td class="p-4 font-mono text-xs sm:text-sm">{{ w.phone }}</td>
                        <td class="p-4 text-center">
                            <a href="/waiters/delete/{{ w.id }}" class="inline-flex w-9 h-9 rounded-xl bg-red-50 text-red-500 hover:bg-red-100 hover:text-red-600 items-center justify-center transition shadow-sm">
                                <i class="fa-solid fa-trash text-xs"></i>
                            </a>
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>
</div>
"""

QR_MENU_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SyntaxCore Restaurant - Digital Menu</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
</head>
<body class="bg-slate-100 text-slate-800 font-sans pb-32">

    <header class="bg-slate-900 text-white p-4 sm:p-5 sticky top-0 z-40 shadow-md flex justify-between items-center">
        <div>
            <h1 class="font-black text-base sm:text-lg tracking-wide">SYNTAXCORE RESTAURANT</h1>
            <p id="table-indicator" class="text-xs text-orange-400 font-bold mt-0.5">Loading Table...</p>
        </div>
        <div class="bg-slate-800 px-3 py-1.5 rounded-xl border border-slate-700 text-xs font-semibold flex items-center gap-1.5 flex-shrink-0">
            <i class="fa-solid fa-utensils text-orange-400"></i> <span class="hidden sm:inline">Self Ordering</span>
        </div>
    </header>

    <main class="max-w-md mx-auto p-4 space-y-4">
        <div class="mb-2">
            <h2 class="text-xs sm:text-sm font-bold text-slate-500 uppercase tracking-wider">Available Menu</h2>
        </div>

        <div id="menu-container" class="space-y-3">
            <!-- Loading indicator -->
            <div class="text-center py-10 text-slate-400 text-xs">
                <i class="fa-solid fa-spinner fa-spin text-lg mb-2"></i>
                <p>Loading fresh menu from kitchen...</p>
            </div>
        </div>
    </main>

    <div id="cart-bar" class="fixed bottom-0 left-0 right-0 bg-white border-t border-slate-200 p-4 shadow-xl hidden z-50 max-w-md mx-auto rounded-t-3xl">
        <div class="flex justify-between items-center gap-3">
            <div>
                <span class="text-xs text-slate-400 font-medium block">Total Items: <strong id="cart-count" class="text-slate-800">0</strong></span>
                <span class="text-base sm:text-lg font-black text-slate-900" id="cart-total">LKR 0.00</span>
            </div>
            <button onclick="openCheckoutModal()" class="bg-orange-600 hover:bg-orange-700 text-white px-5 sm:px-6 py-3 rounded-2xl font-black text-xs sm:text-sm shadow-md transition active:scale-95 flex items-center gap-2 flex-shrink-0">
                <span>View Cart & Order</span> <i class="fa-solid fa-arrow-right"></i>
            </button>
        </div>
    </div>

    <div id="checkout-modal" class="fixed inset-0 bg-slate-900/60 backdrop-blur-sm hidden items-end z-50">
        <div class="bg-white w-full rounded-t-3xl p-5 sm:p-6 max-h-[90vh] overflow-y-auto shadow-2xl">
            <div class="flex justify-between items-center mb-4">
                <h3 class="font-black text-lg text-slate-800">Your Order Summary</h3>
                <button onclick="closeCheckoutModal()" class="w-8 h-8 rounded-full bg-slate-100 text-slate-500 hover:bg-slate-200 flex items-center justify-center font-bold transition"><i class="fa-solid fa-xmark text-sm"></i></button>
            </div>
            
            <div id="modal-cart-items" class="space-y-3 divide-y divide-slate-100 mb-4 text-sm"></div>

            <div class="mb-5">
                <label class="block text-xs font-bold text-slate-500 mb-1">Special Instructions / Notes</label>
                <textarea id="order-comment" rows="2" placeholder="e.g. Less spicy, extra sauce..." class="w-full bg-slate-50 border border-slate-200 rounded-xl p-3 text-xs sm:text-sm focus:outline-none focus:border-orange-500"></textarea>
            </div>

            <div class="bg-slate-50 p-4 rounded-2xl space-y-2 mb-6 border border-slate-200">
                <div class="flex justify-between text-xs text-slate-500">
                    <span>Subtotal</span>
                    <span id="summary-subtotal" class="font-bold text-slate-700">LKR 0.00</span>
                </div>
                <div class="flex justify-between text-sm sm:text-base font-black text-slate-900 pt-2 border-t border-slate-200">
                    <span>Total Amount</span>
                    <span id="summary-total" class="text-orange-600">LKR 0.00</span>
                </div>
            </div>

            <button onclick="submitOrder()" id="submit-btn" class="w-full py-3.5 sm:py-4 bg-slate-900 hover:bg-black text-white rounded-2xl font-black text-sm shadow transition active:scale-95 text-center">
                Confirm & Send Order to Kitchen
            </button>
        </div>
    </div>

    <div id="success-modal" class="fixed inset-0 bg-slate-900/80 backdrop-blur-md hidden items-center justify-center z-50 p-4">
        <div class="bg-white rounded-3xl p-6 sm:p-8 max-w-sm w-full text-center space-y-4 shadow-2xl">
            <div class="w-16 h-16 bg-green-100 text-green-600 rounded-full flex items-center justify-center mx-auto text-2xl shadow-inner">
                <i class="fa-solid fa-check"></i>
            </div>
            <h3 class="font-black text-xl text-slate-800">Order Placed Successfully!</h3>
            <p class="text-xs text-slate-500 leading-relaxed">Your order has been sent to the kitchen. Our staff will serve you shortly.</p>
            <div class="pt-2">
                <button onclick="resetCartAndClose()" class="w-full py-3 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-xl font-bold text-xs transition active:scale-95">Add More Items</button>
            </div>
        </div>
    </div>
</body>
</html>

    <script>
        let menuItems = [];
        let cart = [];
        let tableNumber = "1";

        window.onload = function() {
            const urlParams = new URLSearchParams(window.location.search);
            tableNumber = urlParams.get('table') || '1';
            document.getElementById('table-indicator').innerText = `Table Number: ${tableNumber}`;
            fetchMenuItems();
        };

        function fetchMenuItems() {
            fetch('/api/menu-items')
                .then(res => res.json())
                .then(data => {
                    menuItems = data;
                    renderMenu();
                })
                .catch(err => {
                    console.error('Error fetching menu:', err);
                    document.getElementById('menu-container').innerHTML = '<p class="text-center text-xs text-red-500">Failed to load menu items. Please refresh.</p>';
                });
        }

        function renderMenu() {
            if(menuItems.length === 0) {
                document.getElementById('menu-container').innerHTML = '<p class="text-center text-xs text-slate-400 py-6">No items available in the menu right now.</p>';
                return;
            }

            let html = '';
            menuItems.forEach(item => {
                html += `
                    <div class="bg-white p-3 rounded-2xl border border-slate-200 shadow-sm flex items-center gap-4">
                        <img src="${item.image}" alt="${item.name}" class="w-20 h-20 rounded-xl object-cover flex-shrink-0 bg-slate-100">
                        <div class="flex-1">
                            <span class="text-[10px] bg-orange-50 text-orange-600 px-2 py-0.5 rounded-full font-bold">${item.category}</span>
                            <h4 class="font-black text-slate-800 text-sm mt-1">${item.name}</h4>
                            <span class="font-mono font-bold text-orange-600 text-xs">LKR ${parseFloat(item.price).toFixed(2)}</span>
                        </div>
                        <button onclick="addToCart(${item.id})" class="w-10 h-10 bg-slate-900 hover:bg-black text-white rounded-xl font-bold flex items-center justify-center shadow transition active:scale-95">
                            <i class="fa-solid fa-plus text-xs"></i>
                        </button>
                    </div>
                `;
            });
            document.getElementById('menu-container').innerHTML = html;
        }

        function addToCart(itemId) {
            let item = menuItems.find(i => i.id === itemId);
            let existing = cart.find(i => i.id === itemId);
            if(existing) {
                existing.qty += 1;
            } else {
                cart.push({ ...item, qty: 1 });
            }
            updateCartUI();
        }

        function changeQty(itemId, delta) {
            let existing = cart.find(i => i.id === itemId);
            if(existing) {
                existing.qty += delta;
                if(existing.qty <= 0) {
                    cart = cart.filter(i => i.id !== itemId);
                }
            }
            updateCartUI();
        }

        function updateCartUI() {
            let totalCount = cart.reduce((sum, i) => sum + i.qty, 0);
            let totalPrice = cart.reduce((sum, i) => sum + (parseFloat(i.price) * i.qty), 0);

            document.getElementById('cart-count').innerText = totalCount;
            document.getElementById('cart-total').innerText = `LKR ${totalPrice.toFixed(2)}`;

            let cartBar = document.getElementById('cart-bar');
            if(totalCount > 0) {
                cartBar.classList.remove('hidden');
            } else {
                cartBar.classList.add('hidden');
            }
        }

        function openCheckoutModal() {
            let html = '';
            let subtotal = 0;

            cart.forEach(item => {
                let itemTotal = parseFloat(item.price) * item.qty;
                subtotal += itemTotal;
                html += `
                    <div class="py-3 flex justify-between items-center">
                        <div>
                            <h5 class="font-bold text-slate-800 text-xs">${item.name}</h5>
                            <span class="text-[10px] text-slate-400">LKR ${parseFloat(item.price).toFixed(2)} each</span>
                        </div>
                        <div class="flex items-center gap-3">
                            <div class="flex items-center bg-slate-100 rounded-xl overflow-hidden">
                                <button onclick="changeQty(${item.id}, -1); openCheckoutModal();" class="px-2.5 py-1 text-xs text-slate-600 hover:bg-slate-200">-</button>
                                <span class="px-2 text-xs font-bold">${item.qty}</span>
                                <button onclick="changeQty(${item.id}, 1); openCheckoutModal();" class="px-2.5 py-1 text-xs text-slate-600 hover:bg-slate-200">+</button>
                            </div>
                            <span class="font-mono font-bold text-xs text-slate-800 w-16 text-right">LKR ${itemTotal.toFixed(2)}</span>
                        </div>
                    </div>
                `;
            });

            document.getElementById('modal-cart-items').innerHTML = html;
            document.getElementById('summary-subtotal').innerText = `LKR ${subtotal.toFixed(2)}`;
            document.getElementById('summary-total').innerText = `LKR ${subtotal.toFixed(2)}`;

            let modal = document.getElementById('checkout-modal');
            modal.classList.remove('hidden');
            modal.classList.add('flex');
        }

        function closeCheckoutModal() {
            let modal = document.getElementById('checkout-modal');
            modal.classList.remove('flex');
            modal.classList.add('hidden');
        }

        function submitOrder() {
            let subtotal = cart.reduce((sum, i) => sum + (parseFloat(i.price) * i.qty), 0);
            let comment = document.getElementById('order-comment').value;

            let orderData = {
                table_number: tableNumber,
                waiter_name: "QR Customer",
                items: cart,
                comment: comment || "None",
                subtotal: subtotal,
                discount: 0.00,
                total: subtotal,
                is_kot_printed: false
            };

            let btn = document.getElementById('submit-btn');
            btn.innerText = "Submitting...";
            btn.disabled = true;

            fetch('/api/orders/hold', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(orderData)
            })
            .then(res => res.json())
            .then(data => {
                closeCheckoutModal();
                document.getElementById('success-modal').classList.remove('hidden');
                document.getElementById('success-modal').classList.add('flex');
                btn.innerText = "Confirm & Send Order to Kitchen";
                btn.disabled = false;
            })
            .catch(err => {
                console.error(err);
                alert('Error placing order. Please try again.');
                btn.innerText = "Confirm & Send Order to Kitchen";
                btn.disabled = false;
            });
        }

        function resetCartAndClose() {
            cart = [];
            updateCartUI();
            document.getElementById('success-modal').classList.remove('flex');
            document.getElementById('success-modal').classList.add('hidden');
            document.getElementById('order-comment').value = '';
        }
    </script>
</body>
</html>
"""

INVENTORY_HTML = """
<div class="grid grid-cols-12 gap-4 sm:gap-6 h-full font-sans">
    <!-- Inventory Form (Left) -->
    <div class="col-span-12 lg:col-span-4 bg-white p-5 sm:p-6 rounded-3xl border border-slate-200 shadow-sm flex flex-col justify-between">
        <div>
            <h3 id="form-title" class="font-black text-lg sm:text-xl text-slate-800 mb-4 flex items-center gap-2">
                <i class="fa-solid fa-boxes-stacked text-indigo-600"></i> Add / Edit Item
            </h3>
            <form id="inventory-form" action="/inventory" method="POST" enctype="multipart/form-data" class="space-y-3">
                <div>
                    <label class="text-xs font-bold uppercase text-slate-400 block mb-1">SKU</label>
                    <input type="text" id="inv-sku" name="sku" required placeholder="SKU001" class="w-full p-3 bg-slate-50 border rounded-xl font-mono font-bold text-slate-800 text-sm outline-none focus:border-indigo-500">
                </div>
                <div>
                    <label class="text-xs font-bold uppercase text-slate-400 block mb-1">Item Name</label>
                    <input type="text" id="inv-name" name="name" required placeholder="Chicken Kottu" class="w-full p-3 bg-slate-50 border rounded-xl font-bold text-slate-800 text-sm outline-none focus:border-indigo-500">
                </div>
                <div class="grid grid-cols-2 gap-2">
                    <div>
                        <label class="text-xs font-bold uppercase text-slate-400 block mb-1">Cost Price</label>
                        <input type="number" step="0.01" id="inv-cost" name="cost" required placeholder="0.00" class="w-full p-3 bg-slate-50 border rounded-xl font-mono font-bold text-slate-800 text-sm outline-none focus:border-indigo-500">
                    </div>
                    <div>
                        <label class="text-xs font-bold uppercase text-slate-400 block mb-1">Sale Price</label>
                        <input type="number" step="0.01" id="inv-price" name="price" required placeholder="0.00" class="w-full p-3 bg-slate-50 border rounded-xl font-mono font-bold text-slate-800 text-sm outline-none focus:border-indigo-500">
                    </div>
                </div>
                <div class="grid grid-cols-2 gap-2">
                    <div>
                        <label class="text-xs font-bold uppercase text-slate-400 block mb-1">Current Stock</label>
                        <input type="number" id="inv-stock" name="stock" value="0" placeholder="0" class="w-full p-3 bg-slate-100 border rounded-xl font-mono font-bold text-slate-500 text-sm outline-none" readonly>
                    </div>
                    <div>
                        <label class="text-xs font-bold uppercase text-indigo-600 block mb-1">+ Add Stock</label>
                        <input type="number" id="inv-add-stock" name="add_stock" value="0" placeholder="0" class="w-full p-3 bg-indigo-50/50 border border-indigo-200 rounded-xl font-mono font-bold text-indigo-600 text-sm outline-none focus:border-indigo-500">
                    </div>
                </div>
                <div>
                    <label class="text-xs font-bold uppercase text-slate-400 block mb-1">Item Image</label>
                    <input type="file" name="image" accept="image/*" class="w-full p-2.5 bg-slate-50 border rounded-xl text-xs text-slate-600 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-xs file:font-bold file:bg-indigo-50 file:text-indigo-700 hover:file:bg-indigo-100">
                </div>
                <div class="pt-2">
                    <button type="submit" class="w-full py-3.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl font-black text-sm shadow-md transition active:scale-95 flex items-center justify-center gap-2">
                        <i class="fa-solid fa-check text-xs"></i> Save Item
                    </button>
                </div>
            </form>
        </div>
    </div>

    <!-- Inventory Table (Right) -->
    <div class="col-span-12 lg:col-span-8 bg-white p-5 sm:p-6 rounded-3xl border border-slate-200 shadow-sm flex flex-col overflow-hidden">
        <h3 class="font-black text-lg sm:text-xl text-slate-800 mb-4">Inventory List</h3>
        <div class="overflow-y-auto flex-1 pr-1">
            <div class="overflow-x-auto">
                <table class="w-full text-left border-collapse min-w-[500px]">
                    <thead>
                        <tr class="border-b border-slate-200 text-xs font-bold uppercase text-slate-400">
                            <th class="pb-3">Image</th>
                            <th class="pb-3">SKU & Name</th>
                            <th class="pb-3">Cost / Price</th>
                            <th class="pb-3">Stock</th>
                            <th class="pb-3 text-right">Actions</th>
                        </tr>
                    </thead>
                    <tbody class="divide-y divide-slate-100 text-sm">
                        {% for item in inventory %}
                        <tr class="hover:bg-slate-50/50 transition">
                            <td class="py-3">
                                {% if item.image %}
                                <img src="{{ item.image }}" class="w-10 h-10 rounded-xl object-cover border border-slate-200">
                                {% else %}
                                <div class="w-10 h-10 rounded-xl bg-slate-100 flex items-center justify-center text-slate-400 text-xs font-bold">N/A</div>
                                {% endif %}
                            </td>
                            <td class="py-3">
                                <span class="font-bold text-slate-800 block">{{ item.name }}</span>
                                <span class="text-xs font-mono text-slate-400">{{ item.sku }}</span>
                            </td>
                            <td class="py-3 font-mono text-xs">
                                <span class="text-slate-400 block">C: {{ item.cost }}</span>
                                <span class="font-bold text-indigo-600">P: {{ item.price }}</span>
                            </td>
                            <td class="py-3 font-mono font-bold text-slate-700">{{ item.stock }}</td>
                            <td class="py-3 text-right space-x-1 whitespace-nowrap">
                                <button onclick="editItem('{{ item.sku }}', '{{ item.name }}', {{ item.cost }}, {{ item.price }}, {{ item.stock }})" class="p-2.5 bg-amber-50 text-amber-600 hover:bg-amber-100 rounded-xl transition shadow-sm"><i class="fa-solid fa-pen text-xs"></i></button>
                                <a href="/inventory/delete/{{ item.id }}" onclick="return confirm('Are you sure you want to delete this item?')" class="p-2.5 bg-red-50 text-red-600 hover:bg-red-100 rounded-xl inline-block transition shadow-sm"><i class="fa-solid fa-trash text-xs"></i></a>
                            </td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>
    </div>
</div>


<script>
    function editItem(sku, name, cost, price, stock) {
        document.getElementById('inv-sku').value = sku;
        document.getElementById('inv-sku').readOnly = true; // SKU cannot be changed during update
        document.getElementById('inv-name').value = name;
        document.getElementById('inv-cost').value = cost;
        document.getElementById('inv-price').value = price;
        document.getElementById('inv-stock').value = stock;
        document.getElementById('inv-add-stock').value = 0;
        document.getElementById('form-title').innerText = 'Edit Item (' + sku + ')';
    }
</script>
"""



REPORTS_HTML = """
<div class="flex flex-col h-full font-sans gap-4 p-2 sm:p-4 bg-slate-100 overflow-hidden">
    
    <!-- Top Header & Date Range Filter Bar -->
    <div class="bg-white p-4 sm:p-5 rounded-3xl border border-slate-200 shadow-sm flex flex-col lg:flex-row justify-between items-start lg:items-center gap-4">
        <div>
            <h2 class="font-black text-xl sm:text-2xl text-slate-800">Restaurant Reports & Analytics</h2>
            <p class="text-xs text-slate-400 font-medium">Generate financial Z-reports, stock status, and item sales analytics.</p>
        </div>
        
        <div class="flex flex-col sm:flex-row items-stretch sm:items-center gap-3 w-full lg:w-auto">
            <div class="flex flex-wrap items-center gap-2 bg-slate-50 border border-slate-200 px-3 py-2 rounded-2xl w-full sm:w-auto">
                <span class="text-xs font-bold text-slate-500">From:</span>
                <input type="date" id="report-start-date" class="bg-transparent text-xs font-bold text-slate-700 outline-none flex-1 sm:flex-none">
                <span class="text-xs font-bold text-slate-500 ml-2">To:</span>
                <input type="date" id="report-end-date" class="bg-transparent text-xs font-bold text-slate-700 outline-none flex-1 sm:flex-none">
            </div>
            <div class="flex items-center gap-2">
                <button onclick="generateReports()" class="flex-1 sm:flex-none py-2.5 px-4 sm:px-5 bg-orange-500 hover:bg-orange-600 text-white rounded-2xl font-black text-xs shadow transition active:scale-95 flex items-center justify-center gap-2">
                    <i class="fa-solid fa-filter"></i> Generate
                </button>
                <button onclick="printReport()" class="flex-1 sm:flex-none py-2.5 px-4 bg-slate-900 hover:bg-black text-white rounded-2xl font-black text-xs shadow transition active:scale-95 flex items-center justify-center gap-2">
                    <i class="fa-solid fa-print"></i> Print
                </button>
            </div>
        </div>
    </div>

    <!-- Reports Content Grid Area -->
    <div class="grid grid-cols-12 gap-4 flex-1 overflow-y-auto pr-1">
        
        <!-- Left Column: Z-Report & Summary Cards (Span 12 on mobile, 7 on desktop) -->
        <div class="col-span-12 lg:col-span-7 flex flex-col gap-4">
            
            <!-- Quick Metrics Overview -->
            <div class="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div class="bg-white p-4 rounded-3xl border border-slate-200 shadow-sm flex flex-col justify-between">
                    <span class="text-xs font-bold text-slate-400 uppercase">Total Net Sales</span>
                    <h3 id="rep-total-sales" class="font-mono font-black text-lg sm:text-xl text-slate-900 mt-2">LKR 0.00</h3>
                    <span class="text-[10px] font-bold text-emerald-600 mt-1"><i class="fa-solid fa-arrow-up"></i> Verified Revenue</span>
                </div>
                <div class="bg-white p-4 rounded-3xl border border-slate-200 shadow-sm flex flex-col justify-between">
                    <span class="text-xs font-bold text-slate-400 uppercase">Total Orders</span>
                    <h3 id="rep-total-orders" class="font-mono font-black text-lg sm:text-xl text-orange-600 mt-2">0</h3>
                    <span class="text-[10px] font-bold text-slate-500 mt-1">Completed Bills</span>
                </div>
                <div class="bg-white p-4 rounded-3xl border border-slate-200 shadow-sm flex flex-col justify-between">
                    <span class="text-xs font-bold text-slate-400 uppercase">Discounts Given</span>
                    <h3 id="rep-total-discount" class="font-mono font-black text-lg sm:text-xl text-rose-600 mt-2">LKR 0.00</h3>
                    <span class="text-[10px] font-bold text-rose-500 mt-1">Total Adjustments</span>
                </div>
            </div>

            <!-- Z-Report Detailed Breakdown Box -->
            <div class="bg-white p-4 sm:p-5 rounded-3xl border border-slate-200 shadow-sm flex flex-col gap-3 flex-1">
                <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center border-b pb-3 gap-1">
                    <h3 class="font-black text-sm sm:text-base text-slate-800"><i class="fa-solid fa-file-invoice-dollar text-orange-500 mr-2"></i> Z-Report (Shift & Cash Breakdown)</h3>
                    <span class="text-xs font-bold text-slate-400">Official Register Summary</span>
                </div>
                
                <div class="space-y-2 text-xs font-bold text-slate-600">
                    <div class="flex justify-between p-2.5 bg-slate-50 rounded-xl">
                        <span>Cash Payments Collected:</span>
                        <span id="rep-cash-total" class="font-mono font-black text-slate-900">LKR 0.00</span>
                    </div>
                    <div class="flex justify-between p-2.5 bg-slate-50 rounded-xl">
                        <span>Card Payments Collected:</span>
                        <span id="rep-card-total" class="font-mono font-black text-slate-900">LKR 0.00</span>
                    </div>
                    <div class="flex justify-between p-2.5 bg-slate-50 rounded-xl">
                        <span>Online / Digital Payments:</span>
                        <span id="rep-online-total" class="font-mono font-black text-slate-900">LKR 0.00</span>
                    </div>
                    <div class="flex justify-between p-2.5 bg-emerald-50/60 border border-emerald-200 rounded-xl text-emerald-900">
                        <span>UberEats Revenue:</span>
                        <span id="rep-ubereats-total" class="font-mono font-black text-slate-900">LKR 0.00</span>
                    </div>
                    <div class="flex justify-between p-2.5 bg-amber-50/60 border border-amber-200 rounded-xl text-amber-900">
                        <span>PickMe Food Revenue:</span>
                        <span id="rep-pickme-total" class="font-mono font-black text-slate-900">LKR 0.00</span>
                    </div>
                    <div class="flex justify-between p-2.5 bg-orange-50/60 border border-orange-200 rounded-xl text-orange-900">
                        <span>Gross Drawer Total:</span>
                        <span id="rep-drawer-total" class="font-mono font-black text-sm sm:text-base">LKR 0.00</span>
                    </div>
                </div>
            </div>
        </div>

        <!-- Right Column: Stock & Item Sales Summary (Span 12 on mobile, 5 on desktop) -->
        <div class="col-span-12 lg:col-span-5 flex flex-col gap-4">
            
            <!-- Item-wise Sales Analytics -->
            <div class="bg-white p-4 sm:p-5 rounded-3xl border border-slate-200 shadow-sm flex flex-col flex-1">
                <div class="flex justify-between items-center mb-3">
                    <h3 class="font-black text-sm sm:text-base text-slate-800"><i class="fa-solid fa-chart-pie text-indigo-500 mr-2"></i> Top Selling Items</h3>
                    <span class="text-xs font-bold text-slate-400">Quantity Sold</span>
                </div>
                <div id="rep-items-list" class="space-y-2 overflow-y-auto max-h-[220px] pr-1">
                    <p class="text-center py-6 text-slate-400 font-semibold text-xs">No sales recorded for this period.</p>
                </div>
            </div>

            <!-- Stock / Inventory Status Summary -->
            <div class="bg-white p-4 sm:p-5 rounded-3xl border border-slate-200 shadow-sm flex flex-col">
                <div class="flex justify-between items-center mb-3">
                    <h3 class="font-black text-sm sm:text-base text-slate-800"><i class="fa-solid fa-boxes-stacked text-amber-500 mr-2"></i> Inventory Status</h3>
                    <button onclick="loadStockReport()" class="text-xs font-bold text-orange-600 hover:underline">Refresh Stock</button>
                </div>
                <div id="rep-stock-list" class="space-y-2 overflow-y-auto max-h-[160px] pr-1">
                    <!-- Stock items dynamically loaded -->
                </div>
            </div>

        </div>
    </div>
</div>

<!-- Print-only Report Area -->
<div id="printable-report-area" class="hidden p-4 font-mono text-xs text-black bg-white"></div>

<style>
    @media print {
        body * { visibility: hidden; }
        #printable-report-area, #printable-report-area * { visibility: visible; }
        #printable-report-area { position: absolute; left: 0; top: 0; width: 100%; display: block !important; }
    }
</style>


<script>
    document.addEventListener("DOMContentLoaded", function() {
        let today = new Date().toISOString().split('T')[0];
        if(document.getElementById('report-start-date')) document.getElementById('report-start-date').value = today;
        if(document.getElementById('report-end-date')) document.getElementById('report-end-date').value = today;
        generateReports();
    });

    function generateReports() {
        let startDate = document.getElementById('report-start-date')?.value || '';
        let endDate = document.getElementById('report-end-date')?.value || '';

        fetch(`/api/reports/sales?start=${startDate}&end=${endDate}`)
        .then(res => res.json())
        .then(data => {
            renderReportData(data);
        }).catch(err => {
            console.error("Error loading report data:", err);
        });

        loadStockReport();
    }

    function renderReportData(data) {
        if(document.getElementById('rep-total-sales')) document.getElementById('rep-total-sales').innerText = 'LKR ' + (data.total_sales || 0).toFixed(2);
        if(document.getElementById('rep-total-orders')) document.getElementById('rep-total-orders').innerText = data.total_orders || 0;
        if(document.getElementById('rep-total-discount')) document.getElementById('rep-total-discount').innerText = 'LKR ' + (data.total_discount || 0).toFixed(2);
        
        if(document.getElementById('rep-cash-total')) document.getElementById('rep-cash-total').innerText = 'LKR ' + (data.cash_total || 0).toFixed(2);
        if(document.getElementById('rep-card-total')) document.getElementById('rep-card-total').innerText = 'LKR ' + (data.card_total || 0).toFixed(2);
        if(document.getElementById('rep-online-total')) document.getElementById('rep-online-total').innerText = 'LKR ' + (data.online_total || 0).toFixed(2);
        if(document.getElementById('rep-ubereats-total')) document.getElementById('rep-ubereats-total').innerText = 'LKR ' + (data.ubereats_total || 0).toFixed(2);
        if(document.getElementById('rep-pickme-total')) document.getElementById('rep-pickme-total').innerText = 'LKR ' + (data.pickme_total || 0).toFixed(2);
        if(document.getElementById('rep-drawer-total')) document.getElementById('rep-drawer-total').innerText = 'LKR ' + (data.total_sales || 0).toFixed(2);

        let itemHtml = '';
        if(data.items && data.items.length > 0) {
            data.items.forEach(i => {
                itemHtml += `
                    <div class="flex justify-between items-center bg-slate-50 p-2.5 rounded-xl border border-slate-100">
                        <span class="font-bold text-xs text-slate-800">${i.name}</span>
                        <div class="flex items-center gap-3">
                            <span class="text-xs font-bold text-slate-500">Qty: ${i.qty}</span>
                            <span class="font-mono font-bold text-xs text-orange-600">LKR ${i.total.toFixed(2)}</span>
                        </div>
                    </div>
                `;
            });
        } else {
            itemHtml = '<p class="text-center py-6 text-slate-400 font-semibold text-xs">No items sold in this range.</p>';
        }
        if(document.getElementById('rep-items-list')) document.getElementById('rep-items-list').innerHTML = itemHtml;
    }

    function loadStockReport() {
        fetch('/api/inventory').then(res => res.json()).then(inventory => {
            let stockHtml = '';
            if(inventory && inventory.length > 0) {
                inventory.forEach(inv => {
                    let stockBadge = inv.stock <= 5 ? 
                        '<span class="bg-rose-100 text-rose-700 px-2 py-0.5 rounded text-[10px] font-bold">Low Stock</span>' : 
                        '<span class="bg-emerald-100 text-emerald-700 px-2 py-0.5 rounded text-[10px] font-bold">In Stock</span>';

                    stockHtml += `
                        <div class="flex justify-between items-center bg-slate-50 p-2 rounded-xl border border-slate-100">
                            <div>
                                <h5 class="font-bold text-xs text-slate-800">${inv.name}</h5>
                                <span class="text-[10px] text-slate-400">Price: LKR ${inv.price}</span>
                            </div>
                            <div class="flex items-center gap-2">
                                <span class="font-mono font-bold text-xs text-slate-700">Qty: ${inv.stock !== undefined ? inv.stock : 'N/A'}</span>
                                ${stockBadge}
                            </div>
                        </div>
                    `;
                });
            } else {
                stockHtml = '<p class="text-center py-4 text-slate-400 text-xs">No inventory items found.</p>';
            }
            if(document.getElementById('rep-stock-list')) document.getElementById('rep-stock-list').innerHTML = stockHtml;
        }).catch(err => {
            console.log("Could not load inventory stock data");
        });
    }

    function printReport() {
        let start = document.getElementById('report-start-date')?.value || '';
        let end = document.getElementById('report-end-date')?.value || '';
        let totalSales = document.getElementById('rep-total-sales')?.innerText || 'LKR 0.00';
        let totalOrders = document.getElementById('rep-total-orders')?.innerText || '0';
        let totalDiscount = document.getElementById('rep-total-discount')?.innerText || 'LKR 0.00';
        let cashTotal = document.getElementById('rep-cash-total')?.innerText || 'LKR 0.00';
        let cardTotal = document.getElementById('rep-card-total')?.innerText || 'LKR 0.00';
        let onlineTotal = document.getElementById('rep-online-total')?.innerText || 'LKR 0.00';
        let ubereatsTotal = document.getElementById('rep-ubereats-total')?.innerText || 'LKR 0.00';
        let pickmeTotal = document.getElementById('rep-pickme-total')?.innerText || 'LKR 0.00';

        let printableArea = document.getElementById('printable-report-area');
        if(printableArea) {
            printableArea.innerHTML = `
                <div style="text-align:center; font-weight:bold; font-size:16px; margin-bottom:5px;">SYNTAXCORE RESTAURANT - SALES Z-REPORT</div>
                <div style="text-align:center; font-size:11px; margin-bottom:10px;">Date Range: ${start} to ${end}</div>
                <div style="border-top:1px dashed black; margin:8px 0;"></div>
                <div style="font-size:12px; margin-bottom:4px;"><b>Total Net Sales:</b> ${totalSales}</div>
                <div style="font-size:12px; margin-bottom:4px;"><b>Total Orders Completed:</b> ${totalOrders}</div>
                <div style="font-size:12px; margin-bottom:8px;"><b>Total Discounts:</b> ${totalDiscount}</div>
                <div style="border-top:1px dashed black; margin:8px 0;"></div>
                <div style="font-size:12px; margin-bottom:4px;"><b>Cash Total:</b> ${cashTotal}</div>
                <div style="font-size:12px; margin-bottom:4px;"><b>Card Total:</b> ${cardTotal}</div>
                <div style="font-size:12px; margin-bottom:4px;"><b>Online Total:</b> ${onlineTotal}</div>
                <div style="font-size:12px; margin-bottom:4px;"><b>UberEats Total:</b> ${ubereatsTotal}</div>
                <div style="font-size:12px; margin-bottom:8px;"><b>PickMe Total:</b> ${pickmeTotal}</div>
                <div style="border-top:1px dashed black; margin:8px 0;"></div>
                <div style="font-weight:bold; font-size:13px; margin-bottom:6px;">Top Selling Items Summary:</div>
                <div>${document.getElementById('rep-items-list')?.innerHTML || ''}</div>
                <div style="border-top:1px dashed black; margin:10px 0;"></div>
                <div style="text-align:center; font-size:10px;">Report Generated On: ${new Date().toLocaleString()}</div>
            `;
        }
        window.print();
    }
</script>
"""
# --- FLASK ROUTES ---


# --- Authentication Routes ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = users_collection.find_one({'username': username})
        
        if user and check_password_hash(user['password'], password):
            session['username'] = user['username']
            session['role'] = user['role']
            flash('Login successful!', 'success')
            
            # Role eka anuwa redirect karanawa
            if user['role'] == 'Admin':
                return redirect(url_for('dashboard_view'))
            else:
                return redirect(url_for('pos_panel'))
        else:
            flash('Invalid username or password!', 'error')
            
    return render_template_string(LOGIN_HTML, title='Login - 888 Restaurant')

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully!', 'success')
    return redirect(url_for('login'))


# --- Root Route (App eka open karapu gaman login page ekata yanna) ---
@app.route('/')
def index():
    if 'username' not in session:
        return redirect(url_for('login'))
    
    # Login wela nam role eka balala hari thanata yawanna
    user_role = session.get('role', '')
    if user_role.lower() == 'admin':
        return redirect(url_for('dashboard_view'))
    else:
        return redirect(url_for('pos_panel'))


# --- User Management Routes ---
@app.route('/users', methods=['GET', 'POST'])
@role_required(['Admin'])
def users_management():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        role = request.form.get('role', 'Cashier')
        
        # Check if user already exists
        if users_collection.find_one({'username': username}):
            flash('Username already exists!', 'error')
        else:
            hashed_password = generate_password_hash(password)
            users_collection.insert_one({
                'username': username,
                'password': hashed_password,
                'role': role
            })
            flash('User created successfully!', 'success')
        return redirect(url_for('users_management'))
    
    users = list(users_collection.find())
    return render_template_custom(USERS_HTML, title='User Management', users=users)


@app.route('/users/delete/<user_id>')
@role_required(['Admin'])
def delete_user(user_id):
    try:
        users_collection.delete_one({'_id': ObjectId(user_id)})
        flash('User deleted successfully!', 'success')
    except Exception as e:
        flash('Error deleting user!', 'error')
    return redirect(url_for('users_management'))


# --- Settings Collection helper for Service Charge ---
def get_service_charge_settings():
    setting = db.settings.find_one({'type': 'service_charge'})
    if not setting:
        return {'enabled': False, 'percentage': 10.0, 'label': 'Service Charge'}
    
    # ObjectId eka JSON serializable nathi nisa eka ain karanawa
    setting.pop('_id', None)
    return setting


# --- Admin Dashboard Route (/dashboard) ---
@app.route('/dashboard')
@role_required(['Admin'])
def dashboard_view():
    # 1. Login wela nadda balanna
    if 'username' not in session:
        flash('Please login first!', 'error')
        return redirect(url_for('login'))
    
    # 2. Role eka Admin da kiyala check karanna (Case-insensitive check)
    user_role = session.get('role', '')
    print(f"DEBUG ROLE: {user_role}")  # Render logs wala balaganna puluwan
    
    if user_role.lower() != 'admin':
        flash('Access Denied: Admin only area!', 'error')
        return redirect(url_for('pos_panel'))  # POS ekata yawanna
    
    # --- Original logic ---
    orders_list = list(orders_collection.find())
    total_revenue = sum(row.get('total', 0) for row in orders_list)
    total_orders = orders_collection.count_documents({})
    total_inventory = inventory_collection.count_documents({})
    tables = list(tables_collection.find())
    total_tables = len(tables)
    occupied_count = sum(1 for t in tables if t.get('status') == 'Occupied')

    # Pending orders for dashboard
    orders = list(orders_collection.find({'status': 'Pending'}).sort('id', -1))

    return render_template_custom(
        DASHBOARD_HTML,
        title='Dashboard',
        total_revenue=total_revenue,
        total_orders=total_orders,
        total_inventory=total_inventory,
        total_tables=total_tables,
        occupied_count=occupied_count,
        tables=tables,
        orders=orders,
    )
    

@app.route('/pos')
@role_required(['Admin', 'Cashier', 'Waiter'])
def pos_panel():
    inventory = list(inventory_collection.find())
    tables = list(tables_collection.find())
    waiters = list(waiters_collection.find())
    service_charge_setting = get_service_charge_settings()
    
    return render_template_custom(
        POS_HTML, 
        title='POS Panel', 
        inventory=inventory, 
        tables=tables, 
        waiters=waiters,
        service_charge_setting=service_charge_setting
    )


@app.route('/kitchen')
@role_required(['Admin', 'Cashier', 'Waiter'])
def kitchen_view():
    return render_template_custom(KITCHEN_HTML, title='Kitchen KOT')


@app.route('/qr/<table_id>')
def qr_order_page(table_id):
    inventory = list(inventory_collection.find())
    service_charge_setting = get_service_charge_settings()
    return render_template_custom(
        QR_HTML, title=f'Table {table_id} QR', inventory=inventory, table_id=table_id, service_charge_setting=service_charge_setting
    )


@app.route('/menu')
def qr_menu():
    return render_template_string(QR_MENU_HTML)


# --- Settings Management for Service Charge ---
@app.route('/settings/service-charge', methods=['GET', 'POST'])
@role_required(['Admin'])
def service_charge_settings():
    if request.method == 'POST':
        enabled = True if request.form.get('enabled') == 'on' else False
        try:
            percentage = float(request.form.get('percentage', 10.0))
        except:
            percentage = 10.0
            
        db.settings.update_one(
            {'type': 'service_charge'},
            {'$set': {'enabled': enabled, 'percentage': percentage}},
            upsert=True
        )
        return redirect(url_for('service_charge_settings'))
    
    sc_setting = get_service_charge_settings()
    return render_template_custom(
        SETTINGS_HTML, 
        title='Service Charge Settings', 
        settings=sc_setting
    )


@app.route('/api/settings/service-charge', methods=['GET'])
def api_get_service_charge():
    return jsonify(get_service_charge_settings())


# --- Table Management ---
@app.route('/tables', methods=['GET', 'POST'])
@role_required(['Admin'])
def tables_management():
    if request.method == 'POST':
        t_num = request.form['table_number']
        try:
            if not tables_collection.find_one({'table_number': t_num}):
                new_id = get_next_id('tables')
                tables_collection.insert_one({
                    'id': new_id,
                    'table_number': t_num,
                    'status': 'Available'
                })
        except Exception as e:
            print('Table add error:', e)
        return redirect(url_for('tables_management'))
    
    tables = list(tables_collection.find())
    return render_template_custom(
        TABLES_HTML, title='Table Management', tables=tables
    )


@app.route('/tables/clear/<table_number>')
@role_required(['Admin', 'Cashier'])
def clear_table(table_number):
    tables_collection.update_many(
        {'table_number': table_number},
        {'$set': {'status': 'Available'}}
    )
    return redirect(url_for('dashboard_view'))


@app.route('/tables/delete/<int:id>')
@role_required(['Admin'])
def delete_table(id):
    tables_collection.delete_one({'id': int(id)})
    return redirect(url_for('tables_management'))


# --- Waiters Management ---
@app.route('/waiters', methods=['GET', 'POST'])
@role_required(['Admin'])
def waiters_management():
    if request.method == 'POST':
        name = request.form['name']
        phone = request.form['phone']
        new_id = get_next_id('waiters')
        waiters_collection.insert_one({
            'id': new_id,
            'name': name,
            'phone': phone
        })
        return redirect(url_for('waiters_management'))
    
    waiters = list(waiters_collection.find())
    return render_template_custom(
        WAITERS_HTML, title='Waiters', waiters=waiters
    )


@app.route('/waiters/delete/<int:id>')
@role_required(['Admin'])
def delete_waiter(id):
    waiters_collection.delete_one({'id': int(id)})
    return redirect(url_for('waiters_management'))


# --- Inventory Management ---
@app.route('/inventory', methods=['GET', 'POST'])
@role_required(['Admin'])
def inventory_management():
    if request.method == 'POST':
        sku = request.form['sku']
        name = request.form['name']
        category = request.form.get('category', 'General')
        cost = float(request.form.get('cost', 0))
        price = float(request.form.get('price', 0))
        add_stock = int(
            request.form.get('add_stock', 0) or request.form.get('stock', 0)
        )

        image_filename = ''
        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename != '':
                filename = secure_filename(file.filename)
                image_path = os.path.join(UPLOAD_FOLDER, filename)
                file.save(image_path)
                image_filename = f'/static/uploads/{filename}'

        existing = inventory_collection.find_one({'sku': sku})

        if existing:
            new_stock = existing.get('stock', 0) + add_stock
            final_image = image_filename if image_filename else existing.get('image', '')
            inventory_collection.update_one(
                {'sku': sku},
                {'$set': {
                    'name': name,
                    'category': category,
                    'cost': cost,
                    'price': price,
                    'stock': new_stock,
                    'image': final_image
                }}
            )
        else:
            new_id = get_next_id('inventory')
            inventory_collection.insert_one({
                'id': new_id,
                'sku': sku,
                'name': name,
                'category': category,
                'cost': cost,
                'price': price,
                'stock': add_stock,
                'alert_limit': 5,
                'image': image_filename
            })

        return redirect(url_for('inventory_management'))

    inventory = list(inventory_collection.find())
    return render_template_custom(
        INVENTORY_HTML, title='Inventory', inventory=inventory
    )


@app.route('/inventory/delete/<int:id>')
@role_required(['Admin'])
def delete_inventory(id):
    inventory_collection.delete_one({'id': int(id)})
    return redirect(url_for('inventory_management'))


# --- Reports & Analytics ---
@app.route('/reports')
@role_required(['Admin'])
def sales_report():
    orders = list(orders_collection.find({'status': 'Completed'}))
    sales_map = {}
    for o in orders:
        try:
            items_data = o.get('items', [])
            items = json.loads(items_data) if isinstance(items_data, str) else items_data
            for i in items:
                name = i['name']
                qty = int(i.get('qty', i.get('quantity', 1)))
                rev = float(i['price']) * qty
                if name not in sales_map:
                    sales_map[name] = {'qty': 0, 'revenue': 0.0}
                sales_map[name]['qty'] += qty
                sales_map[name]['revenue'] += rev
        except:
            pass
    report = [
        {'name': k, 'qty': v['qty'], 'revenue': v['revenue']}
        for k, v in sales_map.items()
    ]
    return render_template_custom(
        REPORTS_HTML, title='Sales Reports', report=report
    )


@app.route('/api/reports/sales', methods=['GET'])
def api_sales_report():
    try:
        orders = list(orders_collection.find({'status': 'Completed'}))

        total_sales = 0
        total_orders = len(orders)
        total_discount = 0
        total_service_charge = 0
        cash_total = 0
        card_total = 0
        visa_total = 0
        online_total = 0
        ubereats_total = 0
        pickme_total = 0

        sales_map = {}
        for o in orders:
            tot = o.get('total', 0) if o.get('total') else 0
            disc = o.get('discount', 0) if o.get('discount') else 0
            sc = o.get('service_charge', 0) if o.get('service_charge') else 0
            pm = o.get('payment_method', 'Cash')

            total_sales += tot
            total_discount += disc
            total_service_charge += sc

            if pm == 'Cash':
                cash_total += tot
            elif pm == 'Card':
                card_total += tot
            elif pm == 'Visa':
                visa_total += tot
            elif pm == 'Online':
                online_total += tot
            elif pm == 'UberEats':
                ubereats_total += tot
            elif pm == 'PickMe':
                pickme_total += tot
            else:
                online_total += tot

            try:
                raw_items = o.get('items', [])
                items = (
                    json.loads(raw_items)
                    if isinstance(raw_items, str)
                    else raw_items
                )
                for i in items:
                    name = i['name']
                    qty = int(i.get('qty', i.get('quantity', 1)))
                    rev = float(i['price']) * qty
                    if name not in sales_map:
                        sales_map[name] = {'qty': 0, 'revenue': 0.0}
                    sales_map[name]['qty'] += qty
                    sales_map[name]['revenue'] += rev
            except:
                pass

        items_report = [
            {'name': k, 'qty': v['qty'], 'total': v['revenue']}
            for k, v in sales_map.items()
        ]

        return (
            jsonify({
                'total_sales': total_sales,
                'total_orders': total_orders,
                'total_discount': total_discount,
                'total_service_charge': total_service_charge,
                'cash_total': cash_total,
                'card_total': card_total,
                'visa_total': visa_total,
                'online_total': online_total,
                'ubereats_total': ubereats_total,
                'pickme_total': pickme_total,
                'items': items_report,
            }),
            200,
        )
    except Exception as e:
        print('Error generating sales report:', e)
        return (
            jsonify({
                'total_sales': 0,
                'total_orders': 0,
                'total_discount': 0,
                'total_service_charge': 0,
                'cash_total': 0,
                'card_total': 0,
                'visa_total': 0,
                'online_total': 0,
                'ubereats_total': 0,
                'pickme_total': 0,
                'items': [],
            }),
            200,
        )


# --- Order Processing APIs ---
@app.route('/api/order', methods=['POST'])
def api_create_order():
    data = request.json
    order_id = data.get('order_id')
    table_number = data.get('table_number')
    waiter_name = data.get('waiter_name', 'Cashier')
    items = data.get('items', [])
    comment = data.get('comment', '')
    subtotal = data.get('subtotal', 0)
    discount = data.get('discount', 0)
    service_charge = data.get('service_charge', 0)
    total = data.get('total', 0)
    payment_method = data.get('payment_method', 'Cash')

    items_json = json.dumps(items)
    new_id = get_next_id('orders')

    orders_collection.insert_one({
        'id': new_id,
        'table_number': table_number,
        'waiter_name': waiter_name,
        'items': items_json,
        'comment': comment,
        'subtotal': subtotal,
        'discount': discount,
        'service_charge': service_charge,
        'total': total,
        'payment_method': payment_method,
        'status': 'Completed'
    })

    tables_collection.update_many(
        {'table_number': table_number},
        {'$set': {'status': 'Available'}}
    )

    if order_id:
        held_orders_collection.delete_one({'id': int(order_id)})

    socketio.emit(
        'new_kot',
        {
            'table_number': table_number,
            'waiter_name': waiter_name,
            'items': items_json,
            'comment': comment,
        },
    )
    socketio.emit('refresh_orders', {'status': 'updated'})
    return jsonify({'status': 'success'})


@app.route('/api/order/hold', methods=['POST'])
def hold_order():
    data = request.json
    order_id = data.get('order_id')
    table_number = data.get('table_number')
    waiter_name = data.get('waiter_name', 'Waiter')
    items = data.get('items', [])
    comment = data.get('comment', '')
    subtotal = data.get('subtotal', 0)
    discount = data.get('discount', 0)
    service_charge = data.get('service_charge', 0)
    total = data.get('total', 0)

    items_json = json.dumps(items)

    if order_id:
        held_orders_collection.update_one(
            {'id': int(order_id)},
            {'$set': {
                'table_number': table_number,
                'waiter_name': waiter_name,
                'items': items_json,
                'comment': comment,
                'subtotal': subtotal,
                'discount': discount,
                'service_charge': service_charge,
                'total': total
            }}
        )
    else:
        new_id = get_next_id('held_orders')
        held_orders_collection.insert_one({
            'id': new_id,
            'table_number': table_number,
            'waiter_name': waiter_name,
            'items': items_json,
            'comment': comment,
            'subtotal': subtotal,
            'discount': discount,
            'service_charge': service_charge,
            'total': total
        })

    tables_collection.update_many(
        {'table_number': table_number},
        {'$set': {'status': 'Occupied'}}
    )

    socketio.emit('refresh_orders', {'status': 'updated'})
    return jsonify({'status': 'success'})


@app.route('/api/orders/held', methods=['GET'])
def get_held_orders():
    orders = list(held_orders_collection.find())
    result = []
    for o in orders:
        items_data = o.get('items', [])
        try:
            parsed_items = json.loads(items_data) if isinstance(items_data, str) else items_data
        except:
            parsed_items = items_data

        result.append({
            'id': o['id'],
            'table_number': o['table_number'],
            'waiter_name': o['waiter_name'],
            'items': parsed_items,
            'comment': o.get('comment', ''),
            'subtotal': o.get('subtotal', 0),
            'discount': o.get('discount', 0),
            'service_charge': o.get('service_charge', 0),
            'total': o.get('total', 0),
        })
    return jsonify(result)


@app.route('/api/orders/completed', methods=['GET'])
def get_completed_orders():
    try:
        completed_orders = list(orders_collection.find({'status': 'Completed'}).sort('id', -1))

        results = []
        for o in completed_orders:
            items_data = o.get('items', [])
            try:
                items_data = (
                    json.loads(items_data) if isinstance(items_data, str) else items_data
                )
            except:
                pass

            results.append({
                'id': o['id'],
                'table_number': o.get('table_number'),
                'items': items_data,
                'subtotal': o.get('subtotal', 0),
                'discount': o.get('discount', 0),
                'service_charge': o.get('service_charge', 0),
                'total': o.get('total', 0),
                'payment_method': (
                    o['payment_method'] if 'payment_method' in o else 'Cash'
                ),
                'created_at': 'Today',
            })
        return jsonify(results), 200
    except Exception as e:
        print('Error fetching completed orders:', e)
        return jsonify([]), 200
    
    
@app.route('/api/order/<order_id>', methods=['DELETE'])
def delete_running_order(order_id):
    # Fixed session role check (Capital 'Admin' and correct key 'role')
    if session.get('role') != 'Admin':
        return jsonify({'success': False, 'message': 'Access Denied! Only Admin can delete active orders.'}), 403
    
    try:
        held_orders_collection.delete_one({'id': int(order_id)})
        socketio.emit('refresh_orders', {'status': 'updated'})
        return jsonify({'success': True, 'message': 'Order deleted successfully'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/qr/order', methods=['POST'])
def api_qr_customer_order():
    data = request.json
    table_number = data.get('table_number')
    items = data.get('items', [])
    comment = data.get('comment', 'Customer QR Order')
    subtotal = data.get('subtotal', 0)
    discount = 0
    service_charge = data.get('service_charge', 0)
    total = data.get('total', 0)

    items_json = json.dumps(items)
    new_id = get_next_id('held_orders')

    held_orders_collection.insert_one({
        'id': new_id,
        'table_number': table_number,
        'waiter_name': 'QR Customer',
        'items': items_json,
        'comment': comment,
        'subtotal': subtotal,
        'discount': discount,
        'service_charge': service_charge,
        'total': total
    })

    tables_collection.update_many(
        {'table_number': table_number},
        {'$set': {'status': 'Occupied'}}
    )

    socketio.emit('refresh_orders', {'status': 'new_qr_order'})
    return jsonify({'status': 'success', 'message': 'Order placed successfully!'})


@app.route('/api/menu-items', methods=['GET'])
def get_menu_items():
    items = list(inventory_collection.find())

    result = []
    for item in items:
        img = (
            item.get('image')
            if item.get('image')
            else 'https://images.unsplash.com/photo-1546069901-ba9599a7e63c?w=500&auto=format&fit=crop&q=60'
        )

        result.append({
            'id': item['id'],
            'name': item['name'],
            'price': item['price'],
            'category': (
                item['category']
                if 'category' in item and item['category']
                else 'General'
            ),
            'image': img,
        })
    return jsonify(result)

@app.route('/admin/running-orders')
def admin_running_orders():
    # Fixed role check to match session['role'] == 'Admin'
    if session.get('role') != 'Admin':
        return "Access Denied! Admins only.", 403
    return render_template_custom(ADMIN_ORDERS_HTML, title='Active Orders (Admin)')


@app.route('/orders/complete/<int:order_id>')
def complete_order(order_id):
    order = orders_collection.find_one({'id': int(order_id)})

    if order:
        table_number = order.get('table_number')
        orders_collection.update_one(
            {'id': int(order_id)}, {'$set': {'status': 'Completed'}}
        )
        try:
            tables_collection.update_many(
                {'$or': [{'id': table_number}, {'table_number': table_number}]},
                {'$set': {'status': 'Available'}}
            )
        except Exception as e:
            print('Table status reset error:', e)

    return redirect(url_for('dashboard_view'))


if __name__ == '__main__':
    socketio.run(app, debug=True, port=5000)