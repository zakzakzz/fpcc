from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask_sqlalchemy import SQLAlchemy

import os
import requests
from datetime import datetime
import pytz

# Config Flask App
app = Flask(__name__)
app.secret_key = "secret_key"
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{os.path.join(BASE_DIR, "instance", "database.db")}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(BASE_DIR, "uploads")
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db = SQLAlchemy(app)
db.metadata.clear()


# Telegram Bot Config
TELEGRAM_BOT_TOKEN = '7801719404:AAGH0iYJizTS7_9Vq2TR4C5RIQno5jNRJyY'
TELEGRAM_CHAT_ID = '725821771'  # Replace with actual Chat ID

# Database Models
class User(db.Model):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.Integer, nullable=False, default=0)
    address = db.Column(db.Text, nullable=True)  # Tambahkan kolom alamat


class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    price = db.Column(db.Integer, nullable=False)  # Harga langsung dalam Rupiah
    stock = db.Column(db.Integer, nullable=False)
    image = db.Column(db.String(100), nullable=True)

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    is_admin = db.Column(db.Boolean, default=False)  # True jika pesan dari admin
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)  # Kolom timestamp menggunakan waktu UTC

    # Relationship
    user = db.relationship('User', backref='messages')

    # Method untuk mendapatkan timestamp dalam WIB
    @property
    def timestamp_wib(self):
        return convert_to_wib(self.timestamp)

class Cart(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, default=1)
    is_deleted = db.Column(db.Boolean, default=False)  # Menandai jika produk dihapus

    product = db.relationship('Product', backref='cart_items')


class Order(db.Model):
    __tablename__ = 'orders'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    total_price = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(50), nullable=False, default='Pending')
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)  # Timestamp baru menggunakan waktu UTC
    resi = db.Column(db.String(100), nullable=True)  # Tambahkan kolom resi

    user = db.relationship('User', backref='orders')
    product = db.relationship('Product', backref='orders')

    # Method untuk mendapatkan timestamp dalam WIB
    @property
    def timestamp_wib(self):
        return convert_to_wib(self.timestamp)


def send_telegram_notification(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": message}

    try:
        response = requests.post(url, data=data)
        if response.status_code == 200:
            print("Notification sent successfully.")
        else:
            print(f"Failed to send notification: {response.text}")
    except Exception as e:
        print(f"Error sending notification: {e}")

def format_rupiah(value):
    """
    Convert an integer/float value to Indonesian Rupiah format.
    """
    return f"Rp {value:,.0f}".replace(",", ".")

from sqlalchemy import inspect

def create_default_admin():
    # Periksa apakah tabel 'user' sudah ada
    inspector = inspect(db.engine)
    if 'user' not in inspector.get_table_names():
        print("Table 'user' does not exist. Skipping default admin creation.")
        return

    # Cek apakah admin sudah ada
    admin = User.query.filter_by(username='admin').first()
    if not admin:
        default_admin = User(
            username='admin',
            password=generate_password_hash('password'),  # Password default
            role=1  # Role admin
        )
        db.session.add(default_admin)
        db.session.commit()
        print("Default admin created: username='admin', password='password'")
    else:
        print("Default admin already exists.")


@app.context_processor
def utility_processor():
    return dict(format_rupiah=format_rupiah)

# Middleware to ensure login
@app.before_request
def require_login():
    allowed_routes = ['login', 'register', 'home', 'uploaded_file']
    if request.endpoint not in allowed_routes and 'user_id' not in session:
        return redirect(url_for('login'))

# Routes
@app.route('/')
def home():
    products = Product.query.all()
    return render_template('user_dashboard.html', products=products)

@app.route('/author')
def author():
    return render_template('author.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        # Cek apakah username sudah ada
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash("Username sudah digunakan. Silakan gunakan username lain.")
            return redirect(url_for('register'))

        # Jika username belum ada, buat user baru
        hashed_password = generate_password_hash(password)
        new_user = User(username=username, password=hashed_password)
        db.session.add(new_user)
        db.session.commit()
        flash("Registrasi berhasil! Silakan login.")
        return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password, password):
            # Simpan informasi user ke session
            session['user_id'] = user.id
            session['role'] = user.role  # Role: 0 = User, 1 = Admin

            # Arahkan berdasarkan role
            if user.role == 1:  # Admin
                return redirect(url_for('admin_dashboard'))
            else:  # User
                return redirect(url_for('home'))
        
        flash("Invalid username or password. Please try again.")
    return render_template('login.html')


@app.route('/add_to_cart/<int:product_id>', methods=['POST'])
def add_to_cart(product_id):
    if 'user_id' not in session:
        flash("Harap login terlebih dahulu untuk menambahkan ke keranjang!")
        return redirect(url_for('login'))

    user_id = session['user_id']
    product = Product.query.get(product_id)

    if not product or product.stock <= 0:
        flash("Produk tidak tersedia atau stok habis!")
        return redirect(url_for('home'))

    # Periksa apakah produk sudah ada di keranjang
    cart_item = Cart.query.filter_by(user_id=user_id, product_id=product_id).first()

    if cart_item:
        if cart_item.is_deleted:
            cart_item.is_deleted = False
            cart_item.quantity = 1
        else:
            cart_item.quantity += 1
    else:
        new_cart_item = Cart(user_id=user_id, product_id=product_id, quantity=1)
        db.session.add(new_cart_item)

    try:
        db.session.commit()
        flash(f"{product.name} berhasil ditambahkan ke keranjang!")
    except Exception as e:
        db.session.rollback()
        flash(f"Terjadi kesalahan saat menambahkan ke keranjang: {e}")

    return redirect(url_for('home'))


@app.route('/cart', methods=['GET'])
def view_cart():
    if 'user_id' not in session:
        flash("Harap login terlebih dahulu untuk melihat keranjang!")
        return redirect(url_for('login'))

    user_id = session['user_id']
    user = User.query.get(user_id)  # Dapatkan data pengguna dari database
    cart_items = Cart.query.join(Product).filter(
        Cart.user_id == user_id,
        Cart.is_deleted == False
    ).all()

    total_price = 0
    warnings = []
    valid_items = []

    for item in cart_items:
        if item.product:
            if item.product.stock > 0:
                total_price += item.quantity * item.product.price
                valid_items.append(item)
            else:
                warnings.append(f"Produk '{item.product.name}' habis stok.")
        else:
            warnings.append(f"Produk dengan ID {item.product_id} telah dihapus.")

    if request.headers.get('Accept') == 'application/json':
        return jsonify({
            'total_price': format_rupiah(total_price),
            'cart_items': [{'id': item.id, 'name': item.product.name, 'quantity': item.quantity} for item in valid_items]
        })

    return render_template(
        'cart.html',
        user=user,  # Kirim data pengguna ke template
        cart_items=valid_items,
        total_price=total_price,
        warnings=warnings
    )


@app.route('/update_cart/<int:item_id>', methods=['POST'])
def update_cart(item_id):
    data = request.get_json()
    new_quantity = data.get('quantity')

    cart_item = Cart.query.get_or_404(item_id)
    if cart_item.user_id != session['user_id']:
        return jsonify({'success': False}), 403

    if new_quantity < 1 or new_quantity > 100:
        return jsonify({'success': False}), 400

    cart_item.quantity = new_quantity
    db.session.commit()
    return jsonify({'success': True})

@app.route('/remove_from_cart/<int:cart_id>', methods=['POST'])
def remove_from_cart(cart_id):
    cart_item = Cart.query.get_or_404(cart_id)

    if cart_item.user_id != session['user_id']:
        flash("You are not authorized to remove this item.")
        return redirect(url_for('view_cart'))

    db.session.delete(cart_item)
    db.session.commit()
    flash("Item removed from cart.")
    return redirect(url_for('view_cart'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/admin/chat/<int:user_id>', methods=['GET', 'POST'])
def admin_chat(user_id):
    if session.get('role') != 1:  # Hanya admin yang bisa mengakses
        return redirect(url_for('home'))

    if request.method == 'POST':
        message = request.form['message']
        new_message = Message(user_id=user_id, message=message, is_admin=True)
        db.session.add(new_message)
        db.session.commit()
        flash("Reply sent to user.")
        return redirect(url_for('admin_chat', user_id=user_id))

    messages = Message.query.filter_by(user_id=user_id).order_by(Message.timestamp).all()
    return render_template('admin_chat.html', messages=messages, user_id=user_id)

@app.route('/admin', methods=['GET', 'POST'])
def admin_dashboard():
    if session.get('role') != 1:
        return redirect(url_for('home'))

    products = Product.query.all()

    if request.method == 'POST':
        name = request.form['name']
        description = request.form['description']
        price = int(request.form['price'])  # Harga dalam Rupiah
        stock = int(request.form['stock'])

        file = request.files['image']
        if file and file.filename:
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
        else:
            filename = None

        new_product = Product(name=name, description=description, price=price, stock=stock, image=filename)
        db.session.add(new_product)
        db.session.commit()

        flash("Product added successfully!")
        return redirect(url_for('admin_dashboard'))

    orders = Order.query.all()
    users = User.query.all()
    return render_template('admin_dashboard.html', products=products, orders=orders, users=users)

@app.route('/checkout', methods=['POST'])
def checkout():
    if session.get('user_id') is None:
        flash("Harap login terlebih dahulu untuk checkout!")
        return redirect(url_for('login'))

    user_id = session.get('user_id')
    user = User.query.get(user_id)  # Ambil informasi pengguna
    if not user:
        print("Error: User not found during checkout")
        flash("User not found. Please login again.")
        return redirect(url_for('login'))

    cart_items = Cart.query.filter_by(user_id=user_id).all()
    if not cart_items:
        print("Error: Cart is empty")
        flash("Keranjang Anda kosong!")
        return redirect(url_for('view_cart'))

    try:
        total_price = 0  # Hitung total harga pesanan
        for item in cart_items:
            product = Product.query.get(item.product_id)

            # Validasi jika produk tidak ditemukan
            if not product:
                print(f"Error: Product with ID {item.product_id} not found")
                flash(f"Produk dengan ID {item.product_id} tidak ditemukan.")
                return redirect(url_for('view_cart'))

            # Validasi stok produk
            if product.stock < item.quantity:
                print(f"Error: Stock insufficient for product {product.name}")
                flash(f"Stok produk {product.name} tidak mencukupi.")
                return redirect(url_for('view_cart'))

            # Hitung total harga untuk setiap item
            total_price += product.price * item.quantity

            # Tambahkan pesanan ke tabel 'orders'
            new_order = Order(
                user_id=user_id,
                product_id=item.product_id,
                quantity=item.quantity,
                total_price=product.price * item.quantity,
                status='Pending'
            )
            db.session.add(new_order)

            # Kurangi stok produk
            product.stock -= item.quantity

        # Hapus semua item dari keranjang setelah checkout
        Cart.query.filter_by(user_id=user_id).delete()
        db.session.commit()

        # Kirim pemberitahuan ke Telegram
        message = f"User '{user.username}' telah melakukan pemesanan dengan total harga Rp {total_price:,.0f}."
        send_telegram_notification(message)

        flash("Pesanan Anda berhasil diproses!")
        return redirect(url_for('home'))

    except Exception as e:
        # Tangani error tak terduga dan rollback jika ada masalah
        print(f"Error during checkout: {e}")
        db.session.rollback()
        flash(f"Terjadi kesalahan saat memproses pesanan: {str(e)}")
        return redirect(url_for('view_cart'))

@app.route('/checkout/success')
def checkout_success():
    return render_template('success.html')

@app.route('/update_product/<int:product_id>', methods=['POST'])
def update_product(product_id):
    if session.get('role') != 1:  # Pastikan hanya admin yang bisa mengupdate produk
        flash("You do not have permission to perform this action.")
        return redirect(url_for('home'))

    product = Product.query.get_or_404(product_id)  # Ambil produk berdasarkan ID
    try:
        # Ambil data baru dari form
        new_name = request.form['name']
        new_description = request.form['description']
        new_stock = int(request.form['stock'])

        if new_stock < 0:
            flash("Stock cannot be negative.")
            return redirect(url_for('admin_dashboard'))

        # Perbarui data produk di database
        product.name = new_name
        product.description = new_description
        product.stock = new_stock
        db.session.commit()
        flash(f"Product {product.name} has been updated.")
    except Exception as e:
        db.session.rollback()
        flash(f"Error updating product: {e}")
    return redirect(url_for('admin_dashboard'))

@app.route('/history', methods=['GET'])
def transaction_history():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    orders = Order.query.filter_by(user_id=user_id).order_by(Order.timestamp.desc()).all()
    return render_template('history.html', orders=orders)

@app.route('/admin/orders/ship/<int:order_id>', methods=['POST'])
def ship_order(order_id):
    if session.get('role') != 1:
        flash("You do not have permission to perform this action.")
        return redirect(url_for('home'))

    order = Order.query.get(order_id)
    if not order:
        flash("Order not found.")
        return redirect(url_for('admin_orders'))

    resi = request.form.get('resi')
    if not resi:
        flash("Resi tidak boleh kosong.")
        return redirect(url_for('admin_orders'))

    try:
        order.status = 'Dikirim'
        order.resi = resi
        db.session.commit()
        flash(f"Order ID {order.id} has been marked as 'Dikirim' with Resi {resi}.")
    except Exception as e:
        db.session.rollback()
        flash(f"Failed to update order status: {e}")

    return redirect(url_for('admin_orders'))

@app.route('/delete_product/<int:product_id>', methods=['POST'])
def delete_product(product_id):
    product = Product.query.get(product_id)

    if not product:
        flash("Produk tidak ditemukan.")
        return redirect(url_for('admin_dashboard'))

    # Periksa apakah produk ada di keranjang
    cart_items = Cart.query.filter_by(product_id=product_id, is_deleted=False).all()
    if cart_items:
        flash("Produk ini ada di keranjang salah satu pengguna dan tidak dapat dihapus.")
        return redirect(url_for('admin_dashboard'))

    try:
        # Hapus semua pesanan terkait produk
        Order.query.filter_by(product_id=product_id).delete()

        # Hapus produk
        db.session.delete(product)
        db.session.commit()

        flash(f"Produk {product.name} berhasil dihapus.")
    except Exception as e:
        db.session.rollback()
        flash(f"Terjadi kesalahan saat menghapus produk: {e}")

    return redirect(url_for('admin_dashboard'))

@app.route('/admin/orders')
def admin_orders():
    if session.get('role') != 1:
        return redirect(url_for('home'))  # Hanya admin yang dapat mengakses halaman ini

    orders = Order.query.all()  # Ambil semua pesanan
    return render_template('admin_orders.html', orders=orders)

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/chat', methods=['GET', 'POST'])
def user_chat():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    user = User.query.get(user_id)

    if request.method == 'POST':
        message = request.form['message']
        new_message = Message(user_id=user_id, message=message, is_admin=False)
        db.session.add(new_message)
        db.session.commit()

        # Kirim notifikasi ke Telegram
        send_telegram_notification(f"Pesan baru dari {user.username}")

        flash("Message sent to admin.")
        return redirect(url_for('user_chat'))

    messages = Message.query.filter_by(user_id=user_id).order_by(Message.timestamp).all()
    return render_template('user_chat.html', messages=messages)

# Fungsi untuk mengonversi waktu UTC ke WIB
def convert_to_wib(utc_dt):
    wib_tz = pytz.timezone('Asia/Jakarta')  # Zona waktu WIB
    return utc_dt.astimezone(wib_tz)

@app.route('/update_address', methods=['POST'])
def update_address():
    if 'user_id' not in session:
        flash("Please login to update your address.")
        return redirect(url_for('login'))

    user_id = session['user_id']
    user = User.query.get(user_id)  # Ambil data pengguna dari database

    if not user:
        flash("User not found. Please login again.")
        return redirect(url_for('login'))

    # Update address
    address = request.form['address']
    user.address = address  # Pastikan kolom 'address' sudah ditambahkan ke model User
    db.session.commit()

    flash("Address updated successfully.")
    return redirect(url_for('view_cart'))



# Run App
if __name__ == "__main__":
    with app.app_context():
        db.create_all()  # Buat tabel sesuai model
        print("All tables created successfully.")
        create_default_admin()  # Buat admin default

    #app.run(port=500, debug=True)
    app.run(host='0.0.0.0', port=80, debug=True)

